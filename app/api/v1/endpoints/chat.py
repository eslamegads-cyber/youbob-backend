import json
import os
import time
from dotenv import load_dotenv
from fastapi import APIRouter, Depends, Form, HTTPException, WebSocket, WebSocketDisconnect, Query, UploadFile, File, Request
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from jose import jwt, JWTError
from pydantic import BaseModel
from typing import Any, List
from fastapi_mail import FastMail, MessageSchema, ConnectionConfig, MessageType

from app.db.session import get_db, SessionLocal
from app.models.user import User
from app.models.message import Message
from app.models.conversation import Conversation
from app.models.attachment import MessageAttachment
from app.models.message_status import MessageStatus
from app.models.reaction import MessageReaction

from app.core.security import SECRET_KEY, ALGORITHM
from app.core.chat_manager import manager
from app.core.dependencies import oauth2_scheme

load_dotenv()

# تعريف الراوتر الخاص بملف الشات
router = APIRouter()

# ربط التحقق بالتوكن مع مسار تسجيل الدخول في ملف auth
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/v1/chat/login")


# =========================
# 📦 SCHEMAS (نماذج البيانات)
# =========================
class ContactMatchSchema(BaseModel):
    phones: List[str]


class EmailBackupSchema(BaseModel):
    peer_id: int
    peer_name: str | None = None
    messages: List[dict[str, Any]]


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


def get_current_user_from_token(token: str, db: Session) -> User:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email = payload.get("sub")
        current_user = db.query(User).filter(User.email == email).first()
        if not current_user:
            raise HTTPException(status_code=401, detail="المستخدم غير موجود")
        return current_user
    except JWTError:
        raise HTTPException(status_code=401, detail="التوكن غير صالح")


