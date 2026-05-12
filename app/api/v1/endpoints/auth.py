import json
import logging
import os
import re
import uuid
import aiofiles
from datetime import timedelta
from dotenv import load_dotenv

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect, BackgroundTasks, Query, File, UploadFile, Form, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from jose import jwt, JWTError
from pydantic import BaseModel
from typing import List

from fastapi_mail import FastMail, MessageSchema, ConnectionConfig, MessageType

from app.db.session import get_db, SessionLocal
from app.models.user import User
from app.models.message import Message
from app.models.conversation import Conversation

from app.core.security import (
    SECRET_KEY,
    ALGORITHM,
    ACCESS_TOKEN_EXPIRE_MINUTES,
    get_password_hash,
    verify_password,
    create_access_token,
    create_verification_token,
    verify_verification_token,
    create_password_reset_token,
    verify_password_reset_token
)

from app.core.chat_manager import manager

load_dotenv()

logger = logging.getLogger(__name__)
router = APIRouter()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/v1/chat/login")

# =========================
# 🔐 إعدادات الملفات والصور
# =========================
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB
ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/gif", "image/webp"}
STATIC_DIR = "app/static"
IMAGES_DIR = os.path.join(STATIC_DIR, "images")

async def save_file(file: UploadFile, folder: str, allowed_types=None):
    ext = file.filename.split(".")[-1].lower()
    if allowed_types and file.content_type not in allowed_types:
        raise HTTPException(status_code=400, detail="نوع الصورة غير مدعوم")
    filename = f"{uuid.uuid4().hex}.{ext}"
    file_path = os.path.join(folder, filename)
    size = 0
    async with aiofiles.open(file_path, "wb") as buffer:
        while chunk := await file.read(1024 * 1024):
            size += len(chunk)
            if size > MAX_FILE_SIZE:
                raise HTTPException(status_code=413, detail="حجم الملف كبير جداً")
            await buffer.write(chunk)
    return filename

# =========================
# 📧 إعدادات البريد الإلكتروني
# =========================
mail_config = ConnectionConfig(
    MAIL_USERNAME=os.getenv("MAIL_USERNAME"),
    MAIL_PASSWORD=os.getenv("MAIL_PASSWORD"),
    MAIL_FROM=os.getenv("MAIL_FROM"),
    MAIL_PORT=int(os.getenv("MAIL_PORT") or 587),
    MAIL_SERVER=os.getenv("MAIL_SERVER"),
    MAIL_STARTTLS=True,
    MAIL_SSL_TLS=False,
    USE_CREDENTIALS=True
)

def missing_mail_settings() -> List[str]:
    required_settings = [
        "MAIL_USERNAME",
        "MAIL_PASSWORD",
        "MAIL_FROM",
        "MAIL_SERVER",
        "PUBLIC_BASE_URL",
    ]
    return [key for key in required_settings if not os.getenv(key)]

async def send_verification_email(email: str, token: str):
    missing_settings = missing_mail_settings()
    if missing_settings:
        logger.error("Verification email skipped. Missing mail settings: %s", ", ".join(missing_settings))
        return

    base_url = os.getenv("PUBLIC_BASE_URL", "").rstrip("/")
    verify_url = f"{base_url}/api/v1/auth/verify-email?token={token}" if base_url else None
    action_html = (
        f'<p><a href="{verify_url}" '
        'style="display:inline-block;padding:12px 18px;background:#9B111E;'
        'color:#fff;text-decoration:none;border-radius:8px;">تفعيل الحساب</a></p>'
        if verify_url
        else f"<p>{token}</p>"
    )
    html_content = f"""
    <div style="text-align:center;font-family:Arial,sans-serif;">
        <h2>تفعيل الحساب</h2>
        <p>اضغط الزر التالي لتفعيل حسابك.</p>
        {action_html}
    </div>
    """
    message = MessageSchema(
        subject="تفعيل الحساب",
        recipients=[email],
        body=html_content,
        subtype=MessageType.html
    )
    fm = FastMail(mail_config)
    try:
        await fm.send_message(message)
        logger.info("Verification email sent to %s", email)
    except Exception:
        logger.exception("Verification email failed for %s", email)


async def send_password_reset_email(email: str, token: str):
    missing_settings = missing_mail_settings()
    if missing_settings:
        logger.error("Password reset email skipped. Missing mail settings: %s", ", ".join(missing_settings))
        return

    html_content = f"""
    <div style="text-align:center;font-family:Arial,sans-serif;">
        <h2>استعادة كلمة المرور</h2>
        <p>استخدم الرمز التالي داخل التطبيق لتعيين كلمة مرور جديدة.</p>
        <p style="direction:ltr;word-break:break-all;">{token}</p>
        <p>ينتهي هذا الرمز خلال ساعة واحدة.</p>
    </div>
    """
    message = MessageSchema(
        subject="استعادة كلمة المرور",
        recipients=[email],
        body=html_content,
        subtype=MessageType.html
    )
    fm = FastMail(mail_config)
    try:
        await fm.send_message(message)
        logger.info("Password reset email sent to %s", email)
    except Exception:
        logger.exception("Password reset email failed for %s", email)

# =========================
# 📦 SCHEMAS
# =========================
class ContactMatchSchema(BaseModel):
    phones: List[str]

