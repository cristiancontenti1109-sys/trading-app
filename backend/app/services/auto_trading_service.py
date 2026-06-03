"""
Automated Market Mechanics trading service.

Schedule:
  - 09:35 ET  → Morning scan: open new positions (market-open momentum)
  - 15:15 ET  → Afternoon scan: open afternoon setups
  - 15:45 ET  → EOD close: close all intraday positions before market close

Risk controls:
  - MAX_POSITIONS: max concurrent open positions (default 5)
  - RISK_PER_TRADE: dollar risk per trade (default $200)
  - MAX_DAILY_RISK: max total dollar risk per day (default $1000 = 5 trades)
  - MIN_SCORE: minimum SMC score to execute (default 4/5)
  - MAX_POSITION_PCT: max buying power per single trade (default 20%)
"""

import asyncio
import logging
from datetime import date, datetime
from zoneinfo import ZoneInfo
from typing import Optional, Tuple

import app.services.alpaca_service as alpaca
from app.services.market_data import fetch_ohlcv
from app.services.smc_service import generate_smc_signal, smc_signal_to_dict

logger = logging.getLogger(__name__)

ET = ZoneInfo("America/New_York")

# ── Configuration ──────────────────────────────────────────────────────────────

MAX_POSITIONS = 5
RISK_PER_TRADE = 200.0      # $ risk per trade
MAX_DAILY_RISK = 1000.0     # $ max risk opened per calendar day
MIN_SCORE = 4               # minimum conditions met (out of 5)
MAX_POSITION_PCT = 0.20     # max buying power fraction per trade

# Universe to scan: only Alpaca-supported instruments
SCAN_UNIVERSE = [
    # Stocks
    "AAPL", "MSFT", "GOOGL", "AMZN", "TSLA", "NVDA", "META", "NFLX",
    "AMD", "JPM", "BAC", "GS", "V", "MA", "SPY", "QQQ",
    "UBER", "COIN", "PLTR", "SHOP",
    # Crypto (Alpaca supports 24/7)
    "BTCUSD", "ETHUSD", "SOLUSD", "LINKUSD", "AVAXUSD",
]

ALPACA_STOCKS = {
    "AAPL", "MSFT", "GOOGL", "AMZN", "TSLA", "NVDA", "META", "NFLX",
    "AMD", "JPM", "BAC", "GS", "V", "MA", "SPY", "QQQ",
    "UBER", "COIN", "PLTR", "SHOP",
}

# Simple in-memory daily risk tracker {date: dollars_risked}
_daily_risk: dict = {}


def _today() -> str:
    return date.today().isoformat()


def daily_risk_used() -> float:
    return _daily_risk.get(_today(), 0.0)


def _add_risk(amount: float):
    key = _today()
    _daily_risk[key] = _daily_risk.get(key, 0.0) + amount


def _open_symbols() -> set:
    """Return set of symbols with an open position."""
    try:
        positions = alpaca.get_positions()
        return {p["symbol"] for p in positions}
    except Exception:
        return set()


def _position_size(entry: float, risk_unit: float, buying_power: float, is_stock: bool) -> float:
    """Dollar-risk sizing capped at MAX_POSITION_PCT of buying power."""
    qty = RISK_PER_TRADE / risk_unit
    if is_stock:
        qty = max(1, int(qty))
    else:
        qty = max(0.01, round(qty, 4))

    max_notional = buying_power * MAX_POSITION_PCT
    if qty * entry > max_notional and entry > 0:
        if is_stock:
            qty = max(1, int(max_notional / entry))
        else:
            qty = max(0.01, round(max_notional / entry, 4))

    return qty


async def _scan_symbol(symbol: str) -> Optional[object]:
    """
    Fetch data and generate signal for one symbol.
    Returns (symbol, sig, qty) if actionable, else None.
    """
    try:
        df4h, df1h, df15m = await asyncio.gather(
            fetch_ohlcv(symbol, "4h", limit=200),
            fetch_ohlcv(symbol, "1h", limit=200),
            fetch_ohlcv(symbol, "15m", limit=300),
        )
        if df4h is None or df15m is None:
            return None

        sig = generate_smc_signal(df4h, df15m, symbol, df1h)
        if sig is None or sig.smc_score < MIN_SCORE:
            return None

        return sig
    except Exception as e:
        logger.warning(f"auto_trading scan error {symbol}: {e}")
        return None


