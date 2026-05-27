import asyncio
import aiohttp
import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta
from typing import Optional
import logging

logger = logging.getLogger(__name__)

ASSET_CLASS_MAP = {
    "crypto": ["BTC-USD", "ETH-USD", "SOL-USD", "BNB-USD", "XRP-USD", "ADA-USD", "AVAX-USD", "DOGE-USD"],
    "stocks": ["AAPL", "MSFT", "GOOGL", "AMZN", "TSLA", "NVDA", "META", "NFLX", "SPY", "QQQ"],
    "forex": ["EURUSD=X", "GBPUSD=X", "USDJPY=X", "AUDUSD=X", "USDCAD=X", "USDCHF=X"],
    "commodities": ["GC=F", "SI=F", "CL=F", "NG=F", "ZW=F", "ZC=F"],
}

INTERVAL_MAP = {
    "1m": "1m", "5m": "5m", "15m": "15m",
    "1h": "1h", "4h": "1h",  # yfinance has no 4h; we resample
    "1D": "1d", "1W": "1wk",
}

PERIOD_MAP = {
    "1m": "7d", "5m": "60d", "15m": "60d",
    "1h": "730d", "4h": "730d", "1D": "730d", "1W": "730d",
}


def symbol_to_yf(symbol: str) -> str:
    """Normalize internal symbol to yfinance ticker."""
    mapping = {
        "BTCUSD": "BTC-USD", "ETHUSD": "ETH-USD", "SOLUSD": "SOL-USD",
        "EURUSD": "EURUSD=X", "GBPUSD": "GBPUSD=X", "USDJPY": "USDJPY=X",
        "XAUUSD": "GC=F", "XAGUSD": "SI=F", "USOIL": "CL=F",
    }
    return mapping.get(symbol, symbol)


async def fetch_ohlcv(symbol: str, timeframe: str = "1D", limit: int = 500) -> Optional[pd.DataFrame]:
    """Fetch OHLCV data. Returns DataFrame with columns: open, high, low, close, volume."""
    yf_symbol = symbol_to_yf(symbol)
    interval = INTERVAL_MAP.get(timeframe, "1d")
    period = PERIOD_MAP.get(timeframe, "730d")

    try:
        loop = asyncio.get_event_loop()
        df = await loop.run_in_executor(None, lambda: yf.download(
            yf_symbol, period=period, interval=interval,
            auto_adjust=True, progress=False
        ))

        if df is None or df.empty:
            return None

        # Flatten MultiIndex columns produced by newer yfinance versions
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = [c[0].lower() for c in df.columns]
        else:
            df.columns = [c.lower() for c in df.columns]

        # Rename 'adj close' -> 'close' if present
        if "adj close" in df.columns and "close" not in df.columns:
            df = df.rename(columns={"adj close": "close"})

        df = df[["open", "high", "low", "close", "volume"]].dropna()

        # Resample 1h → 4h
        if timeframe == "4h":
            df = df.resample("4h").agg({
                "open": "first", "high": "max",
                "low": "min", "close": "last", "volume": "sum"
            }).dropna()

        return df.tail(limit)

    except Exception as e:
        logger.error(f"Error fetching {symbol} ({timeframe}): {e}")
        return None


async def fetch_current_price(symbol: str) -> Optional[float]:
    """Get the latest price for a symbol."""
    yf_symbol = symbol_to_yf(symbol)
    try:
        loop = asyncio.get_event_loop()
        ticker = await loop.run_in_executor(None, lambda: yf.Ticker(yf_symbol))
        info = await loop.run_in_executor(None, lambda: ticker.fast_info)
        return float(info.last_price)
    except Exception as e:
        logger.error(f"Error fetching price for {symbol}: {e}")
        return None


