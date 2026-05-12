from typing import List, Optional

import os
import time

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile, status
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_user
from app.db.session import get_db
from app.models.listing import Listing
from app.models.user import User
from app.schemas.listing import ListingCreate, ListingOut, ListingUpdate

router = APIRouter()

LISTING_UPLOAD_DIR = os.path.join("app", "static", "uploads", "listings")
os.makedirs(LISTING_UPLOAD_DIR, exist_ok=True)


@router.post("/", response_model=ListingOut, status_code=status.HTTP_201_CREATED)
def create_listing(
    listing_in: ListingCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    listing = Listing(owner_id=current_user.id, **listing_in.model_dump())
    db.add(listing)
    db.commit()
    db.refresh(listing)
    return listing


@router.get("/", response_model=List[ListingOut])
def read_listings(
    skip: int = 0,
    limit: int = Query(default=50, le=100),
    type: Optional[str] = None,
    q: Optional[str] = None,
    include_inactive: bool = False,
    db: Session = Depends(get_db),
):
    query = db.query(Listing)
    if not include_inactive:
        query = query.filter(Listing.is_active == True)
    if type:
        query = query.filter(Listing.type == type)
    if q:
        pattern = f"%{q.strip()}%"
        query = query.filter(
            or_(
                Listing.title.ilike(pattern),
                Listing.description.ilike(pattern),
                Listing.category.ilike(pattern),
                Listing.location.ilike(pattern),
            )
        )
    return query.order_by(Listing.created_at.desc()).offset(skip).limit(limit).all()


@router.get("/me", response_model=List[ListingOut])
def read_my_listings(
    include_inactive: bool = True,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = db.query(Listing).filter(Listing.owner_id == current_user.id)
    if not include_inactive:
        query = query.filter(Listing.is_active == True)
    return query.order_by(Listing.created_at.desc()).all()


@router.get("/{listing_id}", response_model=ListingOut)
def read_listing(listing_id: int, db: Session = Depends(get_db)):
    listing = db.query(Listing).filter(Listing.id == listing_id).first()
    if not listing or not listing.is_active:
        raise HTTPException(status_code=404, detail="الإعلان غير موجود")
    return listing


@router.put("/{listing_id}", response_model=ListingOut)
def update_listing(
    listing_id: int,
    listing_in: ListingUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    listing = db.query(Listing).filter(Listing.id == listing_id).first()
    if not listing:
        raise HTTPException(status_code=404, detail="الإعلان غير موجود")
    if listing.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="غير مسموح بتعديل هذا الإعلان")

    for field, value in listing_in.model_dump(exclude_unset=True).items():
        setattr(listing, field, value)

    db.add(listing)
    db.commit()
    db.refresh(listing)
    return listing


@router.delete("/{listing_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_listing(
    listing_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    listing = db.query(Listing).filter(Listing.id == listing_id).first()
    if not listing:
        raise HTTPException(status_code=404, detail="الإعلان غير موجود")
    if listing.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="غير مسموح بحذف هذا الإعلان")

    listing.is_active = False
    db.add(listing)
    db.commit()
    return None


@router.post("/{listing_id}/images", response_model=ListingOut)
async def upload_listing_images(
    listing_id: int,
    request: Request,
    files: List[UploadFile] = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    listing = db.query(Listing).filter(Listing.id == listing_id).first()
    if not listing:
        raise HTTPException(status_code=404, detail="الإعلان غير موجود")
    if listing.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="غير مسموح بتعديل هذا الإعلان")

    from app.models.listing_image import ListingImage

    allowed_extensions = {".jpg", ".jpeg", ".png", ".webp"}
    base_url = str(request.base_url).rstrip("/")

    for file in files[:8]:
        ext = os.path.splitext(file.filename or "")[1].lower()
        content_type = (file.content_type or "").lower()
        if not content_type.startswith("image/") and ext not in allowed_extensions:
            raise HTTPException(status_code=400, detail="يجب رفع صور فقط")
        if ext not in allowed_extensions:
            ext = ".jpg"

        file_name = f"{current_user.id}_{listing_id}_{int(time.time() * 1000)}_{len(listing.images)}{ext}"
        file_path = os.path.join(LISTING_UPLOAD_DIR, file_name)
        content = await file.read()
        with open(file_path, "wb") as buffer:
            buffer.write(content)

        image = ListingImage(
            listing_id=listing.id,
            url=f"{base_url}/static/uploads/listings/{file_name}",
        )
        db.add(image)

    db.commit()
    db.refresh(listing)
    return listing
