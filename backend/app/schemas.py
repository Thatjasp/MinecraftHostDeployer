from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, StringConstraints

from app.models import Role, UserStatus

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
