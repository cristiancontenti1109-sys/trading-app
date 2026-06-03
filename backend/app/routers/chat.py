from fastapi import APIRouter, Depends
from pydantic import BaseModel
from typing import Optional

from app.models.user import User
from app.routers.auth import get_current_user

router = APIRouter(prefix="/chat", tags=["chat"])


class ChatRequest(BaseModel):
    message: str
    symbol: Optional[str] = None
    timeframe: str = "4h"
    signal: Optional[dict] = None
    news: Optional[list] = None


class StrategyAnalysisRequest(BaseModel):
    description: str
    symbol: Optional[str] = None


@router.post("/")
async def chat_endpoint(
    req: ChatRequest,
    current_user: User = Depends(get_current_user),
):
    from app.services.ai_service import chat
    context = {"signal": req.signal, "news": req.news or []}
    reply = await chat(req.message, req.symbol, context)
    return {"reply": reply}


@router.post("/strategy")
async def analyze_strategy(
    req: StrategyAnalysisRequest,
    current_user: User = Depends(get_current_user),
):
    """Analyze a natural-language strategy description and return optimal parameters."""
    from app.services.ai_service import analyze_strategy_description
    result = await analyze_strategy_description(req.description, req.symbol)
    return result
