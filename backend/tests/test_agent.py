import asyncio
import uuid

import httpx
import pytest
from langchain_core.messages import AIMessage

from app.agent import graph
from app.agent.llm import planner
from app.config import get_settings
from app.models.tool_run import RunStatus
from app.services import tools as tool_service
from app.tasks.tools import run_tool
from tests.canvas import apply, error_of, layers, scene, select, settle
from tests.test_sessions import open_session

PROMPT = {"prompt": "浅木色桌面上的白色马克杯", "ratio": "1:1", "count": 2}


class FakePlanner:
    def __init__(self, message: AIMessage) -> None:
        self._message = message

    async def ainvoke(self, messages):
        self.messages = messages
        return self._message


class SequencePlanner:
    def __init__(self, *messages: AIMessage) -> None:
        self._messages = list(messages)
        self.messages: list[list] = []

    async def ainvoke(self, messages):
        self.messages.append(messages)
        if len(self.messages) <= len(self._messages):
            return self._messages[len(self.messages) - 1]
        return self._messages[-1]


@pytest.fixture
def fake_planner(monkeypatch):
    def install(message: AIMessage) -> FakePlanner:
        fake = FakePlanner(message)
        monkeypatch.setattr(graph, "planner", lambda: fake)
        return fake

    return install


def tool_call(name: str, args: dict) -> AIMessage:
    return tool_calls((name, args))


def tool_calls(*pairs: tuple[str, dict]) -> AIMessage:
    return AIMessage(
        content="",
        tool_calls=[
            {"name": name, "args": args, "id": f"call_{index}"}
            for index, (name, args) in enumerate(pairs, start=1)
        ],
    )


@pytest.fixture
async def signed_in(client: httpx.AsyncClient, credentials):
    await client.post("/api/auth/register", json=credentials)
    return client


async def send(client: httpx.AsyncClient, session_id: str, text: str) -> dict:
    response = await client.post(f"/api/sessions/{session_id}/messages", json={"text": text})
    assert response.status_code == 201, response.text
    return response.json()


async def test_tool_call_is_planned_and_dispatched(signed_in: httpx.AsyncClient, fake_planner):
    fake_planner(tool_call("generate_image", PROMPT))
    session_id = (await open_session(signed_in))["id"]

    turn = await send(signed_in, session_id, "换一张白底马克杯")

    assert turn["status"] == "running"
    assert [step["tool"] for step in turn["steps"]] == ["generate_image"]
    assert turn["steps"][0]["label"] == "生成图片"
    assert turn["steps"][0]["run_id"]
    assert "没太理解" not in turn["reply"]
    assert "生成图片" in turn["reply"]


async def test_marketing_tool_is_planned_and_dispatched(signed_in: httpx.AsyncClient, fake_planner):
    fake_planner(tool_call("generate_marketing", {"kind": "product"}))
    session_id = (await open_session(signed_in))["id"]

    turn = await send(signed_in, session_id, "出一张商品主图")

    assert turn["status"] == "running"
    assert [step["tool"] for step in turn["steps"]] == ["generate_marketing"]
    assert turn["steps"][0]["label"] == "营销图"
    assert "营销图" in turn["reply"]


async def test_plain_answer_dispatches_nothing(signed_in: httpx.AsyncClient, fake_planner):
    fake_planner(AIMessage(content="现有工具做不到这个。"))
    session_id = (await open_session(signed_in))["id"]

    turn = await send(signed_in, session_id, "帮我写一首诗")

    assert turn["steps"] == []
    assert turn["reply"] == "现有工具做不到这个。"


async def test_long_refusal_keeps_only_the_first_sentence(
    signed_in: httpx.AsyncClient, fake_planner
):
    fake_planner(
        AIMessage(
            content="选区不一定包含老鼠。"
            "replace_region 需要完整提示词，adjust_image 也不能局部改色。"
        )
    )
    session_id = (await open_session(signed_in))["id"]

    turn = await send(signed_in, session_id, "老鼠换成红色")

    assert turn["steps"] == []
    assert turn["reply"] == "选区不一定包含老鼠。"
    assert "replace_region" not in turn["reply"]


