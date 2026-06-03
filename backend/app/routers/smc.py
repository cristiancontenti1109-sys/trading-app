"""
Market Mechanics Router (Brad Goh method)
-----------------------------------------
GET  /smc/signal/{symbol}   → segnale live Market Mechanics (no trade)
POST /smc/execute/{symbol}  → segnale + esecuzione Alpaca paper
GET  /smc/scan              → scansiona universe, ritorna setup attivi (score ≥ 4/5)

Trade management automatico:
  • Entry: market order
  • SL:    limit stop-loss (strutturale, dietro OB)
  • TP1:   limit order per 50% della posizione a 1.5R → SL si sposta a breakeven
  • TP2:   limit order per 40% sulla structural swing target
  • TP3:   trailing sul 10% restante (runner)
"""

import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.routers.auth import get_current_user
from app.models.user import User
from app.services.market_data import fetch_ohlcv
from app.services.smc_service import generate_smc_signal, smc_signal_to_dict, SMCSignal
import app.services.alpaca_service as alpaca

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/smc", tags=["smc"])

ALPACA_STOCKS = {
    "AAPL", "MSFT", "GOOGL", "AMZN", "TSLA", "NVDA", "META", "NFLX",
    "AMD", "SPY", "QQQ", "JPM", "BAC", "GS", "V", "MA",
}
ALPACA_CRYPTO = {
    "BTCUSD", "ETHUSD", "SOLUSD", "LINKUSD", "AVAXUSD",
}

SCAN_UNIVERSE = list(ALPACA_STOCKS) + list(ALPACA_CRYPTO)

MIN_SCORE_EXECUTE = 4   # mandatory: all 4 conditions met


async def _fetch_all(symbol: str):
    """Fetch 4h, 1h, and 15m concurrently."""
    df4h, df1h, df15m = await asyncio.gather(
        fetch_ohlcv(symbol, "4h",  limit=200),
        fetch_ohlcv(symbol, "1h",  limit=200),
        fetch_ohlcv(symbol, "15m", limit=300),
    )
    return df4h, df1h, df15m


def _position_size(sig: SMCSignal, risk_dollars: float, is_stock: bool) -> float:
    """
    Calculate position size from risk_dollars / risk_per_unit.
    Caps at 20% of available Alpaca buying power.
    """
    risk_per_unit = sig.risk
    if risk_per_unit <= 0:
        raise ValueError("Risk per unit is zero or negative")

    qty = risk_dollars / risk_per_unit
    if is_stock:
        qty = max(1, int(qty))
    else:
        qty = max(0.01, round(qty, 4))

    # Buying-power cap
    try:
        acct = alpaca.get_account()
        bp = float(acct["buying_power"])
        max_notional = bp * 0.20
        notional = qty * sig.entry
        if notional > max_notional and sig.entry > 0:
            if is_stock:
                qty = max(1, int(max_notional / sig.entry))
            else:
                qty = max(0.01, round(max_notional / sig.entry, 4))
    except Exception:
        pass

    return qty


def _place_full_trade(sig: SMCSignal, qty: float) -> dict:
    """
    Place a complete Market Mechanics trade on Alpaca:
      1. Market order (entry)
      2. Stop-loss limit order (structural SL)
      3. TP1 limit order for 50% of position (1.5R)
      4. TP2 limit order for 40% of position (structural swing)

    Returns dict with all order IDs and levels.
    """
    side = sig.direction  # "BUY" or "SELL"

    # 1. Entry — market order full size
    entry_order = alpaca.place_market_order(sig.symbol, qty, side)

    # TP split sizes
    qty_tp1 = round(qty * 0.50, 4)  # 50% at TP1
    qty_tp2 = round(qty * 0.40, 4)  # 40% at TP2
    # remaining 10% is runner (no automated limit — managed manually or trailing)

    close_side = "SELL" if side == "BUY" else "BUY"

    # 2. Stop Loss — structural (limit order at SL price for the full qty)
    try:
        sl_order = alpaca.place_limit_order(sig.symbol, qty, close_side, sig.stop_loss)
    except Exception as e:
        sl_order = {"error": str(e)}

    # 3. TP1 — 50% partial at 1.5R
    try:
        tp1_order = alpaca.place_limit_order(sig.symbol, qty_tp1, close_side, sig.tp1)
    except Exception as e:
        tp1_order = {"error": str(e)}

    # 4. TP2 — 40% at structural swing
    try:
        tp2_order = alpaca.place_limit_order(sig.symbol, qty_tp2, close_side, sig.tp2)
    except Exception as e:
        tp2_order = {"error": str(e)}

    return {
        "entry_order": entry_order,
        "sl_order": sl_order,
        "tp1_order": tp1_order,
        "tp2_order": tp2_order,
        "levels": {
            "entry": sig.entry,
            "stop_loss": sig.stop_loss,
            "tp1": sig.tp1,
            "tp2": sig.tp2,
            "tp3": sig.tp3,
            "risk_per_unit": sig.risk,
            "rr_tp1": 1.5,
            "rr_tp2": sig.rr_tp2,
            "rr_tp3": 4.0,
        },
        "size_breakdown": {
            "total_qty": qty,
            "tp1_qty": qty_tp1,
            "tp2_qty": qty_tp2,
            "runner_qty": round(qty - qty_tp1 - qty_tp2, 4),
        },
        "management_note": (
            "TP1 hit → move SL to breakeven. "
            "TP2 hit → trail the runner (10%) with 1 ATR trailing stop."
        ),
    }


