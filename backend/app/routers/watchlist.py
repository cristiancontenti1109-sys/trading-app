from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from pydantic import BaseModel

from app.database import get_db
from app.models.instrument import Instrument, WatchlistItem
from app.models.user import User
from app.routers.auth import get_current_user
from app.services.market_data import search_instruments

router = APIRouter(prefix="/watchlist", tags=["watchlist"])


class AddItemRequest(BaseModel):
    symbol: str
    pinned: bool = False


@router.get("/")
async def get_watchlist(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(WatchlistItem, Instrument)
        .join(Instrument, WatchlistItem.symbol == Instrument.symbol)
        .where(WatchlistItem.user_id == current_user.id)
        .order_by(WatchlistItem.pinned.desc(), WatchlistItem.added_at)
    )
    rows = result.all()
    return [
        {
            "id": item.id,
            "symbol": item.symbol,
            "pinned": item.pinned,
            "added_at": item.added_at.isoformat(),
            "name": instrument.name,
            "asset_class": instrument.asset_class,
            "last_price": instrument.last_price,
        }
        for item, instrument in rows
    ]


@router.post("/")
async def add_to_watchlist(
    data: AddItemRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # Check if already in watchlist
    result = await db.execute(
        select(WatchlistItem).where(
            WatchlistItem.user_id == current_user.id,
            WatchlistItem.symbol == data.symbol,
        )
    )
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Already in watchlist")

    # Free tier limit: 5 instruments
    if current_user.subscription_tier == "free":
        count_result = await db.execute(
            select(WatchlistItem).where(WatchlistItem.user_id == current_user.id)
        )
        if len(count_result.scalars().all()) >= 5:
            raise HTTPException(status_code=403, detail="Free tier limit: 5 instruments. Upgrade to Pro.")

    # Ensure instrument exists in catalog
    inst_result = await db.execute(select(Instrument).where(Instrument.symbol == data.symbol))
    if not inst_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Instrument not found")

    item = WatchlistItem(user_id=current_user.id, symbol=data.symbol, pinned=data.pinned)
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return {"id": item.id, "symbol": item.symbol, "pinned": item.pinned}


@router.delete("/{symbol}")
async def remove_from_watchlist(
    symbol: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await db.execute(
        delete(WatchlistItem).where(
            WatchlistItem.user_id == current_user.id,
            WatchlistItem.symbol == symbol,
        )
    )
    await db.commit()
    return {"ok": True}


@router.patch("/{symbol}/pin")
async def toggle_pin(
    symbol: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(WatchlistItem).where(
            WatchlistItem.user_id == current_user.id,
            WatchlistItem.symbol == symbol,
        )
    )
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Not in watchlist")

    item.pinned = not item.pinned
    await db.commit()
    return {"symbol": symbol, "pinned": item.pinned}


@router.get("/search")
async def search(q: str):
    if len(q) < 1:
        return []
    results = await search_instruments(q)
    return results