def test_spoken_ignores_fallback_when_plan_exists():
    from app.agent.graph import _FALLBACK_REPLY, spoken

    assert "没太理解" not in spoken("", [{"tool": "flip_layer"}])
    assert spoken(_FALLBACK_REPLY, [{"tool": "flip_layer"}, {"tool": "rotate_layer"}]).startswith(
        "将按以下步骤执行"
    )


async def test_canvas_facts_are_given_to_the_planner(signed_in: httpx.AsyncClient, fake_planner):
    fake = fake_planner(AIMessage(content="好的。"))
    session_id = (await open_session(signed_in))["id"]

    await send(signed_in, session_id, "看看这张图")

    system = fake.messages[0].content
    assert "画幅 320×240" in system
    assert "修订号 1" in system
    assert "底图" in system
    assert "当前无选区" in system


async def test_existing_selection_is_given_to_the_planner(
    signed_in: httpx.AsyncClient, fake_planner
):
    fake = fake_planner(tool_call("replace_region", {"prompt": "改成黑色"}))
    session = await open_session(signed_in)
    selected = await signed_in.post(
        f"/api/sessions/{session['id']}/selection",
        json={"revision": session["revision"], "points": [{"x": 0.5, "y": 0.5}]},
    )
    assert selected.status_code == 200

    turn = await send(signed_in, session["id"], "骨头改成黑色")

    assert "已有选区" in fake.messages[0].content
    assert [step["tool"] for step in turn["steps"]] == ["replace_region"]


async def test_unregistered_tool_is_refused(signed_in: httpx.AsyncClient, fake_planner):
    fake_planner(tool_call("teleport_subject", {}))
    session_id = (await open_session(signed_in))["id"]

    turn = await send(signed_in, session_id, "把主体传送走")

    assert turn["steps"] == []
    assert "执行不了" in turn["reply"]


async def test_illegal_params_are_refused(signed_in: httpx.AsyncClient, fake_planner):
    fake_planner(tool_call("generate_image", {"prompt": "  ", "count": 99}))
    session_id = (await open_session(signed_in))["id"]

    turn = await send(signed_in, session_id, "随便来一张")

    assert turn["steps"] == []
    assert "执行不了" in turn["reply"]


async def test_results_join_the_wall_without_switching_current(
    signed_in: httpx.AsyncClient, fake_planner
):
    fake_planner(tool_call("generate_image", PROMPT))
    session = await open_session(signed_in)
    turn = await send(signed_in, session["id"], "换一张")

    await run_tool({}, uuid.UUID(turn["steps"][0]["run_id"]))

    updated = (await signed_in.get(f"/api/sessions/{session['id']}")).json()
    assert len(updated["assets"]) == 3
    assert updated["current_asset_id"] == session["current_asset_id"]
    assert updated["revision"] == 1

    turns = (await signed_in.get(f"/api/sessions/{session['id']}/messages")).json()
    assert turns[-1]["status"] == "succeeded"
    assert turns[-1]["steps"][0]["status"] == "succeeded"


async def test_conversation_is_returned_in_order(signed_in: httpx.AsyncClient, fake_planner):
    fake_planner(AIMessage(content="好的。"))
    session_id = (await open_session(signed_in))["id"]

    await send(signed_in, session_id, "第一句")
    await send(signed_in, session_id, "第二句")

    turns = (await signed_in.get(f"/api/sessions/{session_id}/messages")).json()
    assert [turn["goal"] for turn in turns] == ["第一句", "第二句"]


async def test_planner_receives_bounded_conversation_history(
    signed_in: httpx.AsyncClient, fake_planner
):
    fake = fake_planner(AIMessage(content="好的。"))
    session_id = (await open_session(signed_in))["id"]

    await send(signed_in, session_id, "第一轮请求")
    await send(signed_in, session_id, "第二轮请求")

    system = fake.messages[0].content
    assert "会话历史" in system
    assert "第一轮请求" in system
    assert "第二轮请求" not in system


async def test_missing_api_key_fails_the_turn(signed_in: httpx.AsyncClient, monkeypatch):
    """模型不可用时必须明确失败，不能伪造成功结果。"""
    settings = get_settings()
    monkeypatch.setattr(settings, "dashscope_api_key", "")
    planner.cache_clear()
    session_id = (await open_session(signed_in))["id"]

    turn = await send(signed_in, session_id, "换个背景")

    planner.cache_clear()
    assert turn["status"] == "failed"
    assert "DASHSCOPE_API_KEY" in turn["error"]


