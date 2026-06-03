"""
Semi-Automated 1:2 RR Trend Strategy
=====================================
Indicators:  EMA-50 (trend filter) · RSI-14 (momentum) · ATR-14 (volatility / sizing)
Entry rule:  close > EMA-50 AND RSI crosses above 45 from below → automatic market order
Sizing:      risk_pct (default 1%) of account equity ÷ (ATR × atr_mult)
Exits:       MANUAL — push notification fires when price reaches TP or SL; user approves close
"""

import asyncio
import logging
from dataclasses import dataclass
from datetime import date, datetime
from typing import Optional
from zoneinfo import ZoneInfo

import pandas as pd
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame

import app.services.alpaca_service as alpaca
from app.config import settings

logger = logging.getLogger(__name__)
ET = ZoneInfo("America/New_York")

# ── Configurable parameters ────────────────────────────────────────────────────
RISK_PCT = 0.01          # 1% of equity per trade
ATR_SL_MULT = 1.5        # SL distance = ATR × this
RR_RATIO = 2.0           # TP distance = SL distance × this  (→ 1:2 RR)
EMA_PERIOD = 50
RSI_PERIOD = 14
ATR_PERIOD = 14
RSI_TRIGGER = 45         # RSI must cross above this level

SCAN_UNIVERSE = list(dict.fromkeys([
    # ── S&P 500 / NASDAQ 100 — full liquid universe ──────────────────────────
    # Mega-cap Tech
    "AAPL","MSFT","GOOGL","GOOG","AMZN","NVDA","META","TSLA","AVGO","ORCL",
    # Semiconductors
    "AMD","INTC","QCOM","MU","AMAT","LRCX","KLAC","TXN","MRVL","ON","MPWR",
    # Software / Cloud
    "ADBE","CRM","NOW","INTU","WDAY","SNPS","CDNS","ANSS","CTSH","IBM",
    "MSFT","ORCL","SAP",
    # Internet / E-commerce
    "NFLX","UBER","LYFT","ABNB","BKNG","EXPE","EBAY","ETSY","SHOP","MELI",
    # Fintech / Payments
    "V","MA","PYPL","SQ","AFRM","SOFI","HOOD","COIN","MSTR","UPST",
    # Banks / Finance
    "JPM","BAC","WFC","C","GS","MS","BLK","SCHW","AXP","COF",
    # ETFs — sector & index
    "SPY","QQQ","IWM","DIA","XLK","XLF","XLE","XLV","XLI","XLB","XLU","XLRE",
    "XLP","XLY","ARKK","ARKG","SOXL","TQQQ","SPXL",
    # Growth / Momentum
    "PLTR","CRWD","S","PANW","FTNT","OKTA","ZS","NET","DDOG","SNOW",
    "MNDY","HUBS","TWLO","ZM","DOCU","BOX","GTLB","PATH","AI","SOUN",
    "RBLX","U","TTWO","EA","ATVI",
    # Healthcare / Biotech
    "UNH","LLY","ABBV","JNJ","MRK","PFE","BMY","AMGN","GILD","BIIB",
    "REGN","VRTX","MRNA","BNTX","ILMN","ISRG","MDT","ABT","TMO","DHR",
    # Energy
    "XOM","CVX","COP","EOG","SLB","HAL","MPC","VLO","PSX","OXY",
    # Consumer Discretionary
    "AMZN","TSLA","HD","LOW","TJX","NKE","SBUX","MCD","CMG","YUM",
    "BURL","ROST","DG","DLTR","WMT","COST","TGT","KR",
    # Consumer Staples / Food
    "PG","KO","PEP","MDLZ","GIS","KHC","CL","COLM",
    # Industrials / Aerospace
    "BA","GE","HON","CAT","DE","MMM","LMT","RTX","NOC","GD","UPS","FDX",
    # Autos
    "F","GM","RIVN","LCID",
    # Real Estate / REITs
    "AMT","PLD","EQIX","SPG","O","AVB",
    # Telecom / Media
    "T","VZ","CMCSA","DIS","NFLX","WBD","PARA",
    # Materials
    "FCX","NEM","GOLD","AA","NUE","CF","MOS",
    # China ADRs
    "BABA","JD","PDD","BIDU","NIO","XPEV","LI",
    # Other high-volume
    "GME","AMC","BBBY","SPCE","SNAP","PINS","TWTR","SPOT","ROKU","FUTU",
]))

