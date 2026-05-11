import os
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

# Load environment variables
from dotenv import load_dotenv
load_dotenv()

# 1. تحديد مكان قاعدة البيانات
SQLALCHEMY_DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./eslammohareb.db")

# 2. إنشاء محرك الاتصال (Engine)
if SQLALCHEMY_DATABASE_URL.startswith("sqlite"):
    engine = create_engine(
        SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
    )
else:
    engine = create_engine(SQLALCHEMY_DATABASE_URL)

# 3. إنشاء جلسة الاتصال (Session) التي سنستخدمها في العمليات البرمجية
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# 4. تعريف الفئة الأساسية (Base) التي سترث منها جميع جداولنا لاحقاً
Base = declarative_base()

# 5. وظيفة (Dependency) للحصول على اتصال بقاعدة البيانات وإغلاقه تلقائياً
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
