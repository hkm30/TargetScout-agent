import asyncio
import logging

from app.agents.setup import get_openai_client
from app.config import settings

logger = logging.getLogger(__name__)

SUMMARY_PROMPT = """请为以下文档内容生成两级摘要：

1. **摘要**（3000-5000 tokens）：详细提炼文档核心内容，保留关键数据、论点和结论。
2. **总结**（1000-2000 tokens）：精炼概要，突出最重要的发现和观点。

请用以下格式返回（不要用 markdown 代码块包裹）：
---摘要---
（摘要内容）
---总结---
（总结内容）

文档内容：
{content}"""


async def generate_summaries(text: str, filename: str = "") -> dict:
    """Generate two-level summaries for a document.

    Returns {abstract: str, summary: str}.
    - abstract (摘要): 3000-5000 tokens, detailed extraction
    - summary (总结): 1000-2000 tokens, concise overview
    """
    # Truncate input if too long to fit in context (keep first ~12000 tokens worth of chars)
    max_input_chars = 48000  # ~12000 tokens
    truncated = text[:max_input_chars]
    if len(text) > max_input_chars:
        truncated += "\n\n[... 文档内容已截断 ...]"

    prompt = SUMMARY_PROMPT.format(content=truncated)

    client = get_openai_client()
    response = await asyncio.to_thread(
        client.chat.completions.create,
        model=settings.MODEL_DEPLOYMENT,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=8000,
    )

    result_text = response.choices[0].message.content or ""
    return _parse_summaries(result_text)


def _parse_summaries(text: str) -> dict:
    """Parse the LLM output into abstract and summary sections."""
    abstract = ""
    summary = ""

    if "---摘要---" in text and "---总结---" in text:
        parts = text.split("---总结---")
        abstract_part = parts[0].split("---摘要---")
        if len(abstract_part) > 1:
            abstract = abstract_part[1].strip()
        if len(parts) > 1:
            summary = parts[1].strip()
    else:
        # Fallback: use entire text as both
        half = len(text) // 2
        abstract = text
        summary = text[:half] if len(text) > 2000 else text

    return {"abstract": abstract, "summary": summary}
