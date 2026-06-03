"""
Market Mechanics Router (signal-only)

GET  /smc/signal/{symbol}   — live Market Mechanics signal
GET  /smc/scan              — scan universe, return active setups (score ≥ filter)
"""

import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException, Query

from app.routers.auth import get_current_user
from app.models.user import User
from app.services.market_data import fetch_ohlcv
from app.services.smc_service import generate_smc_signal, smc_signal_to_dict

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/smc", tags=["smc"])

SCAN_UNIVERSE = [
    "AAPL", "MSFT", "GOOGL", "AMZN", "TSLA", "NVDA", "META", "NFLX",
    "AMD", "SPY", "QQQ", "JPM", "BAC", "GS", "V", "MA",
    "BTCUSD", "ETHUSD", "SOLUSD", "LINKUSD", "AVAXUSD",
]


async def _fetch_all(symbol: str):
    df4h, df1h, df15m = await asyncio.gather(
        fetch_ohlcv(symbol, "4h",  limit=200),
        fetch_ohlcv(symbol, "1h",  limit=200),
        fetch_ohlcv(symbol, "15m", limit=300),
    )
    return df4h, df1h, df15m


@router.get("/signal/{symbol}")
async def get_smc_signal(
    symbol: str,
    current_user: User = Depends(get_current_user),
):
    sym = symbol.upper()
    df4h, df1h, df15m = await _fetch_all(sym)

    if df4h is None or df15m is None:
        raise HTTPException(status_code=404, detail=f"No data for {sym}")

    sig = generate_smc_signal(df4h, df15m, sym, df1h)
    if sig is None:
        return {
            "symbol": sym,
            "signal": None,
            "message": "No Market Mechanics setup — conditions not fully met yet",
        }
    return smc_signal_to_dict(sig)


@router.get("/scan")
async def scan_universe(
    min_score: int = Query(default=4, ge=1, le=5),
    current_user: User = Depends(get_current_user),
):
    results = []
    errors = []

    async def _scan_one(sym: str):
        try:
            df4h, df1h, df15m = await _fetch_all(sym)
            if df4h is None or df15m is None:
                return
            sig = generate_smc_signal(df4h, df15m, sym, df1h)
            if sig and sig.smc_score >= min_score:
                results.append(smc_signal_to_dict(sig))
        except Exception as e:
            errors.append({"symbol": sym, "error": str(e)})

    for i in range(0, len(SCAN_UNIVERSE), 4):
        await asyncio.gather(*[_scan_one(s) for s in SCAN_UNIVERSE[i:i + 4]])
        await asyncio.sleep(0.8)

    results.sort(key=lambda x: x["confidence"], reverse=True)
    return {
        "scanned": len(SCAN_UNIVERSE),
        "signals_found": len(results),
        "min_score_filter": f"{min_score}/5",
        "signals": results,
        "errors": errors,
    }
