from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from sqlmodel import Session

from app.config import Settings
from app.db import DbSession
from app.models import AuthSession, Role, User, UserStatus, utcnow
from app.security import hash_session_token

SESSION_COOKIE = "mcpanel_session"


def get_app_settings(request: Request) -> Settings:
    return request.app.state.settings


AppSettings = Annotated[Settings, Depends(get_app_settings)]


def user_from_token(db: Session, settings: Settings, token: str | None) -> User | None:
    """Resolve a session cookie value to an active user. Shared by HTTP and WebSocket auth."""
    if not token:
        return None
    session = db.get(AuthSession, hash_session_token(token, settings.secret_key))
    if session is None or session.expires_at <= utcnow():
        return None
    user = db.get(User, session.user_id)
    if user is None or user.status != UserStatus.ACTIVE:
        return None
    return user


def current_user(request: Request, db: DbSession, settings: AppSettings) -> User:
    user = user_from_token(db, settings, request.cookies.get(SESSION_COOKIE))
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not logged in")
    return user


CurrentUser = Annotated[User, Depends(current_user)]


def require_admin(user: CurrentUser) -> User:
    if user.role != Role.ADMIN:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Admin only")
    return user


AdminUser = Annotated[User, Depends(require_admin)]
