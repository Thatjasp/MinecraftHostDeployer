from datetime import UTC, datetime
from enum import StrEnum

from sqlmodel import Field, SQLModel


def utcnow() -> datetime:
    # SQLModel's UTCDateTime requires aware datetimes and returns them in UTC, even on SQLite.
    return datetime.now(UTC)


class Role(StrEnum):
    ADMIN = "admin"
    USER = "user"


class UserStatus(StrEnum):
    PENDING = "pending"
    ACTIVE = "active"
    DISABLED = "disabled"


class User(SQLModel, table=True):
    __tablename__ = "users"

    id: int | None = Field(default=None, primary_key=True)
    # Stored lowercase so usernames are unique case-insensitively.
    username: str = Field(max_length=32, unique=True, index=True)
    password_hash: str
    role: Role = Field(default=Role.USER)
    status: UserStatus = Field(default=UserStatus.PENDING)
    created_at: datetime = Field(default_factory=utcnow)


class AuthSession(SQLModel, table=True):
    __tablename__ = "sessions"

    # HMAC of the cookie token; the raw token is never stored.
    token_hash: str = Field(primary_key=True, max_length=64)
    user_id: int = Field(foreign_key="users.id", index=True, ondelete="CASCADE")
    created_at: datetime = Field(default_factory=utcnow)
    expires_at: datetime
