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

    PDF/Word -> Azure Document Intelligence (prebuilt-layout with figure extraction)
    TXT/MD   -> Direct decode (no figures)
    """
    ext = Path(filename).suffix.lower()

    if ext in TEXT_EXTENSIONS:
        text = content.decode("utf-8", errors="replace")
        paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
        return {"text": text, "page_count": 1, "paragraphs": paragraphs, "figures": []}

    # PDF or Word -> Document Intelligence (prebuilt-layout)
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
