from sqlalchemy import Column, Integer, String, ForeignKey
from app.db.session import Base


class MessageReaction(Base):
    __tablename__ = "message_reactions"

    id = Column(Integer, primary_key=True)

    message_id = Column(Integer, ForeignKey("messages.id"))
    user_id = Column(Integer, ForeignKey("users.id"))

    reaction = Column(String)  # ❤️ 😂 😮 😡