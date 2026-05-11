import os
import logging
import json

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect, Depends
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime, timezone
from typing import Dict
from sqlalchemy.orm import Session

# استيراد المحرك والـ Base والدوال الخارجية
from app.db.session import engine, Base, get_db, SessionLocal
from app.models import (
    user, message, conversation, notification, reaction, attachment,
    message_status, user_status, blocked_user
)
from app.models.user import User
from app.api.v1.api import api_router
from app.core.notifications import send_push_notification  # تأكد من وجود هذا الملف

# إعداد السجلات (Logs)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# إنشاء الجداول تلقائياً
Base.metadata.create_all(bind=engine)

app = FastAPI(title="Chat App API", version="1.0.0")

# ==========================================
# 1. إعدادات الـ CORS (لدعم React و Flutter Web)
# ==========================================
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",           # ري آكت محلي
        "http://10.71.63.164:5173",     # ري آكت عبر الشبكة
        "http://10.71.63.164",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ==========================================
# 2. مدير اتصالات الـ WebSocket الموحد
# ==========================================
class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[int, WebSocket] = {}

    def _set_user_status(self, user_id: int, online: bool):
        try:
            with SessionLocal() as db:
                user = db.query(User).filter(User.id == user_id).first()
                if user:
                    user.is_online = online
                    if not online:
                        user.last_seen = datetime.now(timezone.utc)
                    db.add(user)
                    db.commit()
        except Exception as e:
            logger.warning(f"⚠️ فشل تحديث حالة المستخدم {user_id}: {e}")

    async def connect(self, user_id: int, websocket: WebSocket):
        await websocket.accept()
        # إغلاق أي اتصال قديم لنفس المستخدم لمنع التكرار
        if user_id in self.active_connections:
            try:
                await self.active_connections[user_id].close()
            except Exception:
                pass
            self.disconnect(user_id)

        self.active_connections[user_id] = websocket
        self._set_user_status(user_id, True)
        logger.info(f"🟢 User {user_id} connected. Total: {len(self.active_connections)}")

    def disconnect(self, user_id: int):
        if user_id in self.active_connections:
            del self.active_connections[user_id]
            self._set_user_status(user_id, False)
            logger.info(f"🔴 User {user_id} disconnected.")

    async def send_personal_message(self, message: dict, recipient_id: int, db: Session):
        websocket = self.active_connections.get(recipient_id)
        if websocket:
            # إرسال عبر الويب سوكيت إذا كان متصلاً (React/Flutter)
            try:
                await websocket.send_json(message)
            except Exception:
                self.disconnect(recipient_id)

        # إرسال Push دائمًا للجوال إذا كان لديه FCM token، حتى لو كان WebSocket متصلًا.
        msg_type = message.get("type") or message.get("message_type", "message")
        silent_push_types = {
            "typing",
            "accept_call",
            "offer",
            "answer",
            "ice_candidate",
            "candidate",
            "call_ended",
            "call_rejected",
        }
        if msg_type in silent_push_types:
            return

        target_user = db.query(User).filter(User.id == recipient_id).first()
        if target_user and target_user.fcm_token:
            is_call = msg_type in {
                "call_request",
            }
            if is_call:
                call_type = message.get("call_type", "voice")
                title = "مكالمة فيديو واردة" if call_type == "video" else "مكالمة صوتية واردة"
                body = f"مكالمة واردة من المستخدم {message.get('sender_id', '')}"
                data = {
                    "type": "call",
                    "event_type": msg_type,
                    "sender_id": message.get("sender_id"),
                    "receiver_id": recipient_id,
                    "call_type": call_type,
                    "channel_name": message.get("channel_name"),
                    "sdp": message.get("sdp"),
                }
            else:
                title = f"رسالة جديدة من {message.get('sender_name', 'صديق')}"
                body = message.get("content", "لديك رسالة جديدة")
                data = {
                    "type": "message",
                    "content_type": msg_type,
                    "sender_id": message.get("sender_id"),
                    "receiver_id": recipient_id,
                    "content": message.get("content") or message.get("text", ""),
                }
            send_push_notification(
                fcm_token=target_user.fcm_token,
                title=title,
                body=body,
                data=data,
            )

manager = ConnectionManager()

