from sqlalchemy import Column, Integer, ForeignKey, Boolean, DateTime
from datetime import datetime, timezone
from app.db.session import Base


class UserStatus(Base):
    __tablename__ = "user_status"

    user_id = Column(Integer, ForeignKey("users.id"), primary_key=True)

    is_online = Column(Boolean, default=False)
    last_seen = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))