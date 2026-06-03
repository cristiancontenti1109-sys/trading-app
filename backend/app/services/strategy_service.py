"""
Five trading strategy analyzers operating on OHLCV + indicator DataFrames.
Each returns a dict with a consistent shape:
  strategy, symbol, timeframe, recommendation, confidence,
  entry_zone, target_price, stop_loss, reasoning, <strategy-specific keys>
"""
import numpy as np
import pandas as pd
from typing import Optional
import logging

from app.services.technical_analysis import compute_indicators

logger = logging.getLogger(__name__)

STRATEGIES = [
    "fibonacci", "smart_money", "elliott_wave", "warren_buffett", "jpmorgan",
    "macd_crossover", "rsi_divergence", "bb_squeeze",
    "support_resistance", "ema_crossover", "ichimoku", "stochastic", "vwap",
]


def _targets(close: float, atr: float, rec: str) -> dict:
    """Return consistent stop + 1.5/3.0/4.5 RR targets for any strategy."""
    sd = atr * 1.5
    if rec == "BUY":
        return dict(stop_loss=round(close - sd, 6),
                    tp1=round(close + 1.5 * sd, 6),
                    tp2=round(close + 3.0 * sd, 6),
                    tp3=round(close + 4.5 * sd, 6),
                    target_price=round(close + 3.0 * sd, 6))
    elif rec == "SELL":
        return dict(stop_loss=round(close + sd, 6),
                    tp1=round(close - 1.5 * sd, 6),
                    tp2=round(close - 3.0 * sd, 6),
                    tp3=round(close - 4.5 * sd, 6),
                    target_price=round(close - 3.0 * sd, 6))
    return dict(stop_loss=round(close - sd, 6),
                tp1=round(close, 6), tp2=round(close, 6), tp3=round(close, 6),
                target_price=round(close, 6))


def run_strategy(df: pd.DataFrame, symbol: str, timeframe: str, strategy: str) -> Optional[dict]:
    if df is None or len(df) < 50:
        return None
    df = compute_indicators(df)
    try:
        fn = {
            "fibonacci":          fibonacci_strategy,
            "smart_money":        smart_money_strategy,
            "elliott_wave":       elliott_wave_strategy,
            "warren_buffett":     warren_buffett_strategy,
            "jpmorgan":           jpmorgan_strategy,
            "macd_crossover":     macd_crossover_strategy,
            "rsi_divergence":     rsi_divergence_strategy,
            "bb_squeeze":         bb_squeeze_strategy,
            "support_resistance": support_resistance_strategy,
            "ema_crossover":      ema_crossover_strategy,
            "ichimoku":           ichimoku_strategy,
            "stochastic":         stochastic_strategy,
            "vwap":               vwap_strategy,
        }[strategy]
        return fn(df, symbol, timeframe)
    except Exception as e:
        logger.error(f"Strategy {strategy} error for {symbol}: {e}")
        return None


# ─────────────────────────────────────────────────────────────────
# 1. FIBONACCI
# ─────────────────────────────────────────────────────────────────
def fibonacci_strategy(df: pd.DataFrame, symbol: str, timeframe: str) -> dict:
    last = df.iloc[-1]
    close = float(last["close"])
    atr = float(last.get("atr", close * 0.02) or close * 0.02)

    # Find significant swing high/low in last 100 bars
    lookback = min(100, len(df) - 1)
    window = df.iloc[-lookback:]
    sh_idx = int(window["high"].idxmax().value if hasattr(window["high"].idxmax(), "value") else 0)
    sl_idx = int(window["low"].idxmin().value if hasattr(window["low"].idxmin(), "value") else 0)

    swing_high = float(window["high"].max())
    swing_low = float(window["low"].min())
    sh_pos = window.index.get_loc(window["high"].idxmax())
    sl_pos = window.index.get_loc(window["low"].idxmin())

    # Trend direction: whichever pivot came LAST defines where we are in the cycle
    range_ = swing_high - swing_low
    if range_ == 0:
        range_ = close * 0.01

    if sh_pos > sl_pos:
        # Most recent move was UP → expect retracement downward
        trend = "up"
        levels = {
            "0.0%":   swing_high,
            "23.6%":  swing_high - 0.236 * range_,
            "38.2%":  swing_high - 0.382 * range_,
            "50.0%":  swing_high - 0.500 * range_,
            "61.8%":  swing_high - 0.618 * range_,
            "78.6%":  swing_high - 0.786 * range_,
            "100.0%": swing_low,
        }
        extensions = {
            "127.2%": swing_high + 0.272 * range_,
            "161.8%": swing_high + 0.618 * range_,
            "261.8%": swing_high + 1.618 * range_,
        }
        base_ref = swing_low  # where trend started from
    else:
        # Most recent move was DOWN → expect retracement upward
        trend = "down"
        levels = {
            "0.0%":   swing_low,
            "23.6%":  swing_low + 0.236 * range_,
            "38.2%":  swing_low + 0.382 * range_,
            "50.0%":  swing_low + 0.500 * range_,
            "61.8%":  swing_low + 0.618 * range_,
            "78.6%":  swing_low + 0.786 * range_,
            "100.0%": swing_high,
        }
        extensions = {
            "61.8% ext": swing_low - 0.618 * range_,
            "100% ext":  swing_low - range_,
            "161.8% ext": swing_low - 1.618 * range_,
        }
        base_ref = swing_high

    # Nearest level to current price
    closest_name = min(levels, key=lambda k: abs(levels[k] - close))
    closest_price = levels[closest_name]
    pct_away = abs(close - closest_price) / (close + 1e-9)

    reasoning = []
    recommendation = "HOLD"
    confidence = 0.50

    at_level = pct_away < 0.012  # within 1.2%
    key_levels = {"38.2%", "50.0%", "61.8%"}

    if at_level and closest_name in key_levels:
        if trend == "down":
            # Price at Fibonacci support after downtrend → BUY bounce
            recommendation = "BUY"
            confidence = 0.68 if closest_name == "61.8%" else 0.63
            reasoning.append(f"Price at Fibonacci {closest_name} retracement support ({closest_price:.6g})")
            reasoning.append(f"Downtrend from {swing_high:.6g} to {swing_low:.6g} — classic bounce zone")
        else:
            # Price at Fibonacci resistance after uptrend → SELL
            recommendation = "SELL"
            confidence = 0.65 if closest_name == "61.8%" else 0.60
            reasoning.append(f"Price at Fibonacci {closest_name} retracement resistance ({closest_price:.6g})")
            reasoning.append(f"Uptrend from {swing_low:.6g} to {swing_high:.6g} — distribution zone")
    elif pct_away < 0.025:
        reasoning.append(f"Approaching Fibonacci {closest_name} ({closest_price:.6g}) — watch for reaction")
    else:
        reasoning.append(f"Price is {pct_away*100:.1f}% from nearest Fib level ({closest_name} @ {closest_price:.6g})")
        reasoning.append("No active Fibonacci confluence — wait for price to reach key level")

    # EMA confluence
    ema20 = float(last.get("ema20", close) or close)
    ema50 = float(last.get("ema50", close) or close)
    if close > ema20 > ema50:
        reasoning.append("EMA 20 > 50 confirms bullish bias — Fibonacci support favoured")
        if recommendation == "BUY":
            confidence += 0.05
    elif close < ema20 < ema50:
        reasoning.append("EMA 20 < 50 confirms bearish bias — Fibonacci resistance favoured")
        if recommendation == "SELL":
            confidence += 0.05

    t = _targets(close, atr, recommendation)
    return {
        "strategy": "fibonacci",
        "symbol": symbol, "timeframe": timeframe,
        "recommendation": recommendation,
        "confidence": round(min(confidence, 0.90), 3),
        "entry_zone": {"low": round(close * 0.999, 6), "high": round(close * 1.001, 6)},
        **t,
        "reasoning": reasoning,
        "fib_levels": {k: round(float(v), 6) for k, v in levels.items()},
        "fib_extensions": {k: round(float(v), 6) for k, v in extensions.items()},
        "swing_high": round(swing_high, 6),
        "swing_low": round(swing_low, 6),
        "trend": trend,
        "closest_level": closest_name,
    }


