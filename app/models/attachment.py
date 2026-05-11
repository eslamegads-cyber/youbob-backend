from sqlalchemy import Column, Integer, String, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
from app.db.session import Base


class MessageAttachment(Base):
    __tablename__ = "message_attachments"

    id = Column(Integer, primary_key=True)

    message_id = Column(Integer, ForeignKey("messages.id"))

    file_url = Column(String, nullable=False)
    file_type = Column(String)  # image, video, file, audio

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    message = relationship("Message", backref="attachments")