async def test_blank_message_is_rejected(signed_in: httpx.AsyncClient):
    session_id = (await open_session(signed_in))["id"]

    response = await signed_in.post(f"/api/sessions/{session_id}/messages", json={"text": "   "})

    assert response.status_code == 422


async def test_messages_require_authentication(client: httpx.AsyncClient):
    path = f"/api/sessions/{uuid.uuid4()}/messages"

    assert (await client.get(path)).status_code == 401
    assert (await client.post(path, json={"text": "你好"})).status_code == 401


def test_cyclic_dependencies_are_rejected():
    from app.agent.plan import PlanError, assemble

    with pytest.raises(PlanError, match="循环"):
        assemble(
            [
                {"id": "a", "tool": "flip_layer", "params": {}, "depends_on": ["b"]},
                {"id": "b", "tool": "flip_layer", "params": {}, "depends_on": ["a"]},
            ]
        )


def test_plan_longer_than_limit_is_rejected():
    from app.agent.plan import MAX_STEPS, PlanError, assemble

    with pytest.raises(PlanError, match="超过"):
        assemble([{"tool": "flip_layer", "params": {}}] * (MAX_STEPS + 1))


async def test_multi_step_plan_waits_for_confirm(signed_in: httpx.AsyncClient, fake_planner):
    fake_planner(
        tool_calls(
            ("flip_layer", {"direction": "horizontal"}),
            ("rotate_layer", {"angle": 15}),
        )
    )
    session_id = (await open_session(signed_in))["id"]

    turn = await send(signed_in, session_id, "水平翻转再转 15 度")

    assert turn["status"] == "queued"
    assert "没太理解" not in turn["reply"]
    assert "确认后开始" in turn["reply"]
    assert [step["tool"] for step in turn["steps"]] == ["flip_layer", "rotate_layer"]
    assert turn["steps"][1]["depends_on"] == ["s1"]
    assert all(step["run_id"] is None for step in turn["steps"])

    session = (await signed_in.get(f"/api/sessions/{session_id}")).json()
    assert session["document"]["layers"][0]["transform"]["scale_x"] == 1


async def test_flip_steps_show_their_direction(signed_in: httpx.AsyncClient, fake_planner):
    fake_planner(
        tool_calls(
            ("flip_layer", {"direction": "horizontal"}),
            ("flip_layer", {"direction": "vertical"}),
        )
    )
    session_id = (await open_session(signed_in))["id"]

    turn = await send(signed_in, session_id, "水平翻转再垂直翻转")

    assert [step["label"] for step in turn["steps"]] == ["水平翻转", "垂直翻转"]
    assert "水平翻转、垂直翻转" in turn["reply"]


async def test_confirm_runs_dependent_steps_in_order(signed_in: httpx.AsyncClient, fake_planner):
    fake_planner(
        tool_calls(
            ("flip_layer", {"direction": "horizontal"}),
            ("rotate_layer", {"angle": 15}),
        )
    )
    session_id = (await open_session(signed_in))["id"]
    turn = await send(signed_in, session_id, "翻转并旋转")

    confirmed = (
        await signed_in.post(f"/api/sessions/{session_id}/messages/{turn['id']}/confirm")
    ).json()
    layer = (
        await signed_in.get(f"/api/sessions/{session_id}")
    ).json()["document"]["layers"][0]

    assert confirmed["status"] == "succeeded"
    assert [step["status"] for step in confirmed["steps"]] == ["succeeded", "succeeded"]
    assert layer["transform"]["scale_x"] == -1
    assert layer["transform"]["rotation"] == 15


async def test_queued_step_unblocks_the_next(signed_in: httpx.AsyncClient, fake_planner):
    fake_planner(
        tool_calls(
            ("remove_background", {}),
            ("flip_layer", {"direction": "horizontal"}),
        )
    )
    session = await open_session(signed_in)
    turn = await send(signed_in, session["id"], "去背景再水平翻转")
    started = (
        await signed_in.post(f"/api/sessions/{session['id']}/messages/{turn['id']}/confirm")
    ).json()

    assert started["status"] == "running"
    assert started["steps"][0]["run_id"]
    assert started["steps"][1]["run_id"] is None

    await run_tool({}, uuid.UUID(started["steps"][0]["run_id"]))
    finished = (await signed_in.get(f"/api/sessions/{session['id']}/messages")).json()[-1]
    updated = (await signed_in.get(f"/api/sessions/{session['id']}")).json()

    assert finished["status"] == "succeeded"
    assert [step["status"] for step in finished["steps"]] == ["succeeded", "succeeded"]
    assert updated["document"]["layers"][0]["transform"]["scale_x"] == -1


