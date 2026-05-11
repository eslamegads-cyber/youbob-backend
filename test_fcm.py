import firebase_admin
from firebase_admin import credentials, messaging
import os

# 1. إعداد المسار والملف
path_to_json = "firebase_key.json"
cred = credentials.Certificate(path_to_json)

if not firebase_admin._apps:
    firebase_admin.initialize_app(cred)

def send_test_notification(token):
    # 2. محتوى الإشعار التجريبي
    message = messaging.Message(
        notification=messaging.Notification(
            title="تجربة ناجحة! 🚀",
            body="إذا رأيت هذه الرسالة، فإن سيرفر FastAPI الخاص بك يرسل إشعارات بنجاح."
        ),
        token=token,
    )

    try:
        response = messaging.send(message)
        print(f"✅ تم إرسال الإشعار بنجاح! رقم العملية: {response}")
    except Exception as e:
        print(f"❌ فشل الإرسال: {e}")

# 3. ضع هنا الـ Token الخاص بهاتفك (مهم جداً)
YOUR_DEVICE_TOKEN = ""

if __name__ == "__main__":
    send_test_notification(YOUR_DEVICE_TOKEN)
