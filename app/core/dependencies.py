from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import jwt, JWTError
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.user import User
from app.core.security import SECRET_KEY, ALGORITHM

# 1. تعريف نظام الأمان (التوكن)
# ملاحظة: تأكد أن tokenUrl يطابق مسار Login الفعلي لديك (غالباً /api/v1/auth/login)
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")

# 2. الدالة التي كانت مفقودة وتسببت في الخطأ
def get_current_user(db: Session = Depends(get_db), token: str = Depends(oauth2_scheme)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="لم يتم التحقق من صحة الاعتماديات",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        # فك تشفير التوكن
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email: str = payload.get("sub")
        if email is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
        
    # البحث عن المستخدم في قاعدة البيانات
    user = db.query(User).filter(User.email == email).first()
    if user is None:
        raise credentials_exception
    
    return user
