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
        # Crypto
        "BTCUSD": "BTC-USD", "ETHUSD": "ETH-USD", "SOLUSD": "SOL-USD",
        "BNBUSD": "BNB-USD", "XRPUSD": "XRP-USD", "ADAUSD": "ADA-USD",
        "DOGEUSD": "DOGE-USD", "AVAXUSD": "AVAX-USD", "LINKUSD": "LINK-USD",
        "DOTUSD": "DOT-USD", "MATICUSD": "MATIC-USD", "LTCUSD": "LTC-USD",
        "BCHUSD": "BCH-USD", "XLMUSD": "XLM-USD", "ATOMUSD": "ATOM-USD",
        "NEARUSD": "NEAR-USD", "UNIUSD": "UNI-USD", "AAVEUSD": "AAVE-USD",
        "ALGOUSD": "ALGO-USD", "TRXUSD": "TRX-USD", "ETCUSD": "ETC-USD",
        "SHIBUSD": "SHIB-USD", "FILUSD": "FIL-USD",
        # Forex — Majors
        "EURUSD": "EURUSD=X", "GBPUSD": "GBPUSD=X", "USDJPY": "USDJPY=X",
        "AUDUSD": "AUDUSD=X", "USDCHF": "USDCHF=X", "USDCAD": "USDCAD=X",
        "NZDUSD": "NZDUSD=X",
        # Forex — Crosses
        "EURGBP": "EURGBP=X", "EURJPY": "EURJPY=X", "GBPJPY": "GBPJPY=X",
        "EURCHF": "EURCHF=X", "EURCAD": "EURCAD=X", "GBPCAD": "GBPCAD=X",
        "CHFJPY": "CHFJPY=X", "AUDCAD": "AUDCAD=X", "AUDJPY": "AUDJPY=X",
        # Commodities
        "XAUUSD": "GC=F", "XAGUSD": "SI=F", "USOIL": "CL=F",
        "NATGAS": "NG=F", "COPPER": "HG=F", "WHEAT": "ZW=F", "CORN": "ZC=F",
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


