from datetime import UTC, datetime
from enum import StrEnum

from sqlmodel import JSON, Column, Field, SQLModel


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


class Server(SQLModel, table=True):
    """A Minecraft server; runs as the itzg/minecraft-server container `mcpanel-<id>`."""

    __tablename__ = "servers"

    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(max_length=40, unique=True)
    port: int = Field(unique=True)
    memory: str = Field(max_length=8)  # itzg MEMORY, e.g. "4G"
    image_tag: str = Field(max_length=32)  # itzg tag: latest, java21, java17, ...
    server_type: str = Field(max_length=32)  # itzg TYPE: VANILLA, AUTO_CURSEFORGE, ...
    # Vanilla: itzg VERSION (LATEST or 1.20.1). Modpacks: the pack's MC version, for display only.
    version: str = Field(max_length=32)
    motd: str = Field(default="", max_length=120)
    modpack: str = Field(default="", max_length=200)  # display name, e.g. "All the Mods 9 · 1.1.1"
    loader: str = Field(default="", max_length=16)  # Forge, NeoForge, Fabric, ...
    # Uploaded zip in $MC_ROOT/modpacks, bind-mounted read-only at /modpacks/pack.zip.
    modpack_zip: str | None = Field(default=None, max_length=64)
    # Additional itzg env for the server type (CurseForge settings etc.).
    extra_env: dict[str, str] = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))
    created_by_id: int | None = Field(default=None, foreign_key="users.id", ondelete="SET NULL")
    created_at: datetime = Field(default_factory=utcnow)
