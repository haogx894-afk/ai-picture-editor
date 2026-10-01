import json
import logging
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from app import agent
from app.agent import plan as plan_mod
from app.layers import Layer, LayerDocument, LayerKind
from app.models import AgentRun, EditSession, ToolRun
from app.models.tool_run import RunStatus
from app.services import assets, runs, selections, sessions, tools
from app.tools import label_of, spec_of

logger = logging.getLogger(__name__)

_HISTORY_TURNS = 6
_HISTORY_FIELD_LIMIT = 320
_HISTORY_TOTAL_LIMIT = 4000
_CONTINUE_EXACT = {"继续", "继续执行", "继续完成", "接着做"}
_CONTINUE_MARKERS = ("上一步", "上一任务", "未完成", "没完成", "没做完", "失败任务")
_MAX_CONTINUATION_ROUNDS = 4


class TurnNotFound(Exception):
    pass


class CannotConfirm(Exception):
    pass


class CannotCancel(Exception):
    pass


class CannotRetry(Exception):
    pass


async def describe(session: AsyncSession, record: EditSession) -> str:
    """给规划模型的画布摘要，只给决策必需的事实。"""
    document = LayerDocument.model_validate(record.document)
    names = [_layer_name(layer) for layer in document.layers]
    parts = [
        f"画幅 {document.width}×{document.height}",
        f"图层 {len(document.layers)} 个，自下而上（{'、'.join(names)}）",
        "layer_id 填图层 id 或名字；不填则作用在选区下最上层图像，换背景作用在背景层",
        f"修订号 {record.revision}",
    ]

    current = await assets.get_for_user(session, record.user_id, record.current_asset_id)
    if current is not None:
        parts.append(f"当前图 {current.image_format}{'，含透明通道' if current.has_alpha else ''}")

    selected = await selections.get(record.id, record.revision)
    if selected:
        markers = selected.get("markers") or []
        where = f"已有选区，{len(markers)} 个标点" if markers else "已有笔刷选区"
        parts.append(f"{where}（选区只限定区域，不限定图层；与 layer_id 同时给出时取交集）")
    else:
        parts.append("当前无选区，区域工具会作用在整个图层")
    return "；".join(parts)


def _layer_name(layer: Layer) -> str:
    text = f"文字「{layer.text[:8]}」" if layer.kind is LayerKind.TEXT and layer.text else None
    name = f"{layer.id}={text or layer.name}"
    return name if layer.visible else f"{name}·隐藏"


async def respond(session: AsyncSession, record: EditSession, goal: str) -> AgentRun:
    """规划一轮指令并落库。多步计划先停住等确认，单步直接开跑。"""
    if _is_continuation(goal):
        return await _continue_latest_failure(session, record, goal)
    return await _plan_and_store(session, record, goal)


async def _plan_and_store(
    session: AsyncSession,
    record: EditSession,
    goal: str,
    *,
    resumed_from_id: uuid.UUID | None = None,
    force_confirm: bool = False,
) -> AgentRun:
    revision = record.revision
    reply, steps, error = "", [], None

    try:
        reply, steps = await agent.run(
            goal,
            await describe(session, record),
            await history_for_planner(session, record),
        )
        steps = await _pin_selection(session, record, steps)
    except agent.PlannerUnavailable as exc:
        error = str(exc)
    except Exception:
        logger.exception("指令规划异常 session_id=%s", record.id)
        await session.rollback()
        error = "规划失败，请重试"

    if error:
        status = RunStatus.FAILED
    elif force_confirm and steps:
        status = RunStatus.QUEUED
        reply = f"{reply.rstrip('。')}。当前画布已变化，请确认后执行。"
    elif plan_mod.needs_confirm(steps):
        status = RunStatus.QUEUED
    elif steps:
        status = RunStatus.RUNNING
    else:
        status = RunStatus.SUCCEEDED

    turn = AgentRun(
        user_id=record.user_id,
        session_id=record.id,
        revision=revision,
        goal=goal,
        reply=reply,
        plan=steps,
        status=status,
        error=error,
        resumed_from_id=resumed_from_id,
        continuation_rounds=0,
    )
    session.add(turn)
    await session.commit()
    await session.refresh(turn)

    if turn.status is RunStatus.RUNNING:
        await _advance(session, turn)
    return turn


