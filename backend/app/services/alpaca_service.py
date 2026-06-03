from alpaca.trading.client import TradingClient
from alpaca.trading.requests import (
    MarketOrderRequest, LimitOrderRequest, GetOrdersRequest,
    TakeProfitRequest, StopLossRequest,
)
from alpaca.trading.enums import OrderSide, TimeInForce, QueryOrderStatus, OrderClass
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockLatestQuoteRequest

from app.config import settings


def _trading_client() -> TradingClient:
    return TradingClient(
        api_key=settings.alpaca_api_key,
        secret_key=settings.alpaca_secret_key,
        paper=True,
    )


def _data_client() -> StockHistoricalDataClient:
    return StockHistoricalDataClient(
        api_key=settings.alpaca_api_key,
        secret_key=settings.alpaca_secret_key,
    )


# ── Account ───────────────────────────────────────────────────────────────────

def get_account() -> dict:
    client = _trading_client()
    acct = client.get_account()
    return {
        "id": str(acct.id),
        "status": str(acct.status),
        "currency": acct.currency,
        "cash": float(acct.cash),
        "portfolio_value": float(acct.portfolio_value),
        "buying_power": float(acct.buying_power),
        "equity": float(acct.equity),
        "last_equity": float(acct.last_equity),
        "day_trade_count": acct.daytrade_count,
        "pattern_day_trader": acct.pattern_day_trader,
    }


# ── Positions ─────────────────────────────────────────────────────────────────

def get_positions() -> list:
    client = _trading_client()
    positions = client.get_all_positions()
    return [
        {
            "symbol": p.symbol,
            "qty": float(p.qty),
            "side": str(p.side),
            "avg_entry_price": float(p.avg_entry_price),
            "current_price": float(p.current_price) if p.current_price else None,
            "market_value": float(p.market_value) if p.market_value else None,
            "unrealized_pl": float(p.unrealized_pl) if p.unrealized_pl else None,
            "unrealized_plpc": float(p.unrealized_plpc) if p.unrealized_plpc else None,
        }
        for p in positions
    ]


# ── Orders ────────────────────────────────────────────────────────────────────

def get_orders(status: str = "open") -> list:
    client = _trading_client()
    qs = QueryOrderStatus.OPEN if status == "open" else QueryOrderStatus.CLOSED
    orders = client.get_orders(GetOrdersRequest(status=qs, limit=50))
    return [_order_to_dict(o) for o in orders]


def cancel_all_orders() -> dict:
    client = _trading_client()
    client.cancel_orders()
    return {"cancelled": "all"}


def cancel_order(order_id: str) -> dict:
    client = _trading_client()
    client.cancel_order_by_id(order_id)
    return {"cancelled": order_id}


def close_position(symbol: str) -> dict:
    client = _trading_client()
    result = client.close_position(symbol.upper())
    return _order_to_dict(result)


# ── Simple orders ─────────────────────────────────────────────────────────────

def place_market_order(symbol: str, qty: float, side: str) -> dict:
    client = _trading_client()
    req = MarketOrderRequest(
        symbol=symbol.upper(),
        qty=qty,
        side=OrderSide.BUY if side.upper() == "BUY" else OrderSide.SELL,
        time_in_force=TimeInForce.DAY,
    )
    return _order_to_dict(client.submit_order(req))


def place_limit_order(symbol: str, qty: float, side: str, limit_price: float) -> dict:
    client = _trading_client()
    req = LimitOrderRequest(
        symbol=symbol.upper(),
        qty=qty,
        side=OrderSide.BUY if side.upper() == "BUY" else OrderSide.SELL,
        time_in_force=TimeInForce.GTC,
        limit_price=round(limit_price, 2),
    )
    return _order_to_dict(client.submit_order(req))


# ── Bracket order (entry + SL + TP1 in one atomic OCO block) ─────────────────

def place_bracket_order(
    symbol: str,
    qty: float,
    side: str,
    take_profit_price: float,
    stop_loss_price: float,
    stop_loss_limit_price=None,
) -> dict:
    """
    Bracket order: market entry + take_profit limit + stop_loss stop.
    Alpaca OCO: when one leg fills, the other is cancelled automatically.

    stop_loss_limit_price: if provided, places a stop-limit instead of a stop.
                           Set slightly below stop_loss_price for slippage protection.
    """
    client = _trading_client()

    # SL limit price: 0.10% worse than stop for stocks, ensures fill
    sl_limit = stop_loss_limit_price or round(
        stop_loss_price * (0.999 if side.upper() == "BUY" else 1.001), 2
    )

    req = MarketOrderRequest(
        symbol=symbol.upper(),
        qty=qty,
        side=OrderSide.BUY if side.upper() == "BUY" else OrderSide.SELL,
        time_in_force=TimeInForce.DAY,
        order_class=OrderClass.BRACKET,
        take_profit=TakeProfitRequest(
            limit_price=round(take_profit_price, 2),
        ),
        stop_loss=StopLossRequest(
            stop_price=round(stop_loss_price, 2),
            limit_price=round(sl_limit, 2),
        ),
    )

    order = client.submit_order(req)
    return _order_to_dict(order)


