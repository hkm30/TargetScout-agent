# Document Image Understanding Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enable the document parsing pipeline to extract, understand, and index images from uploaded PDF/Word files using Document Intelligence Layout + GPT-5.4 multimodal vision.

**Architecture:** Switch `prebuilt-read` → `prebuilt-layout` with `output=figures` for figure detection and cropping. New `vision.py` module sends cropped PNGs to GPT-5.4 for Chinese descriptions. Descriptions merge into the text flow for summarization AND index as standalone figure chunks for retrieval.

**Tech Stack:** Azure Document Intelligence (prebuilt-layout), GPT-5.4 multimodal (via existing OpenAI client), asyncio concurrency with Semaphore(3).

**Spec:** `docs/superpowers/specs/2026-04-10-document-image-understanding-design.md`

---

## File Structure

| File | Action | Responsibility |
|------|--------|---------------|
| `backend/app/documents/parser.py` | Modify | Switch to `prebuilt-layout`, extract figures with cropped images |
| `backend/app/documents/vision.py` | Create | GPT-5.4 multimodal calls to describe figure images |
| `backend/app/documents/chunker.py` | Modify | Append figure chunks after text chunks |
| `backend/app/documents/router.py` | Modify | Orchestrate vision + merge steps in `process_pending_document()` |
| `backend/tests/test_document_chunker.py` | Modify | Tests for `figure_chunks` parameter |
| `backend/tests/test_vision.py` | Create | Tests for `describe_figure` and `describe_all_figures` |
| `backend/tests/test_document_parser.py` | Modify | Update mocks for `prebuilt-layout`, add figure extraction tests |
| `backend/tests/test_document_router.py` | Modify | Update `process_pending_document` tests with vision/merge steps |

---

### Task 1: Update Chunker to Support Figure Chunks

**Files:**
- Modify: `backend/app/documents/chunker.py`
- Modify: `backend/tests/test_document_chunker.py`

- [ ] **Step 1: Write the failing test for figure_chunks parameter**

Add to `backend/tests/test_document_chunker.py`:

```python
def test_chunk_with_figure_chunks_appended():
    """Figure chunks should be appended after regular text chunks with sequential indexes."""
    paragraphs = ["Regular paragraph content here."]
    text = paragraphs[0]
    figure_chunks = [
        {"text": "[Figure 1.0] A bar chart showing IC50 values.\nDescription of figure.", "source_type": "figure", "page_number": 2},
        {"text": "[Figure 1.1] Molecular structure of compound X.\nDescription of structure.", "source_type": "figure", "page_number": 3},
    ]
    chunks = chunk_text(text, paragraphs=paragraphs, figure_chunks=figure_chunks)
    # Regular chunk comes first
    assert chunks[0]["text"] == "Regular paragraph content here."
    assert chunks[0]["chunk_index"] == 0
    assert "source_type" not in chunks[0]
    # Figure chunks follow with sequential indexes
    assert chunks[1]["text"] == figure_chunks[0]["text"]
    assert chunks[1]["chunk_index"] == 1
    assert chunks[1]["source_type"] == "figure"
    assert chunks[1]["page_number"] == 2
    assert chunks[1]["token_count"] > 0
    assert chunks[2]["chunk_index"] == 2
    assert chunks[2]["source_type"] == "figure"


def test_chunk_with_no_figure_chunks():
    """When figure_chunks is None or empty, behavior is unchanged."""
    text = "Simple text."
    chunks_none = chunk_text(text, paragraphs=["Simple text."], figure_chunks=None)
    chunks_empty = chunk_text(text, paragraphs=["Simple text."], figure_chunks=[])
    assert len(chunks_none) == 1
    assert len(chunks_empty) == 1
    assert "source_type" not in chunks_none[0]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && .venv/bin/python -m pytest tests/test_document_chunker.py::test_chunk_with_figure_chunks_appended tests/test_document_chunker.py::test_chunk_with_no_figure_chunks -v`

Expected: FAIL — `chunk_text()` does not accept `figure_chunks` parameter.

- [ ] **Step 3: Implement figure_chunks support in chunker**

Edit `backend/app/documents/chunker.py` — change the `chunk_text` function signature and add figure chunk appending at the end:

