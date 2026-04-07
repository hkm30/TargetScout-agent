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


async def extract_text(filename: str, content: bytes) -> dict:
    """Extract text from a file. Returns {text, page_count, paragraphs}.

    PDF/Word → Azure Document Intelligence (prebuilt-read)
    TXT/MD   → Direct decode
    """
    import asyncio

    ext = Path(filename).suffix.lower()

    if ext in TEXT_EXTENSIONS:
        text = content.decode("utf-8", errors="replace")
        paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
        return {"text": text, "page_count": 1, "paragraphs": paragraphs}

    # PDF or Word → Document Intelligence
    client = _get_doc_intel_client()
    poller = await asyncio.to_thread(
        client.begin_analyze_document,
        "prebuilt-read",
        analyze_request=content,
        content_type="application/octet-stream",
    )
    result = await asyncio.to_thread(poller.result)

    text = result.content or ""
    page_count = len(result.pages) if result.pages else 0
    paragraphs = []
    if result.paragraphs:
        paragraphs = [p.content for p in result.paragraphs if p.content]

    return {"text": text, "page_count": page_count, "paragraphs": paragraphs}
