import logging
from typing import Optional

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are an expert trading analyst assistant embedded in a professional trading platform.
You provide precise, actionable technical and market analysis for crypto, stocks, forex, and commodities.

Your style:
- Concise and professional (2-4 short paragraphs)
- Data-driven: reference specific indicator values and price levels when available
- Risk-aware: always mention stop loss and risk management
- Never claim certainty — use "setup suggests", "analysis indicates", "bias is"
- End with a single disclaimer line

When context is provided, always reference the specific numbers (RSI, ADX, entry zone, SL, TP).
Do not repeat the same context back verbatim — synthesize it into actionable insight."""


async def chat(message: str, symbol: Optional[str], context: dict) -> str:
    from app.config import settings
    api_key = getattr(settings, "anthropic_api_key", None)

    if api_key:
        return await _claude_chat(message, symbol, context, api_key)
    return _rule_based(message, symbol, context)


async def _claude_chat(message: str, symbol: Optional[str], context: dict, api_key: str) -> str:
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)

        ctx = ""
        if symbol:
            ctx += f"\n\nCurrent instrument: **{symbol}**"

        sig = context.get("signal")
        if sig:
            ind = sig.get("indicators", {})
            ctx += f"""
Signal ({sig.get('timeframe', '4h')} timeframe):
  Recommendation: {sig.get('recommendation')} | Confidence: {round(sig.get('confidence', 0) * 100)}%
  Entry zone: {sig.get('entry_zone', {}).get('low')} – {sig.get('entry_zone', {}).get('high')}
  Stop loss: {sig.get('stop_loss')} | TP1: {sig.get('tp1')} | TP2: {sig.get('target_price')}
  RSI: {ind.get('rsi', 'N/A')} | ADX: {ind.get('adx', 'N/A')} | Vol Z-score: {ind.get('vol_zscore', 'N/A')}
  Key confluences: {'; '.join(sig.get('reasoning', [])[:4])}"""

        news = context.get("news", [])
        if news:
            headlines = [n.get("title", "") for n in news[:3] if n.get("title")]
            if headlines:
                ctx += "\n\nRecent news:\n" + "\n".join(f"  • {h}" for h in headlines)

        response = client.messages.create(
            model="claude-opus-4-7",
            max_tokens=700,
            system=SYSTEM_PROMPT + ctx,
            messages=[{"role": "user", "content": message}],
        )
        return response.content[0].text
    except Exception as e:
        logger.error(f"Claude chat error: {e}")
        return _rule_based(message, symbol, context)


async def analyze_strategy_description(description: str, symbol: Optional[str]) -> dict:
    """
    Parse a natural-language strategy description and return optimal parameters + explanation.
    Returns: { explanation, params, rationale }
    """
    from app.config import settings
    api_key = getattr(settings, "anthropic_api_key", None)

    if api_key:
        return await _claude_analyze_strategy(description, symbol, api_key)
    return _rule_based_strategy_analysis(description, symbol)


async def _claude_analyze_strategy(description: str, symbol: Optional[str], api_key: str) -> dict:
    try:
        import anthropic, json
        client = anthropic.Anthropic(api_key=api_key)

        prompt = f"""You are an expert algorithmic trading strategy consultant.

A trader has described their strategy:
"{description}"
{f'Asset context: {symbol}' if symbol else ''}

Analyze this strategy description and return a JSON object with exactly these fields:
{{
  "explanation": "2-3 sentences explaining the strategy type and core logic in plain English",
  "params": {{
    "fast_ema": <integer 3-50>,
    "slow_ema": <integer 10-200>,
    "rsi_period": <integer 5-30>,
    "rsi_oversold": <number 10-45>,
    "rsi_overbought": <number 55-90>,
    "require_macd": <boolean>,
    "require_volume": <boolean>,
    "atr_multiplier": <number 0.5-4.0>
  }},
  "rationale": "2-3 sentences explaining WHY each key parameter was chosen for this strategy"
}}

Rules for parameter selection:
- Scalping/intraday: fast_ema 3-9, slow_ema 8-21, atr_multiplier 0.5-1.0
- Swing trading: fast_ema 9-21, slow_ema 21-55, atr_multiplier 1.5-2.5
- Trend following: fast_ema 20-50, slow_ema 50-200, require_macd true
- Mean reversion: tight RSI bands (oversold 35-40, overbought 60-65), require_volume true
- Momentum: rsi_oversold 40, rsi_overbought 70, require_macd true
- Conservative: require_macd true, require_volume true, atr_multiplier 2.0+
- Aggressive: looser thresholds, atr_multiplier 1.0-1.5

