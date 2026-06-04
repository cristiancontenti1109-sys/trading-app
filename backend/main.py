import asyncio
import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Depends, Query
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.config import settings
from app.database import init_db, get_db, AsyncSessionLocal
from app.models import User, Instrument, WatchlistItem
from app.routers import auth, watchlist, signals, instruments, trades, chat
from app.routers import smc as smc_router
from app.routers import trend_rr as trend_rr_router
from app.services.smc_service import generate_smc_signal, smc_signal_to_dict
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
    # Crypto
    ("BTCUSD", "Bitcoin / USD", "crypto"),
    ("ETHUSD", "Ethereum / USD", "crypto"),
    ("SOLUSD", "Solana / USD", "crypto"),
    ("BNBUSD", "BNB / USD", "crypto"),
    ("XRPUSD", "XRP / USD", "crypto"),
    ("ADAUSD", "Cardano / USD", "crypto"),
    ("DOGEUSD", "Dogecoin / USD", "crypto"),
    ("AVAXUSD", "Avalanche / USD", "crypto"),
    ("LINKUSD", "Chainlink / USD", "crypto"),
    ("DOTUSD", "Polkadot / USD", "crypto"),
    ("MATICUSD", "Polygon / USD", "crypto"),
    ("LTCUSD", "Litecoin / USD", "crypto"),
    ("BCHUSD", "Bitcoin Cash / USD", "crypto"),
    ("XLMUSD", "Stellar / USD", "crypto"),
    ("ATOMUSD", "Cosmos / USD", "crypto"),
    ("NEARUSD", "NEAR Protocol / USD", "crypto"),
    ("UNIUSD", "Uniswap / USD", "crypto"),
    ("AAVEUSD", "Aave / USD", "crypto"),
    ("ALGOUSD", "Algorand / USD", "crypto"),
    ("TRXUSD", "TRON / USD", "crypto"),
    ("ETCUSD", "Ethereum Classic / USD", "crypto"),
    ("SHIBUSD", "Shiba Inu / USD", "crypto"),
    ("FILUSD", "Filecoin / USD", "crypto"),
    # Stocks — US Large Cap
    ("AAPL", "Apple Inc.", "stocks"),
    ("MSFT", "Microsoft Corp.", "stocks"),
    ("GOOGL", "Alphabet Inc.", "stocks"),
    ("AMZN", "Amazon.com Inc.", "stocks"),
    ("TSLA", "Tesla Inc.", "stocks"),
    ("NVDA", "NVIDIA Corp.", "stocks"),
    ("META", "Meta Platforms", "stocks"),
    ("NFLX", "Netflix Inc.", "stocks"),
    ("AMD", "Advanced Micro Devices", "stocks"),
    ("INTC", "Intel Corp.", "stocks"),
    ("ADBE", "Adobe Inc.", "stocks"),
    ("CRM", "Salesforce Inc.", "stocks"),
    ("ORCL", "Oracle Corp.", "stocks"),
    ("CSCO", "Cisco Systems", "stocks"),
    ("QCOM", "Qualcomm Inc.", "stocks"),
    ("IBM", "IBM Corp.", "stocks"),
    ("JPM", "JPMorgan Chase", "stocks"),
    ("BAC", "Bank of America", "stocks"),
    ("GS", "Goldman Sachs", "stocks"),
    ("WFC", "Wells Fargo", "stocks"),
    ("V", "Visa Inc.", "stocks"),
    ("MA", "Mastercard Inc.", "stocks"),
    ("PYPL", "PayPal Holdings", "stocks"),
    ("KO", "Coca-Cola Co.", "stocks"),
    ("PEP", "PepsiCo Inc.", "stocks"),
    ("WMT", "Walmart Inc.", "stocks"),
    ("MCD", "McDonald's Corp.", "stocks"),
    ("SBUX", "Starbucks Corp.", "stocks"),
    ("NKE", "Nike Inc.", "stocks"),
    ("DIS", "Walt Disney Co.", "stocks"),
    ("XOM", "Exxon Mobil Corp.", "stocks"),
    ("BA", "Boeing Co.", "stocks"),
    ("UNH", "UnitedHealth Group", "stocks"),
    ("JNJ", "Johnson & Johnson", "stocks"),
    ("BABA", "Alibaba Group", "stocks"),
    ("SHOP", "Shopify Inc.", "stocks"),
    ("COIN", "Coinbase Global", "stocks"),
    ("PLTR", "Palantir Technologies", "stocks"),
    ("UBER", "Uber Technologies", "stocks"),
    # ETFs
    ("SPY", "SPDR S&P 500 ETF", "stocks"),
    ("QQQ", "Invesco QQQ (Nasdaq-100)", "stocks"),
    ("IWM", "iShares Russell 2000 ETF", "stocks"),
    ("GLD", "SPDR Gold Shares ETF", "stocks"),
    # Forex — Majors
    ("EURUSD", "EUR / USD", "forex"),
    ("GBPUSD", "GBP / USD", "forex"),
    ("USDJPY", "USD / JPY", "forex"),
    ("AUDUSD", "AUD / USD", "forex"),
    ("USDCHF", "USD / CHF", "forex"),
    ("USDCAD", "USD / CAD", "forex"),
    ("NZDUSD", "NZD / USD", "forex"),
    # Forex — Crosses
    ("EURGBP", "EUR / GBP", "forex"),
    ("EURJPY", "EUR / JPY", "forex"),
    ("GBPJPY", "GBP / JPY", "forex"),
    ("EURCHF", "EUR / CHF", "forex"),
    ("EURCAD", "EUR / CAD", "forex"),
    ("GBPCAD", "GBP / CAD", "forex"),
    ("CHFJPY", "CHF / JPY", "forex"),
    ("AUDCAD", "AUD / CAD", "forex"),
    ("AUDJPY", "AUD / JPY", "forex"),
    # Commodities
    ("XAUUSD", "Gold / USD", "commodities"),
    ("XAGUSD", "Silver / USD", "commodities"),
    ("USOIL", "Crude Oil (WTI)", "commodities"),
    ("NATGAS", "Natural Gas", "commodities"),
    ("COPPER", "Copper", "commodities"),
    ("WHEAT", "Wheat", "commodities"),
    ("CORN", "Corn", "commodities"),
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