async def fetch_prices_batch(symbols: list[str]) -> dict[str, float]:
    """Fetch latest prices for multiple symbols. Tries batch download, falls back per-symbol."""
    if not symbols:
        return {}
    import math
    yf_symbols = [symbol_to_yf(s) for s in symbols]
    symbol_map = dict(zip(yf_symbols, symbols))
    prices: dict[str, float] = {}

    try:
        loop = asyncio.get_event_loop()
        df = await loop.run_in_executor(None, lambda: yf.download(
            yf_symbols, period="1d", interval="1m",
            auto_adjust=True, progress=False, threads=False
        ))
        if df is not None and not df.empty:
            # Normalize column names
            if isinstance(df.columns, pd.MultiIndex):
                close_df = df["Close"] if "Close" in df.columns.get_level_values(0) else None
            else:
                cols = [c.lower() for c in df.columns]
                df.columns = cols
                close_df = df[["close"]] if "close" in df.columns else None

            if close_df is not None and not close_df.empty:
                last_row = close_df.iloc[-1]
                if hasattr(last_row, "items"):
                    for yf_sym, price in last_row.items():
                        internal = symbol_map.get(yf_sym)
                        if internal and price is not None:
                            try:
                                v = float(price)
                                if not math.isnan(v) and not math.isinf(v):
                                    prices[internal] = v
                            except (TypeError, ValueError):
                                pass
                else:
                    # Single symbol — last_row is a scalar
                    yf_sym = yf_symbols[0]
                    internal = symbol_map.get(yf_sym)
                    if internal:
                        try:
                            v = float(last_row)
                            if not math.isnan(v):
                                prices[internal] = v
                        except (TypeError, ValueError):
                            pass
    except Exception as e:
        logger.warning(f"Batch price download failed: {e}")

    # Fall back to fast_info for any symbols not retrieved by batch
    missing = [s for s in symbols if s not in prices]
    if missing:
        async def _fetch_one(sym: str):
            p = await fetch_current_price(sym)
            if p is not None:
                prices[sym] = p
        await asyncio.gather(*[_fetch_one(s) for s in missing], return_exceptions=True)

    return prices


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
        # Crypto
        {"symbol": "BTCUSD", "name": "Bitcoin / USD", "asset_class": "crypto"},
        {"symbol": "ETHUSD", "name": "Ethereum / USD", "asset_class": "crypto"},
        {"symbol": "SOLUSD", "name": "Solana / USD", "asset_class": "crypto"},
        {"symbol": "BNBUSD", "name": "BNB / USD", "asset_class": "crypto"},
        {"symbol": "XRPUSD", "name": "XRP / USD", "asset_class": "crypto"},
        {"symbol": "ADAUSD", "name": "Cardano / USD", "asset_class": "crypto"},
        {"symbol": "DOGEUSD", "name": "Dogecoin / USD", "asset_class": "crypto"},
        {"symbol": "AVAXUSD", "name": "Avalanche / USD", "asset_class": "crypto"},
        {"symbol": "LINKUSD", "name": "Chainlink / USD", "asset_class": "crypto"},
        {"symbol": "DOTUSD", "name": "Polkadot / USD", "asset_class": "crypto"},
        {"symbol": "MATICUSD", "name": "Polygon / USD", "asset_class": "crypto"},
        {"symbol": "LTCUSD", "name": "Litecoin / USD", "asset_class": "crypto"},
        {"symbol": "BCHUSD", "name": "Bitcoin Cash / USD", "asset_class": "crypto"},
        {"symbol": "XLMUSD", "name": "Stellar / USD", "asset_class": "crypto"},
        {"symbol": "ATOMUSD", "name": "Cosmos / USD", "asset_class": "crypto"},
        {"symbol": "NEARUSD", "name": "NEAR Protocol / USD", "asset_class": "crypto"},
        {"symbol": "UNIUSD", "name": "Uniswap / USD", "asset_class": "crypto"},
        {"symbol": "AAVEUSD", "name": "Aave / USD", "asset_class": "crypto"},
        {"symbol": "ALGOUSD", "name": "Algorand / USD", "asset_class": "crypto"},
        {"symbol": "TRXUSD", "name": "TRON / USD", "asset_class": "crypto"},
        {"symbol": "ETCUSD", "name": "Ethereum Classic / USD", "asset_class": "crypto"},
        {"symbol": "SHIBUSD", "name": "Shiba Inu / USD", "asset_class": "crypto"},
        {"symbol": "FILUSD", "name": "Filecoin / USD", "asset_class": "crypto"},
        # Stocks — US Large Cap
        {"symbol": "AAPL", "name": "Apple Inc.", "asset_class": "stocks"},
        {"symbol": "MSFT", "name": "Microsoft Corp.", "asset_class": "stocks"},
        {"symbol": "GOOGL", "name": "Alphabet Inc.", "asset_class": "stocks"},
        {"symbol": "AMZN", "name": "Amazon.com Inc.", "asset_class": "stocks"},
        {"symbol": "TSLA", "name": "Tesla Inc.", "asset_class": "stocks"},
        {"symbol": "NVDA", "name": "NVIDIA Corp.", "asset_class": "stocks"},
        {"symbol": "META", "name": "Meta Platforms", "asset_class": "stocks"},
        {"symbol": "NFLX", "name": "Netflix Inc.", "asset_class": "stocks"},
        {"symbol": "AMD", "name": "Advanced Micro Devices", "asset_class": "stocks"},
        {"symbol": "INTC", "name": "Intel Corp.", "asset_class": "stocks"},
        {"symbol": "ADBE", "name": "Adobe Inc.", "asset_class": "stocks"},
        {"symbol": "CRM", "name": "Salesforce Inc.", "asset_class": "stocks"},
        {"symbol": "ORCL", "name": "Oracle Corp.", "asset_class": "stocks"},
        {"symbol": "CSCO", "name": "Cisco Systems", "asset_class": "stocks"},
        {"symbol": "QCOM", "name": "Qualcomm Inc.", "asset_class": "stocks"},
        {"symbol": "IBM", "name": "IBM Corp.", "asset_class": "stocks"},
        {"symbol": "JPM", "name": "JPMorgan Chase", "asset_class": "stocks"},
        {"symbol": "BAC", "name": "Bank of America", "asset_class": "stocks"},
        {"symbol": "GS", "name": "Goldman Sachs", "asset_class": "stocks"},
        {"symbol": "WFC", "name": "Wells Fargo", "asset_class": "stocks"},
        {"symbol": "V", "name": "Visa Inc.", "asset_class": "stocks"},
        {"symbol": "MA", "name": "Mastercard Inc.", "asset_class": "stocks"},
        {"symbol": "PYPL", "name": "PayPal Holdings", "asset_class": "stocks"},
        {"symbol": "KO", "name": "Coca-Cola Co.", "asset_class": "stocks"},
        {"symbol": "PEP", "name": "PepsiCo Inc.", "asset_class": "stocks"},
        {"symbol": "WMT", "name": "Walmart Inc.", "asset_class": "stocks"},
        {"symbol": "MCD", "name": "McDonald's Corp.", "asset_class": "stocks"},
        {"symbol": "SBUX", "name": "Starbucks Corp.", "asset_class": "stocks"},
        {"symbol": "NKE", "name": "Nike Inc.", "asset_class": "stocks"},
        {"symbol": "DIS", "name": "Walt Disney Co.", "asset_class": "stocks"},
        {"symbol": "XOM", "name": "Exxon Mobil Corp.", "asset_class": "stocks"},
        {"symbol": "BA", "name": "Boeing Co.", "asset_class": "stocks"},
        {"symbol": "UNH", "name": "UnitedHealth Group", "asset_class": "stocks"},
        {"symbol": "JNJ", "name": "Johnson & Johnson", "asset_class": "stocks"},
        {"symbol": "BABA", "name": "Alibaba Group", "asset_class": "stocks"},
        {"symbol": "SHOP", "name": "Shopify Inc.", "asset_class": "stocks"},
        {"symbol": "COIN", "name": "Coinbase Global", "asset_class": "stocks"},
        {"symbol": "PLTR", "name": "Palantir Technologies", "asset_class": "stocks"},
        {"symbol": "UBER", "name": "Uber Technologies", "asset_class": "stocks"},
        # ETFs
        {"symbol": "SPY", "name": "SPDR S&P 500 ETF", "asset_class": "stocks"},
        {"symbol": "QQQ", "name": "Invesco QQQ (Nasdaq-100)", "asset_class": "stocks"},
        {"symbol": "IWM", "name": "iShares Russell 2000 ETF", "asset_class": "stocks"},
        {"symbol": "GLD", "name": "SPDR Gold Shares ETF", "asset_class": "stocks"},
        # Forex — Majors
        {"symbol": "EURUSD", "name": "EUR / USD", "asset_class": "forex"},
        {"symbol": "GBPUSD", "name": "GBP / USD", "asset_class": "forex"},
        {"symbol": "USDJPY", "name": "USD / JPY", "asset_class": "forex"},
        {"symbol": "AUDUSD", "name": "AUD / USD", "asset_class": "forex"},
        {"symbol": "USDCHF", "name": "USD / CHF", "asset_class": "forex"},
        {"symbol": "USDCAD", "name": "USD / CAD", "asset_class": "forex"},
        {"symbol": "NZDUSD", "name": "NZD / USD", "asset_class": "forex"},
        # Forex — Crosses
        {"symbol": "EURGBP", "name": "EUR / GBP", "asset_class": "forex"},
        {"symbol": "EURJPY", "name": "EUR / JPY", "asset_class": "forex"},
        {"symbol": "GBPJPY", "name": "GBP / JPY", "asset_class": "forex"},
        {"symbol": "EURCHF", "name": "EUR / CHF", "asset_class": "forex"},
        {"symbol": "EURCAD", "name": "EUR / CAD", "asset_class": "forex"},
        {"symbol": "GBPCAD", "name": "GBP / CAD", "asset_class": "forex"},
        {"symbol": "CHFJPY", "name": "CHF / JPY", "asset_class": "forex"},
        {"symbol": "AUDCAD", "name": "AUD / CAD", "asset_class": "forex"},
        {"symbol": "AUDJPY", "name": "AUD / JPY", "asset_class": "forex"},
        # Commodities
        {"symbol": "XAUUSD", "name": "Gold / USD", "asset_class": "commodities"},
        {"symbol": "XAGUSD", "name": "Silver / USD", "asset_class": "commodities"},
        {"symbol": "USOIL", "name": "Crude Oil (WTI)", "asset_class": "commodities"},
        {"symbol": "NATGAS", "name": "Natural Gas", "asset_class": "commodities"},
        {"symbol": "COPPER", "name": "Copper", "asset_class": "commodities"},
        {"symbol": "WHEAT", "name": "Wheat", "asset_class": "commodities"},
        {"symbol": "CORN", "name": "Corn", "asset_class": "commodities"},
    ]

    for item in catalog:
        if query_lower in item["symbol"].lower() or query_lower in item["name"].lower():
            results.append(item)

    return results[:50]
