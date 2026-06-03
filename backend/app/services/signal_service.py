import pandas as pd
import numpy as np
from datetime import datetime
from typing import Optional
import logging

from app.services.technical_analysis import compute_indicators

logger = logging.getLogger(__name__)


def generate_signal(df: pd.DataFrame, symbol: str, timeframe: str) -> Optional[dict]:
    """
    Elite Confluence Signal Generator.

    Uses a 7-gate binary confirmation system. A BUY or SELL signal is issued only when
    5 or more independent conditions agree on direction. This selectivity is what produces
    high-confidence setups (targeting 80%+ accuracy on issued signals).

    Gates:
      1. EMA alignment (price relative to EMA20/50/200)
      2. RSI quality (momentum in the right range — not extended)
      3. MACD direction (line vs signal + histogram slope)
      4. Trend strength + slope (ADX > 20 + LR slope direction)
      5. Bollinger Band positioning (above/below midline with room)
      6. OBV slope (smart money accumulation/distribution)
      7. Volume-price relationship (volume confirming the move)
    """
    if df is None or len(df) < 50:
        return None

    df = compute_indicators(df)
    last = df.iloc[-1]
    prev = df.iloc[-2]

    close = float(last["close"])
    bull_gates = 0
    bear_gates = 0
    bull_reasons: list[str] = []
    bear_reasons: list[str] = []

    # ── Gate 1: EMA Alignment ──────────────────────────────────────────────
    ema20 = float(last.get("ema20", close))
    ema50 = float(last.get("ema50", close))
    ema200 = float(last.get("ema200", close))
    ema_bull = close > ema20 and ema20 > ema50
    ema_bear = close < ema20 and ema20 < ema50

    if ema_bull:
        bull_gates += 1
        if ema50 > ema200:
            bull_reasons.append("Bullish EMA stack (price > 20 > 50 > 200)")
        else:
            bull_reasons.append("Short-term bullish EMA setup (price > 20 > 50)")
    elif ema_bear:
        bear_gates += 1
        if ema50 < ema200:
            bear_reasons.append("Bearish EMA stack (price < 20 < 50 < 200)")
        else:
            bear_reasons.append("Short-term bearish EMA setup (price < 20 < 50)")

    # ── Gate 2: RSI Quality ────────────────────────────────────────────────
    rsi = float(last.get("rsi", 50))
    # BUY zone: 45-72 (bullish momentum not yet exhausted)
    # SELL zone: 28-55 (bearish momentum not oversold)
    if 45 < rsi < 72:
        bull_gates += 1
        if 55 < rsi < 68:
            bull_reasons.append(f"RSI({rsi:.0f}) in optimal bullish zone (55-68)")
        else:
            bull_reasons.append(f"RSI({rsi:.0f}) in bullish territory")
    elif rsi <= 28:
        bull_gates += 1  # oversold — bounce potential
        bull_reasons.append(f"RSI({rsi:.0f}) deeply oversold — reversal setup")
    elif 28 < rsi < 55:
        bear_gates += 1
        if 32 < rsi < 45:
            bear_reasons.append(f"RSI({rsi:.0f}) in optimal bearish zone (32-45)")
        else:
            bear_reasons.append(f"RSI({rsi:.0f}) in bearish territory")
    elif rsi >= 72:
        bear_gates += 1  # overbought — exhaustion potential
        bear_reasons.append(f"RSI({rsi:.0f}) overbought — upside likely exhausted")

    # ── Gate 3: MACD Direction + Histogram ────────────────────────────────
    macd = float(last.get("macd", 0))
    macd_signal_line = float(last.get("macd_signal", 0))
    macd_hist = float(last.get("macd_hist", 0))
    prev_macd_hist = float(prev.get("macd_hist", 0))
    macd_cross_up = macd > macd_signal_line and float(prev.get("macd", 0)) <= float(prev.get("macd_signal", 0))
    macd_cross_dn = macd < macd_signal_line and float(prev.get("macd", 0)) >= float(prev.get("macd_signal", 0))

    if macd > macd_signal_line:
        bull_gates += 1
        if macd_cross_up:
            bull_reasons.append("MACD fresh bullish crossover")
        elif macd_hist > prev_macd_hist:
            bull_reasons.append("MACD bullish and histogram accelerating")
        else:
            bull_reasons.append("MACD above signal — bullish momentum")
    elif macd < macd_signal_line:
        bear_gates += 1
        if macd_cross_dn:
            bear_reasons.append("MACD fresh bearish crossover")
        elif macd_hist < prev_macd_hist:
            bear_reasons.append("MACD bearish and histogram accelerating downward")
        else:
            bear_reasons.append("MACD below signal — bearish momentum")

    # ── Gate 4: Trend Strength (ADX + LR Slope) ───────────────────────────
    adx = float(last.get("adx", 0))
    lr_slope = float(last.get("lr_slope", 0))
    if adx > 20:
        if lr_slope > 0.05:
            bull_gates += 1
            adx_label = "strong uptrend" if adx > 30 else "developing uptrend"
            bull_reasons.append(f"ADX {adx:.0f} confirms {adx_label} (positive slope {lr_slope:.2f}%)")
        elif lr_slope < -0.05:
            bear_gates += 1
            adx_label = "strong downtrend" if adx > 30 else "developing downtrend"
            bear_reasons.append(f"ADX {adx:.0f} confirms {adx_label} (negative slope {lr_slope:.2f}%)")

    # ── Gate 5: Bollinger Band Positioning ────────────────────────────────
    pct_b = float(last.get("bb_pct_b", 0.5))
    bb_mid = float(last.get("bb_mid", close))

    if close > bb_mid and pct_b < 0.85:
        bull_gates += 1
        bull_reasons.append(f"Price above BB midline ({pct_b:.2f}) — room to upper band")
    elif close < bb_mid and pct_b > 0.15:
        bear_gates += 1
        bear_reasons.append(f"Price below BB midline ({pct_b:.2f}) — room to lower band")

    # ── Gate 6: OBV Slope (Smart Money Accumulation) ──────────────────────
    if "obv" in df.columns:
        obv_tail = df["obv"].tail(10).values.astype(float)
        if len(obv_tail) >= 3:
            obv_slope = float(np.polyfit(range(len(obv_tail)), obv_tail, 1)[0])
            price_range = float(df["close"].tail(10).mean()) + 1e-9
            obv_slope_norm = obv_slope / price_range
            if obv_slope_norm > 0:
                bull_gates += 1
                bull_reasons.append("OBV trending up — smart money accumulation")
            elif obv_slope_norm < 0:
                bear_gates += 1
                bear_reasons.append("OBV trending down — distribution detected")

    # ── Gate 7: Volume + Price Direction ──────────────────────────────────
    vol_zscore = float(last.get("vol_zscore", 0))
    price_change = (close - float(prev["close"])) / (float(prev["close"]) + 1e-9)

    if vol_zscore > 0.3 and price_change > 0:
        bull_gates += 1
        if vol_zscore > 2:
            bull_reasons.append(f"Strong volume spike (+{vol_zscore:.1f}σ) on up move")
        else:
            bull_reasons.append("Volume confirming upside move")
    elif vol_zscore > 0.3 and price_change < 0:
        bear_gates += 1
        if vol_zscore > 2:
            bear_reasons.append(f"Strong volume spike (+{vol_zscore:.1f}σ) on down move")
        else:
            bear_reasons.append("Volume confirming downside move")

    # ── Decision: 5 of 7 gates required ───────────────────────────────────
    MIN_GATES = 5
    MAX_GATES = 7

    if bull_gates >= MIN_GATES and bull_gates > bear_gates:
        recommendation = "BUY"
        # Confidence: 62% at 5/7, +10% per extra gate, +3% if ADX strong
        base_conf = 0.62 + (bull_gates - MIN_GATES) * 0.10
        conf_bonus = 0.03 if adx > 30 else 0.0
        confidence = min(0.93, base_conf + conf_bonus)
        reasons = bull_reasons
    elif bear_gates >= MIN_GATES and bear_gates > bull_gates:
        recommendation = "SELL"
        base_conf = 0.62 + (bear_gates - MIN_GATES) * 0.10
        conf_bonus = 0.03 if adx > 30 else 0.0
        confidence = min(0.93, base_conf + conf_bonus)
        reasons = bear_reasons
    else:
        recommendation = "HOLD"
        confidence = 0.50
        dominant_bull = bull_gates >= bear_gates
        gate_count = max(bull_gates, bear_gates)
        if gate_count == 0:
            reasons = ["No directional signal — indicators are neutral"]
        elif bull_gates == bear_gates:
            reasons = [f"Conflicting signals — {bull_gates} bullish vs {bear_gates} bearish conditions"]
        else:
            dom_dir = "bullish" if dominant_bull else "bearish"
            reasons = [f"Insufficient confluence for a trade — {gate_count}/{MAX_GATES} {dom_dir} conditions met (need {MIN_GATES})"]
            dom_reasons = bull_reasons if dominant_bull else bear_reasons
            reasons += dom_reasons[:2]

    # ── Price Targets (ATR-based 1.5 / 3.0 / 4.5 RR) ─────────────────────
    atr = float(last.get("atr", close * 0.02))
    stop_dist = atr * 1.5

    if recommendation == "BUY":
        entry_low = close * 0.999
        entry_high = close * 1.002
        stop_loss = close - stop_dist
        tp1 = close + 1.5 * stop_dist
        tp2 = close + 3.0 * stop_dist
        tp3 = close + 4.5 * stop_dist
        target_price = tp2
        t_min, t_max = _time_estimate(timeframe, "up")
    elif recommendation == "SELL":
        entry_low = close * 0.998
        entry_high = close * 1.001
        stop_loss = close + stop_dist
        tp1 = close - 1.5 * stop_dist
        tp2 = close - 3.0 * stop_dist
        tp3 = close - 4.5 * stop_dist
        target_price = tp2
        t_min, t_max = _time_estimate(timeframe, "down")
    else:
        entry_low = close * 0.998
        entry_high = close * 1.002
        stop_loss = close - stop_dist
        tp1 = tp2 = tp3 = target_price = float(close)
        t_min, t_max = 1, 5

    is_hot = bool(confidence > 0.75 or float(vol_zscore) > 3.0)
    is_hot_confluence = bool(confidence > 0.75 and float(vol_zscore) > 3.0)

    return {
        "symbol": symbol,
        "timeframe": timeframe,
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "recommendation": recommendation,
        "confidence": round(confidence, 3),
        "entry_zone": {"low": round(entry_low, 6), "high": round(entry_high, 6)},
        "target_price": round(target_price, 6),
        "stop_loss": round(stop_loss, 6),
        "tp1": round(tp1, 6),
        "tp2": round(tp2, 6),
        "tp3": round(tp3, 6),
        "expected_time_to_target": f"P{t_max}D",
        "expected_time_to_target_range": {"min": f"P{t_min}D", "max": f"P{t_max}D"},
        "reasoning": reasons,
        "is_hot": is_hot,
        "is_hot_confluence": is_hot_confluence,
        "indicators": {
            "rsi": round(float(last.get("rsi", 50) or 50), 2),
            "macd": round(float(last.get("macd", 0) or 0), 6),
            "macd_signal": round(float(last.get("macd_signal", 0) or 0), 6),
            "adx": round(float(last.get("adx", 0) or 0), 2),
            "atr": round(float(atr), 6),
            "bb_pct_b": round(float(last.get("bb_pct_b", 0.5) or 0.5), 3),
            "vol_zscore": round(float(last.get("vol_zscore", 0) or 0), 2),
            "ema20": round(float(last.get("ema20", close) or close), 6),
            "ema50": round(float(last.get("ema50", close) or close), 6),
            "ema200": round(float(last.get("ema200", close) or close), 6),
            "bull_gates": bull_gates,
            "bear_gates": bear_gates,
        },
    }


