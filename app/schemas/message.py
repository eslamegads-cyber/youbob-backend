from pydantic import BaseModel
from datetime import datetime

class MessageCreate(BaseModel):
    recipient_id: int
    content: str

class MessageOut(BaseModel):
    id: int
    sender_id: int
    recipient_id: int
    content: str
    timestamp: datetime

    class Config:
        from_attributes = True