@app.websocket("/api/v1/ws/{user_id}")
async def websocket_endpoint(websocket: WebSocket, user_id: int, db: Session = Depends(get_db)):
    await manager.connect(user_id, websocket)
    try:
        while True:
            # 1. استقبال البيانات وتحويلها من نص إلى JSON
            data_raw = await websocket.receive_text()
            msg = json.loads(data_raw)
            logger.info(f"📩 رسالة مستلمة من {user_id}: {msg}")

            # 2. استخراج الحقول
            receiver_id = msg.get("receiver_id")
            msg_type = msg.get("message_type") or msg.get("type", "text")
            
            transient_message_types = {
                'call_request',
                'accept_call',
                'offer',
                'answer',
                'ice_candidate',
                'call_ended',
                'call_rejected',
                'candidate',
                'typing',
            }

            if msg_type in transient_message_types and receiver_id:
                logger.info(f"📡 رسالة فورية [{msg_type}] من {user_id} إلى {receiver_id}")

                if int(receiver_id) != user_id:
                    msg['sender_id'] = user_id
                    await manager.send_personal_message(msg, int(receiver_id), db)
                else:
                    logger.warning("⚠️ محاولة إرسال رسالة فورية إلى نفسك - تم التجاهل")
            
            # ==================== معالجة الرسائل العادية ====================
            else:
                content = msg.get("text") or msg.get("content") 
                
                if receiver_id and content:
                    try:
                        from app.models.message import Message
                        from app.models.conversation import Conversation

                        conversation = db.query(Conversation).filter(
                            ((Conversation.user1_id == user_id) & (Conversation.user2_id == int(receiver_id))) |
                            ((Conversation.user1_id == int(receiver_id)) & (Conversation.user2_id == user_id))
                        ).first()

                        if not conversation:
                            conversation = Conversation(
                                user1_id=user_id,
                                user2_id=int(receiver_id)
                            )
                            db.add(conversation)
                            db.commit()
                            db.refresh(conversation)

                        new_msg = Message(
                            sender_id=user_id,
                            recipient_id=int(receiver_id),
                            content=content,
                            conversation_id=conversation.id,
                            message_type=msg_type
                        )

                        db.add(new_msg)
                        db.commit()
                        db.refresh(new_msg)
                        logger.info(f"✅ تم حفظ الرسالة بنجاح في القاعدة ID: {new_msg.id}")

                        payload_msg = {
                            **msg,
                            "id": new_msg.id,
                            "server_id": new_msg.id,
                            "conversation_id": conversation.id,
                            "sender_id": user_id,
                            "receiver_id": int(receiver_id),
                            "content": content,
                            "message_type": msg_type,
                            "created_at": new_msg.timestamp.isoformat(),
                        }

                        if int(receiver_id) != user_id:
                            await manager.send_personal_message(payload_msg, int(receiver_id), db)
                        else:
                            logger.info("ℹ️ تم حفظ الرسالة ذاتياً ولم يتم إعادة الإرسال لمنع التكرار.")

                    except Exception as e:
                        db.rollback()
                        logger.error(f"❌ خطأ أثناء الحفظ في القاعدة: {e}")

    except WebSocketDisconnect:
        manager.disconnect(user_id)
    except Exception as e:
        logger.error(f"❌ خطأ غير متوقع في الـ WebSocket: {e}")
        manager.disconnect(user_id)

# ==========================================
# 3. إدارة الملفات الثابتة (الصور والمقاطع الصوتية)
# ==========================================
STATIC_DIR = "app/static"
for sub in ["audio", "images", "files"]:
    os.makedirs(os.path.join(STATIC_DIR, sub), exist_ok=True)

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# ==========================================
# 4. ربط المسارات (الخاصة بتعديل وحذف المستخدمين)
# ==========================================
app.include_router(api_router, prefix="/api/v1")

# ==========================================
# 5. الواجهة الرئيسية
# ==========================================
@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    return """
    <html>
        <head>
            <title>Chat API Server</title>
            <style>body { font-family: sans-serif; text-align: center; padding: 50px; background: #f4f4f9; }</style>
        </head>
        <body>
            <h1 style="color: #2c3e50;">Server is Live! 🚀</h1>
            <p>WebSocket URL: <code>ws://10.71.63.164:8000/api/v1/ws/{user_id}</code></p>
            <div style="margin-top: 20px;">
                <a href="/docs" style="padding: 10px 20px; background: #27ae60; color: white; text-decoration: none; border-radius: 5px;">API Documentation</a>
                <a href="/static/admin.html" style="padding: 10px 20px; background: #9B111E; color: white; text-decoration: none; border-radius: 5px; margin-right: 8px;">Admin Docs</a>
            </div>
        </body>
    </html>
    """