def run_custom_strategy(
    df: pd.DataFrame,
    symbol: str,
    timeframe: str,
    fast_ema: int = 9,
    slow_ema: int = 21,
    rsi_period: int = 14,
    rsi_oversold: float = 30.0,
    rsi_overbought: float = 70.0,
    require_macd: bool = True,
    require_volume: bool = False,
    atr_multiplier: float = 1.5,
) -> Optional[dict]:
    """Run a user-defined custom strategy with configurable parameters."""
    if df is None or len(df) < max(slow_ema + 10, 50):
        return None

    df = df.copy()
    close = df["close"]
    high = df["high"]
    low = df["low"]
    volume = df["volume"]

    # Compute custom EMAs
    df["fast_ema"] = close.ewm(span=fast_ema, adjust=False).mean()
    df["slow_ema"] = close.ewm(span=slow_ema, adjust=False).mean()

    # Custom RSI
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(rsi_period).mean()
    loss = (-delta.clip(upper=0)).rolling(rsi_period).mean()
    rs = gain / (loss + 1e-9)
    df["custom_rsi"] = 100 - (100 / (1 + rs))

    # MACD (always 12/26/9)
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    df["custom_macd"] = ema12 - ema26
    df["custom_macd_signal"] = df["custom_macd"].ewm(span=9, adjust=False).mean()

    # ATR
    prev_c = close.shift(1)
    tr = pd.concat([high - low, (high - prev_c).abs(), (low - prev_c).abs()], axis=1).max(axis=1)
    df["custom_atr"] = tr.rolling(14).mean()

    # Volume z-score
    df["custom_vol_z"] = (volume - volume.rolling(20).mean()) / (volume.rolling(20).std() + 1e-9)

    last = df.iloc[-1]
    prev = df.iloc[-2]

    close_val = float(last["close"])
    fast = float(last["fast_ema"])
    slow_val = float(last["slow_ema"])
    rsi = float(last.get("custom_rsi", 50))
    macd_val = float(last.get("custom_macd", 0))
    macd_sig = float(last.get("custom_macd_signal", 0))
    atr = float(last.get("custom_atr", close_val * 0.02))
    vol_z = float(last.get("custom_vol_z", 0))
    prev_fast = float(prev["fast_ema"])
    prev_slow = float(prev["slow_ema"])

    reasons = []
    bull_score = 0
    bear_score = 0

    # EMA crossover
    ema_cross_up = fast > slow_val and prev_fast <= prev_slow
    ema_cross_dn = fast < slow_val and prev_fast >= prev_slow
    if fast > slow_val:
        bull_score += 2 if ema_cross_up else 1
        reasons.append(f"EMA{fast_ema} above EMA{slow_ema}{'  — fresh crossover' if ema_cross_up else ''}")
    elif fast < slow_val:
        bear_score += 2 if ema_cross_dn else 1
        reasons.append(f"EMA{fast_ema} below EMA{slow_ema}{'  — fresh crossover' if ema_cross_dn else ''}")

    # RSI
    if rsi < rsi_oversold:
        bull_score += 1
        reasons.append(f"RSI({rsi:.0f}) below oversold threshold ({rsi_oversold})")
    elif rsi > rsi_overbought:
        bear_score += 1
        reasons.append(f"RSI({rsi:.0f}) above overbought threshold ({rsi_overbought})")
    elif rsi > 50:
        bull_score += 1
        reasons.append(f"RSI({rsi:.0f}) in bullish zone")
    else:
        bear_score += 1
        reasons.append(f"RSI({rsi:.0f}) in bearish zone")

    # MACD
    if require_macd:
        if macd_val > macd_sig:
            bull_score += 1
            reasons.append("MACD bullish alignment")
        else:
            bear_score += 1
            reasons.append("MACD bearish alignment")

    # Volume
    if require_volume:
        pc = (close_val - float(prev["close"])) / (float(prev["close"]) + 1e-9)
        if vol_z > 0.5 and pc > 0:
            bull_score += 1
            reasons.append(f"Volume confirming up move ({vol_z:.1f}σ)")
        elif vol_z > 0.5 and pc < 0:
            bear_score += 1
            reasons.append(f"Volume confirming down move ({vol_z:.1f}σ)")

    total = bull_score + bear_score or 1
    if bull_score > bear_score:
        recommendation = "BUY"
        confidence = min(0.90, 0.50 + bull_score / total * 0.40)
    elif bear_score > bull_score:
        recommendation = "SELL"
        confidence = min(0.90, 0.50 + bear_score / total * 0.40)
    else:
        recommendation = "HOLD"
        confidence = 0.50

    stop_dist = atr * atr_multiplier
    if recommendation == "BUY":
        entry_low, entry_high = close_val * 0.999, close_val * 1.002
        stop_loss = close_val - stop_dist
        tp1 = close_val + 1.5 * stop_dist
        tp2 = close_val + 3.0 * stop_dist
        tp3 = close_val + 4.5 * stop_dist
    elif recommendation == "SELL":
        entry_low, entry_high = close_val * 0.998, close_val * 1.001
        stop_loss = close_val + stop_dist
        tp1 = close_val - 1.5 * stop_dist
        tp2 = close_val - 3.0 * stop_dist
        tp3 = close_val - 4.5 * stop_dist
    else:
        entry_low, entry_high = close_val * 0.998, close_val * 1.002
        stop_loss = close_val - stop_dist
        tp1 = tp2 = tp3 = float(close_val)

    return {
        "strategy": "custom",
        "symbol": symbol,
        "timeframe": timeframe,
        "params": {
            "fast_ema": fast_ema, "slow_ema": slow_ema,
            "rsi_period": rsi_period, "rsi_oversold": rsi_oversold, "rsi_overbought": rsi_overbought,
            "require_macd": require_macd, "require_volume": require_volume, "atr_multiplier": atr_multiplier,
        },
        "recommendation": recommendation,
        "confidence": round(confidence, 3),
        "entry_zone": {"low": round(entry_low, 6), "high": round(entry_high, 6)},
        "stop_loss": round(stop_loss, 6),
        "target_price": round(tp2, 6),
        "tp1": round(tp1, 6),
        "tp2": round(tp2, 6),
        "tp3": round(tp3, 6),
        "reasoning": reasons,
    }


def _time_estimate(timeframe: str, direction: str) -> tuple[int, int]:
    estimates = {
        "1m": (0, 1), "5m": (0, 1), "15m": (0, 2),
        "1h": (1, 3), "4h": (1, 6), "1D": (3, 14), "1W": (14, 60),
    }
    return estimates.get(timeframe, (1, 7))