# ─────────────────────────────────────────────────────────────────
# 2. SMART MONEY CONCEPT (SMC)
# ─────────────────────────────────────────────────────────────────
def smart_money_strategy(df: pd.DataFrame, symbol: str, timeframe: str) -> dict:
    last = df.iloc[-1]
    prev = df.iloc[-2]
    close = float(last["close"])
    atr = float(last.get("atr", close * 0.02) or close * 0.02)

    reasoning = []
    signals = []  # (direction, weight, message)
    zones = []    # for UI display: {"type", "high", "low", "label"}

    # ── Market Structure (Break of Structure / ChoCH) ──────────────
    hh = all(float(df.iloc[-i]["high"]) >= float(df.iloc[-(i+1)]["high"]) for i in range(1, 4))
    hl = all(float(df.iloc[-i]["low"]) >= float(df.iloc[-(i+1)]["low"]) for i in range(1, 4))
    lh = all(float(df.iloc[-i]["high"]) <= float(df.iloc[-(i+1)]["high"]) for i in range(1, 4))
    ll = all(float(df.iloc[-i]["low"]) <= float(df.iloc[-(i+1)]["low"]) for i in range(1, 4))

    if hh and hl:
        signals.append(("BUY", 0.30, "Bullish market structure: Higher Highs + Higher Lows (BOS confirmed)"))
    elif lh and ll:
        signals.append(("SELL", 0.30, "Bearish market structure: Lower Highs + Lower Lows (BOS confirmed)"))

    # ── Order Blocks ───────────────────────────────────────────────
    # Bullish OB: last bearish candle before a strong bullish impulse
    for i in range(2, min(20, len(df))):
        c = df.iloc[-i]
        c_next = df.iloc[-(i-1)]
        c_open, c_close = float(c["open"]), float(c["close"])
        cn_close = float(c_next["close"])
        if c_close < c_open:  # bearish candle
            impulse = (cn_close - c_close) / (c_close + 1e-9)
            if impulse > 0.003:  # strong bullish move after
                ob_high, ob_low = float(c["high"]), float(c["low"])
                if ob_low <= close <= ob_high:
                    msg = f"Retesting Bullish Order Block [{ob_low:.6g} – {ob_high:.6g}]"
                    signals.append(("BUY", 0.40, msg))
                    zones.append({"type": "bull_ob", "high": ob_high, "low": ob_low, "label": "Bull OB"})
                    break

    # Bearish OB: last bullish candle before a strong bearish impulse
    for i in range(2, min(20, len(df))):
        c = df.iloc[-i]
        c_next = df.iloc[-(i-1)]
        c_open, c_close = float(c["open"]), float(c["close"])
        cn_close = float(c_next["close"])
        if c_close > c_open:  # bullish candle
            impulse = (c_close - cn_close) / (c_close + 1e-9)
            if impulse > 0.003:
                ob_high, ob_low = float(c["high"]), float(c["low"])
                if ob_low <= close <= ob_high:
                    msg = f"Retesting Bearish Order Block [{ob_low:.6g} – {ob_high:.6g}]"
                    signals.append(("SELL", 0.40, msg))
                    zones.append({"type": "bear_ob", "high": ob_high, "low": ob_low, "label": "Bear OB"})
                    break

    # ── Fair Value Gaps (FVG / Imbalance) ──────────────────────────
    for i in range(3, min(25, len(df))):
        c1 = df.iloc[-i]
        c3 = df.iloc[-(i-2)]
        c1_high, c1_low = float(c1["high"]), float(c1["low"])
        c3_high, c3_low = float(c3["high"]), float(c3["low"])

        # Bullish FVG: gap where c3.low > c1.high
        if c3_low > c1_high and (c3_low - c1_high) / (c1_high + 1e-9) > 0.001:
            if c1_high <= close <= c3_low:
                msg = f"Price filling Bullish FVG imbalance [{c1_high:.6g} – {c3_low:.6g}]"
                signals.append(("BUY", 0.25, msg))
                zones.append({"type": "bull_fvg", "high": c3_low, "low": c1_high, "label": "Bull FVG"})
                break

        # Bearish FVG: gap where c3.high < c1.low
        if c3_high < c1_low and (c1_low - c3_high) / (c1_low + 1e-9) > 0.001:
            if c3_high <= close <= c1_low:
                msg = f"Price filling Bearish FVG imbalance [{c3_high:.6g} – {c1_low:.6g}]"
                signals.append(("SELL", 0.25, msg))
                zones.append({"type": "bear_fvg", "high": c1_low, "low": c3_high, "label": "Bear FVG"})
                break

    # ── Liquidity Sweeps ───────────────────────────────────────────
    recent_highs = [float(df.iloc[-i]["high"]) for i in range(2, 8)]
    recent_lows  = [float(df.iloc[-i]["low"])  for i in range(2, 8)]
    prev_high = float(prev["high"]); prev_low = float(prev["low"])
    prev_open = float(prev["open"]); prev_close_v = float(prev["close"])

    if prev_high > max(recent_highs) and prev_close_v < prev_open:
        signals.append(("SELL", 0.20,
            f"Stop hunt above {prev_high:.6g} (liquidity sweep of equal highs) — bearish reversal"))
    if prev_low < min(recent_lows) and prev_close_v > prev_open:
        signals.append(("BUY", 0.20,
            f"Stop hunt below {prev_low:.6g} (liquidity sweep of equal lows) — bullish reversal"))

    # ── Premium / Discount zones ───────────────────────────────────
    lookback = min(50, len(df))
    rng_high = float(df.iloc[-lookback:]["high"].max())
    rng_low  = float(df.iloc[-lookback:]["low"].min())
    midpoint = (rng_high + rng_low) / 2
    if close < midpoint:
        signals.append(("BUY", 0.10, f"Price in Discount zone (below 50% range midpoint {midpoint:.6g}) — SMC buy area"))
    else:
        signals.append(("SELL", 0.10, f"Price in Premium zone (above 50% range midpoint {midpoint:.6g}) — SMC sell area"))

    # ── Score ──────────────────────────────────────────────────────
    for _, _, msg in signals:
        reasoning.append(msg)

    buy_score  = sum(w for r, w, _ in signals if r == "BUY")
    sell_score = sum(w for r, w, _ in signals if r == "SELL")

    if buy_score > sell_score and buy_score >= 0.30:
        recommendation = "BUY"
        confidence = min(0.90, 0.48 + buy_score * 0.6)
    elif sell_score > buy_score and sell_score >= 0.30:
        recommendation = "SELL"
        confidence = min(0.90, 0.48 + sell_score * 0.6)
    else:
        recommendation = "HOLD"
        confidence = 0.50

    if not reasoning:
        reasoning.append("No active Smart Money setup at current price")

    t = _targets(close, atr, recommendation)
    return {
        "strategy": "smart_money",
        "symbol": symbol, "timeframe": timeframe,
        "recommendation": recommendation,
        "confidence": round(confidence, 3),
        "entry_zone": {"low": round(close * 0.999, 6), "high": round(close * 1.001, 6)},
        **t,
        "reasoning": reasoning,
        "zones": zones,
        "structure": "Bullish (HH/HL)" if hh and hl else "Bearish (LH/LL)" if lh and ll else "Ranging",
        "buy_score": round(buy_score, 3),
        "sell_score": round(sell_score, 3),
    }