```python
def chunk_text(
    text: str,
    paragraphs: list[str] | None = None,
    max_tokens: int = 600,
    overlap_tokens: int = 100,
    figure_chunks: list[dict] | None = None,
) -> list[dict]:
    """Split text into overlapping chunks.

    Strategy:
    1. If paragraphs are provided, group them into chunks up to max_tokens.
    2. If a single paragraph exceeds max_tokens, split it by token window.
    3. If figure_chunks provided, append them after text chunks with sequential indexes.

    Returns list of {text, chunk_index, token_count, ...}.
    """
    if not paragraphs:
        paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    if not paragraphs:
        paragraphs = [text]

    chunks: list[dict] = []
    current_parts: list[str] = []
    current_tokens = 0
    chunk_index = 0

    for para in paragraphs:
        para_tokens = count_tokens(para)

        # If single paragraph exceeds max, split it by token window
        if para_tokens > max_tokens:
            # Flush current buffer first
            if current_parts:
                chunk_text_str = "\n\n".join(current_parts)
                chunks.append({"text": chunk_text_str, "chunk_index": chunk_index, "token_count": current_tokens})
                chunk_index += 1
                current_parts = []
                current_tokens = 0

            # Split long paragraph by token window
            tokens = _encoder.encode(para)
            start = 0
            while start < len(tokens):
                end = min(start + max_tokens, len(tokens))
                chunk_tokens = tokens[start:end]
                chunk_str = _encoder.decode(chunk_tokens)
                chunks.append({"text": chunk_str, "chunk_index": chunk_index, "token_count": len(chunk_tokens)})
                chunk_index += 1
                start = end - overlap_tokens if end < len(tokens) else end
            continue

        # Would this paragraph overflow the current chunk?
        if current_tokens + para_tokens > max_tokens and current_parts:
            chunk_text_str = "\n\n".join(current_parts)
            chunks.append({"text": chunk_text_str, "chunk_index": chunk_index, "token_count": current_tokens})
            chunk_index += 1

            # Overlap: keep last part if it fits
            last_part = current_parts[-1]
            last_tokens = count_tokens(last_part)
            if last_tokens <= overlap_tokens:
                current_parts = [last_part]
                current_tokens = last_tokens
            else:
                current_parts = []
                current_tokens = 0

        current_parts.append(para)
        current_tokens += para_tokens

    # Flush remaining
    if current_parts:
        chunk_text_str = "\n\n".join(current_parts)
        chunks.append({"text": chunk_text_str, "chunk_index": chunk_index, "token_count": current_tokens})
        chunk_index += 1

    # Append figure chunks with sequential indexes
    if figure_chunks:
        for fc in figure_chunks:
            chunks.append({
                "text": fc["text"],
                "chunk_index": chunk_index,
                "token_count": count_tokens(fc["text"]),
                "source_type": fc.get("source_type", "figure"),
                "page_number": fc.get("page_number", 0),
            })
            chunk_index += 1

    return chunks
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && .venv/bin/python -m pytest tests/test_document_chunker.py -v`

Expected: ALL PASS (both new and existing tests).

- [ ] **Step 5: Commit**

```bash
git add backend/app/documents/chunker.py backend/tests/test_document_chunker.py
git commit -m "feat: add figure_chunks support to chunk_text"
```

---

### Task 2: Create Vision Module

**Files:**
- Create: `backend/app/documents/vision.py`
- Create: `backend/tests/test_vision.py`

- [ ] **Step 1: Write the failing test for describe_figure**

Create `backend/tests/test_vision.py`:

