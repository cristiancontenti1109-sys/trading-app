from sqlalchemy import Column, String, DateTime, JSON, Boolean
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid
from app.database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    email = Column(String, unique=True, nullable=False, index=True)
    hashed_password = Column(String, nullable=False)
    subscription_tier = Column(String, default="free")
    settings_json = Column(JSON, default=lambda: {
        "hot_pattern_threshold": 0.75,
        "hot_volume_zscore": 3.0,
        "atr_multiplier": 0.5,
        "quiet_hours_start": "22:00",
        "quiet_hours_end": "07:00",
        "daily_notification_cap": 20,
        "markets_enabled": ["crypto", "stocks", "forex", "commodities"],
        "timeframes_enabled": ["1h", "4h", "1D"],
        "default_timeframe": "4h",
        "theme": "dark",
    })
    expo_push_token = Column(String, nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    watchlist = relationship("WatchlistItem", back_populates="user", cascade="all, delete-orphan")
    notifications = relationship("Notification", back_populates="user", cascade="all, delete-orphan")