# =========================
# 🔥 مطابقة جهات الاتصال (Match Contacts)
# =========================
@router.post("/match-contacts")
async def match_contacts(
    data: ContactMatchSchema,
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email = payload.get("sub")
        current_user = db.query(User).filter(User.email == email).first()
    except JWTError:
        raise HTTPException(status_code=401, detail="غير مصرح")

    matched = db.query(User).filter(User.phone_number.in_(data.phones)).all()

    return [
        {
            "id": u.id,
            "phone": u.phone_number,
            "email": u.email
        }
        for u in matched if u.id != current_user.id
    ]


# =========================
# 💬 نظام الشات المباشر (WEBSOCKET)
# =========================
@router.websocket("/ws/{user_id}")
async def websocket_endpoint(
    websocket: WebSocket,
    user_id: int,
    token: str = Query(...)
):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email = payload.get("sub")

        with SessionLocal() as db:
            user = db.query(User).filter(User.email == email).first()

            if not user or user.id != user_id:
                await websocket.close(code=1008)
                return

    except JWTError:
        await websocket.close(code=1008)
        return

    await manager.connect(user_id, websocket)

    try:
        while True:
            data = await websocket.receive_text()
            msg = json.loads(data)

            receiver_id = msg.get("receiver_id")
            content = msg.get("content")
            msg_type = msg.get("message_type", "text")

            if not receiver_id:
                continue

            # =========================
            # 📞 أحداث الاتصال / الكتابة
            # =========================
            if msg_type in ["call_offer", "call_answer", "ice_candidate", "hangup", "typing"]:
                with SessionLocal() as db:
                    await manager.send_to_user(receiver_id, msg, db)
                continue

            with SessionLocal() as db:
                # =========================
                # 💬 جلب أو إنشاء المحادثة
                # =========================
                conversation = db.query(Conversation).filter(
                    ((Conversation.user1_id == user_id) & (Conversation.user2_id == receiver_id)) |
                    ((Conversation.user1_id == receiver_id) & (Conversation.user2_id == user_id))
                ).first()

                if not conversation:
                    conversation = Conversation(
                        user1_id=user_id,
                        user2_id=receiver_id
                    )
                    db.add(conversation)
                    db.commit()
                    db.refresh(conversation)

                # =========================
                # 💬 حفظ الرسالة في قاعدة البيانات
                # =========================
                new_msg = Message(
                    sender_id=user_id,
                    recipient_id=receiver_id,
                    conversation_id=conversation.id,
                    content=content,
                    message_type=msg_type
                )

                db.add(new_msg)
                db.commit()
                db.refresh(new_msg)

                payload_msg = {
                    "id": new_msg.id,
                    "conversation_id": conversation.id,
                    "sender_id": user_id,
                    "receiver_id": receiver_id,
                    "content": content,
                    "message_type": msg_type,
                    "timestamp": str(new_msg.timestamp)
                }

                # إرسال الرسالة للطرفين في نفس الوقت
                await manager.send_to_user(receiver_id, payload_msg, db)
                await manager.send_to_user(user_id, payload_msg, db)

    except WebSocketDisconnect:
        manager.disconnect(user_id)

    except Exception as e:
        print("WebSocket Error:", e)
        manager.disconnect(user_id)



# =========================
# 📜 جلب سجل المحادثة (Chat History)
# =========================
@router.get("/history/{peer_id}")
async def get_chat_history(
    peer_id: int,
    db: Session = Depends(get_db),
    token: str = Depends(oauth2_scheme)
):
    # 1. التحقق من التوكن وجلب المستخدم الحالي
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email = payload.get("sub")
        current_user = db.query(User).filter(User.email == email).first()
        if not current_user:
            raise HTTPException(status_code=401, detail="المستخدم غير موجود")
    except JWTError:
        raise HTTPException(status_code=401, detail="التوكن غير صالح")

    # 2. البحث المباشر في جدول الرسائل (أضمن من البحث في جدول المحادثات)
    # نجلب أي رسالة يكون فيها (أنا المرسل وهو المستلم) أو (هو المرسل وأنا المستلم)
    messages = db.query(Message).filter(
        ((Message.sender_id == current_user.id) & (Message.recipient_id == peer_id)) |
        ((Message.sender_id == peer_id) & (Message.recipient_id == current_user.id))
    ).order_by(Message.timestamp.asc()).all()

    # إذا لم يجد رسائل، سيعيد قائمة فارغة بشكل طبيعي
    return [
        {
            "id": m.id,
            "server_id": m.id,
            "sender_id": m.sender_id,
            "receiver_id": m.recipient_id,
            "content": m.content,
            "message_type": m.message_type,
            "created_at": m.timestamp.isoformat() if m.timestamp else None,
            "timestamp": m.timestamp.isoformat() if m.timestamp else None,
        }
        for m in messages
    ]


@router.delete("/messages/{message_id}")
async def delete_message(
    message_id: int,
    db: Session = Depends(get_db),
    token: str = Depends(oauth2_scheme)
):
    current_user = get_current_user_from_token(token, db)
    message = db.query(Message).filter(
        Message.id == message_id,
        ((Message.sender_id == current_user.id) |
         (Message.recipient_id == current_user.id))
    ).first()

    if not message:
        raise HTTPException(status_code=404, detail="الرسالة غير موجودة")

    db.query(MessageReaction).filter(MessageReaction.message_id == message_id).delete()
    db.query(MessageStatus).filter(MessageStatus.message_id == message_id).delete()
    db.query(MessageAttachment).filter(MessageAttachment.message_id == message_id).delete()
    db.delete(message)
    db.commit()
    return {"message": "تم حذف الرسالة"}


@router.delete("/history/{peer_id}")
async def delete_chat_history(
    peer_id: int,
    db: Session = Depends(get_db),
    token: str = Depends(oauth2_scheme)
):
    current_user = get_current_user_from_token(token, db)
    messages = db.query(Message).filter(
        ((Message.sender_id == current_user.id) & (Message.recipient_id == peer_id)) |
        ((Message.sender_id == peer_id) & (Message.recipient_id == current_user.id))
    ).all()
    message_ids = [m.id for m in messages]

    if message_ids:
        db.query(MessageReaction).filter(MessageReaction.message_id.in_(message_ids)).delete(synchronize_session=False)
        db.query(MessageStatus).filter(MessageStatus.message_id.in_(message_ids)).delete(synchronize_session=False)
        db.query(MessageAttachment).filter(MessageAttachment.message_id.in_(message_ids)).delete(synchronize_session=False)
        db.query(Message).filter(Message.id.in_(message_ids)).delete(synchronize_session=False)

    conversation = db.query(Conversation).filter(
        ((Conversation.user1_id == current_user.id) & (Conversation.user2_id == peer_id)) |
        ((Conversation.user1_id == peer_id) & (Conversation.user2_id == current_user.id))
    ).first()
    if conversation:
        db.delete(conversation)

    db.commit()
    return {"message": "تم حذف المحادثة", "deleted_messages": len(message_ids)}


@router.post("/backup/email")
async def send_chat_backup_email(
    backup: EmailBackupSchema,
    db: Session = Depends(get_db),
    token: str = Depends(oauth2_scheme)
):
    current_user = get_current_user_from_token(token, db)
    if not current_user.email:
        raise HTTPException(status_code=400, detail="لا يوجد بريد مرتبط بالحساب")

    backup_json = json.dumps(
        {
            "user_id": current_user.id,
            "peer_id": backup.peer_id,
            "peer_name": backup.peer_name,
            "messages": backup.messages,
            "exported_at": int(time.time()),
        },
        ensure_ascii=False,
        indent=2,
        default=str,
    )
    escaped = backup_json.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    html_content = f"""
    <div dir="rtl" style="font-family:Arial,sans-serif">
      <h2>نسخة احتياطية للمحادثة</h2>
      <p>المحادثة مع: {backup.peer_name or backup.peer_id}</p>
      <p>عدد الرسائل: {len(backup.messages)}</p>
      <pre dir="ltr" style="white-space:pre-wrap;background:#f5f5f5;padding:12px">{escaped}</pre>
    </div>
    """

    message = MessageSchema(
        subject="نسخة احتياطية للمحادثة",
        recipients=[current_user.email],
        body=html_content,
        subtype=MessageType.html
    )
    await FastMail(mail_config).send_message(message)
    return {"message": "تم إرسال النسخة الاحتياطية إلى البريد"}


# =========================
# 📤 رفع الملفات (Upload Files)
# =========================
@router.post("/upload")
async def upload_file(
    request: Request,
    file: UploadFile = File(...),
    file_type: str = Form(...),
    upload_dir: str = Form(...),
    receiver_id: int = Form(...),
    db: Session = Depends(get_db),
    token: str = Depends(oauth2_scheme)
):
    """
    رفع ملف صوتي أو صورة وتنظيمه ضمن مجلدات مُرتبة
    """
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email = payload.get("sub")
        current_user = db.query(User).filter(User.email == email).first()
        if not current_user:
            raise HTTPException(status_code=401, detail="المستخدم غير موجود")
    except JWTError:
        raise HTTPException(status_code=401, detail="التوكن غير صالح")

    allowed_dirs = {"voice", "images", "files"}
    upload_dir = upload_dir.strip().lower()
    if upload_dir not in allowed_dirs:
        upload_dir = "files"

    # اختيار مسار منظّم حسب النوع والمرسل والمستقبل
    target_dir = os.path.join("app", "static", "uploads", upload_dir, str(current_user.id), str(receiver_id))
    os.makedirs(target_dir, exist_ok=True)

    safe_filename = os.path.basename(file.filename)
    if not safe_filename:
        timestamp = int(time.time() * 1000)
        safe_filename = f"{current_user.id}_{timestamp}.bin"
    safe_filename = safe_filename.replace(" ", "_")
    file_name = f"{current_user.id}_{int(time.time() * 1000)}_{safe_filename}"
    file_path = os.path.join(target_dir, file_name)

    with open(file_path, "wb") as buffer:
        content = await file.read()
        buffer.write(content)

    base_url = str(request.base_url).rstrip("/")
    file_url = f"{base_url}/static/uploads/{upload_dir}/{current_user.id}/{receiver_id}/{file_name}"
    return {"file_url": file_url}


# =========================
# 📞 Signaling للمكالمات (Call Signaling)
# =========================
call_offers = {}  # تخزين مؤقت للعروض

class CallOfferSchema(BaseModel):
    sdp: str
    type: str

class ICECandidateSchema(BaseModel):
    candidate: str
    sdpMLineIndex: int
    sdpMid: str

@router.post("/call/offer")
async def send_offer(
    receiver_id: int,
    offer: CallOfferSchema,
    db: Session = Depends(get_db),
    token: str = Depends(oauth2_scheme)
):
    """
    إرسال عرض المكالمة (Offer)
    """
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email = payload.get("sub")
        sender = db.query(User).filter(User.email == email).first()
        if not sender:
            raise HTTPException(status_code=401, detail="المستخدم غير موجود")
    except JWTError:
        raise HTTPException(status_code=401, detail="التوكن غير صالح")

    # تخزين العرض
    call_offers[receiver_id] = {
        "sender_id": sender.id,
        "offer": offer.dict()
    }

    # إرسال إخطار عبر WebSocket أو Firebase
    offer_message = {
        "message_type": "call_offer",
        "sender_id": sender.id,
        "receiver_id": receiver_id,
        "offer": offer.dict()
    }
    
    await manager.send_to_user(receiver_id, offer_message, db)
    return {"message": "Offer sent"}

@router.post("/call/answer")
async def send_answer(
    sender_id: int,
    answer: CallOfferSchema,
    db: Session = Depends(get_db),
    token: str = Depends(oauth2_scheme)
):
    """
    إرسال إجابة المكالمة (Answer)
    """
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email = payload.get("sub")
        receiver = db.query(User).filter(User.email == email).first()
        if not receiver:
            raise HTTPException(status_code=401, detail="المستخدم غير موجود")
    except JWTError:
        raise HTTPException(status_code=401, detail="التوكن غير صالح")

    answer_message = {
        "message_type": "call_answer",
        "sender_id": receiver.id,
        "receiver_id": sender_id,
        "answer": answer.dict()
    }
    
    await manager.send_to_user(sender_id, answer_message, db)
    return {"message": "Answer sent"}

@router.post("/call/ice")
async def send_ice_candidate(
    peer_id: int,
    candidate: ICECandidateSchema,
    db: Session = Depends(get_db),
    token: str = Depends(oauth2_scheme)
):
    """
    إرسال ICE Candidate
    """
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email = payload.get("sub")
        sender = db.query(User).filter(User.email == email).first()
        if not sender:
            raise HTTPException(status_code=401, detail="المستخدم غير موجود")
    except JWTError:
        raise HTTPException(status_code=401, detail="التوكن غير صالح")

    ice_message = {
        "message_type": "ice_candidate",
        "sender_id": sender.id,
        "receiver_id": peer_id,
        "candidate": candidate.dict()
    }
    
    await manager.send_to_user(peer_id, ice_message, db)
    return {"message": "ICE candidate sent"}
