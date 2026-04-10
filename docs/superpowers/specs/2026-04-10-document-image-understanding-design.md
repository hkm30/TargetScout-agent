# Document Image Understanding Design

## Overview

Enhance the document parsing pipeline to extract and understand images (figures, charts, diagrams, tables) in uploaded PDF/Word files. Currently the pipeline uses Azure Document Intelligence `prebuilt-read` which only performs OCR text extraction, ignoring all visual content.

## Approach

**Document Intelligence Layout + GPT Vision** (two-stage pipeline):

1. **Detection & Cropping**: Switch from `prebuilt-read` to `prebuilt-layout` with `output=figures` to detect figures and obtain cropped images via the Document Intelligence API.
2. **Visual Understanding**: Send each cropped figure image to GPT-5.4 multimodal API to generate structured Chinese descriptions.
3. **Dual Integration**: Merge descriptions into the text flow (for summarization) AND index them as separate chunks (for precise retrieval).

## Detailed Design

### 1. Parser Layer (`documents/parser.py`)

**Change**: Switch `prebuilt-read` → `prebuilt-layout` with `output=figures`.

`prebuilt-layout` is a superset of `prebuilt-read` — text extraction capability does not degrade.

**Updated return value** from `extract_text()`:

```python
{
    "text": str,              # Full text content (unchanged)
    "page_count": int,        # Page count (unchanged)
    "paragraphs": list[str],  # Paragraph list (unchanged)
    "figures": [              # NEW: detected figures
        {
            "id": str,            # Figure ID (e.g. "1.0")
            "page_number": int,   # Page where figure appears
            "caption": str,       # Caption text extracted by Document Intelligence
            "image_bytes": bytes, # Cropped figure image (PNG)
            "span_offset": int,   # Position offset in original text
        }
    ]
}
```

**Implementation details**:

- Call `begin_analyze_document("prebuilt-layout", content, content_type="application/octet-stream", output=["figures"])` to enable figure cropping.
- After analysis completes, iterate `result.figures` to get bounding regions, captions, and span offsets.
- For each figure with an `id`, use the Document Intelligence client's `get_analyze_result_figure(model_id, result_id, figure_id)` method to retrieve the cropped PNG bytes. If the SDK method is unavailable, fall back to raw HTTP GET `/analyzeResults/{resultId}/figures/{figureId}`.
- Text-only files (`.txt`, `.md`) bypass this entirely — no change to their path.

### 2. Vision Understanding Layer (`documents/vision.py`) — NEW FILE

New module responsible for calling GPT-5.4 multimodal capability to understand figure images.

```python
async def describe_figure(
    image_bytes: bytes,
    caption: str = "",
    context: str = "",
) -> str:
    """Generate a Chinese description of a figure using multimodal LLM.

    Args:
        image_bytes: Cropped figure image (PNG bytes)
        caption: Original caption from Document Intelligence
        context: Surrounding text for additional understanding

    Returns:
        Chinese description text (300-800 tokens)
    """
```

**Prompt strategy** — tailored for drug development domain:

```
你是药物研发领域的文档分析专家。请分析以下图片，生成详细的中文描述。

要求：
1. 识别图片类型（分子结构图、信号通路图、数据图表、流程图、表格截图等）
2. 提取图片中的关键数据、趋势和发现
3. 用中文生成结构化描述
4. 保留专业术语（药物名、基因名、蛋白名等）的英文原文
5. 如果是数据图表，提取关键数值和统计趋势

{caption context if available}
```

**Concurrency control**: `asyncio.Semaphore(3)` to limit concurrent vision API calls and avoid rate limits.

**API call method**: Uses existing `get_openai_client()` with base64-encoded image:

```python
messages = [
    {"role": "user", "content": [
        {"type": "text", "text": prompt},
        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64_image}"}}
    ]}
]
```

**Batch processing function**:

```python
async def describe_all_figures(
    figures: list[dict],
    paragraphs: list[str],
) -> list[dict]:
    """Process all figures concurrently with semaphore control.

    Returns figures list with added 'description' field.
    """
```

