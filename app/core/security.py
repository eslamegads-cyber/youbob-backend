import os
import bcrypt
from datetime import datetime, timedelta, timezone
from jose import jwt, JWTError
from typing import Optional

# =========================
# 🔐 ENV SECURITY (IMPORTANT)
# =========================
SECRET_KEY = os.getenv("SECRET_KEY", "CHANGE_THIS_IMMEDIATELY")
ALGORITHM = "HS256"

ACCESS_TOKEN_EXPIRE_MINUTES = 30
VERIFICATION_TOKEN_EXPIRE_HOURS = 24
PASSWORD_RESET_TOKEN_EXPIRE_HOURS = 1


# =========================
# 🔑 PASSWORD HASHING
# =========================
def get_password_hash(password: str) -> str:
    password_bytes = password.encode("utf-8")
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password_bytes, salt)
    return hashed.decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return bcrypt.checkpw(
        plain_password.encode("utf-8"),
        hashed_password.encode("utf-8")
    )


# =========================
# 🔐 ACCESS TOKEN (LOGIN)
# =========================
def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):

    to_encode = data.copy()

    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    )

    # 👇 مهم جداً للشات و WebSocket
    to_encode.update({
        "exp": expire,
        "iat": datetime.now(timezone.utc)
    })

    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


# =========================
# 📧 EMAIL VERIFICATION TOKEN
# =========================
def create_verification_token(email: str):

    expire = datetime.now(timezone.utc) + timedelta(
        hours=VERIFICATION_TOKEN_EXPIRE_HOURS
    )

    payload = {
        "sub": email,
        "exp": expire,
        "type": "email_verification"
    }

    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def verify_verification_token(token: str) -> Optional[str]:

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])

        # 👇 تأكد أنه verification token فقط
        if payload.get("type") != "email_verification":
            return None

        return payload.get("sub")

    except JWTError:
        return None


# =========================
# 🔁 PASSWORD RESET TOKEN
# =========================
def create_password_reset_token(email: str):

    expire = datetime.now(timezone.utc) + timedelta(
        hours=PASSWORD_RESET_TOKEN_EXPIRE_HOURS
    )

    payload = {
        "sub": email,
        "exp": expire,
        "type": "password_reset"
    }

    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def verify_password_reset_token(token: str) -> Optional[str]:

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])

        if payload.get("type") != "password_reset":
            return None

        return payload.get("sub")

    except JWTError:
        return None


# =========================
# 🧠 OPTIONAL: GET USER FROM TOKEN
# (مهم جداً للشات)
# =========================
def decode_access_token(token: str) -> Optional[dict]:

    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        return None
