from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional

from app.routers.auth import get_current_user
from app.models.user import User
import app.services.alpaca_service as alpaca

router = APIRouter(prefix="/alpaca", tags=["alpaca"])


class MarketOrderRequest(BaseModel):
    symbol: str
    qty: float
    side: str  # BUY | SELL


class LimitOrderRequest(BaseModel):
    symbol: str
    qty: float
    side: str
    limit_price: float


def _run(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/account")
async def account(current_user: User = Depends(get_current_user)):
    return _run(alpaca.get_account)


@router.get("/positions")
async def positions(current_user: User = Depends(get_current_user)):
    return _run(alpaca.get_positions)


@router.get("/orders")
async def orders(status: str = "open", current_user: User = Depends(get_current_user)):
    return _run(alpaca.get_orders, status)


@router.post("/orders/market")
async def market_order(body: MarketOrderRequest, current_user: User = Depends(get_current_user)):
    return _run(alpaca.place_market_order, body.symbol, body.qty, body.side)


@router.post("/orders/limit")
async def limit_order(body: LimitOrderRequest, current_user: User = Depends(get_current_user)):
    return _run(alpaca.place_limit_order, body.symbol, body.qty, body.side, body.limit_price)


@router.delete("/orders/{order_id}")
async def cancel_order(order_id: str, current_user: User = Depends(get_current_user)):
    return _run(alpaca.cancel_order, order_id)


@router.delete("/positions/{symbol}")
async def close_position(symbol: str, current_user: User = Depends(get_current_user)):
    return _run(alpaca.close_position, symbol)


@router.get("/quote/{symbol}")
async def latest_quote(symbol: str, current_user: User = Depends(get_current_user)):
    return _run(alpaca.get_latest_quote, symbol)