For each figure, extracts surrounding paragraph text as context (2 paragraphs before/after the figure's span offset).

### 3. Fusion Strategy

#### 3a. Merge into Text Flow (for summarization)

After vision understanding completes, insert figure descriptions into the paragraph list at their original positions:

```
[图片: Figure 1 - {caption}]
{GPT Vision 生成的描述}
[/图片]
```

The enriched text (with figure descriptions embedded) is then passed to:
- `generate_summaries()` — so summaries include image information
- `chunk_text()` — so text chunks naturally contain figure descriptions

#### 3b. Independent Figure Chunks (for precise retrieval)

For each figure, generate an additional standalone chunk with `source_type: "figure"`:

```python
{
    "text": f"[Figure {fig['id']}] {caption}\n{description}",
    "chunk_index": ...,
    "source_type": "figure",
    "page_number": fig["page_number"],
}
```

These chunks are indexed alongside regular text chunks in the same AI Search documents index. The existing `source_type` field (currently always `"private_document"`) gains a new value `"figure"` — no schema change needed.

### 4. Updated Processing Pipeline

`process_pending_document()` in `router.py` changes from 5 steps to 7:

```
1. Upload to Blob                           (unchanged)
2. Extract text + figures                   (prebuilt-layout, was prebuilt-read)
3. Understand figures via GPT Vision        (NEW)
4. Merge figure descriptions into text      (NEW)
5. Generate summaries                       (uses enriched text)
6. Chunk and index                          (text chunks + figure chunks)
7. Save metadata to Cosmos                  (unchanged)
```

Steps 3-4 are the new additions. Step 3 runs all figure descriptions concurrently (with semaphore). Step 4 is a pure text manipulation step.

### 5. Chunker Changes (`documents/chunker.py`)

Minimal change: `chunk_text()` gains an optional `figure_chunks` parameter. After generating regular text chunks, figure chunks are appended with sequential `chunk_index` values.

```python
def chunk_text(
    text: str,
    paragraphs: list[str] | None = None,
    max_tokens: int = 600,
    overlap_tokens: int = 100,
    figure_chunks: list[dict] | None = None,  # NEW
) -> list[dict]:
```

Each figure chunk dict has `{text, chunk_index, token_count, source_type, page_number}`.

### 6. Configuration (`config.py`)

No new config needed. Vision calls use the existing `MODEL_DEPLOYMENT` setting (`gpt-54` / GPT-5.4), which supports multimodal input natively.

## Files Changed

| File | Change Type | Description |
|------|-------------|-------------|
| `documents/parser.py` | Modify | `prebuilt-read` → `prebuilt-layout` + figure extraction |
| `documents/vision.py` | **New** | GPT Vision integration for figure understanding |
| `documents/router.py` | Modify | Add vision + merge steps to `process_pending_document()` |
| `documents/chunker.py` | Modify | Support `figure_chunks` parameter |
| `config.py` | No change | Uses existing `MODEL_DEPLOYMENT` (GPT-5.4) |
| `tests/test_parser.py` | **New/Modify** | Tests for layout model + figure extraction |
| `tests/test_vision.py` | **New** | Tests for vision description generation |

## Files NOT Changed

- **AI Search index schema**: `source_type` field already exists, just gains `"figure"` value
- **Cosmos DB schema**: No change — figure info is embedded in summaries
- **Frontend**: No change — consumes summaries and search results as before
- **Agent pipeline**: No change — gets document context via `_build_document_context()`
- **Blob storage**: No change — raw files uploaded as before
- **Orchestrator**: No change — `process_pending_document()` API contract unchanged

## Performance Considerations

- **Latency**: Figure understanding adds ~3-10s per figure (GPT Vision API call). With `Semaphore(3)` concurrency, a 10-figure document takes ~10-30s. This runs within the confirm phase where document processing already runs in parallel with KB search and before agent execution.
- **Cost**: Each figure = 1 vision API call. A typical research paper has 3-8 figures. Cost is proportional to figure count.
- **No regression for text-only files**: `.txt` and `.md` files skip the entire figure pipeline. Documents with no figures detected by `prebuilt-layout` also skip vision calls.
- **Graceful degradation**: If vision API fails for a figure, log the error and continue with caption-only text. The pipeline never fails due to figure understanding failure.

## Error Handling

- **No figures detected**: Skip vision step entirely, proceed with text-only flow (same as current behavior).
- **Vision API failure for individual figure**: Log warning, use caption text as fallback description. Do not fail the entire document.
- **Vision API rate limit**: Handled by existing `Semaphore(3)` + the retry logic pattern already in the codebase.
- **Document Intelligence figure cropping failure**: Log warning, skip that figure. Other figures and text extraction are unaffected.