# ─────────────────────────────────────────────────────────────────
# 3. ELLIOTT WAVE (simplified pivot-based)
# ─────────────────────────────────────────────────────────────────
def elliott_wave_strategy(df: pd.DataFrame, symbol: str, timeframe: str) -> dict:
    last = df.iloc[-1]
    close = float(last["close"])
    atr = float(last.get("atr", close * 0.02) or close * 0.02)

    # Collect swing pivot prices using pre-computed boolean flags
    swing_high_flags = df["swing_high"]
    swing_low_flags  = df["swing_low"]

    pivot_highs = [(i, float(df.iloc[i]["high"]))
                   for i in range(len(df)) if swing_high_flags.iloc[i]]
    pivot_lows  = [(i, float(df.iloc[i]["low"]))
                   for i in range(len(df)) if swing_low_flags.iloc[i]]

    # Keep last 6 of each
    pivot_highs = pivot_highs[-6:]
    pivot_lows  = pivot_lows[-6:]

    reasoning = []
    wave_label = "Insufficient pivots"
    recommendation = "HOLD"
    confidence = 0.50
    target = close
    stop = close - atr
    pivots_out = []

    if len(pivot_highs) < 3 or len(pivot_lows) < 3:
        reasoning.append("Not enough confirmed pivots for Elliott Wave count — needs more price action")
    else:
        # Merge and sort all pivots chronologically
        all_pivots = (
            [(i, p, "H") for i, p in pivot_highs] +
            [(i, p, "L") for i, p in pivot_lows]
        )
        all_pivots.sort(key=lambda x: x[0])
        pivots_out = [{"type": t, "price": round(p, 6)} for _, p, t in all_pivots[-7:]]

        # Look at the last 5 alternating pivots
        seq = all_pivots[-6:]
        types = [t for _, _, t in seq]
        prices = [p for _, p, _ in seq]

        # ── Impulse UP (W1 low → W1 high → W2 low → potential W3 start) ──
        if len(seq) >= 5 and types[-5:] in (["L","H","L","H","L"], ["H","L","H","L","H"]):
            w_types = types[-5:]
            w_prices = prices[-5:]
            if w_types == ["L","H","L","H","L"]:
                # Wave count: 0=W1_start(L) 1=W1_end(H) 2=W2_end(L) 3=W3_partial_end(H) 4=W4_end(L)?
                w1_start = w_prices[0]; w1_end = w_prices[1]
                w2_end   = w_prices[2]; w3_end = w_prices[3]; w4_end = w_prices[4]
                w1_size  = w1_end - w1_start
                w2_ret   = (w1_end - w2_end) / (w1_size + 1e-9)
                w4_ret   = (w3_end - w4_end) / ((w3_end - w2_end) + 1e-9)

                valid_w2 = 0.30 < w2_ret < 0.78   # W2 retraces 30-78% of W1
                valid_w4 = 0.20 < w4_ret < 0.60   # W4 retraces 20-60% of W3
                w3_longer = (w3_end - w2_end) > w1_size * 1.0  # W3 > W1

                if valid_w2 and w3_longer:
                    if close > w4_end:  # W5 impulse up
                        wave_label = "Wave 5 impulse (bullish) — approaching final target"
                        recommendation = "BUY"
                        confidence = 0.65
                        target = w3_end + (w1_size * 0.618)   # W5 = 61.8% of W1
                        stop = w4_end * 0.99
                        reasoning.append(f"Impulse structure L→H→L→H→L detected")
                        reasoning.append(f"W2 retraced {w2_ret*100:.0f}% of W1 (valid: must be <78%)")
                        reasoning.append(f"W3 = {(w3_end-w2_end)/w1_size:.2f}× W1 (valid: must be > 1×)")
                        if valid_w4:
                            reasoning.append(f"W4 retraced {w4_ret*100:.0f}% of W3 — likely in Wave 5 now")
                        reasoning.append(f"W5 target: {target:.6g} (61.8% extension of W1 from W4 end)")
                    else:
                        wave_label = "Wave 4 correction — watching for W5 entry"
                        recommendation = "BUY"
                        confidence = 0.60
                        target = w3_end + (w1_size * 0.5)
                        stop = w2_end * 0.99
                        reasoning.append(f"Possible Wave 4 pullback in bullish impulse sequence")
                        reasoning.append(f"W3 was {(w3_end-w2_end)/w1_size:.2f}× W1 — extended as expected")
                        reasoning.append("Wait for W4 bottom + reversal signal before entering W5")

            elif w_types == ["H","L","H","L","H"]:
                # Bearish impulse
                w1_start = w_prices[0]; w1_end = w_prices[1]
                w2_end   = w_prices[2]; w3_end = w_prices[3]; w4_end = w_prices[4]
                w1_size  = w1_start - w1_end
                w2_ret   = (w2_end - w1_end) / (w1_size + 1e-9)
                w3_longer = (w2_end - w3_end) > w1_size * 1.0

                if 0.30 < w2_ret < 0.78 and w3_longer:
                    wave_label = "Wave 5 impulse (bearish) — final leg down"
                    recommendation = "SELL"
                    confidence = 0.65
                    target = w3_end - (w1_size * 0.618)
                    stop = w4_end * 1.01
                    reasoning.append("Bearish impulse H→L→H→L→H detected")
                    reasoning.append(f"W2 retracement {w2_ret*100:.0f}% — valid Elliott correction")
                    reasoning.append(f"W3 = {(w2_end-w3_end)/w1_size:.2f}× W1 — extended, typical for W3")
                    reasoning.append(f"Bearish W5 target: {target:.6g}")

        # ── A-B-C Correction ──
        if recommendation == "HOLD" and len(seq) >= 4:
            a_to_b_bullish = types[-4:] == ["H","L","H","L"] and prices[-1] < prices[-3]
            if a_to_b_bullish:
                wave_label = "ABC correction — Wave C down in progress"
                a_start = prices[-4]; a_end = prices[-3]
                b_end   = prices[-2]; c_target = a_end - (b_end - a_end) * 1.0
                recommendation = "SELL"
                confidence = 0.58
                target = c_target
                stop = b_end * 1.01
                reasoning.append("A-B-C corrective pattern detected (bearish Wave C)")
                reasoning.append(f"Wave C typically equals Wave A — target {c_target:.6g}")

    if not reasoning:
        reasoning.append(wave_label if wave_label != "Insufficient pivots" else "No clear Elliott Wave structure at this timeframe")
        if pivot_highs and pivot_lows:
            last_ph = pivot_highs[-1][1]; last_pl = pivot_lows[-1][1]
            reasoning.append(f"Last confirmed swing high: {last_ph:.6g} | swing low: {last_pl:.6g}")

    t = _targets(close, atr, recommendation)
    return {
        "strategy": "elliott_wave",
        "symbol": symbol, "timeframe": timeframe,
        "recommendation": recommendation,
        "confidence": round(confidence, 3),
        "entry_zone": {"low": round(close * 0.999, 6), "high": round(close * 1.001, 6)},
        **t,
        "reasoning": reasoning,
        "wave_label": wave_label,
        "pivots": pivots_out,
    }


