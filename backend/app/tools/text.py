import asyncio
import io

from PIL import Image, ImageDraw, ImageFilter
from pydantic import Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.edits.mask import apply_masked
from app.edits.ocr import TextBox, detect_text
from app.layers import LayerKind
from app.models.asset import AssetKind, AssetSource
from app.models.tool_run import ToolRun
from app.providers import EditRequest, get_image_provider
from app.services import assets, runs
from app.tools.base import HIDDEN_MASK, MaskRef, ToolSpec
from app.tools.context import ToolError, document_of, flatten_session, require_session
from app.tools.target import selection_mask, write_layer_image


class RepairTextIn(MaskRef):
    prompt: str = Field(
        default="修复图片中的文字，保持原文、字体风格、透视、光影和材质，不改变文字区域以外的内容。",
        max_length=500,
    )


def _text_mask(boxes: list[TextBox], size: tuple[int, int]) -> bytes:
    """把 OCR 文字框合并成带少量边缘余量的局部修复遮罩。"""
    width, height = size
    mask = Image.new("L", size, 0)
    draw = ImageDraw.Draw(mask)
    margin = max(2, round(min(width, height) * 0.008))
    for box in boxes:
        left = max(0, box.x - margin)
        top = max(0, box.y - margin)
        right = min(width, box.x + box.width + margin)
        bottom = min(height, box.y + box.height + margin)
        draw.rounded_rectangle((left, top, right, bottom), radius=margin, fill=255)

    output = io.BytesIO()
    mask.filter(ImageFilter.GaussianBlur(0.8)).save(output, format="PNG")
    return output.getvalue()


async def repair_text_exec(session: AsyncSession, run: ToolRun) -> dict:
    """只在 OCR 识别出的文字区域生成修复结果，避免拆层或重绘整张图。"""
    record = await require_session(session, run)
    document = document_of(record)
    if any(layer.kind is LayerKind.TEXT and layer.visible for layer in document.layers):
        raise ToolError("当前已有可编辑文字层，请使用改文字工具")

    await runs.report(session, run, 15, "识别文字区域")
    source = await flatten_session(session, record)
    boxes = await asyncio.to_thread(detect_text, source)
    selected_mask = await selection_mask(session, record, run.params.get("mask_asset_id"))
    if not boxes and selected_mask is None:
        # ToolError 由统一执行外壳转成用户可见的失败状态，而不是伪装成已完成。
        raise ToolError("未识别到文字区域，请框选文字区域或提供准确文案后重试")

    image = Image.open(io.BytesIO(source))
    mask = _text_mask(boxes, image.size) if boxes else selected_mask
    recognized = "、".join(box.text for box in boxes if box.text.strip())
    prompt = (
        "只修复 OCR 识别出的文字区域，必须保留原文，不得改写、增删或创造其它文字。"
        f"识别到的原文候选：{recognized or '未提供'}。"
        f"{run.params['prompt']}。文字区域以外的主体、构图、颜色、光影和材质必须保持不变。"
    )
    await runs.report(session, run, 35, "局部修复文字")
    edited = (
        await get_image_provider().edit(
            EditRequest(prompt=prompt, image=source),
            on_progress=lambda progress, stage: runs.report(session, run, progress, stage),
        )
    )[0]
    output = apply_masked(source, edited, mask)
    await runs.report(session, run, 90, "合成文字修复结果")

    image_layers = [layer for layer in document.layers if layer.kind is LayerKind.IMAGE]
    if len(image_layers) == 1:
        return await write_layer_image(
            session, run, record, image_layers[0].id, output, AssetKind.GENERATED
        )

    # 多图层文档不把整张合成图写回任意单层，只进入图片墙供用户确认采用。
    asset = await assets.create_from_bytes(
        session, run.user_id, output, AssetKind.GENERATED, AssetSource.TOOL
    )
    return {
        "asset_ids": [str(asset.id)],
        "text_boxes": [box.__dict__ for box in boxes],
    }


REPAIR_TEXT = ToolSpec(
    name="repair_text",
    label="修复文字",
    description=(
        "自动识别图片中的文字区域，只修复文字并合成回原图。"
        "不要拆层，不要重绘文字区域以外的内容。OCR 无法识别时应提示用户框选区域或提供准确文案。"
    ),
    params=RepairTextIn,
    handler=repair_text_exec,
    queued=True,
    session_required=True,
    agent_hidden=HIDDEN_MASK,
)
