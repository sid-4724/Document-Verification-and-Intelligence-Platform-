import hashlib
import secrets
import time

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from fastapi import Depends, HTTPException, Request, Response
from sqlalchemy import select

from .config import settings
from .db import get_db
from .models import Session, User

hasher = PasswordHasher()
# Also verify a dummy hash for absent accounts to reduce timing differences.
dummy_hash = hasher.hash(secrets.token_urlsafe(24))


def hash_token(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def verify_password(encoded: str, password: str) -> bool:
    try:
        return hasher.verify(encoded, password)
    except (VerificationError, InvalidHashError):
        return False


def start_session(db, user: User, response: Response):
    token, csrf = secrets.token_urlsafe(32), secrets.token_hex(32)
    db.add(
        Session(
            token_hash=hash_token(token),
            user_id=user.id,
            csrf=csrf,
            expires_at=time.time() + 86400 * 7,
        )
    )
    db.commit()
    response.set_cookie(
        "dv_session",
        token,
        httponly=True,
        secure=settings().cookie_secure,
        samesite="lax",
        max_age=604800,
        path="/",
    )
    return {"id": user.id, "email": user.email, "csrf": csrf, "demo_mode": settings().demo_mode}


def current_user(request: Request, db=Depends(get_db)) -> User:
    session = db.get(Session, hash_token(request.cookies.get("dv_session", "")))
    if not session or session.expires_at < time.time():
        raise HTTPException(401, "Please sign in")
    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        supplied = request.headers.get("x-csrf-token", "")
        if not secrets.compare_digest(supplied, session.csrf):
            raise HTTPException(403, "Invalid CSRF token; reload and try again")
    request.state.session = session
    return db.scalar(select(User).where(User.id == session.user_id))
