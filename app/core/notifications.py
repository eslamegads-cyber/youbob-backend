import firebase_admin
from firebase_admin import messaging, credentials
import os
from typing import Optional

# تحديد المسار التلقائي للملف في المجلد الرئيسي
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
path_to_json = os.path.join(BASE_DIR, "firebase_key.json")

_RESERVED_DATA_KEYS = {
    "from",
    "message_type",
}

_RESERVED_PREFIXES = ("google", "gcm")

# تهيئة Firebase مرة واحدة فقط
if not firebase_admin._apps:
    try:
        cred = credentials.Certificate(path_to_json)
        firebase_admin.initialize_app(cred)
        print("✅ تم تهيئة Firebase بنجاح")

    except Exception as e:
        print(f"❌ خطأ في تهيئة Firebase: {e}")

# 🟢 تأكد أن اسم الدالة مطابق لما تستورده في chat_manager
def send_push_notification(fcm_token: str, title: str, body: str, data: Optional[dict] = None):
    if not fcm_token:
        return

    safe_data = _sanitize_fcm_data(data)
    is_call = safe_data.get("type") == "call"
    android_notification = messaging.AndroidNotification(
        channel_id="incoming_calls_ringing" if is_call else "message_channel",
        sound="ringing" if is_call else "default",
        priority="max" if is_call else "high",
        default_vibrate_timings=True,
    )
    message = messaging.Message(
        notification=messaging.Notification(title=title, body=body),
        data=safe_data,
        android=messaging.AndroidConfig(
            priority="high",
            notification=android_notification,
        ),
        apns=messaging.APNSConfig(
            payload=messaging.APNSPayload(
                aps=messaging.Aps(sound="default", content_available=True)
            )
        ),
        token=fcm_token,
    )
    try:
        response = messaging.send(message)
        print(f"✅ تم إرسال الإشعار بنجاح: {response}")
    except Exception as e:
        print(f"❌ فشل إرسال الإشعار: {e}")


def _sanitize_fcm_data(data: Optional[dict]) -> dict[str, str]:
    safe_data: dict[str, str] = {}

    for raw_key, value in (data or {}).items():
        if value is None:
            continue

        key = str(raw_key)
        lower_key = key.lower()
        if lower_key == "message_type":
            key = "event_type"
        elif lower_key in _RESERVED_DATA_KEYS or lower_key.startswith(_RESERVED_PREFIXES):
            key = f"custom_{key}"

        safe_data[key] = str(value)

    return safe_data