async def _continue_latest_failure(
    session: AsyncSession, record: EditSession, goal: str
) -> AgentRun:
    latest = await _latest_turn(session, record)
    if latest is not None and latest.status in {RunStatus.QUEUED, RunStatus.RUNNING}:
        messages = {
            RunStatus.QUEUED: "当前任务正在等待确认，请先确认或取消。",
            RunStatus.RUNNING: "当前任务仍在执行，请等待完成后再继续。",
        }
        return await _notice(session, record, goal, messages[latest.status])
    if latest is not None and latest.plan and latest.status in {
        RunStatus.SUCCEEDED,
        RunStatus.CANCELED,
    }:
        messages = {
            RunStatus.SUCCEEDED: "最近任务已经完成，没有可继续的失败任务。",
            RunStatus.CANCELED: "最近任务已取消，无法继续，请重新描述需求。",
        }
        return await _notice(session, record, goal, messages[latest.status])

    failed = await _latest_failed_turn(session, record)
    if failed is None:
        if latest is not None and latest.status is RunStatus.CANCELED:
            reply = "最近任务已取消，无法继续，请重新描述需求。"
        else:
            reply = "没有可继续的失败任务，请重新描述需求。"
        return await _notice(session, record, goal, reply)

    if not any(step.get("status") == plan_mod.FAILED for step in failed.plan):
        return await _notice(session, record, goal, "最近任务没有可恢复步骤，请重新描述需求。")

    if failed.revision != record.revision:
        return await _plan_and_store(
            session,
            record,
            goal,
            resumed_from_id=failed.id,
            force_confirm=True,
        )

    steps = _copy(failed.plan)
    for step in steps:
        if step.get("status") in {
            plan_mod.FAILED,
            plan_mod.PENDING,
            plan_mod.WAITING,
            plan_mod.QUEUED,
            plan_mod.RUNNING,
        }:
            step["run_id"] = None
            step["status"] = plan_mod.PENDING
            step.pop("approved", None)

    turn = AgentRun(
        user_id=record.user_id,
        session_id=record.id,
        revision=record.revision,
        goal=goal,
        reply="继续执行上一次未完成的任务。",
        plan=steps,
        status=RunStatus.RUNNING,
        error=None,
        resumed_from_id=failed.id,
        continuation_rounds=failed.continuation_rounds,
    )
    session.add(turn)
    await session.commit()
    await session.refresh(turn)
    return await _advance(session, turn)


async def _latest_turn(session: AsyncSession, record: EditSession) -> AgentRun | None:
    return await session.scalar(
        select(AgentRun)
        .where(AgentRun.session_id == record.id)
        .order_by(AgentRun.created_at.desc())
        .limit(1)
    )


async def _latest_failed_turn(session: AsyncSession, record: EditSession) -> AgentRun | None:
    return await session.scalar(
        select(AgentRun)
        .where(AgentRun.session_id == record.id, AgentRun.status == RunStatus.FAILED)
        .order_by(AgentRun.created_at.desc())
        .limit(1)
    )


async def _notice(
    session: AsyncSession, record: EditSession, goal: str, reply: str
) -> AgentRun:
    turn = AgentRun(
        user_id=record.user_id,
        session_id=record.id,
        revision=record.revision,
        goal=goal,
        reply=reply,
        plan=[],
        status=RunStatus.SUCCEEDED,
        error=None,
        continuation_rounds=0,
    )
    session.add(turn)
    await session.commit()
    await session.refresh(turn)
    return turn


