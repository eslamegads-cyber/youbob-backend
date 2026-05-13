from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from app.db.session import Base


class IdentityVerificationRequest(Base):
    __tablename__ = "identity_verification_requests"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)

    document_type = Column(String(50), nullable=False)
    legal_name = Column(String(255), nullable=False)
    national_id = Column(String(100), nullable=False)
    address = Column(Text, nullable=False)
    notes = Column(Text, nullable=True)

    id_front_path = Column(String(500), nullable=False)
    id_back_path = Column(String(500), nullable=False)
    face_front_path = Column(String(500), nullable=False)
    face_left_path = Column(String(500), nullable=False)
    face_right_path = Column(String(500), nullable=False)

    status = Column(String(30), nullable=False, default="pending", index=True)
    reviewer_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    review_notes = Column(Text, nullable=True)
    reviewed_at = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    user = relationship("User", foreign_keys=[user_id], back_populates="identity_requests")
    reviewer = relationship("User", foreign_keys=[reviewer_id])
