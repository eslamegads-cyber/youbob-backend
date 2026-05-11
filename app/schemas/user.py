from datetime import datetime
from pydantic import BaseModel, EmailStr
from typing import Optional, List

# الهيكل الأساسي للبيانات
class UserBase(BaseModel):
    uuid: Optional[str] = None
    full_name: Optional[str] = None
    email: Optional[EmailStr] = None
    phone_number: Optional[str] = None
    profile_pic: Optional[str] = None
    cover_photo: Optional[str] = None
    is_online: Optional[bool] = False
    last_seen: Optional[datetime] = None

# البيانات المطلوبة عند إنشاء حساب جديد
class UserCreate(UserBase):
    full_name: str
    email: EmailStr
    password: str
    phone_number: str

# 👇 هذا هو الكلاس المفقود الذي سبب الخطأ
# يستخدم لتحديث بيانات المستخدم (كل الحقول اختيارية)
class UserUpdate(BaseModel):
    full_name: Optional[str] = None
    email: Optional[EmailStr] = None
    password: Optional[str] = None
    phone_number: Optional[str] = None
    fcm_token: Optional[str] = None # أضفنا هذا لتحديث توكن الإشعارات أيضاً

# البيانات التي تعود للمستخدم (بدون كلمة المرور)
class UserOut(UserBase):
    id: int

    class Config:
        from_attributes = True

# الشيما الخاصة بمزامنة جهات الاتصال
class PhoneSearchSchema(BaseModel):
    phones: List[str]