# ─────────────────────────────────────────────────────────────────
# 4. WARREN BUFFETT (Quality + Value)
# ─────────────────────────────────────────────────────────────────
def warren_buffett_strategy(df: pd.DataFrame, symbol: str, timeframe: str) -> dict:
    last = df.iloc[-1]
    close = float(last["close"])
    atr = float(last.get("atr", close * 0.02) or close * 0.02)
    ema200 = float(last.get("ema200", close) or close)
    ema50  = float(last.get("ema50",  close) or close)
    ema20  = float(last.get("ema20",  close) or close)
    rsi    = float(last.get("rsi", 50) or 50)
    adx    = float(last.get("adx", 0)  or 0)
    bb_pct = float(last.get("bb_pct_b", 0.5) or 0.5)

    quality = 0
    value   = 0
    reasoning = []

    # ── Quality criteria ──────────────────────────────────────────
    if close > ema200:
        quality += 2
        reasoning.append(f"Above 200 EMA ({ema200:.6g}) — long-term uptrend intact, Buffett's #1 filter")
    else:
        quality -= 3
        reasoning.append(f"Below 200 EMA — Buffett avoids assets in structural downtrends")

    if ema20 > ema50 > ema200:
        quality += 1
        reasoning.append("EMA stack aligned (20>50>200) — consistent compounding trend")

    if adx > 25:
        quality += 1
        reasoning.append(f"ADX {adx:.0f} — trend has institutional conviction")
    elif adx < 15:
        quality -= 1
        reasoning.append(f"ADX {adx:.0f} — weak trend, Buffett prefers consistent movers")

    # Consecutive up candles (price strength)
    consec_up = sum(1 for i in range(1, 5)
                    if float(df.iloc[-i]["close"]) > float(df.iloc[-(i+1)]["close"]))
    if consec_up >= 3:
        quality += 1
        reasoning.append(f"{consec_up} of last 4 candles closed higher — consistent buying pressure")

    # ── Value criteria ────────────────────────────────────────────
    if rsi < 55:
        value += 2
        reasoning.append(f"RSI {rsi:.0f} — not overbought, still at reasonable price")
    elif rsi < 65:
        value += 1
        reasoning.append(f"RSI {rsi:.0f} — slightly elevated but acceptable for quality asset")
    else:
        value -= 1
        reasoning.append(f"RSI {rsi:.0f} — Buffett would wait for a pullback to better entry")

    ext_from_50 = (close - ema50) / (ema50 + 1e-9)
    if ext_from_50 < 0.04:
        value += 2
        reasoning.append(f"Price within 4% of 50 EMA — Buffett-style value zone")
    elif ext_from_50 < 0.10:
        value += 1
        reasoning.append(f"Price {ext_from_50*100:.1f}% above 50 EMA — fair value territory")
    elif ext_from_50 < 0.00:
        value += 2
        reasoning.append(f"Price below 50 EMA — deep value opportunity (if quality passes)")
    else:
        value -= 1
        reasoning.append(f"Price {ext_from_50*100:.1f}% above 50 EMA — better to wait for mean reversion")

    if bb_pct < 0.40:
        value += 1
        reasoning.append(f"Bollinger %B at {bb_pct:.2f} — price in lower range, value entry zone")
    elif bb_pct > 0.85:
        value -= 1
        reasoning.append(f"Bollinger %B at {bb_pct:.2f} — price near upper band, not Buffett-style entry")

    # ── Final decision ────────────────────────────────────────────
    total = quality + value
    # Buffett never shorts
    if quality >= 2 and value >= 3 and total >= 5:
        recommendation = "BUY"
        confidence = min(0.88, 0.52 + total * 0.04)
        reasoning.insert(0, "Strong quality + value alignment — high-conviction Buffett entry")
    elif quality >= 2 and value >= 1 and total >= 3:
        recommendation = "BUY"
        confidence = min(0.72, 0.50 + total * 0.03)
        reasoning.insert(0, "Quality business at fair price — Buffett-style partial entry")
    elif quality < 0:
        recommendation = "HOLD"
        confidence = 0.45
        reasoning.insert(0, "Fails quality filter — Buffett would not own this at any price")
    else:
        recommendation = "HOLD"
        confidence = 0.50
        reasoning.insert(0, "Quality is there but price is stretched — be patient, wait for pullback")

    t = _targets(close, atr, recommendation)
    # Override stop to 200 EMA for Buffett (structural invalidation)
    t["stop_loss"] = round(ema200 * 0.97, 6)
    return {
        "strategy": "warren_buffett",
        "symbol": symbol, "timeframe": timeframe,
        "recommendation": recommendation,
        "confidence": round(confidence, 3),
        "entry_zone": {"low": round(ema50 * 0.996, 6), "high": round(ema50 * 1.004, 6)},
        **t,
        "reasoning": reasoning,
        "scores": {"quality": quality, "value": value, "total": total},
        "key_levels": {
            "ema_200": round(ema200, 6),
            "ema_50":  round(ema50,  6),
            "ema_20":  round(ema20,  6),
        },
    }


