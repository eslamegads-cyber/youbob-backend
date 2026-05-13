from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship
from datetime import datetime, timezone

from app.db.session import Base


class Listing(Base):
    __tablename__ = "listings"

    id = Column(Integer, primary_key=True, index=True)
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)

    type = Column(String, nullable=False, index=True)
    title = Column(String, nullable=False, index=True)
    category = Column(String, nullable=True, index=True)
    description = Column(Text, nullable=False)
    amount = Column(String, nullable=True)
    location = Column(String, nullable=False, index=True)
    contact = Column(String, nullable=False)
    details = Column(Text, nullable=True)

    condition = Column(String, nullable=True)
    delivery = Column(String, nullable=True)
    work_type = Column(String, nullable=True)
    area = Column(String, nullable=True)
    rooms = Column(String, nullable=True)
    negotiable = Column(Boolean, default=True)
    is_active = Column(Boolean, default=True, index=True)

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    owner = relationship("User")
    images = relationship(
        "ListingImage",
        back_populates="listing",
        cascade="all, delete-orphan",
    )

    @property
    def image_urls(self):
        return [image.url for image in self.images]

    @property
    def seller_verified(self):
        return bool(getattr(self.owner, "identity_verified", False))
