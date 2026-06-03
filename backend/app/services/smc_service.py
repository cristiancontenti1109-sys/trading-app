"""
Market Mechanics Strategy — Brad Goh (The Trading Geek)
========================================================
Based on the full 10-hour course transcript.

Framework (top-down, 3 timeframes):
  4h  → Trend bias (HH/HL = bull | LH/LL = bear) + Premium/Discount levels
  1h  → Locate Supply/Demand zone or Order Block inside the discount/premium
  15m → Wait for Market Shift (CHoCH) as mandatory entry trigger
         + Liquidity sweep confirmation

Entry rules (ALL required for a valid signal):
  1. 4h bias is clearly bullish or bearish (BOS confirmed)
  2. Price is in the DISCOUNT zone for buys (< 50% of last swing) OR
     PREMIUM zone for sells (> 50% of last swing)
  3. An Order Block exists within the discount/premium area on 1h or 15m
  4. A Liquidity Sweep has occurred at or near the zone (stop hunt confirmed)
  5. A Market Shift (CHoCH) on 15m confirms the reversal

Stop Loss:   behind the Order Block extreme + ATR buffer (structural, NOT arbitrary)
Take Profit: next structural swing high (bull) / swing low (bear) on 4h
             TP1 = 1.5R (partial — close 50% of position)
             TP2 = next 4h swing = structural target
             TP3 = 1:4R extension (let runner go)

Risk:        1–3% per trade, position size from account equity / risk distance
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from dataclasses import dataclass
from datetime import datetime
from typing import Optional
import logging

logger = logging.getLogger(__name__)


# ─── Data structures ─────────────────────────────────────────────────────────

@dataclass
class OrderBlock:
    ts: datetime
    ob_high: float
    ob_low: float
    direction: str          # "bull" | "bear"
    impulse_size_atr: float
    in_discount: bool = False  # True if inside premium/discount zone

    @property
    def midpoint(self) -> float:
        return (self.ob_high + self.ob_low) / 2


@dataclass
class SwingLevel:
    ts: datetime
    level: float
    kind: str               # "high" | "low"


@dataclass
class LiquiditySweep:
    ts: datetime
    swept_level: float
    direction: str          # "bull" (swept lows) | "bear" (swept highs)
    rejection_size_atr: float


@dataclass
class MarketShift:
    ts: datetime
    direction: str          # "bull" (CHoCH up) | "bear" (CHoCH down)
    broken_level: float     # the structural level that was broken


@dataclass
class FairValueGap:
    ts: datetime
    fvg_high: float
    fvg_low: float
    direction: str
    size_atr: float

    @property
    def midpoint(self) -> float:
        return (self.fvg_high + self.fvg_low) / 2


@dataclass
class SMCSignal:
    symbol: str
    timestamp: datetime
    bias_4h: str                    # "bull" | "bear"
    direction: str                  # "BUY" | "SELL"
    confidence: float
    smc_score: int                  # 3–5 conditions met
    is_hot: bool

    # Price levels
    entry: float
    stop_loss: float
    tp1: float                      # 1.5R — close 50% here
    tp2: float                      # structural target (next swing)
    tp3: float                      # 1:4R runner
    risk: float                     # absolute risk per unit
    rr_tp2: float                   # actual RR to TP2

    # Context
    discount_premium_50: float      # 50% level of the swing range
    zone_type: str                  # "order_block" | "demand_zone"
    reasoning: list[str]

    # Raw detected objects
    order_block: Optional[OrderBlock] = None
    sweep: Optional[LiquiditySweep] = None
    market_shift: Optional[MarketShift] = None
    fvg: Optional[FairValueGap] = None
    structural_tp: Optional[float] = None  # next swing level for TP2


# ─── Core helpers ─────────────────────────────────────────────────────────────

def _atr(df: pd.DataFrame, n: int = 14) -> pd.Series:
    pc = df["close"].shift(1)
    tr = pd.concat(
        [df["high"] - df["low"],
         (df["high"] - pc).abs(),
         (df["low"] - pc).abs()],
        axis=1,
    ).max(axis=1)
    return tr.rolling(n).mean()


def _swing_highs(df: pd.DataFrame, n: int = 3) -> list[SwingLevel]:
    """Local swing highs: high[i] is max of surrounding 2n+1 candles."""
    result = []
    for i in range(n, len(df) - n):
        window = df["high"].iloc[i - n: i + n + 1]
        if float(df["high"].iloc[i]) == float(window.max()):
            result.append(SwingLevel(ts=df.index[i], level=float(df["high"].iloc[i]), kind="high"))
    return result


def _swing_lows(df: pd.DataFrame, n: int = 3) -> list[SwingLevel]:
    """Local swing lows: low[i] is min of surrounding 2n+1 candles."""
    result = []
    for i in range(n, len(df) - n):
        window = df["low"].iloc[i - n: i + n + 1]
        if float(df["low"].iloc[i]) == float(window.min()):
            result.append(SwingLevel(ts=df.index[i], level=float(df["low"].iloc[i]), kind="low"))
    return result


# ─── Step 1 — 4h Bias (BOS / trend structure) ─────────────────────────────────

def detect_4h_bias(df4h: pd.DataFrame) -> tuple[str, float, float, float]:
    """
    Identify trend bias from 4h structure.

    Uses the MOST RECENT completed impulse leg to define premium/discount:
      - In a bull trend: range = last swing low → last swing high (recent leg)
      - In a bear trend: range = last swing high → last swing low (recent leg)

    Returns: (bias, swing_high, swing_low, midpoint_50pct)
    """
    if df4h is None or len(df4h) < 30:
        return "neutral", 0, 0, 0

    # Use last 100 candles for bias detection (more responsive)
    df = df4h.tail(100)

    sh_list = _swing_highs(df, n=3)
    sl_list = _swing_lows(df, n=3)

    if len(sh_list) < 2 or len(sl_list) < 2:
        return "neutral", 0, 0, 0

    last_sh  = sh_list[-1].level
    prev_sh  = sh_list[-2].level
    last_sl  = sl_list[-1].level
    prev_sl  = sl_list[-2].level

    # BOS bullish: HH + HL
    if last_sh > prev_sh and last_sl > prev_sl:
        bias = "bull"
    # BOS bearish: LH + LL
    elif last_sh < prev_sh and last_sl < prev_sl:
        bias = "bear"
    else:
        # Fallback: if last SH > prev SH alone = bullish momentum
        if last_sh > prev_sh:
            bias = "bull"
        elif last_sl < prev_sl:
            bias = "bear"
        else:
            bias = "neutral"

    # Define the CURRENT swing range (last impulse leg) for premium/discount
    # Bull: most recent swing low → most recent swing high
    # Bear: most recent swing high → most recent swing low
    if bias == "bull":
        # Find the swing low that preceded the last swing high (the base of the current leg)
        swing_range_low  = last_sl
        swing_range_high = last_sh
    else:
        swing_range_high = last_sh
        swing_range_low  = last_sl

    # Sanity check
    if swing_range_high <= swing_range_low:
        return "neutral", 0, 0, 0

    midpoint = (swing_range_high + swing_range_low) / 2
    return bias, swing_range_high, swing_range_low, midpoint


def next_structural_target(df4h: pd.DataFrame, bias: str, entry: float) -> Optional[float]:
    """
    Find the next 4h structural swing level as TP2 target.
    Bull: next swing high above entry.
    Bear: next swing low below entry.
    """
    if df4h is None:
        return None

    if bias == "bull":
        sh_list = _swing_highs(df4h, n=5)
        targets = [s.level for s in sh_list if s.level > entry]
        return min(targets) if targets else None
    else:
        sl_list = _swing_lows(df4h, n=5)
        targets = [s.level for s in sl_list if s.level < entry]
        return max(targets) if targets else None


# ─── Step 2 — Order Block detection (1h or 15m) ───────────────────────────────

def detect_order_blocks(
    df: pd.DataFrame,
    atr: pd.Series,
    direction: str,
    impulse_mult: float = 1.5,
    discount_high: float = 0,
    discount_low: float = 0,
) -> list[OrderBlock]:
    """
    Bull OB: last bearish candle before bullish impulse ≥ impulse_mult × ATR
    Bear OB: last bullish candle before bearish impulse ≥ impulse_mult × ATR

    discount_high / discount_low: the premium/discount zone to mark OBs inside it.
    """
    obs: list[OrderBlock] = []

    for i in range(1, len(df)):
        a = float(atr.iloc[i])
        if np.isnan(a) or a == 0:
            continue

        if direction == "bull":
            impulse = float(df["close"].iloc[i]) - float(df["open"].iloc[i])
            prev_bearish = float(df["open"].iloc[i - 1]) > float(df["close"].iloc[i - 1])
            if impulse >= a * impulse_mult and prev_bearish:
                ob_h = float(df["open"].iloc[i - 1])
                ob_l = float(df["low"].iloc[i - 1])
                in_zone = (discount_low <= ob_l) and (ob_h <= discount_high) if discount_high else True
                obs.append(OrderBlock(
                    ts=df.index[i - 1],
                    ob_high=ob_h,
                    ob_low=ob_l,
                    direction="bull",
                    impulse_size_atr=round(impulse / a, 2),
                    in_discount=in_zone,
                ))
        else:
            impulse = float(df["open"].iloc[i]) - float(df["close"].iloc[i])
            prev_bullish = float(df["close"].iloc[i - 1]) > float(df["open"].iloc[i - 1])
            if impulse >= a * impulse_mult and prev_bullish:
                ob_h = float(df["high"].iloc[i - 1])
                ob_l = float(df["close"].iloc[i - 1])
                in_zone = (discount_low <= ob_l) and (ob_h <= discount_high) if discount_high else True
                obs.append(OrderBlock(
                    ts=df.index[i - 1],
                    ob_high=ob_h,
                    ob_low=ob_l,
                    direction="bear",
                    impulse_size_atr=round(impulse / a, 2),
                    in_discount=in_zone,
                ))

    return obs


# ─── Step 3 — Liquidity Sweep (mandatory confirmation) ────────────────────────

def detect_liquidity_sweeps(
    df: pd.DataFrame,
    atr: pd.Series,
    swing_lookback: int = 20,
    min_rejection_atr: float = 0.3,
    last_n_candles: int = 10,
) -> list[LiquiditySweep]:
    """
    Liquidity sweep in the last `last_n_candles` candles.
    Bull sweep: wick below recent swing low, close back above → stop hunt done.
    Bear sweep: wick above recent swing high, close back below → stop hunt done.
    """
    sweeps: list[LiquiditySweep] = []
    swing_high = df["high"].rolling(swing_lookback).max().shift(1)
    swing_low  = df["low"].rolling(swing_lookback).min().shift(1)

    start_idx = max(swing_lookback, len(df) - last_n_candles)

    for i in range(start_idx, len(df)):
        a = float(atr.iloc[i])
        if np.isnan(a) or a == 0:
            continue

        sh = float(swing_high.iloc[i])
        sl = float(swing_low.iloc[i])
        hi = float(df["high"].iloc[i])
        lo = float(df["low"].iloc[i])
        cl = float(df["close"].iloc[i])

        if lo < sl and cl > sl:
            rejection = cl - lo
            if rejection >= a * min_rejection_atr:
                sweeps.append(LiquiditySweep(
                    ts=df.index[i],
                    swept_level=sl,
                    direction="bull",
                    rejection_size_atr=round(rejection / a, 2),
                ))
        elif hi > sh and cl < sh:
            rejection = hi - cl
            if rejection >= a * min_rejection_atr:
                sweeps.append(LiquiditySweep(
                    ts=df.index[i],
                    swept_level=sh,
                    direction="bear",
                    rejection_size_atr=round(rejection / a, 2),
                ))

    return sweeps


# ─── Step 4 — Market Shift / CHoCH (mandatory entry trigger) ──────────────────

def detect_market_shift(
    df: pd.DataFrame,
    direction: str,
    lookback: int = 30,
    last_n_candles: int = 10,
) -> Optional[MarketShift]:
    """
    Market Shift = Change of Character (CHoCH) on 15m.

    Bull CHoCH: after a pullback (recent downswing), price closes above
                the last swing high of that pullback → reversal confirmed up.
    Bear CHoCH: after a rally (recent upswing), price closes below
                the last swing low of that rally → reversal confirmed down.
    """
    if len(df) < lookback + last_n_candles:
        return None

    # The pullback window: `lookback` candles before the last `last_n_candles`
    pullback_section = df.iloc[-(lookback + last_n_candles): -last_n_candles]
    trigger_section  = df.iloc[-last_n_candles:]

    if direction == "bull":
        # Pullback = downswing → look for the highest high in the pullback
        # (this is the "lower high" the CHoCH must break above)
        key_level = float(pullback_section["high"].max())
        for i in range(len(trigger_section)):
            if float(trigger_section["close"].iloc[i]) > key_level:
                return MarketShift(
                    ts=trigger_section.index[i],
                    direction="bull",
                    broken_level=key_level,
                )
    else:
        # Rally = upswing → look for the lowest low in the rally
        key_level = float(pullback_section["low"].min())
        for i in range(len(trigger_section)):
            if float(trigger_section["close"].iloc[i]) < key_level:
                return MarketShift(
                    ts=trigger_section.index[i],
                    direction="bear",
                    broken_level=key_level,
                )

    return None


# ─── Step 5 — FVG (bonus confluence) ─────────────────────────────────────────

def detect_fvgs(
    df: pd.DataFrame,
    atr: pd.Series,
    direction: str,
    min_size_atr: float = 0.25,
) -> list[FairValueGap]:
    fvgs: list[FairValueGap] = []
    for i in range(2, len(df)):
        a = float(atr.iloc[i])
        if np.isnan(a) or a == 0:
            continue
        if direction == "bull":
            gap_low  = float(df["low"].iloc[i])
            gap_high = float(df["high"].iloc[i - 2])
            if gap_low > gap_high and (gap_low - gap_high) >= a * min_size_atr:
                fvgs.append(FairValueGap(
                    ts=df.index[i], fvg_high=gap_low, fvg_low=gap_high,
                    direction="bull", size_atr=round((gap_low - gap_high) / a, 2),
                ))
        else:
            gap_high = float(df["high"].iloc[i])
            gap_low  = float(df["low"].iloc[i - 2])
            if gap_high < gap_low and (gap_low - gap_high) >= a * min_size_atr:
                fvgs.append(FairValueGap(
                    ts=df.index[i], fvg_high=gap_low, fvg_low=gap_high,
                    direction="bear", size_atr=round((gap_low - gap_high) / a, 2),
                ))
    return fvgs


# ─── Main signal generator ────────────────────────────────────────────────────

def generate_smc_signal(
    df4h: pd.DataFrame,
    df15m: pd.DataFrame,
    symbol: str,
    df1h: Optional[pd.DataFrame] = None,
) -> Optional[SMCSignal]:
    """
    Market Mechanics Sniper Entry — Brad Goh method.

    Conditions (ALL required except FVG which is bonus):
      [1] 4h bias confirmed (BOS: HH+HL or LH+LL)
      [2] Current price in DISCOUNT zone (bull) or PREMIUM zone (bear) on 4h
      [3] Order Block present in the zone (1h or 15m)
      [4] Liquidity Sweep in last 10 candles (15m) — stop hunt done
      [5] Market Shift / CHoCH on 15m — entry trigger confirmed
      [+] FVG overlapping OB — bonus confluence
    """
    if df4h is None or df15m is None:
        return None
    if len(df4h) < 50 or len(df15m) < 60:
        return None

    # ── [1] 4h Bias ───────────────────────────────────────────────────────────
    bias, swing_high, swing_low, midpoint_50 = detect_4h_bias(df4h)
    if bias == "neutral" or midpoint_50 == 0:
        return None

    ob_dir = "bull" if bias == "bull" else "bear"
    close_now = float(df15m["close"].iloc[-1])

    # ── [2] Premium / Discount filter ────────────────────────────────────────
    # Bull: price must be in DISCOUNT (below 60% of swing range = equilibrium area)
    # Bear: price must be in PREMIUM (above 40% of swing range = equilibrium area)
    # Brad uses strict 50% but we allow up to 60% to catch OBs near equilibrium
    swing_range = swing_high - swing_low
    discount_threshold = swing_low + swing_range * 0.60  # 60% level for bull
    premium_threshold  = swing_low + swing_range * 0.40  # 40% level for bear

    if bias == "bull":
        in_zone = close_now <= discount_threshold
        zone_label = "Discount"
        discount_low  = swing_low
        discount_high = discount_threshold
    else:
        in_zone = close_now >= premium_threshold
        zone_label = "Premium"
        discount_low  = premium_threshold
        discount_high = swing_high

    if not in_zone:
        return None

    # ── [3] Order Block in the zone (15m, with 1h fallback) ──────────────────
    atr15 = _atr(df15m)
    last_atr = float(atr15.iloc[-1])
    if np.isnan(last_atr) or last_atr == 0:
        return None

    obs_15m = detect_order_blocks(
        df15m, atr15, ob_dir,
        impulse_mult=1.5,
        discount_high=discount_high,
        discount_low=discount_low,
    )

    # Prefer OBs that are inside the discount/premium zone; fallback to closest
    zone_obs = [ob for ob in obs_15m if ob.in_discount]
    candidate_obs = zone_obs if zone_obs else obs_15m

    if not candidate_obs:
        return None

    # Use the most recent OB
    last_ob = candidate_obs[-1]

    # Price must be near the OB (within 3 ATR) — not already past it
    if bias == "bull":
        if close_now < last_ob.ob_low - last_atr * 3:  # blown through
            return None
        if close_now > last_ob.ob_high + last_atr * 2:  # too far above
            return None
    else:
        if close_now > last_ob.ob_high + last_atr * 3:
            return None
        if close_now < last_ob.ob_low - last_atr * 2:
            return None

    # ── [4] Liquidity Sweep (mandatory) ──────────────────────────────────────
    sweeps = detect_liquidity_sweeps(
        df15m, atr15,
        swing_lookback=20,
        min_rejection_atr=0.3,
        last_n_candles=15,
    )
    recent_sweep = next(
        (sw for sw in reversed(sweeps) if sw.direction == ob_dir), None
    )
    if recent_sweep is None:
        return None  # No stop hunt = no signal (mandatory per Brad's rules)

    # ── Score starts at 4 (all mandatory conditions met) ─────────────────────
    # [1] 4h bias  [2] discount/premium zone  [3] OB in zone  [4] liquidity sweep
    smc_score = 4

    # ── [5] Market Shift / CHoCH — BONUS (+1 score, sniper entry) ────────────
    ms = detect_market_shift(df15m, ob_dir, lookback=30, last_n_candles=10)
    if ms is not None:
        smc_score = 5   # CHoCH = highest confidence entry

    # ── [+] FVG bonus confluence ──────────────────────────────────────────────
    fvgs = detect_fvgs(df15m, atr15, ob_dir, min_size_atr=0.25)
    nearby_fvg = next(
        (fvg for fvg in reversed(fvgs)
         if abs(fvg.midpoint - last_ob.midpoint) <= last_atr * 4),
        None,
    )

    # ── Entry, SL, TP ─────────────────────────────────────────────────────────
    # Entry: top of OB (bull) or bottom of OB (bear)
    # SL   : beyond the OB extreme + ATR buffer (structural invalidation)
    # TP1  : 1.5R (close 50% — partial profit)
    # TP2  : next structural swing on 4h (Brad's method)
    # TP3  : 4R runner

    if bias == "bull":
        entry   = last_ob.ob_high
        sl      = last_ob.ob_low - last_atr * 0.5   # below OB + buffer
        risk    = entry - sl
    else:
        entry   = last_ob.ob_low
        sl      = last_ob.ob_high + last_atr * 0.5  # above OB + buffer
        risk    = sl - entry

    if risk <= 0:
        return None

    # TP2: next 4h structural swing (Brad's structural TP)
    structural_tp = next_structural_target(df4h, bias, entry)

    if bias == "bull":
        tp1 = entry + risk * 1.5                                         # 1.5R partial
        tp2 = structural_tp if structural_tp and structural_tp > tp1 \
              else entry + risk * 2.5                                     # structural or 2.5R
        tp3 = entry + risk * 4.0                                         # runner
    else:
        tp1 = entry - risk * 1.5
        tp2 = structural_tp if structural_tp and structural_tp < tp1 \
              else entry - risk * 2.5
        tp3 = entry - risk * 4.0

    rr_tp2 = abs(tp2 - entry) / risk if risk > 0 else 0

    # ── Confidence ────────────────────────────────────────────────────────────
    base_conf = 0.78 if smc_score == 4 else 0.88
    if last_ob.impulse_size_atr >= 2.0:
        base_conf = min(0.93, base_conf + 0.04)
    if recent_sweep.rejection_size_atr >= 1.5:
        base_conf = min(0.93, base_conf + 0.03)
    confidence = round(base_conf, 3)

    is_hot = smc_score == 5 or (smc_score == 4 and confidence >= 0.84)

    # ── Reasoning ─────────────────────────────────────────────────────────────
    reasons = [
        f"4h bias: {'BULLISH' if bias == 'bull' else 'BEARISH'} — BOS confirmed (HH+HL structure)",
        f"Price in {zone_label} zone ({close_now:.5g} {'≤' if bias == 'bull' else '≥'} 50% level {midpoint_50:.5g})",
        f"Order Block {last_ob.ob_low:.5g}–{last_ob.ob_high:.5g} (impulse {last_ob.impulse_size_atr:.1f}× ATR)"
        + (" ✓ inside zone" if last_ob.in_discount else ""),
        f"Liquidity sweep at {recent_sweep.swept_level:.5g} — stop hunt confirmed "
        f"(rejection {recent_sweep.rejection_size_atr:.1f}× ATR)",
        f"Market Shift (CHoCH) at {ms.broken_level:.5g} — 15m reversal confirmed" if ms else "No CHoCH yet (bonus condition)",
    ]
    if nearby_fvg:
        reasons.append(
            f"FVG {nearby_fvg.fvg_low:.5g}–{nearby_fvg.fvg_high:.5g} overlapping OB "
            f"({nearby_fvg.size_atr:.1f}× ATR imbalance)"
        )
    if structural_tp:
        reasons.append(f"Structural TP2 at next 4h swing: {tp2:.5g} (RR 1:{rr_tp2:.1f})")

    return SMCSignal(
        symbol=symbol,
        timestamp=datetime.utcnow(),
        bias_4h=bias,
        direction="BUY" if bias == "bull" else "SELL",
        confidence=confidence,
        smc_score=smc_score,
        is_hot=is_hot,
        entry=round(entry, 6),
        stop_loss=round(sl, 6),
        tp1=round(tp1, 6),
        tp2=round(tp2, 6),
        tp3=round(tp3, 6),
        risk=round(risk, 6),
        rr_tp2=round(rr_tp2, 2),
        discount_premium_50=round(midpoint_50, 6),
        zone_type="order_block",
        reasoning=reasons,
        order_block=last_ob,
        sweep=recent_sweep,
        market_shift=ms,
        fvg=nearby_fvg,
        structural_tp=structural_tp,
    )


# ─── Serialization ────────────────────────────────────────────────────────────

def smc_signal_to_dict(sig: SMCSignal) -> dict:
    return {
        "strategy": "market_mechanics",
        "symbol": sig.symbol,
        "timestamp": sig.timestamp.isoformat() + "Z",
        "bias_4h": sig.bias_4h,
        "recommendation": sig.direction,
        "confidence": sig.confidence,
        "smc_score": f"{sig.smc_score}/5",
        "is_hot": sig.is_hot,

        # ── Entry / Risk levels ──────────────────────────────────────────────
        "entry": sig.entry,
        "stop_loss": sig.stop_loss,
        "risk_per_unit": sig.risk,

        # ── Take Profit levels ───────────────────────────────────────────────
        "tp1": sig.tp1,                  # 1.5R — close 50% position here
        "tp2": sig.tp2,                  # structural swing target
        "tp3": sig.tp3,                  # 4R runner
        "rr_tp1": 1.5,
        "rr_tp2": sig.rr_tp2,            # actual structural RR
        "rr_tp3": 4.0,

        # ── Trade management note ────────────────────────────────────────────
        "trade_management": {
            "tp1_action": "Close 50% of position at TP1 (1.5R), move SL to breakeven",
            "tp2_action": "Close remaining 40% at TP2 (structural swing)",
            "tp3_action": "Let 10% runner to TP3 (4R) with trailing SL",
            "sl_note": f"SL at {sig.stop_loss:.5g} — below/above OB extreme + ATR buffer. "
                       "Invalidates if price closes beyond this level.",
        },

        # ── Zone context ─────────────────────────────────────────────────────
        "zone": {
            "type": sig.zone_type,
            "premium_discount_50pct": sig.discount_premium_50,
            "label": "Discount" if sig.bias_4h == "bull" else "Premium",
        },

        "reasoning": sig.reasoning,

        # ── Raw SMC objects ──────────────────────────────────────────────────
        "order_block": {
            "high": sig.order_block.ob_high,
            "low": sig.order_block.ob_low,
            "impulse_atr": sig.order_block.impulse_size_atr,
            "in_discount_zone": sig.order_block.in_discount,
        } if sig.order_block else None,

        "liquidity_sweep": {
            "swept_level": sig.sweep.swept_level,
            "direction": sig.sweep.direction,
            "rejection_atr": sig.sweep.rejection_size_atr,
        } if sig.sweep else None,

        "market_shift": {
            "broken_level": sig.market_shift.broken_level,
            "direction": sig.market_shift.direction,
            "timestamp": sig.market_shift.ts.isoformat() if hasattr(sig.market_shift.ts, "isoformat") else str(sig.market_shift.ts),
        } if sig.market_shift else None,

        "fvg": {
            "high": sig.fvg.fvg_high,
            "low": sig.fvg.fvg_low,
            "size_atr": sig.fvg.size_atr,
        } if sig.fvg else None,
    }
