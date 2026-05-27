from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from pydantic import BaseModel
from typing import Optional
from datetime import datetime

from app.database import get_db
from app.models.trade import Trade
from app.models.user import User
from app.routers.auth import get_current_user

router = APIRouter(prefix="/trades", tags=["trades"])


class TradeCreate(BaseModel):
    symbol: str
    direction: str        # BUY / SELL
    entry_price: float
    size: float = 1.0
    notes: Optional[str] = None


class TradeClose(BaseModel):
    exit_price: float
    notes: Optional[str] = None


def trade_to_dict(t: Trade) -> dict:
    return {
        "id": t.id,
        "symbol": t.symbol,
        "direction": t.direction,
        "entry_price": t.entry_price,
        "exit_price": t.exit_price,
        "size": t.size,
        "status": t.status,
        "notes": t.notes,
        "pnl": t.pnl,
        "pnl_pct": t.pnl_pct,
        "opened_at": t.opened_at.isoformat() + "Z",
        "closed_at": t.closed_at.isoformat() + "Z" if t.closed_at else None,
    }


@router.get("/")
async def list_trades(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Trade)
        .where(Trade.user_id == current_user.id)
        .order_by(desc(Trade.opened_at))
    )
    trades = result.scalars().all()
    return [trade_to_dict(t) for t in trades]


@router.post("/")
async def create_trade(
    data: TradeCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    trade = Trade(
        user_id=current_user.id,
        symbol=data.symbol,
        direction=data.direction.upper(),
        entry_price=data.entry_price,
        size=data.size,
        notes=data.notes,
    )
    db.add(trade)
    await db.commit()
    await db.refresh(trade)
    return trade_to_dict(trade)


@router.patch("/{trade_id}/close")
async def close_trade(
    trade_id: str,
    data: TradeClose,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Trade).where(Trade.id == trade_id, Trade.user_id == current_user.id)
    )
    trade = result.scalar_one_or_none()
    if not trade:
        raise HTTPException(status_code=404, detail="Trade not found")
    if trade.status == "closed":
        raise HTTPException(status_code=400, detail="Trade already closed")

    trade.exit_price = data.exit_price
    trade.status = "closed"
    trade.closed_at = datetime.utcnow()
    if data.notes:
        trade.notes = data.notes
    await db.commit()
    await db.refresh(trade)
    return trade_to_dict(trade)


@router.delete("/{trade_id}")
async def delete_trade(
    trade_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Trade).where(Trade.id == trade_id, Trade.user_id == current_user.id)
    )
    trade = result.scalar_one_or_none()
    if not trade:
        raise HTTPException(status_code=404, detail="Trade not found")
    await db.delete(trade)
    await db.commit()
    return {"ok": True}


@router.get("/stats")
async def trade_stats(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Trade).where(Trade.user_id == current_user.id, Trade.status == "closed")
    )
    closed = result.scalars().all()
    if not closed:
        return {"total": 0, "wins": 0, "losses": 0, "win_rate": 0, "total_pnl": 0, "avg_pnl": 0}

    wins = [t for t in closed if (t.pnl or 0) > 0]
    losses = [t for t in closed if (t.pnl or 0) <= 0]
    total_pnl = sum(t.pnl or 0 for t in closed)

    return {
        "total": len(closed),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": round(len(wins) / len(closed) * 100, 1),
        "total_pnl": round(total_pnl, 4),
        "avg_pnl": round(total_pnl / len(closed), 4),
    }
