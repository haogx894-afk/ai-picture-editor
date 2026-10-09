import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from app import storage
from app.config import get_settings
from app.db import SessionFactory
from app.queue import close_queue
from app.routers import admin, assets, auth, batches, events, health, runs, sessions
from app.services import auth as auth_service

settings = get_settings()
logger = logging.getLogger(__name__)


class SPAStaticFiles(StaticFiles):
    """Serve index.html for client-side routes such as /admin and /editor/:id."""

    async def get_response(self, path: str, scope):  # type: ignore[no-untyped-def]
        try:
            return await super().get_response(path, scope)
        except StarletteHTTPException as exc:
            if exc.status_code == 404 and scope["method"] in {"GET", "HEAD"}:
                return await super().get_response("index.html", scope)
            raise


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    await asyncio.to_thread(storage.ensure_bucket)
    if settings.admin_password:
        try:
            async with SessionFactory() as session:
                await auth_service.ensure_admin(session)
        except Exception:
            logger.exception("管理员账号初始化失败")
    yield
    await close_queue()


app = FastAPI(
    title="AI 修图智能体",
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
    lifespan=lifespan,
)

api = APIRouter(prefix="/api")
api.include_router(health.router)
api.include_router(auth.router)
api.include_router(assets.router)
api.include_router(runs.router)
api.include_router(sessions.router)
api.include_router(batches.router)
api.include_router(admin.router)
app.include_router(api)

# SSE 不挂在 /api 下，便于反向代理单独关闭缓冲
app.include_router(events.router)

# 生产环境下前端与 API 同源，静态产物由本服务托管；开发环境走 Vite dev proxy。
if settings.frontend_dist.is_dir():
    app.mount("/", SPAStaticFiles(directory=settings.frontend_dist, html=True), name="frontend")
