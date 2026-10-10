import asyncio
import io
import uuid
from typing import Annotated

from fastapi import APIRouter, File, HTTPException, Query, UploadFile, status
from fastapi.responses import Response
from PIL import Image, ImageOps, UnidentifiedImageError

from app import storage
from app.db import SessionDep
from app.deps import CurrentUser
from app.models.asset import AssetKind, AssetSource
from app.schemas.asset import AssetOut, LibraryGroupOut
from app.services import assets as asset_service
from app.services.assets import ORPHAN_TITLE
from app.services.images import MAX_FILE_BYTES, ImageRejected, probe

router = APIRouter(prefix="/assets", tags=["assets"])


def _thumbnail(data: bytes, size: int) -> tuple[bytes, str]:
    with Image.open(io.BytesIO(data)) as source:
        image = ImageOps.exif_transpose(source)
        image.thumbnail((size, size), Image.Resampling.LANCZOS)
        has_alpha = image.mode in {"RGBA", "LA", "PA"} or "transparency" in image.info
        output = io.BytesIO()
        if has_alpha:
            image.convert("RGBA").save(output, format="PNG", optimize=True)
            return output.getvalue(), "image/png"
        image.convert("RGB").save(output, format="JPEG", quality=78, optimize=True)
        return output.getvalue(), "image/jpeg"


@router.post("", status_code=status.HTTP_201_CREATED)
async def upload(
    user: CurrentUser,
    session: SessionDep,
    file: Annotated[UploadFile, File()],
) -> AssetOut:
    data = await file.read()
    if len(data) > MAX_FILE_BYTES:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "文件超过 20 MB 上限")

    try:
        meta = probe(data)
    except ImageRejected as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc

    asset = await asset_service.create_from_bytes(
        session, user.id, data, AssetKind.ORIGINAL, AssetSource.UPLOAD, meta
    )
    return AssetOut.of(asset)


@router.get("")
async def list_assets(
    user: CurrentUser,
    session: SessionDep,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[AssetOut]:
    records = await asset_service.list_for_user(session, user.id, limit)
    return [AssetOut.of(asset) for asset in records]


@router.get("/library")
async def list_library(
    user: CurrentUser,
    session: SessionDep,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[LibraryGroupOut]:
    groups = await asset_service.library_for_user(session, user.id, limit)
    return [
        LibraryGroupOut(
            session_id=record.id if record else None,
            title=record.title if record else ORPHAN_TITLE,
            updated_at=record.updated_at if record else cover.created_at,
            cover=AssetOut.of(cover),
            assets=[AssetOut.of(asset) for asset in assets],
        )
        for record, cover, assets in groups
    ]


@router.get("/{asset_id}/thumbnail")
async def thumbnail(
    asset_id: uuid.UUID,
    user: CurrentUser,
    session: SessionDep,
    size: Annotated[int, Query(ge=32, le=512)] = 160,
) -> Response:
    """返回用于列表和图片墙的小图，避免缩略图下载完整原图。"""
    asset = await asset_service.get_for_user(session, user.id, asset_id)
    if asset is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "素材不存在")
    try:
        data = await storage.get(asset.storage_key)
        body, content_type = await asyncio.to_thread(_thumbnail, data, size)
    except (OSError, UnidentifiedImageError) as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "图片无法读取") from exc
    return Response(
        content=body,
        media_type=content_type,
        headers={"Cache-Control": "private, max-age=600, stale-while-revalidate=60"},
    )


@router.get("/{asset_id}")
async def get_asset(asset_id: uuid.UUID, user: CurrentUser, session: SessionDep) -> AssetOut:
    asset = await asset_service.get_for_user(session, user.id, asset_id)
    if asset is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "素材不存在")
    return AssetOut.of(asset)