class ExecuteRequest(BaseModel):
    risk_dollars: float = 200.0   # dollar risk per trade (Brad recommends 1-3% of account)


@router.get("/signal/{symbol}")
async def get_smc_signal(
    symbol: str,
    current_user: User = Depends(get_current_user),
):
    """Live Market Mechanics signal — no trade placed."""
    sym = symbol.upper()
    df4h, df1h, df15m = await _fetch_all(sym)

    if df4h is None or df15m is None:
        raise HTTPException(status_code=404, detail=f"No data for {sym}")

    sig = generate_smc_signal(df4h, df15m, sym, df1h)
    if sig is None:
        return {
            "symbol": sym,
            "signal": None,
            "message": "No Market Mechanics setup — not all 5 conditions met yet",
        }
    return smc_signal_to_dict(sig)


@router.post("/execute/{symbol}")
async def execute_smc_signal(
    symbol: str,
    body: ExecuteRequest,
    current_user: User = Depends(get_current_user),
):
    """
    Market Mechanics execution on Alpaca paper account.
    Places: entry market order + SL limit + TP1 limit (50%) + TP2 limit (40%).
    Only fires if ALL 4 mandatory conditions are met (score ≥ 4/5).
    """
    sym = symbol.upper()
    df4h, df1h, df15m = await _fetch_all(sym)

    if df4h is None or df15m is None:
        raise HTTPException(status_code=404, detail=f"No data for {sym}")

    sig = generate_smc_signal(df4h, df15m, sym, df1h)
    if sig is None:
        return {"symbol": sym, "executed": False,
                "reason": "Conditions not met — waiting for full confluence"}

    if sig.smc_score < MIN_SCORE_EXECUTE:
        return {
            "symbol": sym,
            "executed": False,
            "signal": smc_signal_to_dict(sig),
            "reason": f"Score {sig.smc_score}/5 — need ≥ {MIN_SCORE_EXECUTE}",
        }

    is_stock = sym in ALPACA_STOCKS
    try:
        qty = _position_size(sig, body.risk_dollars, is_stock)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    try:
        trade = _place_full_trade(sig, qty)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Alpaca error: {e}")

    return {
        "symbol": sym,
        "executed": True,
        "signal": smc_signal_to_dict(sig),
        "trade": trade,
        "actual_risk_dollars": round(sig.risk * qty, 2),
    }


@router.get("/scan")
async def scan_universe(
    min_score: int = Query(default=4, ge=1, le=5),
    current_user: User = Depends(get_current_user),
):
    """Scan all tradable symbols for active Market Mechanics setups."""
    results = []
    errors = []

    async def _scan_one(sym: str):
        try:
            df4h, df1h, df15m = await _fetch_all(sym)
            if df4h is None or df15m is None:
                return
            sig = generate_smc_signal(df4h, df15m, sym, df1h)
            if sig and sig.smc_score >= min_score:
                results.append(smc_signal_to_dict(sig))
        except Exception as e:
            errors.append({"symbol": sym, "error": str(e)})

    batch_size = 4
    for i in range(0, len(SCAN_UNIVERSE), batch_size):
        batch = SCAN_UNIVERSE[i:i + batch_size]
        await asyncio.gather(*[_scan_one(s) for s in batch])
        await asyncio.sleep(0.8)

    results.sort(key=lambda x: x["confidence"], reverse=True)

    return {
        "scanned": len(SCAN_UNIVERSE),
        "signals_found": len(results),
        "min_score_filter": f"{min_score}/5",
        "signals": results,
        "errors": errors,
    }
