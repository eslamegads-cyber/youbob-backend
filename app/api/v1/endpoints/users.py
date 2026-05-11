import os
import time

from fastapi import APIRouter, Depends, HTTPException, Body, status, UploadFile, File, Request, Form
from sqlalchemy.orm import Session
from typing import List

from app.db.session import get_db
from app.models.user import User  
from app.schemas.user import UserCreate, UserOut, PhoneSearchSchema, UserUpdate # ✅ تأكد من وجود UserUpdate في الشيمات
from app.core.security import get_password_hash 
from app.core.dependencies import oauth2_scheme, get_current_user 

router = APIRouter()

PROFILE_UPLOAD_DIR = os.path.join("app", "static", "uploads", "profiles")
os.makedirs(PROFILE_UPLOAD_DIR, exist_ok=True)

# 1. إنشاء مستخدم (Register)
@router.post("/", response_model=UserOut)
def create_user(user_in: UserCreate, db: Session = Depends(get_db)):
    # التحقق من البريد أو الهاتف لمنع التكرار
    user_exists = db.query(User).filter(
        (User.email == user_in.email) | (User.phone_number == user_in.phone_number)
    ).first()
    
    if user_exists:
        raise HTTPException(status_code=400, detail="الإيميل أو رقم الهاتف مسجل مسبقاً")
    
    new_user = User(
        full_name=user_in.full_name,
        email=user_in.email,
        phone_number=user_in.phone_number,
        hashed_password=get_password_hash(user_in.password)
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return new_user

# 2. تعديل بيانات المستخدم الحالي (Update Profile)
@router.put("/me", response_model=UserOut)
def update_user_me(
    user_in: UserUpdate, 
    db: Session = Depends(get_db), 
    current_user: User = Depends(get_current_user)
):
    # تحويل البيانات واستبعاد ما لم يتم إرساله
    update_data = user_in.dict(exclude_unset=True)
    
    if "password" in update_data:
        update_data["hashed_password"] = get_password_hash(update_data.pop("password"))

    for field, value in update_data.items():
        setattr(current_user, field, value)

    db.add(current_user)
    db.commit()
    db.refresh(current_user)
    return current_user

# 3. حذف حساب المستخدم (Delete Account)
@router.delete("/me", status_code=status.HTTP_204_NO_CONTENT)
def delete_user_me(
    db: Session = Depends(get_db), 
    current_user: User = Depends(get_current_user)
):
    db.delete(current_user)
    db.commit()
    return None

# 4. مزامنة جهات الاتصال
@router.post("/sync-contacts", response_model=List[UserOut])
def sync_contacts(
    data: PhoneSearchSchema, 
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    found_users = db.query(User).filter(
        User.phone_number.in_(data.phones),
        User.id != current_user.id
    ).all()
    return found_users

# 5. الحصول على بياناتي (Profile)
@router.get("/me", response_model=UserOut)
def read_user_me(current_user: User = Depends(get_current_user)):
    return current_user

# 6. عرض جميع المستخدمين
@router.get("/", response_model=List[UserOut])
def read_users(skip: int = 0, limit: int = 100, db: Session = Depends(get_db), token: str = Depends(oauth2_scheme)):
    return db.query(User).offset(skip).limit(limit).all()

# 7. تحديث FCM Token
@router.post("/update_fcm_token")
def update_fcm_token(
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    تحديث رمز Firebase Cloud Messaging للمستخدم
    """
    fcm_token = payload.get("fcm_token") if isinstance(payload, dict) else payload
    if not fcm_token:
        raise HTTPException(status_code=400, detail="fcm_token is required")

    current_user.fcm_token = fcm_token
    db.add(current_user)
    db.commit()
    db.refresh(current_user)
    return {"message": "FCM token updated successfully"}


@router.post("/me/photo", response_model=UserOut)
async def update_profile_photo(
    request: Request,
    image_type: str = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    رفع صورة الملف الشخصي أو صورة الغلاف.
    image_type: profile_pic أو cover_photo
    """
    if image_type not in {"profile_pic", "cover_photo"}:
        raise HTTPException(status_code=400, detail="image_type غير صالح")

    ext = os.path.splitext(file.filename or "")[1].lower()
    allowed_extensions = {".jpg", ".jpeg", ".png", ".webp"}
    content_type = (file.content_type or "").lower()

    # بعض أجهزة Android ترسل صور المعرض كـ application/octet-stream.
    # لذلك نقبل الملف إذا كان MIME صورة أو امتداده امتداد صورة معروف.
    if not content_type.startswith("image/") and ext not in allowed_extensions:
        raise HTTPException(
            status_code=400,
            detail=f"يجب رفع صورة فقط. النوع المستلم: {content_type or 'غير معروف'}",
        )

    if ext not in allowed_extensions:
        ext = ".jpg"

    file_name = f"{current_user.id}_{image_type}_{int(time.time() * 1000)}{ext}"
    file_path = os.path.join(PROFILE_UPLOAD_DIR, file_name)

    content = await file.read()
    with open(file_path, "wb") as buffer:
        buffer.write(content)

    base_url = str(request.base_url).rstrip("/")
    image_url = f"{base_url}/static/uploads/profiles/{file_name}"
    setattr(current_user, image_type, image_url)

    db.add(current_user)
    db.commit()
    db.refresh(current_user)
    return current_user
