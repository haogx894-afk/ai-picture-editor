from typing import Annotated

from fastapi import Cookie, Depends, HTTPException, status

from app.db import SessionDep
from app.models import User, UserStatus
from app.security import SESSION_COOKIE, read_token
from app.services import auth as auth_service

_UNAUTHENTICATED = HTTPException(status.HTTP_401_UNAUTHORIZED, "未登录或会话已过期")
_ACCOUNT_NOT_APPROVED = {
    UserStatus.PENDING: HTTPException(status.HTTP_403_FORBIDDEN, "账号正在等待管理员审核"),
    UserStatus.REJECTED: HTTPException(status.HTTP_403_FORBIDDEN, "账号审核未通过"),
    UserStatus.SUSPENDED: HTTPException(status.HTTP_403_FORBIDDEN, "账号已被暂停使用"),
}


async def current_user(
    session: SessionDep,
    token: Annotated[str | None, Cookie(alias=SESSION_COOKIE)] = None,
) -> User:
    if token is None:
        raise _UNAUTHENTICATED

    user_id = read_token(token)
    if user_id is None:
        raise _UNAUTHENTICATED

    user = await auth_service.get_by_id(session, user_id)
    if user is None:
        raise _UNAUTHENTICATED
    if not user.can_use_workspace:
        raise _ACCOUNT_NOT_APPROVED[user.status]
    return user


CurrentUser = Annotated[User, Depends(current_user)]


async def admin_user(user: CurrentUser) -> User:
    if not user.is_admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "需要管理员权限")
    return user


AdminUser = Annotated[User, Depends(admin_user)]