# ─────────────────────────────────────────────────────────────────
# 5. JPMORGAN QUANTITATIVE
# ─────────────────────────────────────────────────────────────────
def jpmorgan_strategy(df: pd.DataFrame, symbol: str, timeframe: str) -> dict:
    last = df.iloc[-1]
    prev = df.iloc[-2]
    close  = float(last["close"])
    atr    = float(last.get("atr", close * 0.02) or close * 0.02)
    vol_z  = float(last.get("vol_zscore", 0) or 0)
    lr_slope = float(last.get("lr_slope", 0) or 0)

    reasoning = []
    factors: dict = {}

    # Factor 1 — Cross-sectional momentum (20-bar return, fast/slow blend)
    if len(df) >= 21:
        ret20 = (close - float(df.iloc[-21]["close"])) / (float(df.iloc[-21]["close"]) + 1e-9)
        ret5  = (close - float(df.iloc[-6]["close"]))  / (float(df.iloc[-6]["close"])  + 1e-9)
        mom   = ret20 * 0.7 + ret5 * 0.3
        factors["momentum"] = mom
        label = f"+{mom*100:.1f}%" if mom >= 0 else f"{mom*100:.1f}%"
        if abs(mom) > 0.05:
            tone = "strong bullish" if mom > 0 else "strong bearish"
            reasoning.append(f"Momentum factor ({label}) — {tone} trend return signal")
        elif abs(mom) > 0.02:
            reasoning.append(f"Momentum factor ({label}) — moderate directional drift")
        else:
            reasoning.append(f"Momentum factor near zero ({label}) — no clear directional edge")

    # Factor 2 — Mean-reversion z-score (50-bar)
    if len(df) >= 50:
        mu  = float(df["close"].iloc[-50:].mean())
        sig = float(df["close"].iloc[-50:].std())
        z   = (close - mu) / (sig + 1e-9)
        factors["z_score"] = z
        if z > 2.0:
            reasoning.append(f"Price +{z:.1f}σ above 50-bar mean ({mu:.6g}) — JPM flags mean-reversion risk")
        elif z < -2.0:
            reasoning.append(f"Price {z:.1f}σ below mean ({mu:.6g}) — statistical oversell, mean-reversion opportunity")
        else:
            reasoning.append(f"Z-score {z:.2f} — price near statistical fair value")

    # Factor 3 — Risk-adjusted return proxy (Sharpe-like over 20 bars)
    if len(df) >= 21:
        rets = df["close"].pct_change().iloc[-20:].dropna()
        if len(rets) and rets.std() > 0:
            sharpe = float(rets.mean() / rets.std())
            factors["sharpe_proxy"] = sharpe
            if sharpe > 0.12:
                reasoning.append(f"Risk-adjusted return positive (Sharpe proxy {sharpe:.2f}) — institutional-grade risk/reward")
            elif sharpe < -0.12:
                reasoning.append(f"Poor risk-adjusted return (Sharpe proxy {sharpe:.2f}) — JPM models flag downside risk")
            else:
                reasoning.append(f"Neutral risk-adjusted return (Sharpe proxy {sharpe:.2f})")

    # Factor 4 — Volume factor
    if vol_z > 2.0:
        price_chg = (close - float(prev["close"])) / (float(prev["close"]) + 1e-9)
        if price_chg > 0:
            factors["volume"] = 0.30
            reasoning.append(f"Institutional volume spike (+{vol_z:.1f}σ) on up-move — smart money accumulation")
        else:
            factors["volume"] = -0.30
            reasoning.append(f"High volume ({vol_z:.1f}σ) on down-move — institutional distribution")
    elif vol_z < -0.5:
        factors["volume"] = 0.0
        reasoning.append(f"Below-average volume (z={vol_z:.1f}) — JPM waits for conviction before entry")

    # Factor 5 — Linear regression slope (trend quality)
    factors["lr_slope"] = lr_slope
    if lr_slope > 0.25:
        reasoning.append(f"Positive regression slope ({lr_slope:.2f}%/bar) — quantitative trend confirmation")
    elif lr_slope < -0.25:
        reasoning.append(f"Negative regression slope ({lr_slope:.2f}%/bar) — systematic downtrend signal")

    # ── Composite JPM score ────────────────────────────────────────
    mom_f   = factors.get("momentum", 0.0)
    z_f     = factors.get("z_score", 0.0)
    sp_f    = factors.get("sharpe_proxy", 0.0)
    vol_f   = factors.get("volume", 0.0)
    lr_f    = lr_slope / 10.0   # normalise

    # Momentum-biased model with mean-reversion dampener
    composite = (mom_f * 2.0) + (sp_f * 1.5) + (vol_f * 0.8) + (lr_f * 0.5) + (-z_f * 0.25)

    if composite > 0.12:
        recommendation = "BUY"
        confidence = min(0.90, 0.50 + composite * 0.55)
    elif composite < -0.12:
        recommendation = "SELL"
        confidence = min(0.90, 0.50 + abs(composite) * 0.55)
    else:
        recommendation = "HOLD"
        confidence = 0.50

    if not reasoning:
        reasoning.append("Insufficient data for JPMorgan quantitative model")

    t = _targets(close, atr, recommendation)
    return {
        "strategy": "jpmorgan",
        "symbol": symbol, "timeframe": timeframe,
        "recommendation": recommendation,
        "confidence": round(min(confidence, 0.90), 3),
        "entry_zone": {"low": round(close * 0.999, 6), "high": round(close * 1.001, 6)},
        **t,
        "reasoning": reasoning,
        "factors": {k: round(float(v), 4) for k, v in factors.items()},
        "composite_score": round(float(composite), 4),
    }


# ─────────────────────────────────────────────────────────────────
# 6. MACD CROSSOVER
# ─────────────────────────────────────────────────────────────────
def macd_crossover_strategy(df: pd.DataFrame, symbol: str, timeframe: str) -> dict:
    last = df.iloc[-1]; prev = df.iloc[-2]
    close = float(last["close"]); atr = float(last.get("atr", close * 0.02) or close * 0.02)
    macd = float(last.get("macd", 0) or 0); sig = float(last.get("macd_signal", 0) or 0)
    hist = float(last.get("macd_hist", 0) or 0)
    p_macd = float(prev.get("macd", 0) or 0); p_sig = float(prev.get("macd_signal", 0) or 0)
    p_hist = float(prev.get("macd_hist", 0) or 0)

    reasoning = []; rec = "HOLD"; confidence = 0.50

    cross_up   = macd > sig and p_macd <= p_sig
    cross_down = macd < sig and p_macd >= p_sig

    if cross_up:
        rec = "BUY"; confidence = 0.72
        reasoning.append(f"MACD bullish crossover: line ({macd:.6g}) crossed above signal ({sig:.6g})")
    elif cross_down:
        rec = "SELL"; confidence = 0.72
        reasoning.append(f"MACD bearish crossover: line ({macd:.6g}) crossed below signal ({sig:.6g})")
    elif hist > p_hist > 0:
        rec = "BUY"; confidence = 0.60
        reasoning.append(f"MACD histogram expanding upward ({hist:.6g}) — bullish momentum accelerating")
    elif hist < p_hist < 0:
        rec = "SELL"; confidence = 0.60
        reasoning.append(f"MACD histogram expanding downward ({hist:.6g}) — bearish momentum accelerating")

    reasoning.append(f"MACD is {'above' if macd > 0 else 'below'} zero line — {'bullish' if macd > 0 else 'bearish'} macro bias")

    # Divergence (10-bar)
    if len(df) >= 11:
        p10_close = float(df.iloc[-11]["close"]); p10_macd = float(df.iloc[-11].get("macd", macd) or macd)
        if (close - p10_close) > 0.02 * p10_close and (macd - p10_macd) < 0:
            reasoning.append("⚠️ Bearish divergence: price higher but MACD weakening")
            if rec == "BUY": confidence -= 0.12
        elif (close - p10_close) < -0.02 * p10_close and (macd - p10_macd) > 0:
            reasoning.append("Bullish divergence: price lower but MACD strengthening")
            if rec == "SELL": confidence -= 0.12

    if not reasoning: reasoning.append("No active MACD crossover — awaiting signal")
    t = _targets(close, atr, rec)
    return {"strategy": "macd_crossover", "symbol": symbol, "timeframe": timeframe,
            "recommendation": rec, "confidence": round(min(confidence, 0.88), 3),
            "entry_zone": {"low": round(close * 0.999, 6), "high": round(close * 1.001, 6)},
            **t, "reasoning": reasoning,
            "indicators": {"macd": round(macd, 6), "signal": round(sig, 6), "histogram": round(hist, 6)}}


