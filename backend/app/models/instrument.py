from sqlalchemy import Column, String, Float, DateTime, Boolean, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid
from app.database import Base


class Instrument(Base):
    __tablename__ = "instruments"

    symbol = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    asset_class = Column(String, nullable=False)  # crypto, stocks, forex, commodities
    exchange = Column(String, nullable=True)
    tick_size = Column(Float, nullable=True)
    lot_size = Column(Float, nullable=True)
    last_price = Column(Float, nullable=True)
    last_updated = Column(DateTime, nullable=True)


class WatchlistItem(Base):
    __tablename__ = "watchlist_items"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    symbol = Column(String, ForeignKey("instruments.symbol"), nullable=False)
    pinned = Column(Boolean, default=False)
    added_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="watchlist")
    instrument = relationship("Instrument")