# ── In-memory state ────────────────────────────────────────────────────────────
@dataclass
class ActiveTrade:
    symbol: str
    order_id: str
    entry_price: float
    stop_loss: float
    take_profit: float
    qty: float
    atr: float
    entered_at: str
    notified: bool = False  # True once exit push notification sent


_active_trades: dict[str, ActiveTrade] = {}

# Simple daily P&L tracker  { "YYYY-MM-DD": dollars_realized }
_daily_pnl: dict[str, float] = {}
_trades_opened_today: dict[str, int] = {}  # { "YYYY-MM-DD": count }


def _today() -> str:
    return date.today().isoformat()


def _is_market_open() -> bool:
    """True during US regular session Mon–Fri 09:30–16:00 ET."""
    now = datetime.now(ET)
    if now.weekday() >= 5:          # Saturday=5, Sunday=6
        return False
    market_open = now.replace(hour=9, minute=30, second=0, microsecond=0)
    market_close = now.replace(hour=16, minute=0, second=0, microsecond=0)
    return market_open <= now < market_close


def _record_trade_opened():
    key = _today()
    _trades_opened_today[key] = _trades_opened_today.get(key, 0) + 1


# ── Alpaca bar fetcher ────────────────────────────────────────────────────────

def _fetch_bars(symbol: str, limit: int = 200) -> Optional[pd.DataFrame]:
    """Fetch 1-hour bars for a stock symbol via Alpaca data API."""
    try:
        client = StockHistoricalDataClient(
            api_key=settings.alpaca_api_key,
            secret_key=settings.alpaca_secret_key,
        )
        req = StockBarsRequest(
            symbol_or_symbols=symbol,
            timeframe=TimeFrame.Hour,
            limit=limit,
            feed="iex",  # IEX feed — free, no subscription needed
        )
        bars = client.get_stock_bars(req)
        df = bars.df
        if df is None or df.empty:
            return None
        # Multi-index (symbol, timestamp) → drop symbol level
        if isinstance(df.index, pd.MultiIndex):
            df = df.droplevel(0)
        df.index = pd.to_datetime(df.index)
        df.columns = [c.lower() for c in df.columns]
        return df[["open", "high", "low", "close", "volume"]].dropna().tail(limit)
    except Exception as e:
        logger.warning(f"trend_rr: bar fetch error {symbol}: {e}")
        return None


# ── Indicator helpers ──────────────────────────────────────────────────────────

def _ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()


def _rsi(series: pd.Series, period: int) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = (-delta).clip(lower=0)
    avg_gain = gain.ewm(com=period - 1, adjust=False).mean()
    avg_loss = loss.ewm(com=period - 1, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, 1e-10)
    return 100 - (100 / (1 + rs))


def _atr(df: pd.DataFrame, period: int) -> pd.Series:
    """Wilder RMA smoothing (matches Pine Script ta.atr)."""
    high, low, prev_close = df["high"], df["low"], df["close"].shift()
    tr = pd.concat([high - low, (high - prev_close).abs(), (low - prev_close).abs()], axis=1).max(axis=1)
    return tr.ewm(com=period - 1, adjust=False).mean()


def _check_signal(df: pd.DataFrame) -> tuple[bool, float, float]:
    """Return (signal_fired, last_close, last_atr)."""
    if len(df) < EMA_PERIOD + 5:
        return False, 0.0, 0.0

    ema50 = _ema(df["close"], EMA_PERIOD)
    rsi14 = _rsi(df["close"], RSI_PERIOD)
    atr14 = _atr(df, ATR_PERIOD)

    last_close = float(df["close"].iloc[-1])
    last_ema = float(ema50.iloc[-1])
    last_rsi = float(rsi14.iloc[-1])
    prev_rsi = float(rsi14.iloc[-2])
    last_atr = float(atr14.iloc[-1])

    rsi_crossover = (prev_rsi < RSI_TRIGGER) and (last_rsi >= RSI_TRIGGER)
    price_above_ema = last_close > last_ema

    return (price_above_ema and rsi_crossover), last_close, last_atr


# ── Core logic ─────────────────────────────────────────────────────────────────