async def test_long_goal_continues_planning_after_first_batch(
    signed_in: httpx.AsyncClient, monkeypatch
):
    from app.services import runs as run_service

    planner_instance = SequencePlanner(
        tool_call("split_layers", {}),
        tool_call("flip_layer", {"direction": "horizontal"}),
        AIMessage(content="这张图已完成，没有其它安全可执行步骤。"),
    )
    monkeypatch.setattr(graph, "planner", lambda: planner_instance)

    async def succeed(_session, run):
        await run_service.finish(
            _session, run, status=RunStatus.SUCCEEDED, result={}
        )
        from app.services import agent as agent_service

        await agent_service.continue_plan(_session, run)

    monkeypatch.setattr(tool_service, "execute", succeed)
    session = await open_session(signed_in)
    goal = (
        "请按清单完成这张图片的复杂修图任务：1. 先拆分人物和背景；"
        "2. 再水平翻转主体；3. 保持其它内容不变。"
    )

    turn = await send(signed_in, session["id"], goal)
    assert len(planner_instance.messages) == 1
    assert turn["status"] == "running"
    first_run_id = turn["steps"][0]["run_id"]

    await run_tool({}, uuid.UUID(first_run_id))
    completed = (await signed_in.get(f"/api/sessions/{session['id']}/messages")).json()[-1]

    assert len(planner_instance.messages) == 3
    assert completed["status"] == "succeeded"
    assert [step["tool"] for step in completed["steps"]] == ["split_layers", "flip_layer"]
    assert all(step["status"] == "succeeded" for step in completed["steps"])
    assert "拆层" in planner_instance.messages[1][0].content
    assert goal in planner_instance.messages[1][1].content


async def test_short_goal_does_not_trigger_continuation_planning(
    signed_in: httpx.AsyncClient, fake_planner
):
    fake = fake_planner(tool_call("flip_layer", {"direction": "horizontal"}))
    session = await open_session(signed_in)

    turn = await send(signed_in, session["id"], "水平翻转")

    assert turn["status"] == "succeeded"
    assert fake.messages


async def test_continuation_planner_error_is_visible_as_failed(
    signed_in: httpx.AsyncClient, monkeypatch
):
    from app.models.tool_run import RunStatus
    from app.services import agent as agent_service
    from app.services import runs as run_service

    class FailingContinuationPlanner:
        def __init__(self):
            self.calls = 0

        async def ainvoke(self, _messages):
            self.calls += 1
            if self.calls == 1:
                return tool_call("split_layers", {})
            raise RuntimeError("planner unavailable")

    planner_instance = FailingContinuationPlanner()
    monkeypatch.setattr(graph, "planner", lambda: planner_instance)

    async def succeed(_session, run):
        await run_service.finish(_session, run, status=RunStatus.SUCCEEDED, result={})
        await agent_service.continue_plan(_session, run)

    monkeypatch.setattr(tool_service, "execute", succeed)
    session = await open_session(signed_in)
    goal = "请按清单完成复杂修图任务：1. 先拆层；2. 再继续处理剩余修改。"

    turn = await send(signed_in, session["id"], goal)
    await run_tool({}, uuid.UUID(turn["steps"][0]["run_id"]))

    completed = (await signed_in.get(f"/api/sessions/{session['id']}/messages")).json()[-1]
    assert planner_instance.calls == 2
    assert completed["status"] == "failed"
    assert "续规划失败" in completed["error"]