```python
import pytest
from unittest.mock import MagicMock, patch


@pytest.mark.asyncio
@patch("app.documents.vision.get_openai_client")
async def test_describe_figure_returns_description(mock_get_client):
    from app.documents.vision import describe_figure

    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = "这是一张柱状图，展示了IC50值的分布。"

    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = mock_response
    mock_get_client.return_value = mock_client

    result = await describe_figure(b"fake-png-bytes", caption="Figure 1: IC50 values")

    assert "IC50" in result
    mock_client.chat.completions.create.assert_called_once()
    call_kwargs = mock_client.chat.completions.create.call_args
    # Verify multimodal message structure
    messages = call_kwargs.kwargs.get("messages") or call_kwargs[1].get("messages") or call_kwargs[0][1] if len(call_kwargs[0]) > 1 else call_kwargs.kwargs["messages"]
    user_msg = messages[0]
    assert user_msg["role"] == "user"
    assert isinstance(user_msg["content"], list)
    assert user_msg["content"][1]["type"] == "image_url"


@pytest.mark.asyncio
@patch("app.documents.vision.get_openai_client")
async def test_describe_figure_with_context(mock_get_client):
    from app.documents.vision import describe_figure

    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = "该图展示了EGFR通路的激活机制。"

    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = mock_response
    mock_get_client.return_value = mock_client

    result = await describe_figure(
        b"fake-png-bytes",
        caption="Figure 2: EGFR pathway",
        context="The study examined EGFR mutations in NSCLC patients.",
    )

    assert "EGFR" in result
    # Verify context was included in the prompt
    call_kwargs = mock_client.chat.completions.create.call_args
    messages = call_kwargs.kwargs.get("messages", call_kwargs[1].get("messages", []))
    prompt_text = messages[0]["content"][0]["text"]
    assert "EGFR pathway" in prompt_text
    assert "EGFR mutations" in prompt_text


@pytest.mark.asyncio
@patch("app.documents.vision.get_openai_client")
async def test_describe_figure_api_failure_returns_fallback(mock_get_client):
    from app.documents.vision import describe_figure

    mock_client = MagicMock()
    mock_client.chat.completions.create.side_effect = Exception("API error")
    mock_get_client.return_value = mock_client

    result = await describe_figure(b"fake-png-bytes", caption="Figure 1: IC50 values")

    # Should return caption as fallback, not raise
    assert "Figure 1: IC50 values" in result


@pytest.mark.asyncio
@patch("app.documents.vision.get_openai_client")
async def test_describe_all_figures_concurrent(mock_get_client):
    from app.documents.vision import describe_all_figures

    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = "描述内容"

    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = mock_response
    mock_get_client.return_value = mock_client

    figures = [
        {"id": "1.0", "page_number": 1, "caption": "Fig 1", "image_bytes": b"png1", "span_offset": 50},
        {"id": "1.1", "page_number": 2, "caption": "Fig 2", "image_bytes": b"png2", "span_offset": 200},
    ]
    paragraphs = ["Intro paragraph about the study.", "Methods section details.", "Results show improvement."]

    result = await describe_all_figures(figures, paragraphs)

    assert len(result) == 2
    assert result[0]["description"] == "描述内容"
    assert result[1]["description"] == "描述内容"
    assert mock_client.chat.completions.create.call_count == 2
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && .venv/bin/python -m pytest tests/test_vision.py -v`

Expected: FAIL — `app.documents.vision` module does not exist.

- [ ] **Step 3: Implement vision.py**

Create `backend/app/documents/vision.py`:

```python
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

    # Build a mapping of cumulative char offsets to paragraph indexes
    cumulative = []
    offset = 0
    for para in paragraphs:
        cumulative.append(offset)
        offset += len(para) + 2  # +2 for the "\n\n" separator

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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && .venv/bin/python -m pytest tests/test_vision.py -v`

Expected: ALL PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/documents/vision.py backend/tests/test_vision.py
git commit -m "feat: add vision module for GPT-5.4 figure understanding"
```

---

### Task 3: Update Parser to Use prebuilt-layout with Figure Extraction

**Files:**
- Modify: `backend/app/documents/parser.py`
- Modify: `backend/tests/test_document_parser.py`

- [ ] **Step 1: Write the failing test for figure extraction**

Add to `backend/tests/test_document_parser.py`:

```python
@pytest.mark.asyncio
@patch("app.documents.parser._fetch_figure_image")
@patch("app.documents.parser._get_doc_intel_client")
async def test_extract_text_pdf_extracts_figures(mock_get_client, mock_fetch_image):
    """PDF extraction should return figures with image bytes."""
    mock_caption = MagicMock()
    mock_caption.content = "Figure 1: IC50 distribution"

    mock_span = MagicMock()
    mock_span.offset = 100

    mock_region = MagicMock()
    mock_region.page_number = 1

    mock_figure = MagicMock()
    mock_figure.id = "1.0"
    mock_figure.caption = mock_caption
    mock_figure.spans = [mock_span]
    mock_figure.bounding_regions = [mock_region]

    mock_paragraph = MagicMock()
    mock_paragraph.content = "Some text content."

    mock_result = MagicMock()
    mock_result.content = "Some text content."
    mock_result.pages = [MagicMock()]
    mock_result.paragraphs = [mock_paragraph]
    mock_result.figures = [mock_figure]

    mock_poller = MagicMock()
    mock_poller.result.return_value = mock_result
    mock_poller.result_id = "test-result-id"

    mock_client = MagicMock()
    mock_client.begin_analyze_document.return_value = mock_poller
    mock_get_client.return_value = mock_client

    mock_fetch_image.return_value = b"fake-png-bytes"

    result = await extract_text("report.pdf", b"fake-pdf-bytes")

    # Verify prebuilt-layout was used
    call_args = mock_client.begin_analyze_document.call_args
    assert call_args[0][0] == "prebuilt-layout"

    # Verify figures are returned
    assert len(result["figures"]) == 1
    fig = result["figures"][0]
    assert fig["id"] == "1.0"
    assert fig["caption"] == "Figure 1: IC50 distribution"
    assert fig["image_bytes"] == b"fake-png-bytes"
    assert fig["page_number"] == 1
    assert fig["span_offset"] == 100

    # Text extraction still works
    assert result["text"] == "Some text content."
    assert result["page_count"] == 1


