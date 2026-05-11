import asyncio
from fastapi import WebSocket, WebSocketDisconnect
from typing import Dict
import logging
from app.models.user import User # 👈 استيراد مودل المستخدم لجلب الـ Token
from app.core.notifications import send_push_notification

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[int, WebSocket] = {}

    async def connect(self, user_id: int, websocket: WebSocket):
        await websocket.accept()
        if user_id in self.active_connections:
            try:
                await self.active_connections[user_id].close(code=1000)
            except Exception:
                pass
        self.active_connections[user_id] = websocket
        logger.info(f"🟢 المستخدم {user_id} متصل الآن. إجمالي المتصلين: {len(self.active_connections)}")

    def disconnect(self, user_id: int):
        if user_id in self.active_connections:
            del self.active_connections[user_id]
            logger.info(f"🔴 تم فصل المستخدم {user_id}. إجمالي المتصلين: {len(self.active_connections)}")

    # 🟢 تعديل دالة الإرسال لدعم الإشعارات
    async def send_to_user(self, recipient_id: int, message: dict, db=None):
        websocket = self.active_connections.get(recipient_id)
        
        if websocket:
            # حالة 1: المستخدم متصل -> أرسل عبر WebSocket
            try:
                await websocket.send_json(message)
            except (WebSocketDisconnect, Exception) as e:
                logger.warning(f"⚠️ فشل الإرسال للمستخدم {recipient_id}. السبب: {e}")
                self.disconnect(recipient_id)

        # أرسل Push دائمًا إذا كان للمستخدم FCM token، حتى مع وجود اتصال WebSocket.
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
            "hangup",
            "call_answer",
        }
        if msg_type in silent_push_types:
            return

        if db:
            user = db.query(User).filter(User.id == recipient_id).first()
            if user and user.fcm_token:
                is_call = msg_type in {
                    "call_request",
                    "call_offer",
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
                    sender_name = message.get("sender_name", "صديق")
                    content = message.get("message_content") or message.get("content") or "رسالة جديدة"
                    title = f"رسالة من {sender_name}"
                    body = content
                    data = {
                        "type": "message",
                        "content_type": msg_type,
                        "sender_id": message.get("sender_id"),
                        "receiver_id": recipient_id,
                        "content": content,
                    }

                send_push_notification(
                    fcm_token=user.fcm_token,
                    title=title,
                    body=body,
                    data=data,
                )

    async def broadcast(self, message: dict):
        if not self.active_connections:
            return
        async def _safe_send(user_id: int, ws: WebSocket):
            try:
                await ws.send_json(message)
            except (WebSocketDisconnect, Exception):
                return user_id
            return None

        tasks = [_safe_send(user_id, ws) for user_id, ws in self.active_connections.items()]
        results = await asyncio.gather(*tasks)
        for user_id in results:
            if user_id is not None:
                self.disconnect(user_id)

manager = ConnectionManager()
