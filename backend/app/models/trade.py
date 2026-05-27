from sqlalchemy import Column, String, Float, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid
from app.database import Base


class Trade(Base):
    __tablename__ = "trades"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    symbol = Column(String, nullable=False)
    direction = Column(String, nullable=False)   # BUY / SELL
    entry_price = Column(Float, nullable=False)
    exit_price = Column(Float, nullable=True)
    size = Column(Float, nullable=False, default=1.0)
    status = Column(String, default="open")      # open / closed
    notes = Column(Text, nullable=True)
    opened_at = Column(DateTime, default=datetime.utcnow)
    closed_at = Column(DateTime, nullable=True)

    user = relationship("User")

    @property
    def pnl(self):
        if self.exit_price is None:
            return None
        if self.direction == "BUY":
            return round((self.exit_price - self.entry_price) * self.size, 6)
        else:
            return round((self.entry_price - self.exit_price) * self.size, 6)

    @property
    def pnl_pct(self):
        if self.exit_price is None or self.entry_price == 0:
            return None
        if self.direction == "BUY":
            return round((self.exit_price - self.entry_price) / self.entry_price * 100, 2)
        else:
            return round((self.entry_price - self.exit_price) / self.entry_price * 100, 2)