# ─────────────────────────────────────────────────────────────────
# 7. RSI DIVERGENCE
# ─────────────────────────────────────────────────────────────────
def rsi_divergence_strategy(df: pd.DataFrame, symbol: str, timeframe: str) -> dict:
    last = df.iloc[-1]
    close = float(last["close"]); atr = float(last.get("atr", close * 0.02) or close * 0.02)
    rsi = float(last.get("rsi", 50) or 50)

    reasoning = []; rec = "HOLD"; confidence = 0.50

    # Detect swing points for divergence over last 20 bars
    window = df.iloc[-20:].reset_index(drop=True)
    price_vals = window["close"].values
    rsi_vals   = window["rsi"].fillna(50).values

    # Find local price highs/lows
    def local_max_idx(arr, n=3):
        return [i for i in range(n, len(arr)-n) if arr[i] == max(arr[i-n:i+n+1])]
    def local_min_idx(arr, n=3):
        return [i for i in range(n, len(arr)-n) if arr[i] == min(arr[i-n:i+n+1])]

    ph = local_max_idx(price_vals); pl = local_min_idx(price_vals)
    rh = local_max_idx(rsi_vals);   rl = local_min_idx(rsi_vals)

    bearish_div = (len(ph) >= 2 and len(rh) >= 2 and
                   price_vals[ph[-1]] > price_vals[ph[-2]] and
                   rsi_vals[rh[-1]]   < rsi_vals[rh[-2]])
    bullish_div = (len(pl) >= 2 and len(rl) >= 2 and
                   price_vals[pl[-1]] < price_vals[pl[-2]] and
                   rsi_vals[rl[-1]]   > rsi_vals[rl[-2]])

    if bullish_div:
        rec = "BUY"; confidence = 0.70
        reasoning.append(f"Regular Bullish Divergence: price making lower lows but RSI making higher lows")
        reasoning.append(f"RSI ({rsi:.0f}) showing hidden accumulation — trend reversal signal")
    elif bearish_div:
        rec = "SELL"; confidence = 0.70
        reasoning.append(f"Regular Bearish Divergence: price making higher highs but RSI making lower highs")
        reasoning.append(f"RSI ({rsi:.0f}) showing hidden distribution — reversal warning")
    else:
        if rsi < 30:
            rec = "BUY"; confidence = 0.62
            reasoning.append(f"RSI ({rsi:.0f}) deeply oversold — mean reversion opportunity")
        elif rsi > 70:
            rec = "SELL"; confidence = 0.62
            reasoning.append(f"RSI ({rsi:.0f}) overbought — exhaustion signal")
        else:
            reasoning.append(f"RSI ({rsi:.0f}) — no divergence detected, neutral zone")

    reasoning.append(f"RSI at {rsi:.0f}: {'bullish zone (>60)' if rsi > 60 else 'bearish zone (<40)' if rsi < 40 else 'neutral (40-60)'}")
    t = _targets(close, atr, rec)
    return {"strategy": "rsi_divergence", "symbol": symbol, "timeframe": timeframe,
            "recommendation": rec, "confidence": round(min(confidence, 0.88), 3),
            "entry_zone": {"low": round(close * 0.999, 6), "high": round(close * 1.001, 6)},
            **t, "reasoning": reasoning,
            "rsi": round(rsi, 1), "divergence": "bullish" if bullish_div else "bearish" if bearish_div else "none"}


# ─────────────────────────────────────────────────────────────────
# 8. BOLLINGER BAND SQUEEZE
# ─────────────────────────────────────────────────────────────────
def bb_squeeze_strategy(df: pd.DataFrame, symbol: str, timeframe: str) -> dict:
    last = df.iloc[-1]; prev = df.iloc[-2]
    close = float(last["close"]); atr = float(last.get("atr", close * 0.02) or close * 0.02)
    bb_w = float(last.get("bb_width", 0.04) or 0.04)
    pct_b = float(last.get("bb_pct_b", 0.5) or 0.5)
    p_bb_w = float(prev.get("bb_width", bb_w) or bb_w)

    reasoning = []; rec = "HOLD"; confidence = 0.50

    # Historical BB width (last 50 bars) for percentile
    if len(df) >= 50:
        hist_width = df["bb_width"].iloc[-50:].dropna()
        pctile = (hist_width < bb_w).mean() * 100  # current width percentile
    else:
        pctile = 50.0

    squeeze_active = pctile < 20  # width in bottom 20% of last 50 bars
    expanding      = bb_w > p_bb_w * 1.02  # width expanding by >2%

    if squeeze_active and expanding:
        # Breakout from squeeze — direction by price vs midband
        if pct_b > 0.55:
            rec = "BUY"; confidence = 0.73
            reasoning.append(f"Bollinger Band Squeeze breakout to the UPSIDE (BB width {bb_w:.3f}, was in bottom {pctile:.0f}th pctile)")
            reasoning.append(f"Price at {pct_b:.2f} %B — above midband, confirming bullish breakout")
        elif pct_b < 0.45:
            rec = "SELL"; confidence = 0.73
            reasoning.append(f"Bollinger Band Squeeze breakout to the DOWNSIDE (BB width {bb_w:.3f})")
            reasoning.append(f"Price at {pct_b:.2f} %B — below midband, confirming bearish breakout")
        else:
            reasoning.append(f"BB Squeeze expanding but direction unclear (%B = {pct_b:.2f}) — wait for close above/below midband")
    elif squeeze_active:
        reasoning.append(f"BB Squeeze in progress (width {bb_w:.3f}, {pctile:.0f}th percentile) — coiling for breakout")
        reasoning.append("Accumulation phase: enter on breakout above/below bands")
        rec = "HOLD"
    else:
        reasoning.append(f"No active squeeze (BB width {bb_w:.3f}, {pctile:.0f}th percentile)")
        if pct_b > 0.8:
            rec = "SELL"; confidence = 0.55
            reasoning.append(f"Price near upper Bollinger Band ({pct_b:.2f} %B) — mean-reversion risk")
        elif pct_b < 0.2:
            rec = "BUY"; confidence = 0.55
            reasoning.append(f"Price near lower Bollinger Band ({pct_b:.2f} %B) — oversold bounce zone")

    t = _targets(close, atr, rec)
    return {"strategy": "bb_squeeze", "symbol": symbol, "timeframe": timeframe,
            "recommendation": rec, "confidence": round(min(confidence, 0.88), 3),
            "entry_zone": {"low": round(close * 0.999, 6), "high": round(close * 1.001, 6)},
            **t, "reasoning": reasoning,
            "bb_width": round(bb_w, 4), "bb_pct_b": round(pct_b, 3),
            "squeeze_active": squeeze_active, "width_percentile": round(pctile, 1)}