async def test_continuation_deduplicates_same_tool_and_params(
    signed_in: httpx.AsyncClient, monkeypatch
):
    from app.services import runs as run_service

    planner_instance = SequencePlanner(
        tool_call("split_layers", {}),
        tool_call("split_layers", {}),
    )
    monkeypatch.setattr(graph, "planner", lambda: planner_instance)

    async def succeed(_session, run):
        await run_service.finish(_session, run, status=RunStatus.SUCCEEDED, result={})
        from app.services import agent as agent_service

        await agent_service.continue_plan(_session, run)

    monkeypatch.setattr(tool_service, "execute", succeed)
    session = await open_session(signed_in)
    turn = await send(
        signed_in,
        session["id"],
        "请按清单完成复杂任务：1. 拆层；2. 保持图层结构不变。",
    )

    await run_tool({}, uuid.UUID(turn["steps"][0]["run_id"]))
    completed = (await signed_in.get(f"/api/sessions/{session['id']}/messages")).json()[-1]

    assert len(planner_instance.messages) == 2
    assert len(completed["steps"]) == 1
    assert "没有可安全执行" in completed["reply"]


async def test_continuation_stops_after_real_tool_failure(
    signed_in: httpx.AsyncClient, monkeypatch
):
    from app.services import runs as run_service

    planner_instance = SequencePlanner(
        tool_call("split_layers", {}),
        tool_call("flip_layer", {"direction": "horizontal"}),
    )
    monkeypatch.setattr(graph, "planner", lambda: planner_instance)

    async def fail(_session, run):
        await run_service.finish(_session, run, status=RunStatus.FAILED, error="工具失败")
        from app.services import agent as agent_service

        await agent_service.continue_plan(_session, run)

    monkeypatch.setattr(tool_service, "execute", fail)
    session = await open_session(signed_in)
    turn = await send(
        signed_in,
        session["id"],
        "请按清单完成复杂任务：1. 拆层；2. 再水平翻转。",
    )

    await run_tool({}, uuid.UUID(turn["steps"][0]["run_id"]))
    failed = (await signed_in.get(f"/api/sessions/{session['id']}/messages")).json()[-1]

    assert len(planner_instance.messages) == 1
    assert failed["status"] == "failed"
    assert failed["steps"][0]["status"] == "failed"


async def test_two_layers_in_one_turn_share_the_same_selection(
    signed_in: httpx.AsyncClient, fake_planner
):
    """选区被钉进每一步，第一步清除选区、修订号递增都不影响第二步。"""
    fake_planner(
        tool_calls(
            ("replace_region", {"prompt": "改成红色", "layer_id": "subject"}),
            ("replace_region", {"prompt": "改成蓝色", "layer_id": "background"}),
        )
    )
    session = await open_session(signed_in, image=scene())
    before = await apply(signed_in, session["id"], "split_layers")
    await select(signed_in, session["id"], before["revision"], points=[{"x": 0.5, "y": 0.5}])

    turn = await send(signed_in, session["id"], "主体改红色，背景改蓝色")
    await signed_in.post(f"/api/sessions/{session['id']}/messages/{turn['id']}/confirm")
    finished = await settle(signed_in, session["id"])
    after = (await signed_in.get(f"/api/sessions/{session['id']}")).json()

    assert finished["status"] == "succeeded"
    for layer_id in ("subject", "background"):
        assert layers(after)[layer_id]["asset_id"] != layers(before)[layer_id]["asset_id"]


async def test_selection_expires_when_the_plan_changes_the_canvas(
    signed_in: httpx.AsyncClient, fake_planner
):
    fake_planner(
        tool_calls(
            ("crop_canvas", {"ratio": "1:1"}),
            ("replace_region", {"prompt": "改成红色"}),
        )
    )
    session = await open_session(signed_in)
    await select(signed_in, session["id"], session["revision"], points=[{"x": 0.5, "y": 0.5}])

    turn = await send(signed_in, session["id"], "先裁成正方形再把选区改成红色")
    await signed_in.post(f"/api/sessions/{session['id']}/messages/{turn['id']}/confirm")
    finished = await settle(signed_in, session["id"])
    failed = next(step for step in finished["steps"] if step["tool"] == "replace_region")

    assert finished["status"] == "failed"
    assert "选区失效" in await error_of(signed_in, failed["run_id"])


async def test_cancel_drops_unstarted_steps(signed_in: httpx.AsyncClient, fake_planner):
    fake_planner(
        tool_calls(
            ("flip_layer", {"direction": "horizontal"}),
            ("rotate_layer", {"angle": 10}),
        )
    )
    session_id = (await open_session(signed_in))["id"]
    turn = await send(signed_in, session_id, "翻转再旋转")

    canceled = (
        await signed_in.post(f"/api/sessions/{session_id}/messages/{turn['id']}/cancel")
    ).json()
    session = (await signed_in.get(f"/api/sessions/{session_id}")).json()

    assert canceled["status"] == "canceled"
    assert [step["status"] for step in canceled["steps"]] == ["canceled", "canceled"]
    assert session["document"]["layers"][0]["transform"]["scale_x"] == 1