async def scan_symbol(symbol: str, open_syms: set) -> Optional[ActiveTrade]:
    """Scan one symbol — place entry order if signal fires and no existing position."""
    if symbol in _active_trades or symbol in open_syms:
        return None

    loop = asyncio.get_event_loop()
    df = await loop.run_in_executor(None, lambda: _fetch_bars(symbol, 200))
    if df is None or df.empty:
        return None

    fired, entry_price, atr_val = _check_signal(df)
    if not fired or atr_val <= 0:
        return None

    try:
        acct = alpaca.get_account()
        equity = float(acct["equity"])
    except Exception as e:
        logger.error(f"trend_rr: cannot fetch account: {e}")
        return None

    sl_dist = atr_val * ATR_SL_MULT
    qty = max(1, int((equity * RISK_PCT) / sl_dist))
    stop_loss = round(entry_price - sl_dist, 4)
    take_profit = round(entry_price + sl_dist * RR_RATIO, 4)

    logger.info(
        f"trend_rr SIGNAL {symbol} | close={entry_price:.4f} SL={stop_loss:.4f} "
        f"TP={take_profit:.4f} qty={qty} risk=${equity * RISK_PCT:.0f}"
    )

    try:
        order = alpaca.place_market_order(symbol, qty, "BUY")
        trade = ActiveTrade(
            symbol=symbol,
            order_id=order["id"],
            entry_price=entry_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            qty=qty,
            atr=atr_val,
            entered_at=datetime.utcnow().isoformat(),
        )
        _active_trades[symbol] = trade
        _record_trade_opened()
        logger.info(f"trend_rr: entry order placed {symbol} id={order['id']}")
        return trade
    except Exception as e:
        logger.error(f"trend_rr: order error {symbol}: {e}")
        return None


async def monitor_exits():
    """Check each active trade — send push notification when TP or SL is reached."""
    if not _active_trades:
        return

    from app.database import AsyncSessionLocal
    from app.models import User
    from sqlalchemy import select
    from app.services.notification_service import send_push_notification

    for symbol, trade in list(_active_trades.items()):
        if trade.notified:
            continue
        try:
            q = alpaca.get_latest_quote(symbol)
            current = (q["bid"] + q["ask"]) / 2
        except Exception:
            continue

        tp_hit = current >= trade.take_profit
        sl_hit = current <= trade.stop_loss
        if not (tp_hit or sl_hit):
            continue

        reason = "TARGET REACHED (1:2 RR)" if tp_hit else "STOP LOSS HIT"
        pnl_est = round((current - trade.entry_price) * trade.qty, 2)
        sign = "+" if pnl_est >= 0 else ""

        logger.info(f"trend_rr EXIT ALERT {symbol} — {reason} price={current:.4f}")

        title = f"⚠️ {symbol} — {reason}"
        body = (
            f"Entry: {trade.entry_price:.4f}  Now: {current:.4f}\n"
            f"Est. P&L: {sign}${pnl_est:.2f} — Review and confirm close"
        )

        try:
            async with AsyncSessionLocal() as db:
                result = await db.execute(select(User).where(User.expo_push_token.isnot(None)))
                users = result.scalars().all()
            for user in users:
                if user.expo_push_token:
                    await send_push_notification(
                        user.expo_push_token, title, body,
                        data={"screen": "trend-rr", "action": "exit_review", "symbol": symbol},
                    )
        except Exception as e:
            logger.error(f"trend_rr: push error: {e}")

        trade.notified = True


async def run_scan():
    """Full cycle: scan universe for entries + monitor active trade exits."""
    if not _is_market_open():
        logger.info("trend_rr: market closed — skipping scan")
        return

    now_et = datetime.now(ET).strftime("%H:%M ET")
    logger.info(f"=== TREND RR: scan started at {now_et} — {len(SCAN_UNIVERSE)} symbols ===")

    # Fetch open positions once for the whole scan
    try:
        open_syms = {p["symbol"] for p in alpaca.get_positions()}
    except Exception:
        open_syms = set()

    # Parallel batches of 8 — fast enough without hammering the Alpaca IEX feed
    BATCH = 8
    signals_found = 0
    for i in range(0, len(SCAN_UNIVERSE), BATCH):
        batch = SCAN_UNIVERSE[i:i + BATCH]
        results = await asyncio.gather(*[scan_symbol(s, open_syms) for s in batch], return_exceptions=True)
        for r in results:
            if isinstance(r, ActiveTrade):
                signals_found += 1
        await asyncio.sleep(0.5)   # brief pause between batches

    await monitor_exits()
    logger.info(
        f"=== TREND RR: scan done — {len(_active_trades)} active trades "
        f"| new signals: {signals_found} "
        f"| opened today: {_trades_opened_today.get(_today(), 0)} ==="
    )


