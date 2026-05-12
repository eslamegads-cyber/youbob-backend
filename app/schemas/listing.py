from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class ListingBase(BaseModel):
    type: str = Field(..., min_length=2, max_length=50)
    title: str = Field(..., min_length=2, max_length=160)
    category: Optional[str] = Field(default=None, max_length=80)
    description: str = Field(..., min_length=3)
    amount: Optional[str] = Field(default=None, max_length=80)
    location: str = Field(..., min_length=2, max_length=160)
    contact: str = Field(..., min_length=3, max_length=160)
    details: Optional[str] = None
    condition: Optional[str] = Field(default=None, max_length=80)
    delivery: Optional[str] = Field(default=None, max_length=80)
    work_type: Optional[str] = Field(default=None, max_length=80)
    area: Optional[str] = Field(default=None, max_length=80)
    rooms: Optional[str] = Field(default=None, max_length=80)
    negotiable: bool = True


class ListingCreate(ListingBase):
    pass


class ListingUpdate(BaseModel):
    type: Optional[str] = Field(default=None, min_length=2, max_length=50)
    title: Optional[str] = Field(default=None, min_length=2, max_length=160)
    category: Optional[str] = Field(default=None, max_length=80)
    description: Optional[str] = Field(default=None, min_length=3)
    amount: Optional[str] = Field(default=None, max_length=80)
    location: Optional[str] = Field(default=None, min_length=2, max_length=160)
    contact: Optional[str] = Field(default=None, min_length=3, max_length=160)
    details: Optional[str] = None
    condition: Optional[str] = Field(default=None, max_length=80)
    delivery: Optional[str] = Field(default=None, max_length=80)
    work_type: Optional[str] = Field(default=None, max_length=80)
    area: Optional[str] = Field(default=None, max_length=80)
    rooms: Optional[str] = Field(default=None, max_length=80)
    negotiable: Optional[bool] = None
    is_active: Optional[bool] = None


class ListingOut(ListingBase):
    id: int
    owner_id: int
    is_active: bool
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    image_urls: List[str] = Field(default_factory=list)

    class Config:
        from_attributes = True