def _place_trade(sig, qty: float) -> dict:
    """
    Place a 3-leg Market Mechanics bracket trade.
    Levels anchored to current live quote to ensure SL validity.
    """
    quote = alpaca.get_latest_quote(sig.symbol)
    side = sig.direction

    if side == "SELL":
        ref_price = quote["ask"]           # short fills at ask (or worse)
        sl = round(ref_price + sig.risk * 0.5, 2)   # SL above ask
        tp1 = round(ref_price - sig.risk * 1.5, 2)  # TP1 below ask
    else:
        ref_price = quote["bid"]           # long fills at ask but check against bid
        sl = round(ref_price - sig.risk * 0.5, 2)   # SL below bid
        tp1 = round(ref_price + sig.risk * 1.5, 2)  # TP1 above bid

    tp2 = sig.tp2  # structural target unchanged

    return alpaca.place_mm_trade(sig.symbol, int(qty), side, sl, tp1, tp2)


async def run_morning_scan():
    """09:35 ET — scan universe, open best setups."""
    logger.info("=== AUTO TRADING: Morning scan started ===")
    await _run_scan(session="morning")


async def run_afternoon_scan():
    """15:15 ET — catch afternoon momentum setups."""
    logger.info("=== AUTO TRADING: Afternoon scan started ===")
    await _run_scan(session="afternoon")


async def notify_eod_review():
    """
    15:45 ET — notify user to review open positions before market close.
    Does NOT close anything automatically. User must call POST /auto-trading/eod-close.
    """
    logger.info("=== AUTO TRADING: EOD review notification ===")
    try:
        positions = alpaca.get_positions()
        stock_positions = [p for p in positions if p["symbol"] in ALPACA_STOCKS]
        if not stock_positions:
            logger.info("EOD notify: no open stock positions")
            return

        lines = []
        total_pl = 0.0
        for p in stock_positions:
            pl = p.get("unrealized_pl") or 0.0
            total_pl += pl
            sign = "+" if pl >= 0 else ""
            lines.append(f"{p['symbol']} {p['qty']}x {sign}${pl:.2f}")

        summary = " | ".join(lines)
        pl_sign = "+" if total_pl >= 0 else ""
        logger.info(
            f"EOD notify: {len(stock_positions)} open positions — {summary} "
            f"| Total P&L: {pl_sign}${total_pl:.2f} — "
            f"Approve close via POST /auto-trading/eod-close"
        )

        # Push notification to all users with expo tokens
        from app.database import AsyncSessionLocal
        from app.models import User
        from sqlalchemy import select
        from app.services.notification_service import send_push_notification

        async with AsyncSessionLocal() as db:
            result = await db.execute(select(User).where(User.expo_push_token.isnot(None)))
            users = result.scalars().all()

        title = f"⚠️ Market closes in 15 min — {len(stock_positions)} open positions"
        body = f"{summary} | Total: {pl_sign}${total_pl:.2f}\nTap to review and close."

        for user in users:
            if user.expo_push_token:
                await send_push_notification(
                    user.expo_push_token, title, body,
                    data={"screen": "auto-trading", "action": "eod_review"},
                )

    except Exception as e:
        logger.error(f"EOD notify failed: {e}")


async def run_eod_close():
    """
    Manually triggered EOD close — called only after user approval.
    Cancels all pending orders then closes all stock positions.
    """
    logger.info("=== AUTO TRADING: EOD close (user approved) ===")
    try:
        alpaca.cancel_all_orders()
        positions = alpaca.get_positions()
        stock_positions = [p for p in positions if p["symbol"] in ALPACA_STOCKS]

        if not stock_positions:
            logger.info("EOD close: no stock positions to close")
            return {"closed": []}

        closed = []
        for p in stock_positions:
            sym = p["symbol"]
            try:
                result = alpaca.close_position(sym)
                closed.append({"symbol": sym, "order_id": result.get("id"), "status": result.get("status")})
                logger.info(f"EOD close {sym}: order {result.get('id')}")
            except Exception as e:
                logger.error(f"EOD close error {sym}: {e}")
                closed.append({"symbol": sym, "error": str(e)})

        logger.info(f"EOD close: {len(closed)} positions submitted")
        return {"closed": closed}
    except Exception as e:
        logger.error(f"EOD close failed: {e}")
        return {"error": str(e)}