@pytest.mark.asyncio
@patch("app.documents.parser._get_doc_intel_client")
async def test_extract_text_pdf_no_figures(mock_get_client):
    """PDF with no figures should return empty figures list."""
    mock_result = MagicMock()
    mock_result.content = "Text only document."
    mock_result.pages = [MagicMock()]
    mock_result.paragraphs = [MagicMock(content="Text only document.")]
    mock_result.figures = None

    mock_poller = MagicMock()
    mock_poller.result.return_value = mock_result

    mock_client = MagicMock()
    mock_client.begin_analyze_document.return_value = mock_poller
    mock_get_client.return_value = mock_client

    result = await extract_text("report.pdf", b"fake-pdf-bytes")

    assert result["figures"] == []
    assert result["text"] == "Text only document."


@pytest.mark.asyncio
async def test_extract_text_txt_returns_empty_figures():
    """Text files should return empty figures list."""
    content = "Plain text content.\n\nSecond paragraph.".encode("utf-8")
    result = await extract_text("notes.txt", content)
    assert result["figures"] == []
    assert result["text"] == "Plain text content.\n\nSecond paragraph."
```

- [ ] **Step 2: Run new tests to verify they fail**

Run: `cd backend && .venv/bin/python -m pytest tests/test_document_parser.py::test_extract_text_pdf_extracts_figures tests/test_document_parser.py::test_extract_text_pdf_no_figures tests/test_document_parser.py::test_extract_text_txt_returns_empty_figures -v`

Expected: FAIL — `extract_text` does not return `figures` key, `_fetch_figure_image` does not exist.

- [ ] **Step 3: Update existing test for prebuilt-layout**

The existing `test_extract_text_pdf_calls_doc_intelligence` asserts `"prebuilt-read"` was called. Update it to assert `"prebuilt-layout"`:

In `backend/tests/test_document_parser.py`, change the existing test:

```python
@pytest.mark.asyncio
@patch("app.documents.parser._get_doc_intel_client")
async def test_extract_text_pdf_calls_doc_intelligence(mock_get_client):
    # Setup mock Document Intelligence client
    mock_paragraph = MagicMock()
    mock_paragraph.content = "Extracted paragraph from PDF."

    mock_page = MagicMock()

    mock_result = MagicMock()
    mock_result.content = "Extracted paragraph from PDF."
    mock_result.pages = [mock_page, mock_page]  # 2 pages
    mock_result.paragraphs = [mock_paragraph]
    mock_result.figures = None

    mock_poller = MagicMock()
    mock_poller.result.return_value = mock_result

    mock_client = MagicMock()
    mock_client.begin_analyze_document.return_value = mock_poller
    mock_get_client.return_value = mock_client

    result = await extract_text("report.pdf", b"fake-pdf-bytes")

    call_args = mock_client.begin_analyze_document.call_args
    assert call_args[0][0] == "prebuilt-layout"
    assert result["text"] == "Extracted paragraph from PDF."
    assert result["page_count"] == 2
    assert len(result["paragraphs"]) == 1
    assert result["figures"] == []