# ─────────────────────────────────────────────────────────────────
# 9. SUPPORT & RESISTANCE
# ─────────────────────────────────────────────────────────────────
def support_resistance_strategy(df: pd.DataFrame, symbol: str, timeframe: str) -> dict:
    last = df.iloc[-1]
    close = float(last["close"]); atr = float(last.get("atr", close * 0.02) or close * 0.02)

    # Find horizontal S/R levels via price cluster analysis (last 100 bars)
    lookback = min(100, len(df))
    prices = []
    window = df.iloc[-lookback:]
    swing_h = window[window["swing_high"] == True]["high"].tolist()
    swing_l = window[window["swing_low"]  == True]["low"].tolist()
    prices = swing_h + swing_l

    levels = []
    if prices:
        prices.sort()
        cluster_dist = close * 0.005  # 0.5% clustering tolerance
        clusters = [[prices[0]]]
        for p in prices[1:]:
            if p - clusters[-1][-1] < cluster_dist:
                clusters[-1].append(p)
            else:
                clusters.append([p])
        levels = sorted([sum(c)/len(c) for c in clusters if len(c) >= 2],
                        key=lambda x: abs(x - close))[:6]

    reasoning = []; rec = "HOLD"; confidence = 0.50
    nearest_support = None; nearest_resistance = None

    for lvl in sorted(levels):
        if lvl < close and (nearest_support is None or lvl > nearest_support):
            nearest_support = lvl
        if lvl > close and (nearest_resistance is None or lvl < nearest_resistance):
            nearest_resistance = lvl

    if nearest_support and abs(close - nearest_support) / close < 0.015:
        rec = "BUY"; confidence = 0.68
        reasoning.append(f"Price at strong support level {nearest_support:.6g} (tested ≥2 times)")
        reasoning.append("Classic S/R bounce setup — buy the support")
    elif nearest_resistance and abs(close - nearest_resistance) / close < 0.015:
        rec = "SELL"; confidence = 0.65
        reasoning.append(f"Price at strong resistance level {nearest_resistance:.6g} (tested ≥2 times)")
        reasoning.append("Classic S/R rejection setup — sell the resistance")
    else:
        if nearest_support:
            dist_s = abs(close - nearest_support) / close * 100
            reasoning.append(f"Nearest support: {nearest_support:.6g} ({dist_s:.1f}% away)")
        if nearest_resistance:
            dist_r = abs(close - nearest_resistance) / close * 100
            reasoning.append(f"Nearest resistance: {nearest_resistance:.6g} ({dist_r:.1f}% away)")
        if not levels:
            reasoning.append("No significant S/R clusters found in recent price history")

    t = _targets(close, atr, rec)
    return {"strategy": "support_resistance", "symbol": symbol, "timeframe": timeframe,
            "recommendation": rec, "confidence": round(min(confidence, 0.88), 3),
            "entry_zone": {"low": round(close * 0.999, 6), "high": round(close * 1.001, 6)},
            **t, "reasoning": reasoning,
            "levels": [round(l, 6) for l in levels],
            "nearest_support": round(nearest_support, 6) if nearest_support else None,
            "nearest_resistance": round(nearest_resistance, 6) if nearest_resistance else None}


# ─────────────────────────────────────────────────────────────────
# 10. EMA CROSSOVER (Golden / Death Cross)
# ─────────────────────────────────────────────────────────────────
def ema_crossover_strategy(df: pd.DataFrame, symbol: str, timeframe: str) -> dict:
    last = df.iloc[-1]; prev = df.iloc[-2]
    close = float(last["close"]); atr = float(last.get("atr", close * 0.02) or close * 0.02)
    e20 = float(last.get("ema20", close) or close); e50 = float(last.get("ema50", close) or close)
    e200 = float(last.get("ema200", close) or close)
    p20 = float(prev.get("ema20", e20) or e20); p50 = float(prev.get("ema50", e50) or e50)
    p200 = float(prev.get("ema200", e200) or e200)

    reasoning = []; rec = "HOLD"; confidence = 0.50

    # Fresh crossovers
    golden_20_50 = e20 > e50 and p20 <= p50
    death_20_50  = e20 < e50 and p20 >= p50
    golden_50_200 = e50 > e200 and p50 <= p200
    death_50_200  = e50 < e200 and p50 >= p200

    if golden_50_200:
        rec = "BUY"; confidence = 0.80
        reasoning.append(f"🌟 GOLDEN CROSS: EMA 50 ({e50:.6g}) crossed above EMA 200 ({e200:.6g}) — major bullish signal")
        reasoning.append("Long-term institutional buyers entering the market")
    elif death_50_200:
        rec = "SELL"; confidence = 0.80
        reasoning.append(f"💀 DEATH CROSS: EMA 50 ({e50:.6g}) crossed below EMA 200 ({e200:.6g}) — major bearish signal")
        reasoning.append("Institutional selling pressure confirmed across timeframe")
    elif golden_20_50:
        rec = "BUY"; confidence = 0.68
        reasoning.append(f"EMA 20 ({e20:.6g}) crossed above EMA 50 ({e50:.6g}) — short-term momentum bullish")
    elif death_20_50:
        rec = "SELL"; confidence = 0.68
        reasoning.append(f"EMA 20 ({e20:.6g}) crossed below EMA 50 ({e50:.6g}) — short-term momentum bearish")
    else:
        # EMA ribbon analysis
        if e20 > e50 > e200:
            rec = "BUY"; confidence = 0.60
            reasoning.append(f"EMA ribbon fully aligned bullish (20>{e50:.6g}>200) — trend continuation")
        elif e20 < e50 < e200:
            rec = "SELL"; confidence = 0.60
            reasoning.append(f"EMA ribbon fully aligned bearish (20<50<200) — trend continuation down")
        else:
            reasoning.append(f"EMA ribbon mixed (20:{e20:.6g} 50:{e50:.6g} 200:{e200:.6g}) — choppy conditions")

    gap_20_50 = abs(e20 - e50) / e50 * 100
    reasoning.append(f"EMA 20/50 gap: {gap_20_50:.2f}% — {'widening trend' if gap_20_50 > 1 else 'tight, possible cross soon'}")

    t = _targets(close, atr, rec)
    return {"strategy": "ema_crossover", "symbol": symbol, "timeframe": timeframe,
            "recommendation": rec, "confidence": round(min(confidence, 0.88), 3),
            "entry_zone": {"low": round(close * 0.999, 6), "high": round(close * 1.001, 6)},
            **t, "reasoning": reasoning,
            "ema20": round(e20, 6), "ema50": round(e50, 6), "ema200": round(e200, 6)}


# ─────────────────────────────────────────────────────────────────
# 11. ICHIMOKU CLOUD
# ─────────────────────────────────────────────────────────────────
def ichimoku_strategy(df: pd.DataFrame, symbol: str, timeframe: str) -> dict:
    last_idx = len(df) - 1
    close_s  = df["close"]; high_s = df["high"]; low_s = df["low"]
    close = float(close_s.iloc[-1]); atr = float(df.iloc[-1].get("atr", close * 0.02) or close * 0.02)

    def mid(h, l): return (h + l) / 2

    # Tenkan (9), Kijun (26), Senkou B (52)
    def ichi_line(period):
        if last_idx < period - 1: return close
        return mid(float(high_s.iloc[-period:].max()), float(low_s.iloc[-period:].min()))

    tenkan  = ichi_line(9)
    kijun   = ichi_line(26)
    senkou_b = ichi_line(52)
    senkou_a = mid(tenkan, kijun)

    cloud_top = max(senkou_a, senkou_b)
    cloud_bot = min(senkou_a, senkou_b)
    # Chikou: close 26 bars ago
    chikou_compare = float(close_s.iloc[-27]) if len(close_s) >= 27 else close

    reasoning = []; rec = "HOLD"; confidence = 0.50; score = 0

    # Price vs cloud
    if close > cloud_top:
        score += 2; reasoning.append(f"Price above Kumo cloud ({cloud_bot:.6g}–{cloud_top:.6g}) — bullish zone")
    elif close < cloud_bot:
        score -= 2; reasoning.append(f"Price below Kumo cloud — bearish zone")
    else:
        reasoning.append(f"Price inside Kumo cloud ({cloud_bot:.6g}–{cloud_top:.6g}) — neutral/transitioning")

    # TK Cross
    if tenkan > kijun:
        score += 1; reasoning.append(f"Tenkan ({tenkan:.6g}) above Kijun ({kijun:.6g}) — bullish TK alignment")
    else:
        score -= 1; reasoning.append(f"Tenkan ({tenkan:.6g}) below Kijun ({kijun:.6g}) — bearish TK alignment")

    # Chikou
    if close > chikou_compare:
        score += 1; reasoning.append("Chikou above price 26 periods ago — bullish confirmation")
    else:
        score -= 1; reasoning.append("Chikou below past price — bearish confirmation")

    # Cloud colour (future cloud)
    if senkou_a > senkou_b:
        score += 1; reasoning.append("Cloud is green (Senkou A > B) — bullish future bias")
    else:
        score -= 1; reasoning.append("Cloud is red (Senkou A < B) — bearish future bias")

    if score >= 3:
        rec = "BUY"; confidence = min(0.85, 0.50 + score * 0.09)
    elif score <= -3:
        rec = "SELL"; confidence = min(0.85, 0.50 + abs(score) * 0.09)
    elif score >= 1:
        rec = "BUY"; confidence = 0.58
    elif score <= -1:
        rec = "SELL"; confidence = 0.58

    t = _targets(close, atr, rec)
    return {"strategy": "ichimoku", "symbol": symbol, "timeframe": timeframe,
            "recommendation": rec, "confidence": round(confidence, 3),
            "entry_zone": {"low": round(close * 0.999, 6), "high": round(close * 1.001, 6)},
            **t, "reasoning": reasoning,
            "tenkan": round(tenkan, 6), "kijun": round(kijun, 6),
            "senkou_a": round(senkou_a, 6), "senkou_b": round(senkou_b, 6),
            "cloud_top": round(cloud_top, 6), "cloud_bot": round(cloud_bot, 6),
            "ichimoku_score": score}


