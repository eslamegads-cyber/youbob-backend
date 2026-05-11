from sqlalchemy import Column, Integer, ForeignKey, Boolean, DateTime
from datetime import datetime, timezone
from app.db.session import Base


class MessageStatus(Base):
    __tablename__ = "message_status"

    id = Column(Integer, primary_key=True)

    message_id = Column(Integer, ForeignKey("messages.id"))
    user_id = Column(Integer, ForeignKey("users.id"))

    is_seen = Column(Boolean, default=False)
    seen_at = Column(DateTime(timezone=True), nullable=True)