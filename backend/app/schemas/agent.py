import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, Field, field_validator

from app.models import AgentRun
from app.models.tool_run import RunStatus
from app.tools import label_of

MAX_MESSAGE = 1000


class MessageIn(BaseModel):
    text: Annotated[str, Field(min_length=1, max_length=MAX_MESSAGE)]

    @field_validator("text")
    @classmethod
    def _require_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("指令不能为空")
        return value


class PlanStepOut(BaseModel):
    id: str
    tool: str
    label: str
    depends_on: list[str] = []
    run_id: uuid.UUID | None = None
    status: str = "pending"

    @classmethod
    def of(cls, step: dict) -> "PlanStepOut":
        run_id = step.get("run_id")
        return cls(
            id=step.get("id") or step["tool"],
            tool=step["tool"],
            label=label_of(step["tool"], step.get("params")),
            depends_on=list(step.get("depends_on") or []),
            run_id=uuid.UUID(run_id) if run_id else None,
            status=step.get("status") or ("succeeded" if run_id else "pending"),
        )


class TurnActivityOut(BaseModel):
    phase: Literal[
        "planning",
        "executing",
        "awaiting_confirmation",
        "completed",
        "failed",
        "canceled",
    ]
    message: str
    completed_steps: int
    total_steps: int
    current_step_id: str | None = None

    @classmethod
    def of(cls, turn: AgentRun, steps: list[PlanStepOut]) -> "TurnActivityOut":
        completed = sum(step.status == "succeeded" for step in steps)
        total = len(steps)

        if turn.status is RunStatus.RUNNING:
            for index, step in enumerate(steps, start=1):
                if step.status in {"queued", "running"}:
                    return cls(
                        phase="executing",
                        message=f"正在执行第 {index}/{total} 步：{step.label}",
                        completed_steps=completed,
                        total_steps=total,
                        current_step_id=step.id,
                    )
            return cls(
                phase="planning",
                message="正在检查剩余要求并规划后续步骤…",
                completed_steps=completed,
                total_steps=total,
            )

        if turn.status is RunStatus.QUEUED:
            waiting = next((step for step in steps if step.status == "waiting"), None)
            return cls(
                phase="awaiting_confirmation",
                message="计划已生成，等待确认后继续执行",
                completed_steps=completed,
                total_steps=total,
                current_step_id=waiting.id if waiting else None,
            )

        messages = {
            RunStatus.SUCCEEDED: "任务已完成",
            RunStatus.FAILED: "任务执行失败",
            RunStatus.CANCELED: "任务已取消",
        }
        phases = {
            RunStatus.SUCCEEDED: "completed",
            RunStatus.FAILED: "failed",
            RunStatus.CANCELED: "canceled",
        }
        return cls(
            phase=phases[turn.status],
            message=messages[turn.status],
            completed_steps=completed,
            total_steps=total,
        )


class TurnOut(BaseModel):
    id: uuid.UUID
    resumed_from_id: uuid.UUID | None
    continuation_rounds: int
    auto_continue: bool
    revision: int
    goal: str
    reply: str
    status: RunStatus
    error: str | None
    created_at: datetime
    steps: list[PlanStepOut] = []
    activity: TurnActivityOut

    @classmethod
    def of(cls, turn: AgentRun) -> "TurnOut":
        steps = [PlanStepOut.of(step) for step in turn.plan]
        return cls(
            id=turn.id,
            resumed_from_id=turn.resumed_from_id,
            continuation_rounds=turn.continuation_rounds,
            auto_continue=turn.auto_continue,
            revision=turn.revision,
            goal=turn.goal,
            reply=turn.reply,
            status=turn.status,
            error=turn.error,
            created_at=turn.created_at,
            steps=steps,
            activity=TurnActivityOut.of(turn, steps),
        )