def _is_continuation(goal: str) -> bool:
    text = "".join(goal.split())
    return text in _CONTINUE_EXACT or any(marker in text for marker in _CONTINUE_MARKERS)


async def history_for_planner(session: AsyncSession, record: EditSession) -> str:
    """构造有界的会话摘要，避免把完整工具载荷或图片数据送入规划模型。"""
    result = await session.scalars(
        select(AgentRun)
        .where(AgentRun.session_id == record.id)
        .order_by(AgentRun.created_at.desc())
        .limit(_HISTORY_TURNS)
    )
    turns = list(reversed(list(result)))
    if not turns:
        return "暂无历史记录"

    lines = ["以下是最近会话摘要，仅用于理解上下文："]
    for index, turn in enumerate(turns, start=1):
        steps = "、".join(
            f"{label_of(step['tool'], step.get('params'))}[{step.get('status', 'pending')}]"
            for step in turn.plan
        ) or "无工具步骤"
        line = (
            f"第{index}轮：用户={_clip(turn.goal)}；"
            f"Agent={_clip(turn.reply)}；步骤={_clip(steps)}"
        )
        if turn.error:
            line += f"；错误={_clip(turn.error)}"
        lines.append(line)

    return _clip("\n".join(lines), _HISTORY_TOTAL_LIMIT)


def _clip(value: str, limit: int = _HISTORY_FIELD_LIMIT) -> str:
    value = " ".join(value.split())
    return value if len(value) <= limit else value[: limit - 1].rstrip() + "…"


async def _pin_selection(
    session: AsyncSession, record: EditSession, steps: list[dict]
) -> list[dict]:
    """把当轮选区钉进每个需要遮罩的步骤。

    清除选区与修订号递增都发生在第一步之后，显式 id 才能让后续步骤共用同一块区域。
    """
    stored = await selections.get(record.id, record.revision)
    mask_asset_id = (stored or {}).get("mask_asset_id")
    if not mask_asset_id:
        return steps
    for step in steps:
        params = step["params"]
        if _wants_mask(step["tool"]) and not params.get("mask_asset_id"):
            step["params"] = {**params, "mask_asset_id": mask_asset_id}
    return steps


def _wants_mask(tool: str) -> bool:
    return "mask_asset_id" in spec_of(tool).params.model_fields


async def confirm(session: AsyncSession, record: EditSession, turn_id: uuid.UUID) -> AgentRun:
    turn = await _get(session, record, turn_id)
    steps = _copy(turn.plan)
    waiting = [step for step in steps if step["status"] == plan_mod.WAITING]
    if turn.status is not RunStatus.QUEUED and not waiting:
        raise CannotConfirm
    for step in waiting:
        step["status"] = plan_mod.PENDING
        step["approved"] = True
    turn.plan = steps
    turn.status = RunStatus.RUNNING
    _touch(turn)
    await session.commit()
    return await _advance(session, turn)


async def cancel(session: AsyncSession, record: EditSession, turn_id: uuid.UUID) -> AgentRun:
    turn = await _get(session, record, turn_id)
    if turn.status.is_terminal:
        raise CannotCancel
    turn.plan = plan_mod.cancel_remaining(_copy(turn.plan))
    await _cancel_queued_runs(session, turn.plan)
    _touch(turn)
    turn.status = RunStatus(plan_mod.settle(turn.plan))
    await session.commit()
    await session.refresh(turn)
    return turn


async def retry(session: AsyncSession, record: EditSession, turn_id: uuid.UUID) -> AgentRun:
    turn = await _get(session, record, turn_id)
    steps = _copy(turn.plan)
    failed = next((step for step in reversed(steps) if step["status"] == plan_mod.FAILED), None)
    if failed is None:
        raise CannotRetry
    failed["run_id"] = None
    failed["status"] = plan_mod.PENDING
    turn.plan = steps
    turn.status = RunStatus.RUNNING
    turn.error = None
    _touch(turn)
    await session.commit()
    return await _advance(session, turn)


