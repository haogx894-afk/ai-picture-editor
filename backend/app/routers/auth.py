from fastapi import APIRouter, HTTPException, Response, status

from app.config import get_settings
from app.db import SessionDep
from app.deps import CurrentUser
from app.models import User
from app.schemas.auth import Credentials, UserOut
from app.security import SESSION_COOKIE, issue_token
from app.services import auth as auth_service

router = APIRouter(prefix="/auth", tags=["auth"])


def _start_session(response: Response, user: User) -> UserOut:
    settings = get_settings()
    response.set_cookie(
        SESSION_COOKIE,
        issue_token(user.id),
        max_age=settings.jwt_ttl_hours * 3600,
        httponly=True,
        samesite="lax",
        secure=settings.cookie_secure,
        path="/",
    )
    return UserOut.model_validate(user)


@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register(credentials: Credentials, response: Response, session: SessionDep) -> UserOut:
    try:
        user = await auth_service.register(session, credentials.username, credentials.password)
    except auth_service.UsernameTaken:
        raise HTTPException(status.HTTP_409_CONFLICT, "该用户名已被占用") from None
    if user.can_use_workspace:
        return _start_session(response, user)
    return UserOut.model_validate(user)


@router.post("/login")
async def login(credentials: Credentials, response: Response, session: SessionDep) -> UserOut:
    try:
        user = await auth_service.authenticate(session, credentials.username, credentials.password)
    except auth_service.InvalidCredentials:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "用户名或密码错误") from None
    except auth_service.AccountNotApproved as exc:
        messages = {
            "pending": "账号正在等待管理员审核",
            "rejected": "账号审核未通过",
            "suspended": "账号已被暂停使用",
        }
        raise HTTPException(status.HTTP_403_FORBIDDEN, messages[exc.status.value]) from None
    return _start_session(response, user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE, path="/")


@router.get("/me")
async def me(user: CurrentUser) -> UserOut:
    return UserOut.model_validate(user)
