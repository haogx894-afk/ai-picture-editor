import uuid
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select

from app.config import get_settings
from app.db import SessionDep
from app.deps import AdminUser
from app.models import User, UserPlan, UserStatus
from app.schemas.admin import AdminUserOut, UserAdminPatch

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/users")
async def list_users(
    _: AdminUser,
    session: SessionDep,
    user_status: Annotated[UserStatus | None, Query(alias="status")] = None,
) -> list[AdminUserOut]:
    query = select(User).order_by(User.created_at.desc())
    if user_status is not None:
        query = query.where(User.status == user_status)
    users = await session.scalars(query)
    return [AdminUserOut.model_validate(user) for user in users]


@router.patch("/users/{user_id}")
async def update_user(
    _: AdminUser, user_id: uuid.UUID, payload: UserAdminPatch, session: SessionDep
) -> AdminUserOut:
    user = await session.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "用户不存在")
    if user.is_admin:
        raise HTTPException(status.HTTP_409_CONFLICT, "管理员账号不能通过用户管理修改")

    if payload.plan is not None:
        settings = get_settings()
        defaults = {
            UserPlan.FREE: (
                settings.free_agent_input_limit,
                settings.free_agent_output_limit,
                settings.free_edit_limit,
            ),
            UserPlan.VIP: (
                settings.vip_agent_input_limit,
                settings.vip_agent_output_limit,
                settings.vip_edit_limit,
            ),
            UserPlan.SVIP: (
                settings.svip_agent_input_limit,
                settings.svip_agent_output_limit,
                settings.svip_edit_limit,
            ),
        }
        (
            user.agent_input_limit,
            user.agent_output_limit,
            user.edit_limit,
        ) = defaults[payload.plan]

    for field in (
        "status",
        "plan",
        "agent_input_limit",
        "agent_output_limit",
        "edit_limit",
    ):
        value = getattr(payload, field)
        if value is not None:
            setattr(user, field, value)
    await session.commit()
    await session.refresh(user)
    return AdminUserOut.model_validate(user)
