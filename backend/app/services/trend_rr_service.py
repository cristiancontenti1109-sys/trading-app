"""
1:2 RR Trend Strategy — Signal Scanner (no order execution)
============================================================
Indicators:  EMA-50 (trend filter) · RSI-14 (momentum) · ATR-14 (volatility)
Entry rule:  close > EMA-50 AND RSI crosses above 45 from below → signal
Exits:       user-managed (manual)
"""

import asyncio
import logging
from datetime import datetime
from typing import Optional
from zoneinfo import ZoneInfo

import pandas as pd

logger = logging.getLogger(__name__)
ET = ZoneInfo("America/New_York")

# ── Configurable parameters ────────────────────────────────────────────────────
RISK_PCT       = 0.01   # reference risk % (display only)
ATR_SL_MULT    = 1.5
RR_RATIO       = 2.0
EMA_PERIOD     = 50
RSI_PERIOD     = 14
ATR_PERIOD     = 14
RSI_TRIGGER    = 45

SCAN_UNIVERSE = list(dict.fromkeys([
    # Mega-cap Tech
    "AAPL","MSFT","GOOGL","GOOG","AMZN","NVDA","META","TSLA","AVGO","ORCL",
    # Semiconductors
    "AMD","INTC","QCOM","MU","AMAT","LRCX","KLAC","TXN","MRVL","ON","MPWR",
    # Software / Cloud
    "ADBE","CRM","NOW","INTU","WDAY","SNPS","CDNS","ANSS","CTSH","IBM","SAP",
    # Internet / E-commerce
    "NFLX","UBER","LYFT","ABNB","BKNG","EXPE","EBAY","ETSY","SHOP","MELI",
    # Fintech / Payments
    "V","MA","PYPL","SQ","AFRM","SOFI","HOOD","COIN","MSTR","UPST",
    # Banks / Finance
    "JPM","BAC","WFC","C","GS","MS","BLK","SCHW","AXP","COF",
    # ETFs
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
    # Consumer
    "HD","LOW","TJX","NKE","SBUX","MCD","CMG","YUM","BURL","ROST",
    "DG","DLTR","WMT","COST","TGT","KR","PG","KO","PEP","MDLZ","GIS","KHC","CL",
    # Industrials / Aerospace
    "BA","GE","HON","CAT","DE","MMM","LMT","RTX","NOC","GD","UPS","FDX",
    # Autos
    "F","GM","RIVN","LCID",
    # Real Estate / REITs
    "AMT","PLD","EQIX","SPG","O","AVB",
    # Telecom / Media
    "T","VZ","CMCSA","DIS","WBD","PARA",
    # Materials
    "FCX","NEM","GOLD","AA","NUE","CF","MOS",
    # China ADRs
    "BABA","JD","PDD","BIDU","NIO","XPEV","LI",
    # Other high-volume
    "GME","AMC","SNAP","PINS","SPOT","ROKU","FUTU",
]))


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
    high, low, prev_close = df["high"], df["low"], df["close"].shift()
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs(),
    ], axis=1).max(axis=1)
    return tr.ewm(com=period - 1, adjust=False).mean()


def _is_market_open() -> bool:
    now = datetime.now(ET)
    if now.weekday() >= 5:
        return False
    market_open  = now.replace(hour=9,  minute=30, second=0, microsecond=0)
    market_close = now.replace(hour=16, minute=0,  second=0, microsecond=0)
    return market_open <= now < market_close


# ── Signal scoring (no orders) ─────────────────────────────────────────────────

