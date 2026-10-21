import threading
from datetime import timedelta

from fastapi import APIRouter, HTTPException, Request, Response, status
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, delete, func, select

from app.config import Settings
from app.db import DbSession
from app.deps import SESSION_COOKIE, AppSettings, CurrentUser
from app.models import AuthSession, Role, User, UserStatus, utcnow
from app.schemas import Credentials, LoginRequest, SetupStatus, UserOut
from app.security import (
    hash_password,
    hash_session_token,
    needs_rehash,
    new_session_token,
    verify_password,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])

# Serializes "is this the first user?" + insert, so two simultaneous sign-ups can't both be admin.
_register_lock = threading.Lock()


def _user_count(db: Session) -> int:
    return db.exec(select(func.count()).select_from(User)).one()


def _start_session(db: Session, settings: Settings, response: Response, user: User) -> None:
    now = utcnow()
    db.exec(delete(AuthSession).where(AuthSession.expires_at <= now))
    token = new_session_token()
    db.add(
        AuthSession(
            token_hash=hash_session_token(token, settings.secret_key),
            user_id=user.id,
            expires_at=now + timedelta(days=settings.session_days),
        )
    )
    db.commit()
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=settings.session_days * 86400,
        httponly=True,
        samesite="strict",
        secure=settings.cookie_secure,
    )


@router.get("/setup", response_model=SetupStatus)
def setup_status(db: DbSession) -> SetupStatus:
    return SetupStatus(needs_setup=_user_count(db) == 0)


@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def register(body: Credentials, response: Response, db: DbSession, settings: AppSettings) -> User:
    """The first account becomes an active admin and is logged in; later ones await approval."""
    with _register_lock:
        first = _user_count(db) == 0
        user = User(
            username=body.username,
            password_hash=hash_password(body.password),
            role=Role.ADMIN if first else Role.USER,
            status=UserStatus.ACTIVE if first else UserStatus.PENDING,
        )
        db.add(user)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            raise HTTPException(status.HTTP_409_CONFLICT, "Username is taken") from None
        db.refresh(user)

    if first:
        _start_session(db, settings, response, user)
    return user


@router.post("/login", response_model=UserOut)
def login(
    body: LoginRequest,
    request: Request,
    response: Response,
    db: DbSession,
    settings: AppSettings,
) -> User:
    limiter = request.app.state.login_limiter
    username = body.username.strip().lower()
    ip = request.client.host if request.client else "unknown"
    keys = (f"ip:{ip}", f"user:{ip}:{username}")
    if any(limiter.blocked(k) for k in keys):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Too many attempts, try later")

    user = db.exec(select(User).where(User.username == username)).first()
    if not verify_password(user.password_hash if user else None, body.password):
        for k in keys:
            limiter.record_failure(k)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid username or password")
    limiter.reset(keys[1])

    if user.status == UserStatus.PENDING:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Account is awaiting admin approval")
    if user.status == UserStatus.DISABLED:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Account is disabled")

    if needs_rehash(user.password_hash):
        user.password_hash = hash_password(body.password)
        db.add(user)
    _start_session(db, settings, response, user)
    return user


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(request: Request, db: DbSession, settings: AppSettings) -> Response:
    token = request.cookies.get(SESSION_COOKIE)
    if token:
        token_hash = hash_session_token(token, settings.secret_key)
        db.exec(delete(AuthSession).where(AuthSession.token_hash == token_hash))
        db.commit()
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    response.delete_cookie(SESSION_COOKIE, samesite="strict", httponly=True)
    return response


@router.get("/me", response_model=UserOut)
def me(user: CurrentUser) -> User:
    return user
