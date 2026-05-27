from sqlalchemy import Column, String, DateTime, ForeignKey, Boolean
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid
from app.database import Base


class Notification(Base):
    __tablename__ = "notifications"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    signal_id = Column(String, nullable=True)
    type = Column(String, nullable=False)  # HOT, HOT_CONFLUENCE
    title = Column(String, nullable=False)
    body = Column(String, nullable=False)
    symbol = Column(String, nullable=False)
    sent_at = Column(DateTime, default=datetime.utcnow)
    delivered_at = Column(DateTime, nullable=True)
    opened_at = Column(DateTime, nullable=True)
    muted_until = Column(DateTime, nullable=True)

    user = relationship("User", back_populates="notifications")
