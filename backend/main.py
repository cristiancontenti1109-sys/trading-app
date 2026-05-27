import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Depends, Query
from fastapi.middleware.cors import CORSMiddleware
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.config import settings
from app.database import init_db, get_db, AsyncSessionLocal
from app.models import User, Instrument, WatchlistItem
from app.routers import auth, watchlist, signals, instruments, trades
from app.websocket.manager import manager
from app.services.market_data import fetch_ohlcv, fetch_current_price
from app.services.signal_service import generate_signal
from app.services.notification_service import (
    send_push_notification, should_send_notification,
    mark_notification_sent, is_in_quiet_hours, build_hot_notification,
)
from app.routers.auth import get_current_user

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()

INSTRUMENT_CATALOG = [
    ("BTCUSD", "Bitcoin / USD", "crypto"),
    ("ETHUSD", "Ethereum / USD", "crypto"),
    ("SOLUSD", "Solana / USD", "crypto"),
    ("BNBUSD", "BNB / USD", "crypto"),
    ("XRPUSD", "XRP / USD", "crypto"),
    ("ADAUSD", "Cardano / USD", "crypto"),
    ("DOGEUSD", "Dogecoin / USD", "crypto"),
    ("AAPL", "Apple Inc.", "stocks"),
    ("MSFT", "Microsoft Corp.", "stocks"),
    ("GOOGL", "Alphabet Inc.", "stocks"),
    ("AMZN", "Amazon.com Inc.", "stocks"),
    ("TSLA", "Tesla Inc.", "stocks"),
    ("NVDA", "NVIDIA Corp.", "stocks"),
    ("META", "Meta Platforms", "stocks"),
    ("NFLX", "Netflix Inc.", "stocks"),
    ("SPY", "SPDR S&P 500 ETF", "stocks"),
    ("EURUSD", "EUR / USD", "forex"),
    ("GBPUSD", "GBP / USD", "forex"),
    ("USDJPY", "USD / JPY", "forex"),
    ("AUDUSD", "AUD / USD", "forex"),
    ("XAUUSD", "Gold / USD", "commodities"),
    ("XAGUSD", "Silver / USD", "commodities"),
    ("USOIL", "Crude Oil (WTI)", "commodities"),
]


async def seed_instruments():
    """Populate the instruments table on startup."""
    async with AsyncSessionLocal() as db:
        for symbol, name, asset_class in INSTRUMENT_CATALOG:
            result = await db.execute(select(Instrument).where(Instrument.symbol == symbol))
            if not result.scalar_one_or_none():
                db.add(Instrument(symbol=symbol, name=name, asset_class=asset_class))
        await db.commit()


async def run_signal_pipeline():
    """Run signal generation for all watchlisted instruments."""
    logger.info("Running signal pipeline...")
    async with AsyncSessionLocal() as db:
        # Get all unique symbols in any watchlist
        result = await db.execute(select(WatchlistItem.symbol).distinct())
        symbols = [row[0] for row in result.all()]

        for symbol in symbols:
            for timeframe in ["4h", "1D"]:
                try:
                    df = await fetch_ohlcv(symbol, timeframe)
                    if df is None or df.empty:
                        continue

                    signal = generate_signal(df, symbol, timeframe)
                    if not signal:
                        continue

                    # Broadcast to WebSocket subscribers
                    await manager.broadcast_signal(symbol, signal)

                    # Notify users if HOT
                    if signal.get("is_hot") and timeframe == "4h":
                        await notify_hot_signal(db, symbol, signal)

                except Exception as e:
                    logger.error(f"Signal pipeline error for {symbol}/{timeframe}: {e}")


async def notify_hot_signal(db: AsyncSession, symbol: str, signal: dict):
    """Fan out HOT signal notifications to all users watching the symbol."""
    result = await db.execute(
        select(User).join(WatchlistItem, User.id == WatchlistItem.user_id)
        .where(WatchlistItem.symbol == symbol)
    )
    users = result.scalars().all()

    condition = "hot_confluence" if signal.get("is_hot_confluence") else "hot"

    for user in users:
        s = user.settings_json or {}
        if not should_send_notification(user.id, symbol, condition, s.get("daily_notification_cap", 20)):
            continue
        if is_in_quiet_hours(s.get("quiet_hours_start", "22:00"), s.get("quiet_hours_end", "07:00")):
            continue
        if not user.expo_push_token:
            continue

        title, body = build_hot_notification(signal)
        sent = await send_push_notification(
            user.expo_push_token, title, body,
            data={"symbol": symbol, "type": condition, "screen": "instrument"},
        )
        if sent:
            mark_notification_sent(user.id, symbol, condition)


async def run_price_updates():
    """Broadcast latest prices to WebSocket clients."""
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(WatchlistItem.symbol).distinct())
        symbols = [row[0] for row in result.all()]

    for symbol in symbols:
        price = await fetch_current_price(symbol)
        if price:
            await manager.broadcast_price(symbol, price, 0.0)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    await seed_instruments()

    scheduler.add_job(run_signal_pipeline, "interval", minutes=15, id="signal_pipeline")
    scheduler.add_job(run_price_updates, "interval", seconds=30, id="price_updates")
    scheduler.start()
    logger.info("Scheduler started")

    yield

    scheduler.shutdown()


app = FastAPI(
    title="Trading Signal API",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(watchlist.router)
app.include_router(signals.router)
app.include_router(instruments.router)
app.include_router(trades.router)


@app.get("/health")
async def health():
    return {"status": "ok", "timestamp": datetime.utcnow().isoformat()}


@app.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    token: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    try:
        from jose import jwt, JWTError
        payload = jwt.decode(token, settings.secret_key, algorithms=["HS256"])
        user_id = payload.get("sub")
        if not user_id:
            await websocket.close(code=4001)
            return
    except Exception:
        await websocket.close(code=4001)
        return

    await manager.connect(websocket, user_id)
    try:
        while True:
            data = await websocket.receive_json()
            action = data.get("action")
            symbol = data.get("symbol")

            if action == "subscribe" and symbol:
                manager.subscribe(user_id, symbol)
                await websocket.send_json({"type": "subscribed", "symbol": symbol})
            elif action == "unsubscribe" and symbol:
                manager.unsubscribe(user_id, symbol)
                await websocket.send_json({"type": "unsubscribed", "symbol": symbol})

    except WebSocketDisconnect:
        manager.disconnect(websocket, user_id)
