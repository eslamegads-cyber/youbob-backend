import os
import time
import uuid

from fastapi import APIRouter, Depends, HTTPException, Body, status, UploadFile, File, Request, Form
from sqlalchemy.orm import Session
from typing import List

from app.db.session import get_db
from app.models.identity_verification import IdentityVerificationRequest
from app.models.user import User  
from app.schemas.user import UserCreate, UserOut, PhoneSearchSchema, UserUpdate # ✅ تأكد من وجود UserUpdate في الشيمات
from app.core.security import get_password_hash 
from app.core.dependencies import oauth2_scheme, get_current_user 

router = APIRouter()

PROFILE_UPLOAD_DIR = os.path.join("app", "static", "uploads", "profiles")
IDENTITY_UPLOAD_DIR = os.path.join("app", "static", "uploads", "identity")
os.makedirs(PROFILE_UPLOAD_DIR, exist_ok=True)
os.makedirs(IDENTITY_UPLOAD_DIR, exist_ok=True)
MAX_IDENTITY_FILE_SIZE = 6 * 1024 * 1024
ALLOWED_IDENTITY_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".avif", ".heic"}

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


async def _save_identity_file(
    file: UploadFile,
    field_name: str,
    user_id: int,
    base_url: str,
) -> str:
    ext = os.path.splitext(file.filename or "")[1].lower()
    content_type = (file.content_type or "").lower()
    if not content_type.startswith("image/") and ext not in ALLOWED_IDENTITY_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"{field_name}: يجب رفع صورة فقط")
    if ext not in ALLOWED_IDENTITY_EXTENSIONS:
        ext = ".jpg"

    user_dir = os.path.join(IDENTITY_UPLOAD_DIR, str(user_id))
    os.makedirs(user_dir, exist_ok=True)

    file_name = f"{field_name}_{uuid.uuid4().hex}{ext}"
    file_path = os.path.join(user_dir, file_name)
    size = 0
    with open(file_path, "wb") as buffer:
        while chunk := await file.read(1024 * 1024):
            size += len(chunk)
            if size > MAX_IDENTITY_FILE_SIZE:
                buffer.close()
                os.remove(file_path)
                raise HTTPException(
                    status_code=413,
                    detail=f"{field_name}: حجم الصورة يجب ألا يتجاوز 6MB",
                )
            buffer.write(chunk)

    return f"{base_url}/static/uploads/identity/{user_id}/{file_name}"


@router.post("/me/identity-verification", status_code=status.HTTP_201_CREATED)
async def submit_identity_verification(
    request: Request,
    document_type: str = Form(...),
    legal_name: str = Form(...),
    national_id: str = Form(...),
    address: str = Form(...),
    notes: str = Form(""),
    id_front: UploadFile = File(...),
    id_back: UploadFile = File(...),
    face_front: UploadFile = File(...),
    face_left: UploadFile = File(...),
    face_right: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    استقبال طلب تحقيق الهوية من التطبيق.
    يرفع صور الهوية وصور الوجه الثلاث، ويحفظ الطلب بحالة pending.
    """
    if current_user.identity_verification_status == "pending":
        pending = db.query(IdentityVerificationRequest).filter(
            IdentityVerificationRequest.user_id == current_user.id,
            IdentityVerificationRequest.status == "pending",
        ).first()
        if pending:
            raise HTTPException(status_code=400, detail="لديك طلب تحقق قيد المراجعة")

    base_url = str(request.base_url).rstrip("/")
    saved_files = {
        "id_front_path": await _save_identity_file(
            id_front, "id_front", current_user.id, base_url
        ),
        "id_back_path": await _save_identity_file(
            id_back, "id_back", current_user.id, base_url
        ),
        "face_front_path": await _save_identity_file(
            face_front, "face_front", current_user.id, base_url
        ),
        "face_left_path": await _save_identity_file(
            face_left, "face_left", current_user.id, base_url
        ),
        "face_right_path": await _save_identity_file(
            face_right, "face_right", current_user.id, base_url
        ),
    }

    verification_request = IdentityVerificationRequest(
        user_id=current_user.id,
        document_type=document_type.strip(),
        legal_name=legal_name.strip(),
        national_id=national_id.strip(),
        address=address.strip(),
        notes=notes.strip() or None,
        status="pending",
        **saved_files,
    )
    current_user.identity_verification_status = "pending"
    current_user.identity_verified = False

    db.add(verification_request)
    db.add(current_user)
    db.commit()
    db.refresh(verification_request)
    db.refresh(current_user)

    return {
        "id": verification_request.id,
        "status": verification_request.status,
        "identity_verified": current_user.identity_verified,
        "identity_verification_status": current_user.identity_verification_status,
        "message": "تم إرسال طلب تحقيق الهوية للمراجعة",
    }


@router.get("/me/identity-verification")
def get_my_identity_verification_status(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    latest = db.query(IdentityVerificationRequest).filter(
        IdentityVerificationRequest.user_id == current_user.id
    ).order_by(IdentityVerificationRequest.created_at.desc()).first()

    return {
        "identity_verified": current_user.identity_verified,
        "identity_verification_status": current_user.identity_verification_status,
        "latest_request_id": latest.id if latest else None,
        "latest_request_status": latest.status if latest else None,
        "review_notes": latest.review_notes if latest else None,
    }

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
