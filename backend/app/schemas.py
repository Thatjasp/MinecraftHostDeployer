from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, Field, StringConstraints

from app.models import Role, UserStatus
from app.servers import IMAGE_TAGS, ServerState

Username = Annotated[
    str,
    StringConstraints(strip_whitespace=True, to_lower=True, pattern=r"^[A-Za-z0-9_-]{3,32}$"),
]
Password = Annotated[str, StringConstraints(min_length=8, max_length=128)]


class Credentials(BaseModel):
    username: Username
    password: Password


class LoginRequest(BaseModel):
    # No format rules on login: a bad username is just a failed login.
    username: str
    password: str


class UserOut(BaseModel):
    id: int
    username: str
    role: Role
    status: UserStatus
    created_at: datetime


class SetupStatus(BaseModel):
    needs_setup: bool


class UserUpdate(BaseModel):
    role: Role | None = None
    status: UserStatus | None = None


ImageTag = Literal[IMAGE_TAGS]  # type: ignore[valid-type]


class ServerCreate(BaseModel):
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=40)]
    version: Annotated[
        str,
        StringConstraints(strip_whitespace=True, pattern=r"^(LATEST|SNAPSHOT|[0-9][\w.-]{0,30})$"),
    ] = "LATEST"
    port: int | None = Field(default=None, ge=1024, le=65535)  # None = next free from 25565
    memory: Annotated[str, StringConstraints(pattern=r"^[1-9][0-9]{0,5}[MG]$")] = "4G"
    image_tag: ImageTag = "latest"
    motd: Annotated[str, StringConstraints(max_length=120)] = ""
    accept_eula: Literal[True]
    start: bool = True


class ServerOut(BaseModel):
    id: int
    name: str
    port: int
    memory: str
    image_tag: str
    server_type: str
    version: str
    motd: str
    created_at: datetime
    state: ServerState
    detail: str | None


class CommandIn(BaseModel):
    command: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1000)]


class CommandOut(BaseModel):
    output: str
