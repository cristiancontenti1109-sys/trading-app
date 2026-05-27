from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from app.models.instrument import Instrument
from app.models.user import User
from app.routers.auth import get_current_user
from app.services.market_data import fetch_current_price

router = APIRouter(prefix="/instruments", tags=["instruments"])


@router.get("/{symbol}")
async def get_instrument(
    symbol: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Instrument).where(Instrument.symbol == symbol))
    instrument = result.scalar_one_or_none()
    if not instrument:
        raise HTTPException(status_code=404, detail="Instrument not found")

    # Fetch live price
    price = await fetch_current_price(symbol)
    if price:
        instrument.last_price = price
        from datetime import datetime
        instrument.last_updated = datetime.utcnow()
        await db.commit()

    return {
        "symbol": instrument.symbol,
        "name": instrument.name,
        "asset_class": instrument.asset_class,
        "exchange": instrument.exchange,
        "last_price": instrument.last_price,
        "last_updated": instrument.last_updated.isoformat() if instrument.last_updated else None,
    }


@router.get("/{symbol}/price")
async def get_price(symbol: str, current_user: User = Depends(get_current_user)):
    price = await fetch_current_price(symbol)
    if price is None:
        raise HTTPException(status_code=404, detail="Price not available")
    return {"symbol": symbol, "price": price}