async def continue_plan(session: AsyncSession, run: ToolRun) -> None:
    """某一步结束后推进后续依赖，刷新后也能从已落库的计划接着跑。"""
    if run.session_id is None:
        return
    turn = await _turn_of_run(session, run)
    if turn is None:
        return

    steps = _copy(turn.plan)
    record = await sessions.load(session, run.session_id)
    for step in steps:
        if step.get("run_id") == str(run.id):
            step["status"] = run.status.value
    turn.plan = steps
    # 计划执行过程中，前置成功步骤可能推进画布 revision；失败步骤不更新
    # 记录的基准，这样用户在失败后修改画布时仍能被识别为 revision 变化。
    if run.status is RunStatus.SUCCEEDED:
        turn.revision = record.revision
    _touch(turn)
    # 先不落库：同步的下一步（如翻转）跟这次一起提交，前端不会捞到「上一步完了、下一步还没开始」
    await _advance(session, turn)


async def turns_of(session: AsyncSession, record: EditSession, limit: int = 50) -> list[AgentRun]:
    result = await session.scalars(
        select(AgentRun)
        .where(AgentRun.session_id == record.id)
        .order_by(AgentRun.created_at)
        .limit(limit)
    )
    return list(result)


async def _advance(session: AsyncSession, turn: AgentRun) -> AgentRun:
    steps = _copy(turn.plan)
    progressed = True
    while progressed:
        progressed = False
        for step in plan_mod.ready(steps):
            if spec_of(step["tool"]).needs_approval and not step.get("approved"):
                step["status"] = plan_mod.WAITING
                continue
            run = await tools.submit(
                session, turn.user_id, step["tool"], step["params"], turn.session_id
            )
            step["run_id"] = str(run.id)
            step["status"] = run.status.value
            if run.status is RunStatus.SUCCEEDED:
                record = await sessions.load(session, turn.session_id)
                turn.revision = record.revision
            turn.plan = steps
            turn.status = RunStatus.RUNNING
            _touch(turn)
            await session.commit()
            progressed = run.status is RunStatus.SUCCEEDED

    settled = RunStatus(plan_mod.settle(steps))
    if settled is RunStatus.SUCCEEDED and _should_continue(turn):
        turn.plan = steps
        turn.status = settled
        _touch(turn)
        await session.commit()
        await session.refresh(turn)
        return await _continue_successful_batch(session, turn)

    turn.plan = steps
    turn.status = settled
    waiting = any(step["status"] == plan_mod.WAITING for step in steps)
    if turn.status is RunStatus.QUEUED and waiting:
        turn.reply = turn.reply or "下一步需要确认后再执行。"
    _touch(turn)
    await session.commit()
    await session.refresh(turn)
    return turn


async def _continue_successful_batch(session: AsyncSession, turn: AgentRun) -> AgentRun:
    """Ask the planner for the next batch without creating another AgentRun."""
    if turn.continuation_rounds >= _MAX_CONTINUATION_ROUNDS:
        turn.status = RunStatus.SUCCEEDED
        turn.reply = _append_reply(
            turn.reply,
            f"已完成当前批次，但已达到连续规划上限（{_MAX_CONTINUATION_ROUNDS} 轮）。",
        )
        _touch(turn)
        await session.commit()
        await session.refresh(turn)
        return turn

    record = await sessions.load(session, turn.session_id)
    completed = _completed_summary(turn.plan)
    planning_error = False
    try:
        reply, proposed = await agent.run(
            turn.goal,
            await describe(session, record),
            await history_for_planner(session, record),
            completed_steps=completed,
        )
        proposed = await _pin_selection(session, record, proposed)
    except agent.PlannerUnavailable:
        proposed = []
        planning_error = True
    except Exception:
        logger.exception("续规划异常 session_id=%s turn_id=%s", record.id, turn.id)
        proposed = []
        planning_error = True

    fresh = _new_steps(turn.plan, proposed)
    if not fresh:
        if planning_error:
            turn.status = RunStatus.FAILED
            turn.error = "续规划失败，请重新描述需求"
            addition = "已完成部分任务，但后续规划失败，请重新描述未完成要求。"
        else:
            turn.status = RunStatus.SUCCEEDED
            turn.error = None
            addition = "已完成部分任务，但没有可安全执行的后续步骤。请检查未完成要求后重新描述。"
        turn.reply = _append_reply(turn.reply, addition)
        _touch(turn)
        await session.commit()
        await session.refresh(turn)
        return turn

    turn.continuation_rounds += 1
    turn.plan = [*turn.plan, *fresh]
    turn.status = RunStatus.RUNNING
    labels = "、".join(label_of(step["tool"], step.get("params")) for step in fresh)
    turn.reply = _append_reply(turn.reply, f"已完成当前批次，继续处理：{labels}。")
    _touch(turn)
    await session.commit()
    return await _advance(session, turn)


