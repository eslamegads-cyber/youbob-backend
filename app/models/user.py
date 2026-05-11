from sqlalchemy import Column, Integer, String, Boolean, DateTime
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
from app.db.session import Base
import uuid


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    uuid = Column(String, unique=True, index=True, default=lambda: str(uuid.uuid4()))

    full_name = Column(String, nullable=True)
    email = Column(String, unique=True, index=True, nullable=False)
    phone_number = Column(String, unique=True, index=True, nullable=True)
    hashed_password = Column(String, nullable=False)
    fcm_token = Column(String, nullable=True) 
    profile_pic = Column(String, nullable=True)
    cover_photo = Column(String, nullable=True)

    id_front = Column(String, nullable=True)
    id_back = Column(String, nullable=True)
    selfie = Column(String, nullable=True)

    is_active = Column(Boolean, default=False)
    is_verified = Column(Boolean, default=False)

    is_online = Column(Boolean, default=False)
    last_seen = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    sent_messages = relationship("Message", foreign_keys="Message.sender_id", back_populates="sender")
    received_messages = relationship("Message", foreign_keys="Message.recipient_id", back_populates="recipient")