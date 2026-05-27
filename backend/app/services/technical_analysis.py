import pandas as pd
import numpy as np
from typing import Optional
import logging

logger = logging.getLogger(__name__)


def compute_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Compute all technical indicators on an OHLCV DataFrame."""
    if df is None or len(df) < 50:
        return df

    df = df.copy()
    close = df["close"]
    high = df["high"]
    low = df["low"]
    volume = df["volume"]

    # --- Trend ---
    df["ema20"] = close.ewm(span=20, adjust=False).mean()
    df["ema50"] = close.ewm(span=50, adjust=False).mean()
    df["ema200"] = close.ewm(span=200, adjust=False).mean()

    # ADX
    df["adx"] = _adx(high, low, close, 14)

    # Linear regression slope (20 bars)
    df["lr_slope"] = _lr_slope(close, 20)

    # --- Momentum ---
    df["rsi"] = _rsi(close, 14)

    # MACD
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    df["macd"] = ema12 - ema26
    df["macd_signal"] = df["macd"].ewm(span=9, adjust=False).mean()
    df["macd_hist"] = df["macd"] - df["macd_signal"]

    # Stochastic
    df["stoch_k"], df["stoch_d"] = _stochastic(high, low, close, 14, 3)

    # Williams %R
    df["willr"] = _williams_r(high, low, close, 14)

    # --- Volatility ---
    df["bb_mid"] = close.rolling(20).mean()
    rolling_std = close.rolling(20).std()
    df["bb_upper"] = df["bb_mid"] + 2 * rolling_std
    df["bb_lower"] = df["bb_mid"] - 2 * rolling_std
    df["bb_width"] = (df["bb_upper"] - df["bb_lower"]) / df["bb_mid"]
    df["bb_pct_b"] = (close - df["bb_lower"]) / (df["bb_upper"] - df["bb_lower"])

    df["atr"] = _atr(high, low, close, 14)

    # --- Volume ---
    df["obv"] = _obv(close, volume)
    df["vwap"] = _vwap(high, low, close, volume)
    df["vol_ma20"] = volume.rolling(20).mean()
    df["vol_zscore"] = (volume - volume.rolling(20).mean()) / (volume.rolling(20).std() + 1e-9)

    # --- Structure ---
    df["swing_high"] = _swing_high(high, 5)
    df["swing_low"] = _swing_low(low, 5)

    return df


def _rsi(close: pd.Series, period: int) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = (-delta.clip(upper=0)).rolling(period).mean()
    rs = gain / (loss + 1e-9)
    return 100 - (100 / (1 + rs))


def _atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int) -> pd.Series:
    prev_close = close.shift(1)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs()
    ], axis=1).max(axis=1)
    return tr.rolling(period).mean()


def _adx(high: pd.Series, low: pd.Series, close: pd.Series, period: int) -> pd.Series:
    atr = _atr(high, low, close, period)
    dm_plus = (high.diff()).clip(lower=0)
    dm_minus = (-low.diff()).clip(lower=0)
    dm_plus = dm_plus.where(dm_plus > dm_minus, 0)
    dm_minus = dm_minus.where(dm_minus > dm_plus, 0)
    di_plus = 100 * dm_plus.rolling(period).mean() / (atr + 1e-9)
    di_minus = 100 * dm_minus.rolling(period).mean() / (atr + 1e-9)
    dx = 100 * (di_plus - di_minus).abs() / (di_plus + di_minus + 1e-9)
    return dx.rolling(period).mean()


def _stochastic(high, low, close, k_period, d_period):
    lowest_low = low.rolling(k_period).min()
    highest_high = high.rolling(k_period).max()
    k = 100 * (close - lowest_low) / (highest_high - lowest_low + 1e-9)
    d = k.rolling(d_period).mean()
    return k, d


def _williams_r(high, low, close, period):
    highest_high = high.rolling(period).max()
    lowest_low = low.rolling(period).min()
    return -100 * (highest_high - close) / (highest_high - lowest_low + 1e-9)


def _obv(close: pd.Series, volume: pd.Series) -> pd.Series:
    direction = close.diff().apply(lambda x: 1 if x > 0 else (-1 if x < 0 else 0))
    return (direction * volume).cumsum()


def _vwap(high, low, close, volume) -> pd.Series:
    typical = (high + low + close) / 3
    return (typical * volume).cumsum() / (volume.cumsum() + 1e-9)


def _lr_slope(close: pd.Series, period: int) -> pd.Series:
    slopes = pd.Series(index=close.index, dtype=float)
    x = np.arange(period)
    for i in range(period - 1, len(close)):
        y = close.iloc[i - period + 1:i + 1].values
        slope = np.polyfit(x, y, 1)[0]
        slopes.iloc[i] = slope / (close.iloc[i] + 1e-9) * 100  # normalize to %
    return slopes


def _swing_high(high: pd.Series, lookback: int) -> pd.Series:
    result = pd.Series(False, index=high.index)
    for i in range(lookback, len(high) - lookback):
        window = high.iloc[i - lookback:i + lookback + 1]
        if high.iloc[i] == window.max():
            result.iloc[i] = True
    return result


def _swing_low(low: pd.Series, lookback: int) -> pd.Series:
    result = pd.Series(False, index=low.index)
    for i in range(lookback, len(low) - lookback):
        window = low.iloc[i - lookback:i + lookback + 1]
        if low.iloc[i] == window.min():
            result.iloc[i] = True
    return result
