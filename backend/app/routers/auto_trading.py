"""
Auto-trading control endpoints.

GET  /auto-trading/status       — current state (positions, risk used, config)
POST /auto-trading/scan/morning — manually trigger morning scan
POST /auto-trading/scan/afternoon — manually trigger afternoon scan
POST /auto-trading/eod-close    — manually trigger EOD position close
PATCH /auto-trading/config      — update risk controls at runtime
"""

import asyncio
from fastapi import APIRouter, Depends, BackgroundTasks
from pydantic import BaseModel
from typing import Optional

from app.routers.auth import get_current_user
from app.models.user import User
import app.services.auto_trading_service as ats

router = APIRouter(prefix="/auto-trading", tags=["auto-trading"])


class ConfigUpdate(BaseModel):
    risk_per_trade: Optional[float] = None
    max_positions: Optional[int] = None
    max_daily_risk: Optional[float] = None
    min_score: Optional[int] = None


@router.get("/status")
async def status(current_user: User = Depends(get_current_user)):
    """Return auto-trading status: positions, risk used, config."""
    return ats.get_status()


@router.post("/scan/morning")
async def trigger_morning(
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
):
    """Manually trigger a morning scan (runs in background)."""
    background_tasks.add_task(ats.run_morning_scan)
    return {"message": "Morning scan started", "daily_risk_used": ats.daily_risk_used()}


@router.post("/scan/afternoon")
async def trigger_afternoon(
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
):
    """Manually trigger an afternoon scan (runs in background)."""
    background_tasks.add_task(ats.run_afternoon_scan)
    return {"message": "Afternoon scan started", "daily_risk_used": ats.daily_risk_used()}


@router.post("/eod-close")
async def trigger_eod(current_user: User = Depends(get_current_user)):
    """
    Close all open stock positions — requires explicit user call (approval).
    Never triggered automatically; the scheduler only sends a notification.
    """
    result = await ats.run_eod_close()
    return {"message": "EOD close executed", **result}


@router.patch("/config")
async def update_config(
    body: ConfigUpdate,
    current_user: User = Depends(get_current_user),
):
    """Update risk controls at runtime without restart."""
    if body.risk_per_trade is not None:
        ats.RISK_PER_TRADE = body.risk_per_trade
    if body.max_positions is not None:
        ats.MAX_POSITIONS = body.max_positions
    if body.max_daily_risk is not None:
        ats.MAX_DAILY_RISK = body.max_daily_risk
    if body.min_score is not None:
        ats.MIN_SCORE = body.min_score

    return {
        "updated": True,
        "config": {
            "risk_per_trade": ats.RISK_PER_TRADE,
            "max_positions": ats.MAX_POSITIONS,
            "max_daily_risk": ats.MAX_DAILY_RISK,
            "min_score": ats.MIN_SCORE,
        },
    }