async def _run_scan(session: str):
    """Core scanning loop — shared by morning and afternoon jobs."""
    try:
        acct = alpaca.get_account()
        bp = float(acct["buying_power"])
        equity = float(acct["equity"])
    except Exception as e:
        logger.error(f"auto_trading: cannot fetch account: {e}")
        return

    # Guard: risk cap
    risk_used = daily_risk_used()
    if risk_used >= MAX_DAILY_RISK:
        logger.info(f"auto_trading [{session}]: daily risk cap hit (${risk_used:.0f}/${MAX_DAILY_RISK:.0f})")
        return

    # Guard: position count
    open_syms = _open_symbols()
    slots_available = MAX_POSITIONS - len(open_syms)
    if slots_available <= 0:
        logger.info(f"auto_trading [{session}]: max positions reached ({len(open_syms)})")
        return

    logger.info(
        f"auto_trading [{session}]: BP=${bp:,.0f}  equity=${equity:,.0f}  "
        f"open={len(open_syms)}/{MAX_POSITIONS}  daily_risk=${risk_used:.0f}/${MAX_DAILY_RISK:.0f}"
    )

    # Scan universe in batches of 4
    signals = []
    batch_size = 4
    for i in range(0, len(SCAN_UNIVERSE), batch_size):
        batch = [s for s in SCAN_UNIVERSE[i:i + batch_size] if s not in open_syms]
        if not batch:
            continue
        results = await asyncio.gather(*[_scan_symbol(s) for s in batch])
        for sig in results:
            if sig:
                signals.append(sig)
        await asyncio.sleep(0.5)

    if not signals:
        logger.info(f"auto_trading [{session}]: no qualifying signals found")
        return

    # Sort by score desc, then confidence desc
    signals.sort(key=lambda s: (s.smc_score, s.confidence), reverse=True)
    logger.info(f"auto_trading [{session}]: {len(signals)} signals found, taking top {slots_available}")

    placed = 0
    for sig in signals:
        if placed >= slots_available:
            break
        remaining_risk = MAX_DAILY_RISK - daily_risk_used()
        if remaining_risk < RISK_PER_TRADE:
            logger.info("auto_trading: daily risk cap nearly exhausted — stopping")
            break
        if sig.symbol in _open_symbols():
            continue

        is_stock = sig.symbol in ALPACA_STOCKS
        qty = _position_size(sig.entry, sig.risk, bp, is_stock)

        try:
            result = _place_trade(sig, qty)
            _add_risk(RISK_PER_TRADE)
            placed += 1
            logger.info(
                f"auto_trading [{session}]: opened {sig.direction} {sig.symbol} "
                f"qty={qty} score={sig.smc_score}/5 conf={sig.confidence:.0%} "
                f"risk=${RISK_PER_TRADE:.0f}"
            )
            # Log each leg
            for leg in ["leg_a_tp1", "leg_b_tp2", "leg_c_runner"]:
                order = result.get(leg, {})
                if "error" in order:
                    logger.warning(f"  {leg}: {order['error']}")
                elif "id" in order:
                    logger.info(f"  {leg}: {order['id']} status={order['status']}")
        except Exception as e:
            logger.error(f"auto_trading [{session}]: trade error {sig.symbol}: {e}")

    logger.info(f"=== AUTO TRADING [{session}]: done — {placed} trades opened ===")


def get_status() -> dict:
    """Return current auto-trading status (for API endpoint)."""
    try:
        positions = alpaca.get_positions()
        orders = alpaca.get_orders("open")
        acct = alpaca.get_account()
    except Exception as e:
        return {"error": str(e)}

    return {
        "daily_risk_used": daily_risk_used(),
        "daily_risk_cap": MAX_DAILY_RISK,
        "risk_per_trade": RISK_PER_TRADE,
        "max_positions": MAX_POSITIONS,
        "open_positions": len(positions),
        "open_orders": len(orders),
        "buying_power": float(acct["buying_power"]),
        "equity": float(acct["equity"]),
        "portfolio_value": float(acct["portfolio_value"]),
        "config": {
            "min_score": MIN_SCORE,
            "scan_universe_size": len(SCAN_UNIVERSE),
            "schedule": {
                "morning_scan": "09:35 ET",
                "afternoon_scan": "15:15 ET",
                "eod_close": "15:45 ET",
            },
        },
        "positions": positions,
    }
