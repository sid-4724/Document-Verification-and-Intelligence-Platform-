import time
from collections import defaultdict, deque

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from ..auth import current_user, dummy_hash, hash_token, hasher, start_session, verify_password
from ..config import settings
from ..db import get_db
from ..models import (
    Session,
    User,
)
from ..schemas import (
    Credentials,
)

router = APIRouter()
attempts = defaultdict(deque)


def auth_limit(request):
    key = request.client.host if request.client else "local"
    recent = attempts[key]
    now = time.time()
    while recent and recent[0] < now - 60:
        recent.popleft()
    if len(recent) >= 20:
        raise HTTPException(429, "Too many authentication attempts; wait one minute")
    recent.append(now)


@router.post("/api/auth/register", status_code=201)
def register(body: Credentials, request: Request, response: Response, db=Depends(get_db)):
    auth_limit(request)
    user = User(email=body.email, password_hash=hasher.hash(body.password))
    db.add(user)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Email already registered")
    return start_session(db, user, response)


@router.post("/api/auth/login")
def login(body: Credentials, request: Request, response: Response, db=Depends(get_db)):
    auth_limit(request)
    user = db.scalar(select(User).where(User.email == body.email))
    valid = verify_password(user.password_hash if user else dummy_hash, body.password)
    if not user or not valid:
        raise HTTPException(401, "Email or password is incorrect")
    old = db.get(Session, hash_token(request.cookies.get("dv_session", "")))
    if old:
        db.delete(old)
    return start_session(db, user, response)


@router.get("/api/auth/me")
def me(request: Request, user=Depends(current_user)):
    return {
        "id": user.id,
        "email": user.email,
        "csrf": request.state.session.csrf,
        "demo_mode": settings().demo_mode,
    }


@router.post("/api/auth/logout")
def logout(request: Request, response: Response, user=Depends(current_user), db=Depends(get_db)):
    db.delete(db.get(Session, request.state.session.token_hash))
    db.commit()
    response.delete_cookie("dv_session", path="/")
    return {"ok": True}