def place_oco_exit(
    symbol: str,
    qty: float,
    close_side: str,
    take_profit_price: float,
    stop_loss_price: float,
) -> dict:
    """
    OCO exit order: TP limit + SL stop.
    Used to attach exits to an already-open position.
    """
    client = _trading_client()
    from alpaca.trading.requests import LimitOrderRequest
    from alpaca.trading.enums import OrderClass as OC

    sl_limit = round(
        stop_loss_price * (0.999 if close_side.upper() == "SELL" else 1.001), 2
    )

    req = LimitOrderRequest(
        symbol=symbol.upper(),
        qty=qty,
        side=OrderSide.SELL if close_side.upper() == "SELL" else OrderSide.BUY,
        time_in_force=TimeInForce.GTC,
        limit_price=round(take_profit_price, 2),
        order_class=OC.OCO,
        stop_loss=StopLossRequest(
            stop_price=round(stop_loss_price, 2),
            limit_price=round(sl_limit, 2),
        ),
    )
    return _order_to_dict(client.submit_order(req))


# ── Market Mechanics full trade ───────────────────────────────────────────────

def place_mm_trade(
    symbol: str,
    qty: int,
    side: str,
    sl: float,
    tp1: float,
    tp2: float,
) -> dict:
    """
    Market Mechanics trade management (Brad Goh method):
      • Leg A — 50% of position: bracket order (market entry + TP1 + SL)
      • Leg B — 40% of position: bracket order (market entry + TP2 + SL)
      • Leg C — 10% runner: plain market order (managed manually with trailing SL)

    When TP1 fills → Alpaca automatically cancels the SL on Leg A.
    At that point, you should manually move the SL on Leg B to breakeven.
    """
    client = _trading_client()
    order_side = OrderSide.BUY if side.upper() == "BUY" else OrderSide.SELL

    qty_a = max(1, round(qty * 0.50))   # 50% → TP1
    qty_b = max(1, round(qty * 0.40))   # 40% → TP2
    qty_c = max(0, qty - qty_a - qty_b) # 10% runner

    sl_limit = round(sl * (0.999 if side.upper() == "BUY" else 1.001), 2)

    results = {}

    # Leg A — TP1 bracket
    try:
        req_a = MarketOrderRequest(
            symbol=symbol.upper(),
            qty=qty_a,
            side=order_side,
            time_in_force=TimeInForce.DAY,
            order_class=OrderClass.BRACKET,
            take_profit=TakeProfitRequest(limit_price=round(tp1, 2)),
            stop_loss=StopLossRequest(
                stop_price=round(sl, 2),
                limit_price=sl_limit,
            ),
        )
        results["leg_a_tp1"] = _order_to_dict(client.submit_order(req_a))
    except Exception as e:
        results["leg_a_tp1"] = {"error": str(e)}

    # Leg B — TP2 bracket
    try:
        req_b = MarketOrderRequest(
            symbol=symbol.upper(),
            qty=qty_b,
            side=order_side,
            time_in_force=TimeInForce.DAY,
            order_class=OrderClass.BRACKET,
            take_profit=TakeProfitRequest(limit_price=round(tp2, 2)),
            stop_loss=StopLossRequest(
                stop_price=round(sl, 2),
                limit_price=sl_limit,
            ),
        )
        results["leg_b_tp2"] = _order_to_dict(client.submit_order(req_b))
    except Exception as e:
        results["leg_b_tp2"] = {"error": str(e)}

    # Leg C — runner (market only, no automated exit)
    if qty_c > 0:
        try:
            req_c = MarketOrderRequest(
                symbol=symbol.upper(),
                qty=qty_c,
                side=order_side,
                time_in_force=TimeInForce.DAY,
            )
            results["leg_c_runner"] = _order_to_dict(client.submit_order(req_c))
        except Exception as e:
            results["leg_c_runner"] = {"error": str(e)}

    results["summary"] = {
        "symbol": symbol.upper(),
        "side": side.upper(),
        "total_qty": qty,
        "qty_a_tp1": qty_a,
        "qty_b_tp2": qty_b,
        "qty_c_runner": qty_c,
        "stop_loss": sl,
        "tp1": tp1,
        "tp2": tp2,
        "management": "TP1 fills → cancel SL leg A auto. Move SL leg B to breakeven manually.",
    }

    return results


def _order_to_dict(o) -> dict:
    return {
        "id": str(o.id),
        "client_order_id": str(o.client_order_id),
        "symbol": o.symbol,
        "qty": float(o.qty) if o.qty else None,
        "filled_qty": float(o.filled_qty) if o.filled_qty else 0,
        "side": str(o.side),
        "type": str(o.order_type),
        "time_in_force": str(o.time_in_force),
        "limit_price": float(o.limit_price) if o.limit_price else None,
        "stop_price": float(o.stop_price) if getattr(o, "stop_price", None) else None,
        "filled_avg_price": float(o.filled_avg_price) if o.filled_avg_price else None,
        "status": str(o.status),
        "order_class": str(o.order_class) if getattr(o, "order_class", None) else None,
        "created_at": o.created_at.isoformat() if o.created_at else None,
        "submitted_at": o.submitted_at.isoformat() if o.submitted_at else None,
        "filled_at": o.filled_at.isoformat() if o.filled_at else None,
    }


# ── Market Data ───────────────────────────────────────────────────────────────

def get_latest_quote(symbol: str) -> dict:
    client = _data_client()
    req = StockLatestQuoteRequest(symbol_or_symbols=symbol.upper())
    quotes = client.get_stock_latest_quote(req)
    q = quotes[symbol.upper()]
    return {
        "symbol": symbol.upper(),
        "bid": float(q.bid_price),
        "ask": float(q.ask_price),
        "bid_size": float(q.bid_size),
        "ask_size": float(q.ask_size),
        "timestamp": q.timestamp.isoformat(),
    }
