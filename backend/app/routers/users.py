from fastapi import APIRouter, HTTPException, status
from sqlmodel import Session, delete, select

from app.db import DbSession
from app.deps import AdminUser
from app.models import AuthSession, User, UserStatus
from app.schemas import UserOut, UserUpdate

router = APIRouter(prefix="/api/users", tags=["users"])


def _get_user(db: Session, user_id: int) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    return user


@router.get("", response_model=list[UserOut])
def list_users(db: DbSession, _admin: AdminUser) -> list[User]:
    return list(db.exec(select(User).order_by(User.created_at)))


@router.patch("/{user_id}", response_model=UserOut)
def update_user(user_id: int, body: UserUpdate, db: DbSession, admin: AdminUser) -> User:
    user = _get_user(db, user_id)
    # Admins can't demote/disable/delete themselves, so an active admin always remains.
    if user.id == admin.id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "You can't change your own account here")

    user.role = body.role or user.role
    user.status = body.status or user.status
    if user.status != UserStatus.ACTIVE:
        db.exec(delete(AuthSession).where(AuthSession.user_id == user.id))
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(user_id: int, db: DbSession, admin: AdminUser) -> None:
    user = _get_user(db, user_id)
    if user.id == admin.id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "You can't delete yourself")
    db.delete(user)
    db.commit()