```

Also update `test_extract_text_docx_calls_doc_intelligence`:

```python
@pytest.mark.asyncio
@patch("app.documents.parser._get_doc_intel_client")
async def test_extract_text_docx_calls_doc_intelligence(mock_get_client):
    mock_result = MagicMock()
    mock_result.content = "Word document text."
    mock_result.pages = [MagicMock()]
    mock_result.paragraphs = []
    mock_result.figures = None

    mock_poller = MagicMock()
    mock_poller.result.return_value = mock_result

    mock_client = MagicMock()
    mock_client.begin_analyze_document.return_value = mock_poller
    mock_get_client.return_value = mock_client

    result = await extract_text("study.docx", b"fake-docx-bytes")

    mock_client.begin_analyze_document.assert_called_once()
    assert result["text"] == "Word document text."
    assert result["page_count"] == 1
    assert result["paragraphs"] == []
    assert result["figures"] == []
```

- [ ] **Step 4: Implement updated parser.py**

Replace the contents of `backend/app/documents/parser.py`:

```python
import asyncio
import io
import logging
from pathlib import Path

from azure.ai.documentintelligence import DocumentIntelligenceClient
from azure.core.credentials import AzureKeyCredential
from azure.identity import DefaultAzureCredential

from app.config import settings

logger = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".txt", ".md"}
TEXT_EXTENSIONS = {".txt", ".md"}
DOC_INTEL_EXTENSIONS = {".pdf", ".docx"}


def _get_doc_intel_client() -> DocumentIntelligenceClient:
    endpoint = settings.DOC_INTELLIGENCE_ENDPOINT
    if not endpoint:
        raise ValueError(
            "AZURE_DOC_INTELLIGENCE_ENDPOINT is not configured. "
            "PDF/Word file processing requires Azure Document Intelligence. "
            "Please set AZURE_DOC_INTELLIGENCE_ENDPOINT in the environment."
        )
    key = settings.DOC_INTELLIGENCE_KEY
    if key:
        credential = AzureKeyCredential(key)
    else:
        credential = DefaultAzureCredential()
    return DocumentIntelligenceClient(endpoint=endpoint, credential=credential)


def validate_file(filename: str, size_bytes: int) -> str | None:
    """Return an error message if the file is invalid, or None if OK."""
    ext = Path(filename).suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        return f"Unsupported file type: {ext}. Supported: {', '.join(SUPPORTED_EXTENSIONS)}"
    if size_bytes == 0:
        return "File is empty"
    max_bytes = settings.DOC_MAX_FILE_SIZE_MB * 1024 * 1024
    if size_bytes > max_bytes:
        return f"File too large: {size_bytes / 1024 / 1024:.1f}MB exceeds {settings.DOC_MAX_FILE_SIZE_MB}MB limit"
    return None


async def _fetch_figure_image(client: DocumentIntelligenceClient, result_id: str, figure_id: str) -> bytes | None:
    """Fetch a cropped figure image from Document Intelligence.

    Tries SDK method first, falls back to HTTP GET.
    """
    # Try SDK method
    try:
        image_iter = await asyncio.to_thread(
            client.get_analyze_result_figure,
            model_id="prebuilt-layout",
            result_id=result_id,
            figure_id=figure_id,
        )
        chunks = []
        for chunk in image_iter:
            chunks.append(chunk)
        return b"".join(chunks)
    except (AttributeError, TypeError) as e:
        logger.debug("SDK figure retrieval not available: %s, trying HTTP fallback", e)
    except Exception as e:
        logger.warning("SDK figure retrieval failed for %s: %s, trying HTTP fallback", figure_id, e)

    # Fallback: raw HTTP GET
    try:
        import httpx

        endpoint = settings.DOC_INTELLIGENCE_ENDPOINT.rstrip("/")
        url = (
            f"{endpoint}/documentintelligence/documentModels/prebuilt-layout"
            f"/analyzeResults/{result_id}/figures/{figure_id}"
        )
        headers: dict[str, str] = {}
        key = settings.DOC_INTELLIGENCE_KEY
        if key:
            headers["Ocp-Apim-Subscription-Key"] = key
        async with httpx.AsyncClient() as http_client:
            resp = await http_client.get(url, headers=headers, params={"api-version": "2024-11-30"})
            if resp.status_code == 200:
                return resp.content
            logger.warning("HTTP figure retrieval failed: status=%s", resp.status_code)
    except Exception as e:
        logger.warning("HTTP figure retrieval error for %s: %s", figure_id, e)

    return None