def _should_continue(turn: AgentRun) -> bool:
    """Only complex goals opt into another planning round."""
    goal = "".join(turn.goal.split())
    numbered = sum(goal.count(f"{index}.") for index in range(1, 10))
    return len(goal) >= 80 or numbered >= 2 or any(
        mark in goal for mark in ("以下", "清单", "分别")
    )


def _completed_summary(steps: list[dict]) -> str:
    completed = [
        f"{label_of(step['tool'], step.get('params'))}[{step.get('status', plan_mod.PENDING)}]"
        for step in steps
        if step.get("status") == plan_mod.SUCCEEDED
    ]
    return "、".join(completed) if completed else "暂无已完成步骤"


def _new_steps(existing: list[dict], proposed: list[dict]) -> list[dict]:
    known = {_step_key(step) for step in existing}
    fresh: list[dict] = []
    previous = existing[-1]["id"] if existing else None
    next_index = len(existing) + 1
    for source in proposed:
        if _step_key(source) in known:
            continue
        step = dict(source)
        step["id"] = f"s{next_index}"
        step["depends_on"] = [previous] if previous else []
        step["run_id"] = None
        step["status"] = plan_mod.PENDING
        step.pop("approved", None)
        fresh.append(step)
        known.add(_step_key(source))
        previous = step["id"]
        next_index += 1
    return fresh


def _step_key(step: dict) -> tuple[str, str]:
    return step["tool"], json.dumps(step.get("params") or {}, sort_keys=True, separators=(",", ":"))


def _append_reply(current: str, addition: str) -> str:
    current = current.rstrip("。 ")
    return f"{current}；{addition}" if current else addition


async def _cancel_queued_runs(session: AsyncSession, steps: list[dict]) -> None:
    for step in steps:
        if not step.get("run_id") or step["status"] != plan_mod.QUEUED:
            continue
        run = await session.get(ToolRun, uuid.UUID(step["run_id"]))
        if run is None or run.status is not RunStatus.QUEUED:
            continue
        await runs.finish(session, run, status=RunStatus.CANCELED, error="已取消")
        step["status"] = plan_mod.CANCELED


async def _get(session: AsyncSession, record: EditSession, turn_id: uuid.UUID) -> AgentRun:
    turn = await session.scalar(
        select(AgentRun).where(AgentRun.id == turn_id, AgentRun.session_id == record.id)
    )
    if turn is None:
        raise TurnNotFound
    return turn


async def _turn_of_run(session: AsyncSession, run: ToolRun) -> AgentRun | None:
    turns = await session.scalars(
        select(AgentRun)
        .where(AgentRun.session_id == run.session_id)
        .order_by(AgentRun.created_at.desc())
        .limit(20)
    )
    run_id = str(run.id)
    for turn in turns:
        if any(step.get("run_id") == run_id for step in turn.plan):
            return turn
    return None


def _copy(steps: list) -> list[dict]:
    return [dict(step) for step in steps]


def _touch(turn: AgentRun) -> None:
    flag_modified(turn, "plan")
