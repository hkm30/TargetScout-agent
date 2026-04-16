import asyncio
import base64
import logging

from app.agents.setup import get_openai_client
from app.config import settings

logger = logging.getLogger(__name__)

_VISION_SEMAPHORE = asyncio.Semaphore(3)

FIGURE_PROMPT = """你是药物研发领域的文档分析专家。请分析以下图片，生成详细的中文描述。

要求：
1. 识别图片类型（分子结构图、信号通路图、数据图表、流程图、表格截图等）
2. 提取图片中的关键数据、趋势和发现
3. 用中文生成结构化描述
4. 保留专业术语（药物名、基因名、蛋白名等）的英文原文
5. 如果是数据图表，提取关键数值和统计趋势"""


async def describe_figure(
    image_bytes: bytes,
    caption: str = "",
    context: str = "",
) -> str:
    """Generate a Chinese description of a figure using GPT-5.4 multimodal.

    Args:
        image_bytes: Cropped figure image (PNG bytes).
        caption: Original caption from Document Intelligence.
        context: Surrounding text for additional understanding.

    Returns:
        Chinese description text. On failure, returns caption as fallback.
    """
    prompt_parts = [FIGURE_PROMPT]
    if caption:
        prompt_parts.append(f"\n图片标题: {caption}")
    if context:
        prompt_parts.append(f"\n上下文: {context}")
    prompt = "\n".join(prompt_parts)

    b64_image = base64.b64encode(image_bytes).decode("utf-8")
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/png;base64,{b64_image}"},
                },
            ],
        }
    ]

    try:
        client = get_openai_client()
        response = await asyncio.to_thread(
            client.chat.completions.create,
            model=settings.MODEL_DEPLOYMENT,
            messages=messages,
            max_completion_tokens=2000,
        )
        return response.choices[0].message.content or caption or ""
    except Exception as e:
        logger.warning("Vision API failed for figure (caption=%s): %s", caption, e)
        return f"[图片: {caption}]" if caption else "[图片: 无法解析]"


async def describe_all_figures(
    figures: list[dict],
    paragraphs: list[str],
) -> list[dict]:
    """Process all figures concurrently with semaphore control.

    For each figure, extracts surrounding paragraph text as context
    (by matching span_offset against cumulative paragraph lengths).

    Returns the same figures list with an added 'description' field on each.
    """
    if not figures:
        return figures

    cumulative = []
    offset = 0
    for para in paragraphs:
        cumulative.append(offset)
        offset += len(para) + 2

    def _get_context(span_offset: int) -> str:
        """Get ~2 paragraphs around the figure's position."""
        para_idx = 0
        for i, cum in enumerate(cumulative):
            if cum > span_offset:
                break
            para_idx = i
        start = max(0, para_idx - 1)
        end = min(len(paragraphs), para_idx + 2)
        return " ".join(paragraphs[start:end])

    async def _describe_one(fig: dict) -> dict:
        async with _VISION_SEMAPHORE:
            context = _get_context(fig.get("span_offset", 0))
            description = await describe_figure(
                fig["image_bytes"],
                caption=fig.get("caption", ""),
                context=context,
            )
            return {**fig, "description": description}

    tasks = [_describe_one(fig) for fig in figures]
    return list(await asyncio.gather(*tasks))