async def test_failed_step_can_be_retried(signed_in: httpx.AsyncClient, fake_planner):
    fake_planner(tool_call("replace_region", {"prompt": "改成黑色", "layer_id": "不存在的层"}))
    session_id = (await open_session(signed_in))["id"]
    turn = await send(signed_in, session_id, "把不存在的层换成黑色")

    await run_tool({}, uuid.UUID(turn["steps"][0]["run_id"]))
    failed = (await signed_in.get(f"/api/sessions/{session_id}/messages")).json()[-1]
    assert failed["status"] == "failed"

    retried = (
        await signed_in.post(f"/api/sessions/{session_id}/messages/{failed['id']}/retry")
    ).json()
    assert retried["status"] == "running"
    assert retried["steps"][0]["run_id"] != failed["steps"][0]["run_id"]


async def test_continue_resumes_latest_failure_without_repeating_successful_steps(
    signed_in: httpx.AsyncClient, fake_planner
):
    fake_planner(
        tool_calls(
            ("flip_layer", {"direction": "horizontal"}),
            ("replace_region", {"prompt": "改成黑色", "layer_id": "不存在的层"}),
        )
    )
    session = await open_session(signed_in)
    turn = await send(signed_in, session["id"], "先翻转再改色")
    started = (
        await signed_in.post(f"/api/sessions/{session['id']}/messages/{turn['id']}/confirm")
    ).json()

    first_run_id = started["steps"][0]["run_id"]
    await run_tool({}, uuid.UUID(first_run_id))
    after_first = (await signed_in.get(f"/api/sessions/{session['id']}/messages")).json()[-1]
    second_run_id = after_first["steps"][1]["run_id"]
    await run_tool({}, uuid.UUID(second_run_id))
    failed = (await signed_in.get(f"/api/sessions/{session['id']}/messages")).json()[-1]
    assert failed["status"] == "failed"
    assert [step["status"] for step in failed["steps"]] == ["succeeded", "failed"]
    current = (await signed_in.get(f"/api/sessions/{session['id']}" )).json()
    assert failed["revision"] == current["revision"]

    resumed = await send(signed_in, session["id"], "上一步任务没完成，继续完成")

    assert resumed["id"] != failed["id"]
    assert resumed["steps"][0]["status"] == "succeeded"
    assert resumed["steps"][0]["run_id"] == first_run_id
    assert resumed["steps"][1]["run_id"] != second_run_id
    current = (await signed_in.get(f"/api/sessions/{session['id']}" )).json()
    assert current["document"]["layers"][0]["transform"]["scale_x"] == -1


async def test_continue_replans_after_canvas_revision_changes(
    signed_in: httpx.AsyncClient, fake_planner
):
    fake = fake_planner(
        tool_calls(
            ("flip_layer", {"direction": "horizontal"}),
            ("replace_region", {"prompt": "改成黑色", "layer_id": "不存在的层"}),
        )
    )
    session = await open_session(signed_in)
    turn = await send(signed_in, session["id"], "先翻转再改色")
    started = (
        await signed_in.post(f"/api/sessions/{session['id']}/messages/{turn['id']}/confirm")
    ).json()
    await run_tool({}, uuid.UUID(started["steps"][0]["run_id"]))
    after_first = (await signed_in.get(f"/api/sessions/{session['id']}/messages")).json()[-1]
    await run_tool({}, uuid.UUID(after_first["steps"][1]["run_id"]))
    failed = (await signed_in.get(f"/api/sessions/{session['id']}/messages")).json()[-1]

    await apply(signed_in, session["id"], "flip_layer", {"direction": "vertical"})
    fake._message = tool_call("rotate_layer", {"angle": 15})

    replanned = await send(signed_in, session["id"], "上一步任务没完成，继续完成")

    assert replanned["resumed_from_id"] == failed["id"]
    assert replanned["status"] == "queued"
    assert [step["tool"] for step in replanned["steps"]] == ["rotate_layer"]
    assert replanned["steps"][0]["run_id"] is None
    assert "画布已变化" in replanned["reply"]