async def extract_text(filename: str, content: bytes) -> dict:
    """Extract text and figures from a file.

    Returns {text, page_count, paragraphs, figures}.

    PDF/Word → Azure Document Intelligence (prebuilt-layout with figure extraction)
    TXT/MD   → Direct decode (no figures)
    """
    ext = Path(filename).suffix.lower()

    if ext in TEXT_EXTENSIONS:
        text = content.decode("utf-8", errors="replace")
        paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
        return {"text": text, "page_count": 1, "paragraphs": paragraphs, "figures": []}

    # PDF or Word → Document Intelligence (prebuilt-layout)
    client = _get_doc_intel_client()
    poller = await asyncio.to_thread(
        client.begin_analyze_document,
        "prebuilt-layout",
        io.BytesIO(content),
        content_type="application/octet-stream",
        output=["figures"],
    )
    result = await asyncio.to_thread(poller.result)

    text = result.content or ""
    page_count = len(result.pages) if result.pages else 0
    paragraphs = []
    if result.paragraphs:
        paragraphs = [p.content for p in result.paragraphs if p.content]

    # Extract figures
    figures = []
    if result.figures:
        # Get result_id for figure image retrieval
        result_id = getattr(poller, "result_id", None)
        if not result_id:
            # Parse from continuation_token as fallback
            try:
                token = poller.continuation_token
                if token and "/analyzeResults/" in token:
                    result_id = token.split("/analyzeResults/")[-1].split("?")[0].split("/")[0]
            except Exception:
                pass

        for fig in result.figures:
            caption = ""
            if fig.caption:
                caption = fig.caption.content or ""
            page_number = 0
            if fig.bounding_regions:
                page_number = fig.bounding_regions[0].page_number
            span_offset = 0
            if fig.spans:
                span_offset = fig.spans[0].offset

            image_bytes = None
            if result_id and fig.id:
                image_bytes = await _fetch_figure_image(client, result_id, fig.id)

            if image_bytes:
                figures.append({
                    "id": fig.id,
                    "page_number": page_number,
                    "caption": caption,
                    "image_bytes": image_bytes,
                    "span_offset": span_offset,
                })
            else:
                logger.warning("Skipping figure %s: could not retrieve image", fig.id)

    return {"text": text, "page_count": page_count, "paragraphs": paragraphs, "figures": figures}
```

- [ ] **Step 5: Run all parser tests**

Run: `cd backend && .venv/bin/python -m pytest tests/test_document_parser.py -v`

Expected: ALL PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/documents/parser.py backend/tests/test_document_parser.py
git commit -m "feat: switch parser to prebuilt-layout with figure extraction"
```

---

### Task 4: Update Router to Integrate Vision + Merge Pipeline

**Files:**
- Modify: `backend/app/documents/router.py`
- Modify: `backend/tests/test_document_router.py`

- [ ] **Step 1: Write the failing test for process_pending_document with figures**

Add to `backend/tests/test_document_router.py`:

First, update the `_mock_all_deps()` function to include the new dependencies:

```python
def _mock_all_deps():
    """Return a dict of patches for all external dependencies."""
    return {
        "blob": patch("app.documents.router.BlobDocumentStorage"),
        "extract": patch("app.documents.router.extract_text", new_callable=AsyncMock),
        "summarize": patch("app.documents.router.generate_summaries", new_callable=AsyncMock),
        "index": patch("app.documents.router.index_document_chunks", new_callable=AsyncMock),
        "delete_chunks": patch("app.documents.router.delete_document_chunks", new_callable=AsyncMock),
        "cosmos": patch("app.documents.router._get_cosmos_docs"),
        "describe_figures": patch("app.documents.router.describe_all_figures", new_callable=AsyncMock),
    }
```

Then add the test:

```python
@pytest.mark.asyncio
async def test_process_pending_document_with_figures():
    """process_pending_document should run vision, merge descriptions, and create figure chunks."""
    from app.documents.router import process_pending_document, _pending_files

    doc_id = "test-fig-doc"
    _pending_files[doc_id] = {
        "content": b"fake-pdf-content",
        "file_name": "study.pdf",
        "content_hash": "abc123",
    }

    patches = _mock_all_deps()
    with patches["blob"] as mock_blob_cls, \
         patches["extract"] as mock_extract, \
         patches["summarize"] as mock_summarize, \
         patches["index"] as mock_index, \
         patches["cosmos"] as mock_get_cosmos, \
         patches["describe_figures"] as mock_describe:

        mock_blob_instance = MagicMock()
        mock_blob_instance.upload_document.return_value = "https://blob.test/study.pdf"
        mock_blob_cls.return_value = mock_blob_instance

        mock_cosmos = _make_cosmos_mock()
        mock_get_cosmos.return_value = mock_cosmos

        mock_extract.return_value = {
            "text": "Introduction text.\n\nResults show improvement.",
            "page_count": 2,
            "paragraphs": ["Introduction text.", "Results show improvement."],
            "figures": [
                {
                    "id": "1.0",
                    "page_number": 1,
                    "caption": "Figure 1: IC50 values",
                    "image_bytes": b"fake-png",
                    "span_offset": 50,
                },
            ],
        }

        mock_describe.return_value = [
            {
                "id": "1.0",
                "page_number": 1,
                "caption": "Figure 1: IC50 values",
                "image_bytes": b"fake-png",
                "span_offset": 50,
                "description": "这是一张柱状图，展示了不同化合物的IC50值分布。",
            },
        ]

        mock_summarize.return_value = {"abstract": "Detailed abstract.", "summary": "Brief summary."}

        result = await process_pending_document(doc_id)

        # Vision was called with figures and paragraphs
        mock_describe.assert_called_once()
        call_args = mock_describe.call_args
        assert len(call_args[0][0]) == 1  # 1 figure
        assert call_args[0][0][0]["id"] == "1.0"

        # Summarizer received enriched text (with figure description merged)
        summarize_call = mock_summarize.call_args
        enriched_text = summarize_call[0][0]
        assert "[图片:" in enriched_text
        assert "IC50" in enriched_text

        # Index was called with figure chunks included
        index_call = mock_index.call_args
        chunks = index_call[0][2]  # third positional arg = chunks
        figure_chunks = [c for c in chunks if c.get("source_type") == "figure"]
        assert len(figure_chunks) == 1
        assert "IC50" in figure_chunks[0]["text"]

        assert result["status"] == "ready"
        assert result["summary"] == "Brief summary."
```

- [ ] **Step 2: Run the new test to verify it fails**

Run: `cd backend && .venv/bin/python -m pytest tests/test_document_router.py::test_process_pending_document_with_figures -v`

Expected: FAIL — `describe_all_figures` is not imported in `router.py`.

- [ ] **Step 3: Implement router changes**

Edit `backend/app/documents/router.py`. Add the import and update `process_pending_document()`:

Add at the top of the file (after existing imports):

```python
from app.documents.vision import describe_all_figures
```

Replace the `process_pending_document` function:

