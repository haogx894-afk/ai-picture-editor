import uuid

import httpx
import pytest
from sqlalchemy import select

from app.config import get_settings
from app.db import SessionFactory
from app.models import User, UserPlan, UserStatus
from app.security import hash_password
from app.services.quota import QuotaExceeded, consume_agent_turn, consume_edit


async def _create_admin() -> User:
    admin = User(
        username=f"test_admin_{uuid.uuid4().hex[:10]}",
        password_hash=hash_password("test-admin-password"),
        status=UserStatus.APPROVED,
        is_admin=True,
        plan=UserPlan.SVIP,
        agent_input_limit=500,
        agent_output_limit=500,
        edit_limit=500,
    )
    async with SessionFactory() as session:
        session.add(admin)
        await session.commit()
        await session.refresh(admin)
    return admin


async def test_registration_waits_for_admin_approval(
    client: httpx.AsyncClient, credentials: dict[str, str]
):
    get_settings().require_registration_approval = True

    response = await client.post("/api/auth/register", json=credentials)

    assert response.status_code == 201
    assert response.json()["status"] == "pending"
    assert "session" not in response.cookies
    login = await client.post("/api/auth/login", json=credentials)
    assert login.status_code == 403
    assert "审核" in login.json()["detail"]


async def test_admin_can_approve_user_and_set_plan(client: httpx.AsyncClient, credentials):
    admin = await _create_admin()
    registered = await client.post("/api/auth/register", json=credentials)
    user_id = registered.json()["id"]

    await client.post(
        "/api/auth/login",
        json={"username": admin.username, "password": "test-admin-password"},
    )
    response = await client.patch(
        f"/api/admin/users/{user_id}",
        json={"status": "approved", "plan": "vip"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "approved"
    assert body["plan"] == "vip"
    assert body["agent_input_limit"] == get_settings().vip_agent_input_limit


async def test_quota_reservation_stops_after_limit(credentials):
    user = User(
        username=credentials["username"],
        password_hash=hash_password(credentials["password"]),
        status=UserStatus.APPROVED,
        agent_input_limit=2,
        agent_output_limit=2,
        edit_limit=2,
    )
    async with SessionFactory() as session:
        session.add(user)
        await session.commit()
        await session.refresh(user)

        await consume_agent_turn(session, user)
        await consume_agent_turn(session, user)
        with pytest.raises(QuotaExceeded, match="agent_input"):
            await consume_agent_turn(session, user)

        stored = await session.scalar(select(User).where(User.id == user.id))
        assert stored is not None
        assert stored.agent_input_used == 2
        assert stored.agent_output_used == 2
        assert stored.edit_used == 0

        await consume_edit(session, stored)
        await consume_edit(session, stored)
        with pytest.raises(QuotaExceeded, match="edit"):
            await consume_edit(session, stored)