async def test_continue_does_not_duplicate_a_running_task(
    signed_in: httpx.AsyncClient, fake_planner
):
    fake_planner(tool_call("remove_background", {}))
    session = await open_session(signed_in)

    running = await send(signed_in, session["id"], "去除背景")
    continued = await send(signed_in, session["id"], "继续")

    assert running["status"] == "running"
    assert continued["steps"] == []
    assert continued["resumed_from_id"] is None
    assert "仍在执行" in continued["reply"]


async def test_continue_reports_when_latest_task_is_already_succeeded(
    signed_in: httpx.AsyncClient, fake_planner
):
    fake_planner(AIMessage(content="好的。"))
    session = await open_session(signed_in)

    await send(signed_in, session["id"], "查看当前图片")
    continued = await send(signed_in, session["id"], "继续")

    assert continued["steps"] == []
    assert continued["resumed_from_id"] is None
    assert "没有可继续的失败任务" in continued["reply"]


async def test_continue_ignores_a_newer_running_notice_and_resumes_failure(
    signed_in: httpx.AsyncClient, fake_planner
):
    fake_planner(tool_call("replace_region", {"prompt": "改成黑色", "layer_id": "不存在的层"}))
    session = await open_session(signed_in)

    running = await send(signed_in, session["id"], "把不存在的层换成黑色")
    notice = await send(signed_in, session["id"], "继续")
    assert notice["steps"] == []
    assert "仍在执行" in notice["reply"]

    await run_tool({}, uuid.UUID(running["steps"][0]["run_id"]))
    turns = (await signed_in.get(f"/api/sessions/{session['id']}/messages")).json()
    failed = next(turn for turn in turns if turn["id"] == running["id"])
    assert failed["status"] == "failed"

    resumed = await send(signed_in, session["id"], "继续")

    assert resumed["resumed_from_id"] == failed["id"]
    assert resumed["status"] == "running"


async def test_worker_interruption_marks_tool_and_agent_as_failed(
    signed_in: httpx.AsyncClient, fake_planner, monkeypatch
):
    fake_planner(tool_call("remove_background", {}))
    session = await open_session(signed_in)
    turn = await send(signed_in, session["id"], "去除背景")

    async def interrupted(*_args, **_kwargs):
        raise asyncio.CancelledError

    monkeypatch.setattr(tool_service, "execute", interrupted)

    with pytest.raises(asyncio.CancelledError):
        await run_tool({}, uuid.UUID(turn["steps"][0]["run_id"]))

    run = (await signed_in.get(f"/api/runs/{turn['steps'][0]['run_id']}"))
    assert run.status_code == 200
    assert run.json()["status"] == "failed"
    assert "中断" in (run.json()["error"] or "")

    message = (await signed_in.get(f"/api/sessions/{session['id']}/messages")).json()[-1]
    assert message["status"] == "failed"
    assert message["steps"][0]["status"] == "failed"


async def test_queue_failure_marks_tool_as_failed(
    signed_in: httpx.AsyncClient, monkeypatch
):
    async def unavailable(*_args, **_kwargs):
        raise RuntimeError("redis unavailable")

    monkeypatch.setattr(tool_service, "enqueue", unavailable)
    session = await open_session(signed_in)

    response = await signed_in.post(
        f"/api/sessions/{session['id']}/tools",
        json={"tool": "remove_background", "params": {}},
    )

    assert response.status_code == 202, response.text
    run = response.json()["run"]
    assert run["status"] == "failed"
    assert "队列" in (run["error"] or "")


async def test_failed_step_does_not_leave_dependent_plan_running(
    signed_in: httpx.AsyncClient, fake_planner, monkeypatch
):
    fake_planner(
        tool_calls(
            ("remove_background", {}),
            ("flip_layer", {"direction": "horizontal"}),
        )
    )

    async def unavailable(*_args, **_kwargs):
        raise RuntimeError("redis unavailable")

    monkeypatch.setattr(tool_service, "enqueue", unavailable)
    session = await open_session(signed_in)

    turn = await send(signed_in, session["id"], "去除背景后水平翻转")
    turn = (
        await signed_in.post(f"/api/sessions/{session['id']}/messages/{turn['id']}/confirm")
    ).json()

    assert turn["status"] == "failed"
    assert [step["status"] for step in turn["steps"]] == ["failed", "pending"]
