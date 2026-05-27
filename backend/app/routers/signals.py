from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from typing import Optional

from app.database import get_db
from app.models.signal import Signal
from app.models.user import User
from app.routers.auth import get_current_user
from app.services.market_data import fetch_ohlcv
from app.services.signal_service import generate_signal

router = APIRouter(prefix="/signals", tags=["signals"])

TIMEFRAMES = ["1m", "5m", "15m", "1h", "4h", "1D", "1W"]


@router.get("/{symbol}")
async def get_signal(
    symbol: str,
    timeframe: str = Query("4h", enum=TIMEFRAMES),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get the latest signal for a symbol. Generates fresh if none cached recently."""
    # Try cached signal first (last 30 minutes)
    from datetime import datetime, timedelta
    cutoff = datetime.utcnow() - timedelta(minutes=30)
    result = await db.execute(
        select(Signal)
        .where(Signal.symbol == symbol, Signal.timeframe == timeframe, Signal.created_at > cutoff)
        .order_by(desc(Signal.created_at))
        .limit(1)
    )
    cached = result.scalar_one_or_none()
    if cached:
        return _signal_to_dict(cached)

    # Generate fresh signal
    df = await fetch_ohlcv(symbol, timeframe)
    if df is None or df.empty:
        raise HTTPException(status_code=404, detail=f"No market data for {symbol}")

    signal_data = generate_signal(df, symbol, timeframe)
    if not signal_data:
        raise HTTPException(status_code=422, detail="Insufficient data to generate signal")

    # Persist
    signal = Signal(
        symbol=symbol,
        timeframe=timeframe,
        ts=datetime.utcnow(),
        recommendation=signal_data["recommendation"],
        confidence=signal_data["confidence"],
        entry_low=signal_data["entry_zone"]["low"],
        entry_high=signal_data["entry_zone"]["high"],
        target_price=signal_data["target_price"],
        stop_loss=signal_data["stop_loss"],
        reasoning=signal_data["reasoning"],
        is_hot=signal_data["is_hot"],
        is_hot_confluence=signal_data["is_hot_confluence"],
    )
    db.add(signal)
    await db.commit()

    return signal_data


@router.get("/{symbol}/history")
async def get_signal_history(
    symbol: str,
    timeframe: str = Query("4h", enum=TIMEFRAMES),
    limit: int = Query(30, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Signal)
        .where(Signal.symbol == symbol, Signal.timeframe == timeframe)
        .order_by(desc(Signal.created_at))
        .limit(limit)
    )
    signals = result.scalars().all()
    return [_signal_to_dict(s) for s in signals]


@router.get("/{symbol}/ohlcv")
async def get_ohlcv(
    symbol: str,
    timeframe: str = Query("4h", enum=TIMEFRAMES),
    limit: int = Query(200, le=500),
    current_user: User = Depends(get_current_user),
):
    df = await fetch_ohlcv(symbol, timeframe, limit)
    if df is None or df.empty:
        raise HTTPException(status_code=404, detail=f"No data for {symbol}")

    return {
        "symbol": symbol,
        "timeframe": timeframe,
        "candles": [
            {
                "time": int(ts.timestamp()),
                "open": row["open"],
                "high": row["high"],
                "low": row["low"],
                "close": row["close"],
                "volume": row["volume"],
            }
            for ts, row in df.iterrows()
        ],
    }


@router.get("/{symbol}/news")
async def get_symbol_news(
    symbol: str,
    current_user: User = Depends(get_current_user),
):
    """Return recent news articles for a symbol."""
    from app.services.market_data import fetch_news
    news = await fetch_news(symbol)
    return {"symbol": symbol, "news": news}


def _signal_to_dict(s: Signal) -> dict:
    return {
        "id": s.id,
        "symbol": s.symbol,
        "timeframe": s.timeframe,
        "timestamp": s.ts.isoformat() + "Z",
        "recommendation": s.recommendation,
        "confidence": s.confidence,
        "entry_zone": {"low": s.entry_low, "high": s.entry_high},
        "target_price": s.target_price,
        "stop_loss": s.stop_loss,
        "reasoning": s.reasoning or [],
        "is_hot": s.is_hot,
        "is_hot_confluence": s.is_hot_confluence,
        "created_at": s.created_at.isoformat() + "Z",
    }
