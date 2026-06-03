"""
Semi-Auto 1:2 RR Trend Strategy endpoints.

GET   /trend-rr/status         — active trades, config, live P&L
POST  /trend-rr/scan           — manually trigger a scan cycle
POST  /trend-rr/close/{symbol} — user-approved manual close
PATCH /trend-rr/config         — update risk params at runtime
"""

from fastapi import APIRouter, BackgroundTasks, Depends
from pydantic import BaseModel
from typing import Optional

from app.routers.auth import get_current_user
from app.models.user import User
import app.services.trend_rr_service as trs

router = APIRouter(prefix="/trend-rr", tags=["trend-rr"])


class ConfigUpdate(BaseModel):
    risk_pct: Optional[float] = None          # percent, e.g. 1.0 = 1%
    atr_sl_multiplier: Optional[float] = None
    rr_ratio: Optional[float] = None
    rsi_trigger: Optional[int] = None


@router.get("/status")
async def status(current_user: User = Depends(get_current_user)):
    return trs.get_status()


@router.post("/scan")
async def trigger_scan(
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
):
    background_tasks.add_task(trs.run_scan)
    return {"message": "Trend RR scan started", "active_trades": len(trs._active_trades)}


@router.post("/close/{symbol}")
async def close_trade(
    symbol: str,
    current_user: User = Depends(get_current_user),
):
    return trs.manual_close_trade(symbol)


@router.patch("/config")
async def update_config(
    body: ConfigUpdate,
    current_user: User = Depends(get_current_user),
):
    if body.risk_pct is not None:
        trs.RISK_PCT = body.risk_pct / 100
    if body.atr_sl_multiplier is not None:
        trs.ATR_SL_MULT = body.atr_sl_multiplier
    if body.rr_ratio is not None:
        trs.RR_RATIO = body.rr_ratio
    if body.rsi_trigger is not None:
        trs.RSI_TRIGGER = body.rsi_trigger

    return {
        "updated": True,
        "config": {
            "risk_pct": round(trs.RISK_PCT * 100, 2),
            "atr_sl_multiplier": trs.ATR_SL_MULT,
            "rr_ratio": trs.RR_RATIO,
            "rsi_trigger": trs.RSI_TRIGGER,
        },
    }