```python
async def process_pending_document(document_id: str) -> dict:
    """Process a pending document: blob upload, extract, vision, summarize, chunk, index.

    Called from the orchestrator during the confirm/run phase.
    File content comes from _pending_files in-memory store.
    Returns the document metadata dict.
    """
    pending = _pending_files.pop(document_id, None)
    if pending is None:
        # Not in memory — might be a duplicate/already-processed doc, check Cosmos
        cosmos = _get_cosmos_docs()
        doc = await cosmos.get_document(document_id)
        if doc and doc.get("status") == "ready" and doc.get("summary"):
            return doc
        raise ValueError(f"Document {document_id} content not found in pending store")

    content = pending["content"]
    file_name = pending["file_name"]
    content_hash = pending["content_hash"]

    # Check if same content was already fully processed (dedup at processing time)
    cosmos = _get_cosmos_docs()
    try:
        existing = await cosmos.find_by_content_hash(content_hash)
    except Exception:
        existing = None
    if existing and existing.get("status") == "ready" and existing.get("summary"):
        return existing

    # 1. Upload to Blob
    blob = BlobDocumentStorage()
    blob_url = await asyncio.to_thread(
        blob.upload_document, document_id, file_name, content
    )

    # 2. Extract text + figures
    extracted = await extract_text(file_name, content)
    figures = extracted.get("figures", [])

    # 3. Understand figures via GPT-5.4 Vision
    if figures:
        figures = await describe_all_figures(figures, extracted.get("paragraphs", []))

    # 4. Merge figure descriptions into text
    enriched_text = extracted["text"]
    enriched_paragraphs = list(extracted.get("paragraphs", []))
    if figures:
        enriched_text, enriched_paragraphs = _merge_figure_descriptions(
            enriched_text, enriched_paragraphs, figures
        )

    # 5. Generate summaries (using enriched text)
    summaries = await generate_summaries(enriched_text, file_name)

    # 6. Chunk and index (with figure chunks)
    figure_chunks = _build_figure_chunks(figures) if figures else None
    chunks = chunk_text(
        text=enriched_text,
        paragraphs=enriched_paragraphs,
        figure_chunks=figure_chunks,
    )
    await index_document_chunks(document_id, file_name, chunks)

    # 7. Save metadata to Cosmos
    now = datetime.now(timezone.utc).isoformat()
    doc_meta = {
        "id": document_id,
        "file_name": file_name,
        "file_size": len(content),
        "content_hash": content_hash,
        "blob_url": blob_url,
        "page_count": extracted.get("page_count", 0),
        "chunk_count": len(chunks),
        "figure_count": len(figures),
        "abstract": summaries["abstract"],
        "summary": summaries["summary"],
        "status": "ready",
        "created_at": now,
    }
    await cosmos.save_document(doc_meta)

    return doc_meta


def _merge_figure_descriptions(
    text: str,
    paragraphs: list[str],
    figures: list[dict],
) -> tuple[str, list[str]]:
    """Insert figure descriptions into text and paragraph list at their original positions.

    Returns (enriched_text, enriched_paragraphs).
    """
    if not figures:
        return text, paragraphs

    # Sort figures by span_offset descending so insertions don't shift earlier offsets
    sorted_figs = sorted(figures, key=lambda f: f.get("span_offset", 0), reverse=True)

    enriched_text = text
    for fig in sorted_figs:
        description = fig.get("description", "")
        caption = fig.get("caption", "")
        offset = fig.get("span_offset", 0)
        label = fig.get("id", "")

        block = f"\n\n[图片: Figure {label} - {caption}]\n{description}\n[/图片]\n\n"
        enriched_text = enriched_text[:offset] + block + enriched_text[offset:]

    # Rebuild paragraphs from enriched text
    enriched_paragraphs = [p.strip() for p in enriched_text.split("\n\n") if p.strip()]

    return enriched_text, enriched_paragraphs


def _build_figure_chunks(figures: list[dict]) -> list[dict]:
    """Build standalone figure chunks for independent indexing."""
    chunks = []
    for fig in figures:
        caption = fig.get("caption", "")
        description = fig.get("description", "")
        label = fig.get("id", "")
        chunk_text = f"[Figure {label}] {caption}\n{description}"
        chunks.append({
            "text": chunk_text,
            "source_type": "figure",
            "page_number": fig.get("page_number", 0),
        })
    return chunks
```

- [ ] **Step 4: Run all router tests**

Run: `cd backend && .venv/bin/python -m pytest tests/test_document_router.py -v`

Expected: ALL PASS (new test + existing tests still green).

Note: If existing upload tests fail because they don't mock `describe_all_figures`, add `patches["describe_figures"]` to their context managers. The `describe_all_figures` import at module level means it needs to be patched even when not called (unless the extract mock returns `figures: []`). Since the existing tests mock `extract_text` to return `{"text": ..., "page_count": ..., "paragraphs": ...}` without a `"figures"` key, the `figures = extracted.get("figures", [])` will return `[]` and skip the vision step — so existing tests should still pass without change.

- [ ] **Step 5: Run the full test suite**

Run: `cd backend && .venv/bin/python -m pytest tests/ -v --ignore=tests/test_export.py`

Expected: ALL PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/documents/router.py backend/tests/test_document_router.py
git commit -m "feat: integrate vision understanding and figure merging into document pipeline"
```

---

### Task 5: Final Integration Test and Cleanup

**Files:**
- All modified files (read-only verification)

- [ ] **Step 1: Run the full test suite one final time**

Run: `cd backend && .venv/bin/python -m pytest tests/ -v --ignore=tests/test_export.py`

Expected: ALL PASS.

- [ ] **Step 2: Verify no import errors by starting the app briefly**

Run: `cd backend && .venv/bin/python -c "from app.documents.parser import extract_text; from app.documents.vision import describe_figure, describe_all_figures; from app.documents.chunker import chunk_text; from app.documents.router import process_pending_document; print('All imports OK')"`

Expected: `All imports OK`

- [ ] **Step 3: Commit any final fixes (if needed) and verify git status**

Run: `git status` to ensure everything is committed and clean.

- [ ] **Step 4: Final commit if there are any remaining changes**

```bash
git add -A
git commit -m "chore: final cleanup for document image understanding feature"
```
