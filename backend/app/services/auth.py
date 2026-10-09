import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models import User, UserPlan, UserStatus
from app.security import hash_password, verify_password


class UsernameTaken(Exception):
    pass


class InvalidCredentials(Exception):
    pass


class AccountNotApproved(Exception):
    def __init__(self, status: UserStatus):
        self.status = status
        super().__init__(status.value)


async def register(session: AsyncSession, username: str, password: str) -> User:
    settings = get_settings()
    user = User(
        username=username,
        password_hash=hash_password(password),
        status=(
            UserStatus.PENDING
            if settings.require_registration_approval
            else UserStatus.APPROVED
        ),
        plan=UserPlan.FREE,
        agent_input_limit=settings.free_agent_input_limit,
        agent_output_limit=settings.free_agent_output_limit,
        edit_limit=settings.free_edit_limit,
    )
    session.add(user)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise UsernameTaken from exc
    return user


async def authenticate(session: AsyncSession, username: str, password: str) -> User:
    user = await session.scalar(select(User).where(User.username == username))
    if user is None or not verify_password(password, user.password_hash):
        raise InvalidCredentials
    if not user.can_use_workspace:
        raise AccountNotApproved(user.status)
    return user


async def get_by_id(session: AsyncSession, user_id: uuid.UUID) -> User | None:
    return await session.get(User, user_id)


async def ensure_admin(session: AsyncSession) -> User | None:
    """Create or reconcile the single administrator from deployment settings.

    The configured administrator may be renamed or have its password rotated
    without deleting the account or any user-owned data.
    """
    settings = get_settings()
    if not settings.admin_password:
        return None

    admin = await session.scalar(select(User).where(User.username == settings.admin_username))
    existing_admin = await session.scalar(select(User).where(User.is_admin.is_(True)))
    if existing_admin is not None:
        if admin is not None and admin.id != existing_admin.id:
            raise RuntimeError("管理员用户名已被其他用户占用")
        admin = existing_admin
        admin.username = settings.admin_username
        admin.password_hash = hash_password(settings.admin_password)
        admin.status = UserStatus.APPROVED
    elif admin is None:
        admin = User(
            username=settings.admin_username,
            password_hash=hash_password(settings.admin_password),
            status=UserStatus.APPROVED,
            is_admin=True,
            plan=UserPlan.SVIP,
            agent_input_limit=settings.svip_agent_input_limit,
            agent_output_limit=settings.svip_agent_output_limit,
            edit_limit=settings.svip_edit_limit,
        )
        session.add(admin)
    else:
        admin.is_admin = True
        admin.status = UserStatus.APPROVED
        admin.password_hash = hash_password(settings.admin_password)

    await session.commit()
    await session.refresh(admin)
    return admin
