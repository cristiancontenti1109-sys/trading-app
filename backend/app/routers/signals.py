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
    cutoff = datetime.utcnow() - timedelta(minutes=10)
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


@router.get("/{symbol}/strategy")
async def get_strategy_signal(
    symbol: str,
    strategy: str = Query(..., enum=[
        "fibonacci", "smart_money", "elliott_wave", "warren_buffett", "jpmorgan",
        "macd_crossover", "rsi_divergence", "bb_squeeze",
        "support_resistance", "ema_crossover", "ichimoku", "stochastic", "vwap",
    ]),
    timeframe: str = Query("4h", enum=TIMEFRAMES),
    current_user: User = Depends(get_current_user),
):
    """Run a specific named strategy on live OHLCV data."""
    from app.services.strategy_service import run_strategy
    df = await fetch_ohlcv(symbol, timeframe, 200)
    if df is None or df.empty:
        raise HTTPException(status_code=404, detail=f"No market data for {symbol}")
    result = run_strategy(df, symbol, timeframe, strategy)
    if result is None:
        raise HTTPException(status_code=422, detail="Insufficient data for strategy analysis")
    return result


@router.post("/{symbol}/custom")
async def run_custom_strategy(
    symbol: str,
    params: dict,
    timeframe: str = Query("4h", enum=TIMEFRAMES),
    current_user: User = Depends(get_current_user),
):
    """Run user-defined custom strategy with configurable parameters."""
    from app.services.signal_service import run_custom_strategy
    df = await fetch_ohlcv(symbol, timeframe, 300)
    if df is None or df.empty:
        raise HTTPException(status_code=404, detail=f"No market data for {symbol}")
    result = run_custom_strategy(
        df, symbol, timeframe,
        fast_ema=int(params.get("fast_ema", 9)),
        slow_ema=int(params.get("slow_ema", 21)),
        rsi_period=int(params.get("rsi_period", 14)),
        rsi_oversold=float(params.get("rsi_oversold", 30)),
        rsi_overbought=float(params.get("rsi_overbought", 70)),
        require_macd=bool(params.get("require_macd", True)),
        require_volume=bool(params.get("require_volume", False)),
        atr_multiplier=float(params.get("atr_multiplier", 1.5)),
    )
    if result is None:
        raise HTTPException(status_code=422, detail="Insufficient data for custom strategy")
    return result


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
