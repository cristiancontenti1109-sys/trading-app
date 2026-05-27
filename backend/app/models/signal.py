from sqlalchemy import Column, String, Float, DateTime, JSON, Integer, Boolean
from datetime import datetime
import uuid
from app.database import Base


class Signal(Base):
    __tablename__ = "signals"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    symbol = Column(String, nullable=False, index=True)
    timeframe = Column(String, nullable=False)
    ts = Column(DateTime, nullable=False, index=True)
    recommendation = Column(String, nullable=False)  # BUY / SELL / HOLD
    confidence = Column(Float, nullable=False)
    entry_low = Column(Float, nullable=True)
    entry_high = Column(Float, nullable=True)
    target_price = Column(Float, nullable=True)
    stop_loss = Column(Float, nullable=True)
    expected_days_min = Column(Integer, nullable=True)
    expected_days_max = Column(Integer, nullable=True)
    reasoning = Column(JSON, default=list)
    model_version = Column(String, default="rule-based-v1")
    is_hot = Column(Boolean, default=False)
    is_hot_confluence = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class SignalOutcome(Base):
    __tablename__ = "signal_outcomes"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    signal_id = Column(String, nullable=False, index=True)
    outcome = Column(String, nullable=True)  # hit_target, hit_stop, expired
    actual_return = Column(Float, nullable=True)
    actual_time_to_target = Column(Integer, nullable=True)  # days
    evaluated_at = Column(DateTime, nullable=True)
