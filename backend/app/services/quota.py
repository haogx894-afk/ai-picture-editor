from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User


class QuotaExceeded(Exception):
    def __init__(self, resource: str):
        self.resource = resource
        super().__init__(resource)


async def consume_agent_turn(session: AsyncSession, user: User) -> None:
    """Reserve one complete Agent turn while holding the user's row lock."""
    locked = await session.get(User, user.id, with_for_update=True)
    if locked is None:
        raise QuotaExceeded("account")
    if locked.agent_input_used >= locked.agent_input_limit:
        raise QuotaExceeded("agent_input")
    if locked.agent_output_used >= locked.agent_output_limit:
        raise QuotaExceeded("agent_output")
    locked.agent_input_used += 1
    locked.agent_output_used += 1
    await session.commit()


async def consume_edit(session: AsyncSession, user: User) -> None:
    locked = await session.get(User, user.id, with_for_update=True)
    if locked is None:
        raise QuotaExceeded("account")
    if locked.edit_used >= locked.edit_limit:
        raise QuotaExceeded("edit")
    locked.edit_used += 1
    await session.commit()
