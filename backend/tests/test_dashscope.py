import httpx
import pytest

from app.providers.base import ContentSafetyError, ProviderError
from app.providers.dashscope import DashScopeImageProvider


class _FakeClient:
    def __init__(self, body: dict):
        self._body = body

    async def get(self, path: str) -> httpx.Response:
        return httpx.Response(200, json=self._body)


def _provider(task_body: dict) -> DashScopeImageProvider:
    provider = object.__new__(DashScopeImageProvider)
    provider._client = _FakeClient(task_body)
    return provider


@pytest.mark.asyncio
async def test_green_net_rejection_is_reported_as_content_safety_error():
    provider = _provider(
        {
            "output": {
                "task_status": "FAILED",
                "message": "Green net check rejected image (output)",
            }
        }
    )

    with pytest.raises(ContentSafetyError, match="内容安全审核未通过"):
        await provider._await_result("task-1", None)


@pytest.mark.asyncio
async def test_other_task_failure_keeps_provider_detail():
    provider = _provider(
        {
            "output": {
                "task_status": "FAILED",
                "message": "upstream temporarily unavailable",
            }
        }
    )

    with pytest.raises(ProviderError, match="upstream temporarily unavailable"):
        await provider._await_result("task-2", None)
