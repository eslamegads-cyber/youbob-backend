from sqlalchemy import Column, Integer, ForeignKey
from app.db.session import Base


class BlockedUser(Base):
    __tablename__ = "blocked_users"

    id = Column(Integer, primary_key=True)

    blocker_id = Column(Integer, ForeignKey("users.id"))
    blocked_id = Column(Integer, ForeignKey("users.id"))