Respond with ONLY the JSON object, no other text."""

        response = client.messages.create(
            model="claude-opus-4-7",
            max_tokens=600,
            messages=[{"role": "user", "content": prompt}],
        )
        text = response.content[0].text.strip()
        # Strip markdown code fences if present
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        return json.loads(text.strip())
    except Exception as e:
        logger.error(f"Claude strategy analysis error: {e}")
        return _rule_based_strategy_analysis(description, symbol)


def _rule_based_strategy_analysis(description: str, symbol: Optional[str]) -> dict:
    """Keyword-based strategy parameter suggestion when no API key is available."""
    d = description.lower()

    # Detect strategy archetype from keywords
    is_scalping   = any(w in d for w in ["scalp", "1m", "5m", "quick", "fast", "intraday short"])
    is_swing      = any(w in d for w in ["swing", "few days", "week", "medium term", "days"])
    is_trend      = any(w in d for w in ["trend", "follow", "momentum long", "breakout", "continuation"])
    is_reversion  = any(w in d for w in ["mean reversion", "reversal", "oversold", "overbought", "bounce"])
    is_momentum   = any(w in d for w in ["momentum", "rsi", "strength", "accelerat"])
    is_conservative = any(w in d for w in ["safe", "conservative", "low risk", "slow", "careful", "confirm"])
    is_aggressive = any(w in d for w in ["aggressive", "high risk", "quick profit", "fast", "tight stop"])
    uses_macd     = any(w in d for w in ["macd", "crossover", "histogram", "signal line"])
    uses_volume   = any(w in d for w in ["volume", "vol", "participation", "smart money"])
    uses_ema      = any(w in d for w in ["ema", "moving average", "ma ", "sma"])
    uses_bb       = any(w in d for w in ["bollinger", "band", "squeeze"])

    # Default parameters
    params = {
        "fast_ema": 9, "slow_ema": 21, "rsi_period": 14,
        "rsi_oversold": 30.0, "rsi_overbought": 70.0,
        "require_macd": False, "require_volume": False, "atr_multiplier": 1.5,
    }
    explanation = ""
    rationale_parts = []

    if is_scalping:
        params.update({"fast_ema": 5, "slow_ema": 13, "rsi_period": 7,
                        "rsi_oversold": 25.0, "rsi_overbought": 75.0,
                        "require_macd": False, "require_volume": False, "atr_multiplier": 0.75})
        explanation = "Scalping strategy targeting small, rapid moves on short timeframes. Uses very responsive EMAs and a shorter RSI period to capture fast momentum shifts."
        rationale_parts = ["EMA 5/13 reacts quickly to price changes ideal for scalping", "RSI period 7 is sensitive enough for short-term entries", "ATR 0.75× keeps stops tight to preserve R/R on small moves"]

    elif is_swing:
        params.update({"fast_ema": 13, "slow_ema": 34, "rsi_period": 14,
                        "rsi_oversold": 35.0, "rsi_overbought": 65.0,
                        "require_macd": True, "require_volume": False, "atr_multiplier": 2.0})
        explanation = "Swing trading strategy designed to capture multi-day moves. Combines EMA crossovers with MACD confirmation to filter noise and avoid false breakouts."
        rationale_parts = ["EMA 13/34 is a classic swing pair with solid trend filtering", "MACD confirmation reduces false crossover signals", "ATR 2.0× gives trades room to develop over several sessions"]

    elif is_reversion:
        params.update({"fast_ema": 9, "slow_ema": 21, "rsi_period": 14,
                        "rsi_oversold": 38.0, "rsi_overbought": 62.0,
                        "require_macd": False, "require_volume": True, "atr_multiplier": 1.25})
        explanation = "Mean reversion strategy targeting price extremes. Enters when price is statistically stretched from fair value, requiring volume to confirm institutional participation at the reversal point."
        rationale_parts = ["Tighter RSI bands (38/62) catch genuine extremes earlier", "Volume requirement confirms the reversal has institutional backing", "ATR 1.25× stops are tight since reversion trades have clear invalidation levels"]

    elif is_trend:
        params.update({"fast_ema": 21, "slow_ema": 55, "rsi_period": 14,
                        "rsi_oversold": 40.0, "rsi_overbought": 70.0,
                        "require_macd": True, "require_volume": True, "atr_multiplier": 2.0})
        explanation = "Trend-following strategy that waits for strong directional momentum before entering. Uses longer EMAs to stay aligned with the primary trend and filters out choppy conditions."
        rationale_parts = ["EMA 21/55 filters out short-term noise while staying responsive to trend changes", "Both MACD and volume required for maximum confluence", "ATR 2.0× provides enough room for pullbacks within the trend"]

    elif is_momentum:
        params.update({"fast_ema": 9, "slow_ema": 21, "rsi_period": 14,
                        "rsi_oversold": 40.0, "rsi_overbought": 72.0,
                        "require_macd": True, "require_volume": False, "atr_multiplier": 1.5})
        explanation = "Momentum strategy that buys into strength rather than waiting for dips. RSI is kept in the bullish zone (40-72) to ensure entry during confirmed momentum, not exhaustion."
        rationale_parts = ["RSI 40 oversold threshold enters during pullbacks within an uptrend", "RSI 72 overbought avoids chasing extended moves", "MACD required to confirm momentum is building, not fading"]

    elif is_conservative:
        params.update({"fast_ema": 21, "slow_ema": 50, "rsi_period": 14,
                        "rsi_oversold": 30.0, "rsi_overbought": 70.0,
                        "require_macd": True, "require_volume": True, "atr_multiplier": 2.5})
        explanation = "Conservative strategy requiring multiple independent confirmations before entering. Prioritizes high-quality setups over trade frequency, accepting fewer but more reliable signals."
        rationale_parts = ["EMA 21/50 filters out short-term noise completely", "Both MACD and volume required — signals fire less often but with higher confidence", "ATR 2.5× wide stops prevent being stopped out by normal volatility"]

    elif is_aggressive:
        params.update({"fast_ema": 5, "slow_ema": 13, "rsi_period": 9,
                        "rsi_oversold": 25.0, "rsi_overbought": 75.0,
                        "require_macd": False, "require_volume": False, "atr_multiplier": 1.0})
        explanation = "Aggressive strategy prioritizing trade frequency and early entry over confirmation. Uses fast-reacting indicators to enter positions as soon as momentum shifts."
        rationale_parts = ["EMA 5/13 generates frequent crossovers for more trade opportunities", "No MACD/volume filters to avoid missing early moves", "ATR 1.0× tight stops maximize R/R but require active management"]

    else:
        # Default balanced strategy
        params.update({"fast_ema": 9, "slow_ema": 21, "rsi_period": 14,
                        "rsi_oversold": 30.0, "rsi_overbought": 70.0,
                        "require_macd": uses_macd, "require_volume": uses_volume, "atr_multiplier": 1.5})
        explanation = "Balanced strategy using classic EMA crossover with RSI momentum filter. Suitable for most market conditions and timeframes."
        rationale_parts = ["EMA 9/21 is a proven standard crossover pair", "RSI 30/70 classic thresholds avoid false extremes", "ATR 1.5× balanced stop provides good R/R across timeframes"]

    # Override MACD/volume if explicitly mentioned
    if uses_macd:
        params["require_macd"] = True
    if uses_volume:
        params["require_volume"] = True

    if not explanation:
        explanation = f"Strategy based on your description: {description[:120]}."

    return {
        "explanation": explanation,
        "params": params,
        "rationale": " ".join(rationale_parts[:3]),
    }


def _rule_based(message: str, symbol: Optional[str], context: dict) -> str:
    if not symbol:
        return "Select an instrument from your watchlist to get context-aware analysis."

    sig = context.get("signal")
    if not sig:
        return f"No signal data loaded for {symbol}. Click on the instrument to generate a fresh analysis first."

    rec = sig.get("recommendation", "HOLD")
    conf = round(sig.get("confidence", 0) * 100)
    ind = sig.get("indicators", {})
    rsi = ind.get("rsi", 50) or 50
    adx = ind.get("adx", 0) or 0
    vol_z = ind.get("vol_zscore", 0) or 0
    ez = sig.get("entry_zone", {})
    sl = sig.get("stop_loss")
    tp1 = sig.get("tp1")
    tp2 = sig.get("target_price")
    tf = sig.get("timeframe", "4h")
    reasoning = sig.get("reasoning", [])
    ml = message.lower()

    lines = []

    if any(w in ml for w in ["buy", "long", "bullish", "should i enter", "good time"]):
        if rec == "BUY":
            lines.append(f"**{symbol}** has an active BUY signal on the {tf} timeframe with {conf}% confidence. The technical setup supports a long entry in the zone **{ez.get('low')} – {ez.get('high')}**, with stop at **{sl}** and TP1 at **{tp1}** (1.5R).")
            lines.append(f"RSI at {rsi:.1f} is in the bullish zone with room to move. ADX at {adx:.0f} {'confirms a strong trend.' if adx > 25 else 'is developing — wait for a clean break before sizing up fully.'}")
        elif rec == "SELL":
            lines.append(f"Current analysis advises **against** buying {symbol} here — the {tf} signal is SELL with {conf}% confidence. Entering long against the trend significantly reduces your edge.")
            lines.append(f"Key bearish factors: {'; '.join(reasoning[:2]) if reasoning else 'bearish price structure'}. Consider waiting for a reversal confirmation before going long.")
        else:
            lines.append(f"{symbol} is in a **HOLD** state on {tf}. No clear directional edge — the model is waiting for conditions to align more clearly before committing to a direction.")
            lines.append(f"Current readings: RSI {rsi:.1f}, ADX {adx:.0f}. {'Low ADX suggests a ranging market.' if adx < 20 else 'Watch for a decisive break of key levels.'}")

    elif any(w in ml for w in ["sell", "short", "bearish", "going down"]):
        if rec == "SELL":
            lines.append(f"**{symbol}** has a SELL signal on {tf} with {conf}% confidence. Short entries are favored in the zone **{ez.get('low')} – {ez.get('high')}**, stop at **{sl}**, TP1 at **{tp1}**.")
            lines.append(f"Bearish confluences: {'; '.join(reasoning[:3]) if reasoning else 'bearish momentum and structure'}.")
        else:
            lines.append(f"Current analysis does **not** support a short position in {symbol}. The {tf} signal is {rec} ({conf}%) — shorting against the bias carries elevated risk.")

    elif "rsi" in ml:
        z = "overbought (>70) — longs may be exhausted" if rsi > 70 else "oversold (<30) — potential bounce zone" if rsi < 30 else f"neutral at {rsi:.1f}"
        lines.append(f"**{symbol} RSI is at {rsi:.1f}** — {z}. {'High RSI in a strong uptrend can persist for many candles.' if rsi > 70 and rec == 'BUY' else 'Oversold RSI is a necessary but not sufficient condition for a reversal — wait for a higher close confirmation.' if rsi < 30 else 'No extreme reading — momentum is balanced.'}")

    elif any(w in ml for w in ["stop", "risk", "loss", "sl", "tp", "target"]):
        lines.append(f"**Risk levels for {symbol}** ({tf}):")
        lines.append(f"  • Stop loss: **{sl}**\n  • TP1 (1.5R): **{tp1}**\n  • TP2 (3.0R): **{tp2}**")
        lines.append("Rule of thumb: risk no more than 1-2% of your account per trade. Size your position so that hitting the stop loss equals your predetermined loss amount.")

    elif any(w in ml for w in ["trend", "direction", "ema", "moving average"]):
        trend_str = "bullish" if rec == "BUY" else "bearish" if rec == "SELL" else "neutral/sideways"
        adx_str = "strong and directional" if adx > 30 else "developing" if adx > 20 else "weak — market is ranging"
        lines.append(f"**{symbol} trend ({tf}):** {trend_str}. ADX at {adx:.0f} is {adx_str}.")
        if reasoning:
            lines.append(f"Key trend factors: {'; '.join(r for r in reasoning if 'EMA' in r or 'trend' in r.lower() or 'slope' in r.lower())[:2] or reasoning[0]}.")

    elif any(w in ml for w in ["volume", "vol"]):
        vol_desc = f"elevated at +{vol_z:.1f}σ above average" if vol_z > 1 else f"below average ({vol_z:.1f}σ)" if vol_z < -0.5 else "near average"
        lines.append(f"**{symbol} volume** is {vol_desc} on the {tf} chart. {'Strong participation supports the current directional move.' if vol_z > 1.5 else 'Low volume moves are less reliable — wait for volume confirmation.'}")

    elif any(w in ml for w in ["news", "fundamental", "what's happening"]):
        news = context.get("news", [])
        if news:
            lines.append(f"Recent news for **{symbol}**:")
            for n in news[:3]:
                t = n.get("title", "")
                pub = n.get("publisher", "")
                if t:
                    lines.append(f"  • {t}{f' — {pub}' if pub else ''}")
        else:
            lines.append(f"No recent news data available for {symbol}. Check financial news sources for the latest developments.")

    else:
        lines.append(f"**{symbol}** analysis ({tf} timeframe): **{rec}** signal with {conf}% confidence.")
        if reasoning:
            lines.append(f"Key factors: {'; '.join(reasoning[:3])}.")
        lines.append(f"Entry zone: {ez.get('low')} – {ez.get('high')} | SL: {sl} | TP1: {tp1} | TP2: {tp2}")
        if adx > 25:
            lines.append(f"Trend is well-established (ADX {adx:.0f}) — favorable conditions for trend-following entries.")
        elif adx < 20:
            lines.append(f"Low ADX ({adx:.0f}) suggests a ranging environment. Consider mean-reversion tactics and tighter position sizing.")

    lines.append("\n*Not financial advice. Always apply your own judgment and risk management.*")
    return "\n\n".join(lines)