async def run_eod_scan():
    """
    EOD review at 15:45 ET — monitor exits and log open positions.
    Does NOT auto-close anything; push notification is sent to all users.
    """
    logger.info("=== TREND RR: EOD review ===")

    await monitor_exits()

    if not _active_trades:
        logger.info("trend_rr EOD: no open positions")
        return

    try:
        from app.database import AsyncSessionLocal
        from app.models import User
        from sqlalchemy import select
        from app.services.notification_service import send_push_notification

        lines = []
        total_pnl = 0.0
        for sym, t in _active_trades.items():
            try:
                q = alpaca.get_latest_quote(sym)
                price = (q["bid"] + q["ask"]) / 2
                pnl = (price - t.entry_price) * t.qty
                total_pnl += pnl
                sign = "+" if pnl >= 0 else ""
                lines.append(f"{sym} {sign}${pnl:.0f}")
            except Exception:
                lines.append(sym)

        summary = " | ".join(lines)
        total_sign = "+" if total_pnl >= 0 else ""

        title = f"⚠️ Trend RR — {len(_active_trades)} open position(s) at EOD"
        body = f"{summary}\nTotal est. P&L: {total_sign}${total_pnl:.2f} — Review in Trend RR tab"

        async with AsyncSessionLocal() as db:
            result = await db.execute(select(User).where(User.expo_push_token.isnot(None)))
            users = result.scalars().all()

        for user in users:
            if user.expo_push_token:
                await send_push_notification(
                    user.expo_push_token, title, body,
                    data={"screen": "trend-rr", "action": "eod_review"},
                )

        logger.info(f"trend_rr EOD: notified — {summary}")
    except Exception as e:
        logger.error(f"trend_rr EOD notify error: {e}")


def manual_close_trade(symbol: str) -> dict:
    """User-approved close: market sell + remove from state."""
    symbol = symbol.upper()
    trade = _active_trades.get(symbol)
    if not trade:
        return {"error": f"No active trend-rr trade for {symbol}"}
    try:
        result = alpaca.close_position(symbol)
        del _active_trades[symbol]
        logger.info(f"trend_rr: manual close {symbol}")
        return {"closed": symbol, "order": result}
    except Exception as e:
        logger.error(f"trend_rr: close error {symbol}: {e}")
        return {"error": str(e)}


def get_status() -> dict:
    trades_out = []
    for symbol, t in _active_trades.items():
        current = None
        pnl = None
        pnl_pct = None
        try:
            q = alpaca.get_latest_quote(symbol)
            current = round((q["bid"] + q["ask"]) / 2, 4)
            pnl = round((current - t.entry_price) * t.qty, 2)
            pnl_pct = round((current - t.entry_price) / t.entry_price * 100, 2)
        except Exception:
            pass

        trades_out.append({
            "symbol": symbol,
            "order_id": t.order_id,
            "entry_price": t.entry_price,
            "stop_loss": t.stop_loss,
            "take_profit": t.take_profit,
            "qty": t.qty,
            "atr": round(t.atr, 4),
            "entered_at": t.entered_at,
            "exit_notified": t.notified,
            "current_price": current,
            "unrealized_pnl": pnl,
            "unrealized_pnl_pct": pnl_pct,
        })

    market_open = _is_market_open()
    now_et = datetime.now(ET).strftime("%H:%M ET (%A)")

    return {
        "strategy": "Semi-Auto 1:2 RR Trend Strategy",
        "active_trades": len(_active_trades),
        "market_open": market_open,
        "current_time_et": now_et,
        "trades_opened_today": _trades_opened_today.get(_today(), 0),
        "config": {
            "risk_pct": round(RISK_PCT * 100, 2),
            "atr_sl_multiplier": ATR_SL_MULT,
            "rr_ratio": RR_RATIO,
            "ema_period": EMA_PERIOD,
            "rsi_period": RSI_PERIOD,
            "rsi_trigger": RSI_TRIGGER,
            "scan_universe": SCAN_UNIVERSE,
            "timeframe": "1h",
        },
        "trades": trades_out,
    }
