"""
1:2 RR Trend Strategy — signal-only endpoints.

GET   /trend-rr/status         — config & market status
POST  /trend-rr/strategy-scan  — scan all symbols with selected strategy
PATCH /trend-rr/config         — update strategy parameters at runtime
"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from typing import Optional

from app.routers.auth import get_current_user
from app.models.user import User
import app.services.trend_rr_service as trs

router = APIRouter(prefix="/trend-rr", tags=["trend-rr"])


class ConfigUpdate(BaseModel):
    atr_sl_multiplier: Optional[float] = None
    rr_ratio: Optional[float] = None
    rsi_trigger: Optional[int] = None


@router.get("/status")
async def status(current_user: User = Depends(get_current_user)):
    return trs.get_status()


@router.post("/strategy-scan")
async def run_strategy_scan(
    strategy: str,
    timeframe: str = "1D",
    current_user: User = Depends(get_current_user),
):
    picks = await trs.strategy_scan(strategy, timeframe, 10)
    return {
        "picks": picks,
        "total_scanned": len(trs.SCAN_UNIVERSE),
        "strategy": strategy,
        "timeframe": timeframe,
    }


@router.patch("/config")
async def update_config(
    body: ConfigUpdate,
    current_user: User = Depends(get_current_user),
):
    if body.atr_sl_multiplier is not None:
        trs.ATR_SL_MULT = body.atr_sl_multiplier
    if body.rr_ratio is not None:
        trs.RR_RATIO = body.rr_ratio
    if body.rsi_trigger is not None:
        trs.RSI_TRIGGER = body.rsi_trigger

    return {
        "updated": True,
        "config": {
            "atr_sl_multiplier": trs.ATR_SL_MULT,
            "rr_ratio": trs.RR_RATIO,
            "rsi_trigger": trs.RSI_TRIGGER,
        },
    }