def _score_symbol(symbol: str, df: pd.DataFrame) -> Optional[dict]:
    """Score a symbol 0-100 based on proximity to trend-RR entry signal."""
    if len(df) < EMA_PERIOD + 10:
        return None

    ema50 = _ema(df["close"], EMA_PERIOD)
    rsi14 = _rsi(df["close"], RSI_PERIOD)
    atr14 = _atr(df, ATR_PERIOD)

    last_close = float(df["close"].iloc[-1])
    last_ema   = float(ema50.iloc[-1])
    last_rsi   = float(rsi14.iloc[-1])
    last_atr   = float(atr14.iloc[-1])

    if last_close <= last_ema:
        return None
    if not (28 <= last_rsi <= 68):
        return None
    if last_atr <= 0:
        return None

    rsi_dist      = abs(last_rsi - RSI_TRIGGER)
    rsi_score     = max(0.0, 40.0 - rsi_dist * 2.0)
    rsi_slope     = float(rsi14.iloc[-1] - rsi14.iloc[-5]) if len(rsi14) >= 5 else 0.0
    momentum_score = min(30.0, max(0.0, rsi_slope * 3.0))
    pct_above     = (last_close - last_ema) / last_ema * 100
    trend_score   = 30.0 if pct_above < 1 else 22.0 if pct_above < 3 else 12.0 if pct_above < 6 else 4.0

    total = round(rsi_score + momentum_score + trend_score, 1)

    sl_dist     = last_atr * ATR_SL_MULT
    stop_loss   = round(last_close - sl_dist, 4)
    take_profit = round(last_close + sl_dist * RR_RATIO, 4)

    return {
        "symbol":        symbol,
        "score":         total,
        "price":         round(last_close, 4),
        "rsi":           round(last_rsi, 1),
        "rsi_momentum":  round(rsi_slope, 2),
        "pct_above_ema": round(pct_above, 2),
        "ema50":         round(last_ema, 4),
        "atr":           round(last_atr, 4),
        "stop_loss":     stop_loss,
        "take_profit":   take_profit,
    }


async def scan_for_top_picks(n: int = 10) -> list[dict]:
    """Scan full universe, score every symbol, return top-n — no orders placed."""
    from app.services.market_data import fetch_ohlcv

    picks: list[dict] = []
    BATCH = 8

    async def _score_one(sym: str) -> Optional[dict]:
        df = await fetch_ohlcv(sym, "1h", limit=150)
        if df is None or df.empty:
            return None
        return _score_symbol(sym, df)

    for i in range(0, len(SCAN_UNIVERSE), BATCH):
        batch = SCAN_UNIVERSE[i:i + BATCH]
        results = await asyncio.gather(*[_score_one(s) for s in batch], return_exceptions=True)
        for r in results:
            if isinstance(r, dict):
                picks.append(r)
        await asyncio.sleep(0.3)

    picks.sort(key=lambda x: x["score"], reverse=True)
    return picks[:n]


async def strategy_scan(strategy: str, timeframe: str, n: int = 10) -> list[dict]:
    """Scan SCAN_UNIVERSE with any strategy, return top-n by confidence (BUY first)."""
    from app.services.market_data import fetch_ohlcv
    from app.services.strategy_service import run_strategy

    results: list[dict] = []
    BATCH = 5

    async def _analyze(sym: str) -> Optional[dict]:
        loop = asyncio.get_event_loop()
        df = await fetch_ohlcv(sym, timeframe, limit=300)
        if df is None or df.empty:
            return None
        result = await loop.run_in_executor(None, lambda: run_strategy(df, sym, timeframe, strategy))
        if result is None or result.get("recommendation") == "HOLD":
            return None
        return result

    for i in range(0, len(SCAN_UNIVERSE), BATCH):
        batch = SCAN_UNIVERSE[i:i + BATCH]
        batch_res = await asyncio.gather(*[_analyze(s) for s in batch], return_exceptions=True)
        for r in batch_res:
            if isinstance(r, dict):
                results.append(r)
        await asyncio.sleep(0.4)

    buys  = sorted([r for r in results if r["recommendation"] == "BUY"],  key=lambda x: x.get("confidence", 0), reverse=True)
    sells = sorted([r for r in results if r["recommendation"] == "SELL"], key=lambda x: x.get("confidence", 0), reverse=True)
    return (buys + sells)[:n]


def get_status() -> dict:
    return {
        "strategy":        "1:2 RR Trend Strategy — Signal Scanner",
        "market_open":     _is_market_open(),
        "current_time_et": datetime.now(ET).strftime("%H:%M ET (%A)"),
        "config": {
            "atr_sl_multiplier": ATR_SL_MULT,
            "rr_ratio":          RR_RATIO,
            "ema_period":        EMA_PERIOD,
            "rsi_period":        RSI_PERIOD,
            "rsi_trigger":       RSI_TRIGGER,
            "scan_universe":     SCAN_UNIVERSE,
            "timeframe":         "1h",
        },
    }