# ─────────────────────────────────────────────────────────────────
# 12. STOCHASTIC OSCILLATOR
# ─────────────────────────────────────────────────────────────────
def stochastic_strategy(df: pd.DataFrame, symbol: str, timeframe: str) -> dict:
    last = df.iloc[-1]; prev = df.iloc[-2]
    close = float(last["close"]); atr = float(last.get("atr", close * 0.02) or close * 0.02)
    k = float(last.get("stoch_k", 50) or 50); d = float(last.get("stoch_d", 50) or 50)
    pk = float(prev.get("stoch_k", k) or k); pd_ = float(prev.get("stoch_d", d) or d)

    reasoning = []; rec = "HOLD"; confidence = 0.50

    cross_up   = k > d and pk <= pd_
    cross_down = k < d and pk >= pd_

    if k < 20 and d < 20:
        if cross_up:
            rec = "BUY"; confidence = 0.75
            reasoning.append(f"Stochastic %K ({k:.0f}) crossed above %D ({d:.0f}) from OVERSOLD zone (<20) — strong BUY")
        else:
            rec = "BUY"; confidence = 0.62
            reasoning.append(f"Stochastic deeply oversold (K:{k:.0f} D:{d:.0f}) — mean reversion expected")
    elif k > 80 and d > 80:
        if cross_down:
            rec = "SELL"; confidence = 0.75
            reasoning.append(f"Stochastic %K ({k:.0f}) crossed below %D ({d:.0f}) from OVERBOUGHT zone (>80) — strong SELL")
        else:
            rec = "SELL"; confidence = 0.62
            reasoning.append(f"Stochastic deeply overbought (K:{k:.0f} D:{d:.0f}) — reversal risk high")
    elif cross_up:
        rec = "BUY"; confidence = 0.60
        reasoning.append(f"Stochastic bullish crossover: %K ({k:.0f}) above %D ({d:.0f})")
    elif cross_down:
        rec = "SELL"; confidence = 0.60
        reasoning.append(f"Stochastic bearish crossover: %K ({k:.0f}) below %D ({d:.0f})")
    else:
        reasoning.append(f"Stochastic K:{k:.0f} D:{d:.0f} — no active crossover, {'approaching overbought' if k > 65 else 'approaching oversold' if k < 35 else 'mid-range'}")

    # Momentum direction of %K
    reasoning.append(f"%K is {'rising' if k > pk else 'falling'} ({pk:.0f}→{k:.0f}) — {'bullish' if k > pk else 'bearish'} momentum")

    t = _targets(close, atr, rec)
    return {"strategy": "stochastic", "symbol": symbol, "timeframe": timeframe,
            "recommendation": rec, "confidence": round(min(confidence, 0.88), 3),
            "entry_zone": {"low": round(close * 0.999, 6), "high": round(close * 1.001, 6)},
            **t, "reasoning": reasoning,
            "stoch_k": round(k, 1), "stoch_d": round(d, 1)}


# ─────────────────────────────────────────────────────────────────
# 13. VWAP
# ─────────────────────────────────────────────────────────────────
def vwap_strategy(df: pd.DataFrame, symbol: str, timeframe: str) -> dict:
    last = df.iloc[-1]
    close = float(last["close"]); atr = float(last.get("atr", close * 0.02) or close * 0.02)
    vwap  = float(last.get("vwap", close) or close)
    ema20 = float(last.get("ema20", close) or close)

    dev_pct = (close - vwap) / (vwap + 1e-9) * 100
    reasoning = []; rec = "HOLD"; confidence = 0.50

    if close > vwap:
        reasoning.append(f"Price ({close:.6g}) above VWAP ({vwap:.6g}) — institutional bulls in control")
        if dev_pct > 2:
            rec = "SELL"; confidence = 0.60
            reasoning.append(f"Price {dev_pct:.1f}% above VWAP — extended, mean reversion to VWAP likely")
        else:
            rec = "BUY"; confidence = 0.62
            reasoning.append(f"Price {dev_pct:.1f}% above VWAP — healthy bullish positioning")
    else:
        reasoning.append(f"Price ({close:.6g}) below VWAP ({vwap:.6g}) — sellers dominant")
        if dev_pct < -2:
            rec = "BUY"; confidence = 0.60
            reasoning.append(f"Price {dev_pct:.1f}% below VWAP — oversold relative to institutional average")
        else:
            rec = "SELL"; confidence = 0.62
            reasoning.append(f"Price {dev_pct:.1f}% below VWAP — bearish institutional bias")

    # VWAP as dynamic support/resistance
    vwap_test = abs(close - vwap) / vwap < 0.005
    if vwap_test:
        reasoning.append(f"Price testing VWAP ({vwap:.6g}) — key decision level for institutional traders")
        confidence += 0.05

    # EMA vs VWAP confluence
    if ema20 > vwap and close > vwap:
        reasoning.append("EMA 20 above VWAP — short-term trend aligned with institutional benchmark")
        if rec == "BUY": confidence += 0.03
    elif ema20 < vwap and close < vwap:
        reasoning.append("EMA 20 below VWAP — short-term trend aligned bearish with institutional selling")
        if rec == "SELL": confidence += 0.03

    t = _targets(close, atr, rec)
    return {"strategy": "vwap", "symbol": symbol, "timeframe": timeframe,
            "recommendation": rec, "confidence": round(min(confidence, 0.85), 3),
            "entry_zone": {"low": round(close * 0.999, 6), "high": round(close * 1.001, 6)},
            **t, "reasoning": reasoning,
            "vwap": round(vwap, 6), "deviation_pct": round(dev_pct, 2)}