# =========================
# 🧾 تسجيل حساب جديد (يدعم الصور)
# =========================
@router.post("/register")
async def register_user(
    background_tasks: BackgroundTasks,
    full_name: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    phone_number: str = Form(...),
    profile_pic: UploadFile = File(None),
    id_front: UploadFile = File(None),
    id_back: UploadFile = File(None),
    cover_photo: UploadFile = File(None),
    camera_verification: UploadFile = File(None),
    db: Session = Depends(get_db)
):
    if not re.match(r"^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[^A-Za-z0-9]).{8,}$", password):
        raise HTTPException(
            status_code=400,
            detail="كلمة المرور يجب أن تكون 8 أحرف على الأقل وتحتوي على حرف كبير وحرف صغير ورقم ورمز"
        )

    if not re.match(r"^\+?[0-9]{8,15}$", phone_number):
        raise HTTPException(status_code=400, detail="رقم الهاتف يجب أن يكون من 8 إلى 15 رقمًا")

    existing_user = db.query(User).filter(
        (User.email == email) | (User.phone_number == phone_number)
    ).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="البريد أو رقم الهاتف مستخدم بالفعل")

    uploaded_files = {}
    if profile_pic:
        uploaded_files["profile_url"] = f"/static/images/{await save_file(profile_pic, IMAGES_DIR, ALLOWED_IMAGE_TYPES)}"
    if id_front:
        uploaded_files["id_front_url"] = f"/static/images/{await save_file(id_front, IMAGES_DIR, ALLOWED_IMAGE_TYPES)}"
    if id_back:
        uploaded_files["id_back_url"] = f"/static/images/{await save_file(id_back, IMAGES_DIR, ALLOWED_IMAGE_TYPES)}"
    if cover_photo:
        uploaded_files["cover_url"] = f"/static/images/{await save_file(cover_photo, IMAGES_DIR, ALLOWED_IMAGE_TYPES)}"
    if camera_verification:
        uploaded_files["camera_url"] = f"/static/images/{await save_file(camera_verification, IMAGES_DIR, ALLOWED_IMAGE_TYPES)}"

    # 👇 تم تعديل الحقل الأخير ليصبح selfie بدلاً من الاسم القديم
    new_user = User(
        full_name=full_name,
        email=email,
        hashed_password=get_password_hash(password),
        phone_number=phone_number,
        is_active=False,
        profile_pic=uploaded_files.get("profile_url"),
        id_front=uploaded_files.get("id_front_url"),
        id_back=uploaded_files.get("id_back_url"),
        cover_photo=uploaded_files.get("cover_url"),
        selfie=uploaded_files.get("camera_url") 
    )

    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    token = create_verification_token(email)
    background_tasks.add_task(send_verification_email, email, token)

    return {"message": "تم إنشاء الحساب، يرجى تفعيل البريد"}

# =========================
# ✅ تفعيل البريد الإلكتروني
# =========================
@router.get("/verify-email")
async def verify_email(token: str, db: Session = Depends(get_db)):
    email = verify_verification_token(token)
    if not email:
        raise HTTPException(status_code=400, detail="توكن غير صالح")
    user = db.query(User).filter(User.email == email).first()
    if not user:
        raise HTTPException(status_code=404, detail="المستخدم غير موجود")
    user.is_active = True
    user.is_verified = True
    db.commit()
    return {"message": "تم تفعيل الحساب بنجاح"}


@router.post("/resend-verification")
async def resend_verification_email(
    background_tasks: BackgroundTasks,
    email: str = Form(...),
    db: Session = Depends(get_db)
):
    user = db.query(User).filter(User.email == email).first()
    if user and not user.is_active:
        token = create_verification_token(email)
        background_tasks.add_task(send_verification_email, email, token)

    return {"message": "إذا كان البريد مسجلاً وغير مفعل، سيتم إرسال رسالة تفعيل جديدة"}


# =========================
# 🔁 نسيت كلمة المرور
# =========================
@router.post("/forgot-password")
async def forgot_password(
    background_tasks: BackgroundTasks,
    email: str = Form(...),
    db: Session = Depends(get_db)
):
    user = db.query(User).filter(User.email == email).first()
    if user:
        token = create_password_reset_token(email)
        background_tasks.add_task(send_password_reset_email, email, token)

    return {"message": "إذا كان البريد مسجلاً، سيتم إرسال رسالة استعادة كلمة المرور"}


@router.post("/reset-password")
async def reset_password(
    token: str = Form(...),
    new_password: str = Form(...),
    db: Session = Depends(get_db)
):
    if not re.match(r"^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[^A-Za-z0-9]).{8,}$", new_password):
        raise HTTPException(
            status_code=400,
            detail="كلمة المرور يجب أن تكون 8 أحرف على الأقل وتحتوي على حرف كبير وحرف صغير ورقم ورمز"
        )

    email = verify_password_reset_token(token)
    if not email:
        raise HTTPException(status_code=400, detail="رمز الاستعادة غير صالح أو منتهي")

    user = db.query(User).filter(User.email == email).first()
    if not user:
        raise HTTPException(status_code=404, detail="المستخدم غير موجود")

    user.hashed_password = get_password_hash(new_password)
    db.commit()
    return {"message": "تم تغيير كلمة المرور بنجاح"}

# =========================
# 🔑 تسجيل الدخول (Login)
# =========================
@router.post("/login")
def login(db: Session = Depends(get_db), form_data: OAuth2PasswordRequestForm = Depends()):
    user = db.query(User).filter(User.email == form_data.username).first()
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="إيميل أو كلمة مرور غير صحيحة",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="يرجى تفعيل البريد الإلكتروني قبل تسجيل الدخول"
        )
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.email}, expires_delta=access_token_expires
    )
    return {
        "access_token": access_token, 
        "token_type": "bearer",
        "user_id": user.id
    }