SMC_SCAN_SYMBOLS = [
    "AAPL", "NVDA", "TSLA", "MSFT", "SPY", "QQQ",
    "BTCUSD", "ETHUSD", "SOLUSD",
    "EURUSD", "GBPUSD",
]


async def run_smc_scan():
    """Scan key symbols for Market Mechanics setups every 15 min and broadcast HOT signals."""
    logger.info("Running Market Mechanics scan...")
    for symbol in SMC_SCAN_SYMBOLS:
        try:
            df4h  = await fetch_ohlcv(symbol, "4h",  limit=200)
            df1h  = await fetch_ohlcv(symbol, "1h",  limit=200)
            df15m = await fetch_ohlcv(symbol, "15m", limit=300)
            if df4h is None or df15m is None:
                continue
            sig = generate_smc_signal(df4h, df15m, symbol, df1h)
            if sig and sig.smc_score >= 4:
                payload = smc_signal_to_dict(sig)
                payload["type"] = "smc_signal"
                await manager.broadcast_signal(symbol, payload)
                logger.info(
                    f"Market Mechanics signal {symbol}: {sig.direction} "
                    f"score={sig.smc_score}/5 conf={sig.confidence}"
                )
        except Exception as e:
            logger.error(f"SMC scan error {symbol}: {e}")


async def run_price_updates():
    """Broadcast latest prices to WebSocket clients."""
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(WatchlistItem.symbol).distinct())
        symbols = [row[0] for row in result.all()]

    for symbol in symbols:
        price = await fetch_current_price(symbol)
        if price:
            await manager.broadcast_price(symbol, price, 0.0)


async def seed_default_user():
    """Create a default admin account on first boot if no users exist."""
    from app.routers.auth import hash_password
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(User).limit(1))
        if result.scalar_one_or_none() is None:
            admin = User(
                email="admin@trading.com",
                hashed_password=hash_password("trading123"),
            )
            db.add(admin)
            await db.commit()
            logger.info("Default user created: admin@trading.com / trading123")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    await seed_instruments()
    await seed_default_user()

    scheduler.add_job(run_signal_pipeline, "interval", minutes=15, id="signal_pipeline")
    scheduler.add_job(run_price_updates, "interval", seconds=30, id="price_updates")
    scheduler.add_job(run_smc_scan, "interval", minutes=15, id="smc_scan")
    # Keep-alive ping — prevents Render free tier from sleeping
    async def _self_ping():
        import aiohttp
        host = os.getenv("RENDER_EXTERNAL_URL", "http://localhost:8080")
        try:
            async with aiohttp.ClientSession() as s:
                await s.get(f"{host}/health", timeout=aiohttp.ClientTimeout(total=10))
            logger.debug("keep-alive ping OK")
        except Exception as e:
            logger.debug(f"keep-alive ping: {e}")

    scheduler.add_job(_self_ping, "interval", minutes=10, id="keep_alive")

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
app.include_router(chat.router)
app.include_router(smc_router.router)
app.include_router(trend_rr_router.router)


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


# ── Serve React frontend ──────────────────────────────────────────────────────
_HERE = os.path.dirname(os.path.abspath(__file__))
_FRONTEND = (
    os.path.join(_HERE, "frontend_dist")           # Render / production build
    if os.path.isdir(os.path.join(_HERE, "frontend_dist"))
    else os.path.join(_HERE, "..", "web", "dist")  # local dev fallback
)
if os.path.isdir(_FRONTEND):
    _assets = os.path.join(_FRONTEND, "assets")
    if os.path.isdir(_assets):
        app.mount("/assets", StaticFiles(directory=_assets), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def serve_frontend(full_path: str):
        return FileResponse(os.path.join(_FRONTEND, "index.html"))