async def fetch_news(symbol: str) -> list[dict]:
    """Fetch recent news articles for a symbol via yfinance."""
    yf_symbol = symbol_to_yf(symbol)
    try:
        loop = asyncio.get_event_loop()
        ticker = await loop.run_in_executor(None, lambda: yf.Ticker(yf_symbol))
        raw = await loop.run_in_executor(None, lambda: ticker.news)

        news = []
        for item in (raw or [])[:10]:
            # yfinance >= 0.2.50 nests data under 'content'; older versions use flat keys
            content = item.get("content") if isinstance(item.get("content"), dict) else item
            title = content.get("title") or item.get("title", "")
            if not title:
                continue

            publisher = (
                (content.get("provider") or {}).get("displayName")
                or item.get("publisher", "")
            )
            # URL: newer format uses canonicalUrl.url, older uses link
            url_obj = content.get("canonicalUrl")
            url = (url_obj.get("url") if isinstance(url_obj, dict) else None) or item.get("link", "")

            # Publish time: try ISO string first (new format), then unix int (old format)
            pub_date = content.get("pubDate") or ""
            if pub_date:
                try:
                    from datetime import timezone
                    dt = datetime.fromisoformat(pub_date.replace("Z", "+00:00"))
                    pub_time = int(dt.timestamp())
                except Exception:
                    pub_time = 0
            else:
                pub_time = int(item.get("providerPublishTime") or 0)

            news.append({
                "title": title,
                "publisher": publisher,
                "url": url,
                "time": pub_time,
            })

        return news
    except Exception as e:
        logger.error(f"Error fetching news for {symbol}: {e}")
        return []


async def search_instruments(query: str) -> list[dict]:
    """Search for instruments by keyword."""
    results = []
    query_lower = query.lower()

    catalog = [
        {"symbol": "BTCUSD", "name": "Bitcoin / USD", "asset_class": "crypto"},
        {"symbol": "ETHUSD", "name": "Ethereum / USD", "asset_class": "crypto"},
        {"symbol": "SOLUSD", "name": "Solana / USD", "asset_class": "crypto"},
        {"symbol": "BNBUSD", "name": "BNB / USD", "asset_class": "crypto"},
        {"symbol": "XRPUSD", "name": "XRP / USD", "asset_class": "crypto"},
        {"symbol": "ADAUSD", "name": "Cardano / USD", "asset_class": "crypto"},
        {"symbol": "DOGEDUSD", "name": "Dogecoin / USD", "asset_class": "crypto"},
        {"symbol": "AAPL", "name": "Apple Inc.", "asset_class": "stocks"},
        {"symbol": "MSFT", "name": "Microsoft Corp.", "asset_class": "stocks"},
        {"symbol": "GOOGL", "name": "Alphabet Inc.", "asset_class": "stocks"},
        {"symbol": "AMZN", "name": "Amazon.com Inc.", "asset_class": "stocks"},
        {"symbol": "TSLA", "name": "Tesla Inc.", "asset_class": "stocks"},
        {"symbol": "NVDA", "name": "NVIDIA Corp.", "asset_class": "stocks"},
        {"symbol": "META", "name": "Meta Platforms", "asset_class": "stocks"},
        {"symbol": "NFLX", "name": "Netflix Inc.", "asset_class": "stocks"},
        {"symbol": "SPY", "name": "SPDR S&P 500 ETF", "asset_class": "stocks"},
        {"symbol": "EURUSD", "name": "EUR / USD", "asset_class": "forex"},
        {"symbol": "GBPUSD", "name": "GBP / USD", "asset_class": "forex"},
        {"symbol": "USDJPY", "name": "USD / JPY", "asset_class": "forex"},
        {"symbol": "AUDUSD", "name": "AUD / USD", "asset_class": "forex"},
        {"symbol": "XAUUSD", "name": "Gold / USD", "asset_class": "commodities"},
        {"symbol": "XAGUSD", "name": "Silver / USD", "asset_class": "commodities"},
        {"symbol": "USOIL", "name": "Crude Oil (WTI)", "asset_class": "commodities"},
    ]

    for item in catalog:
        if query_lower in item["symbol"].lower() or query_lower in item["name"].lower():
            results.append(item)

    return results[:20]
