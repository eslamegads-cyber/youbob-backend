
from fastapi import APIRouter
from app.api.v1.endpoints import auth, chat, maintenance, users

# 1. إنشاء الراوتر الرئيسي للنسخة الأولى من الـ API
api_router = APIRouter()

# 2. ربط ملف الـ auth (تعديل الـ prefix إلى /auth)
api_router.include_router(auth.router, prefix="/auth", tags=["authentication"])

# 3. ربط ملف الـ chat
api_router.include_router(chat.router, prefix="/chat", tags=["chat-operations"])

# 4. ربط ملف الـ users 
api_router.include_router(users.router, prefix="/users", tags=["users-operations"])

# 5. أدوات الصيانة المؤقتة
api_router.include_router(maintenance.router, prefix="/maintenance", tags=["maintenance"])
