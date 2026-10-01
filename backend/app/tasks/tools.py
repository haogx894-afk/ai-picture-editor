import asyncio
import logging
import uuid

from app.db import SessionFactory
from app.models.tool_run import RunStatus
from app.services import runs, tools

logger = logging.getLogger(__name__)


async def run_tool(_: dict, run_id: uuid.UUID) -> None:
    async with SessionFactory() as session:
        try:
            run = await runs.load(session, run_id)
        except runs.RunNotFound:
            return
        # 队列重投或 worker 重启后的重复消费不应二次扣费
        if run.status.is_terminal:
            return

        try:
            await tools.execute(session, run)
        except asyncio.CancelledError:
            # ARQ cancels this coroutine when the worker timeout expires.  The
            # cancellation otherwise leaves a queued/running ToolRun forever.
            await session.rollback()
            try:
                run = await runs.load(session, run_id)
                if not run.status.is_terminal:
                    await runs.finish(
                        session,
                        run,
                        status=RunStatus.FAILED,
                        error="worker 中断，任务未完成，请重试",
                    )
                    from app.services import agent as agent_service

                    await agent_service.continue_plan(session, run)
            except runs.RunNotFound:
                return
            except Exception:
                logger.exception("记录 worker 中断失败 run_id=%s", run_id)
            raise
