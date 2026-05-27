import pandas as pd
import numpy as np
from datetime import datetime
from typing import Optional
import logging

from app.services.technical_analysis import compute_indicators

logger = logging.getLogger(__name__)


def generate_signal(df: pd.DataFrame, symbol: str, timeframe: str) -> Optional[dict]:
    """
    Rule-based signal generator. Produces a Signal dict from an OHLCV+indicators DataFrame.
    Confidence is built from a weighted vote of independent indicator groups.
    """
    if df is None or len(df) < 50:
        return None

    df = compute_indicators(df)
    last = df.iloc[-1]
    prev = df.iloc[-2]

    reasons = []
    bull_score = 0.0
    bear_score = 0.0
    weight_total = 0.0

    # --- Trend group (weight 0.30) ---
    trend_w = 0.30
    weight_total += trend_w
    trend_bull = 0.0

    above_ema20 = last["close"] > last["ema20"]
    ema_stack = last["ema20"] > last["ema50"] > last["ema200"]
    ema_bear_stack = last["ema20"] < last["ema50"] < last["ema200"]

    if above_ema20:
        trend_bull += 0.3
    if ema_stack:
        trend_bull += 0.7
        reasons.append("Bullish EMA stack (20 > 50 > 200)")
    elif ema_bear_stack:
        trend_bull -= 0.7
        reasons.append("Bearish EMA stack (20 < 50 < 200)")

    if last.get("lr_slope", 0) > 0.1:
        trend_bull += 0.3
        reasons.append(f"Positive linear regression slope ({last['lr_slope']:.2f}%)")
    elif last.get("lr_slope", 0) < -0.1:
        trend_bull -= 0.3

    bull_score += trend_w * max(0, min(1, (trend_bull + 1) / 2))
    bear_score += trend_w * max(0, min(1, (-trend_bull + 1) / 2))

    # --- Momentum group (weight 0.25) ---
    mom_w = 0.25
    weight_total += mom_w
    mom_bull = 0.0

    rsi = last.get("rsi", 50)
    if rsi > 60 and rsi < 80:
        mom_bull += 0.5
        reasons.append(f"RSI({rsi:.0f}) in bullish zone (60–80)")
    elif rsi > 80:
        mom_bull -= 0.3
        reasons.append(f"RSI({rsi:.0f}) overbought — caution")
    elif rsi < 40 and rsi > 20:
        mom_bull -= 0.5
        reasons.append(f"RSI({rsi:.0f}) in bearish zone (20–40)")
    elif rsi < 20:
        mom_bull += 0.2
        reasons.append(f"RSI({rsi:.0f}) oversold — potential reversal")

    macd_cross_up = last.get("macd", 0) > last.get("macd_signal", 0) and prev.get("macd", 0) <= prev.get("macd_signal", 0)
    macd_cross_down = last.get("macd", 0) < last.get("macd_signal", 0) and prev.get("macd", 0) >= prev.get("macd_signal", 0)
    if macd_cross_up:
        mom_bull += 0.5
        reasons.append("MACD bullish crossover")
    elif macd_cross_down:
        mom_bull -= 0.5
        reasons.append("MACD bearish crossover")
    elif last.get("macd_hist", 0) > 0:
        mom_bull += 0.2
    else:
        mom_bull -= 0.2

    bull_score += mom_w * max(0, min(1, (mom_bull + 1) / 2))
    bear_score += mom_w * max(0, min(1, (-mom_bull + 1) / 2))

    # --- Volatility / BB group (weight 0.20) ---
    bb_w = 0.20
    weight_total += bb_w
    bb_bull = 0.0

    pct_b = last.get("bb_pct_b", 0.5)
    if pct_b > 0.8:
        bb_bull -= 0.3
        reasons.append("Price near upper Bollinger Band — possible overbought")
    elif pct_b < 0.2:
        bb_bull += 0.3
        reasons.append("Price near lower Bollinger Band — possible oversold")
    elif 0.4 < pct_b < 0.6:
        bb_bull += 0.1

    bull_score += bb_w * max(0, min(1, (bb_bull + 1) / 2))
    bear_score += bb_w * max(0, min(1, (-bb_bull + 1) / 2))

    # --- Volume group (weight 0.25) ---
    vol_w = 0.25
    weight_total += vol_w
    vol_bull = 0.0

    zscore = last.get("vol_zscore", 0)
    if zscore > 2.0:
        price_change = (last["close"] - prev["close"]) / (prev["close"] + 1e-9)
        if price_change > 0:
            vol_bull += 0.6
            reasons.append(f"Volume spike +{zscore:.1f}σ on up move")
        else:
            vol_bull -= 0.6
            reasons.append(f"Volume spike +{zscore:.1f}σ on down move")

    bull_score += vol_w * max(0, min(1, (vol_bull + 1) / 2))
    bear_score += vol_w * max(0, min(1, (-vol_bull + 1) / 2))

    # --- Final recommendation ---
    net_bull = bull_score - bear_score
    if net_bull > 0.08:
        recommendation = "BUY"
        confidence = min(0.95, 0.45 + net_bull * 1.5)
    elif net_bull < -0.08:
        recommendation = "SELL"
        confidence = min(0.95, 0.45 + abs(net_bull) * 1.5)
    else:
        recommendation = "HOLD"
        confidence = 0.50

    # --- Price targets ---
    atr = last.get("atr", last["close"] * 0.02)
    close = last["close"]

    if recommendation == "BUY":
        entry_low = close * 0.999
        entry_high = close * 1.002
        target_price = close + 3 * atr
        stop_loss = close - 1.5 * atr
        expected_days_min, expected_days_max = _time_estimate(timeframe, "up")
    elif recommendation == "SELL":
        entry_low = close * 0.998
        entry_high = close * 1.001
        target_price = close - 3 * atr
        stop_loss = close + 1.5 * atr
        expected_days_min, expected_days_max = _time_estimate(timeframe, "down")
    else:
        entry_low = close * 0.998
        entry_high = close * 1.002
        target_price = close
        stop_loss = close - 1.5 * atr
        expected_days_min, expected_days_max = 1, 5

    # HOT detection — cast to Python bool to avoid numpy.bool_ serialization issues
    is_hot = bool(confidence > 0.75 or float(zscore) > 3.0)
    is_hot_confluence = bool(confidence > 0.75 and float(zscore) > 3.0)

    if not reasons:
        reasons.append("Mixed signals — no clear directional bias")

    return {
        "symbol": symbol,
        "timeframe": timeframe,
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "recommendation": recommendation,
        "confidence": round(confidence, 3),
        "entry_zone": {"low": round(entry_low, 6), "high": round(entry_high, 6)},
        "target_price": round(target_price, 6),
        "stop_loss": round(stop_loss, 6),
        "expected_time_to_target": f"P{expected_days_max}D",
        "expected_time_to_target_range": {
            "min": f"P{expected_days_min}D",
            "max": f"P{expected_days_max}D",
        },
        "reasoning": reasons,
        "is_hot": is_hot,
        "is_hot_confluence": is_hot_confluence,
        "indicators": {
            "rsi": round(float(last.get("rsi", 50) or 50), 2),
            "macd": round(float(last.get("macd", 0) or 0), 6),
            "macd_signal": round(float(last.get("macd_signal", 0) or 0), 6),
            "adx": round(float(last.get("adx", 0) or 0), 2),
            "atr": round(float(atr or 0), 6),
            "bb_pct_b": round(float(last.get("bb_pct_b", 0.5) or 0.5), 3),
            "vol_zscore": round(float(last.get("vol_zscore", 0) or 0), 2),
            "ema20": round(float(last.get("ema20", close) or close), 6),
            "ema50": round(float(last.get("ema50", close) or close), 6),
            "ema200": round(float(last.get("ema200", close) or close), 6),
        },
    }


def _time_estimate(timeframe: str, direction: str) -> tuple[int, int]:
    """Rough time-to-target estimate in days based on timeframe."""
    estimates = {
        "1m": (0, 1), "5m": (0, 1), "15m": (0, 2),
        "1h": (1, 3), "4h": (1, 6), "1D": (3, 14), "1W": (14, 60),
    }
    return estimates.get(timeframe, (1, 7))
