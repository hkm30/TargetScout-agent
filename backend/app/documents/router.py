import asyncio
import hashlib
import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, UploadFile, File

from app.config import settings
from app.documents.parser import validate_file, extract_text
from app.documents.chunker import chunk_text
from app.documents.summarizer import generate_summaries
from app.documents.vision import describe_all_figures
from app.knowledge.blob_client import BlobDocumentStorage
from app.knowledge.cosmos_client import _get_cosmos_docs
from app.knowledge.search_client import index_document_chunks, delete_document_chunks

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/documents", tags=["documents"])

# In-memory store for pending uploads (max 5 files × 10MB = 50MB).
# Each entry: {"content": bytes, "file_name": str, "content_hash": str}
# Cleared when processed at confirm time, or removed on delete/cancel.
_pending_files: dict[str, dict] = {}


@router.post("/upload")
async def upload_documents(files: list[UploadFile] = File(...)):
    """Upload files: validate and hold in memory.

    Heavy processing (blob upload, text extraction, summarization, chunking,
    indexing) is deferred to the confirm/run phase in the orchestrator.
    """
    if len(files) > settings.DOC_MAX_FILE_COUNT:
        raise HTTPException(
            status_code=400,
            detail=f"Too many files: {len(files)} exceeds limit of {settings.DOC_MAX_FILE_COUNT}",
        )

    results = []
    for file in files:
        filename = file.filename or "unknown"
        content = await file.read()

        # Validate
        error = validate_file(filename, len(content))
        if error:
            results.append({"file_name": filename, "status": "failed", "error": error})
            continue

        # Dedup: check in-memory pending + Cosmos for already-processed
        content_hash = hashlib.sha256(content).hexdigest()

        # Check in-memory pending files first
        pending_dup_id = None
        for pid, pdata in _pending_files.items():
            if pdata["content_hash"] == content_hash:
                pending_dup_id = pid
                break
        if pending_dup_id:
            results.append({
                "id": pending_dup_id,
                "file_name": filename,
                "file_size": len(content),
                "status": "duplicate",
                "message": f"{filename}文件已经上传过",
            })
            continue

        # Check Cosmos for previously processed documents
        try:
            existing = await _get_cosmos_docs().find_by_content_hash(content_hash)
        except Exception:
            existing = None

        if existing and existing.get("id") and existing.get("status") == "ready" and existing.get("summary"):
            results.append({
                "id": existing["id"],
                "file_name": existing.get("file_name", filename),
                "file_size": existing.get("file_size", len(content)),
                "status": "duplicate",
                "message": f"{filename}文件已经上传过",
                "abstract": existing.get("abstract", ""),
                "summary": existing.get("summary", ""),
                "created_at": existing.get("created_at", ""),
            })
            continue

        document_id = str(uuid.uuid4())
        # Hold in memory only — no Blob or Cosmos until confirm
        _pending_files[document_id] = {
            "content": content,
            "file_name": filename,
            "content_hash": content_hash,
        }
        now = datetime.now(timezone.utc).isoformat()
        results.append({
            "id": document_id,
            "file_name": filename,
            "file_size": len(content),
            "status": "pending",
            "created_at": now,
        })

    return {"documents": results}


def _merge_figure_descriptions(
    text: str,
    paragraphs: list[str],
    figures: list[dict],
) -> tuple[str, list[str]]:
    """Insert figure descriptions into text and paragraph list at their original positions."""
    if not figures:
        return text, paragraphs
    sorted_figs = sorted(figures, key=lambda f: f.get("span_offset", 0), reverse=True)
    enriched_text = text
    for fig in sorted_figs:
        description = fig.get("description", "")
        caption = fig.get("caption", "")
        offset = fig.get("span_offset", 0)
        label = fig.get("id", "")
        block = f"\n\n[图片: Figure {label} - {caption}]\n{description}\n[/图片]\n\n"
        enriched_text = enriched_text[:offset] + block + enriched_text[offset:]
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
    raw_text = extracted["text"]
    paragraphs = extracted.get("paragraphs") or [p.strip() for p in raw_text.split("\n\n") if p.strip()]
    figures = extracted.get("figures", [])

    # 3. Understand figures via GPT-5.4 Vision
    described_figures = await describe_all_figures(figures, paragraphs) if figures else []

    # 4. Merge figure descriptions into text
    enriched_text, enriched_paragraphs = _merge_figure_descriptions(
        raw_text, paragraphs, described_figures,
    )

    # 5. Generate summaries using enriched text
    summaries = await generate_summaries(enriched_text, file_name)

    # 6. Chunk and index with figure chunks
    figure_chunks = _build_figure_chunks(described_figures)
    chunks = chunk_text(
        text=enriched_text,
        paragraphs=enriched_paragraphs,
        figure_chunks=figure_chunks if figure_chunks else None,
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
        "figure_count": len(described_figures),
        "chunk_count": len(chunks),
        "abstract": summaries["abstract"],
        "summary": summaries["summary"],
        "status": "ready",
        "created_at": now,
    }
    await cosmos.save_document(doc_meta)

    return doc_meta


@router.get("/{document_id}")
async def get_document(document_id: str):
    """Get document metadata and summaries."""
    doc = await _get_cosmos_docs().get_document(document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    return doc


@router.delete("/{document_id}")
async def delete_document(document_id: str):
    """Delete a document — cleans up pending memory, Blob, Cosmos, and AI Search."""
    # Always clean up in-memory pending content
    _pending_files.pop(document_id, None)

    doc = await _get_cosmos_docs().get_document(document_id)

    if doc:
        # Delete from Cosmos DB
        try:
            await _get_cosmos_docs().delete_document(document_id)
        except Exception:
            logger.warning("Cosmos DB deletion failed for document %s", document_id)

        # Delete from Blob (only if it was uploaded)
        if doc.get("blob_url"):
            try:
                blob = BlobDocumentStorage()
                await asyncio.to_thread(blob.delete_document, document_id, doc["file_name"])
            except Exception:
                logger.warning("Blob deletion failed for document %s", document_id)

    # Always try to clean up AI Search chunks (even if Cosmos record is gone)
    try:
        await delete_document_chunks(document_id)
    except Exception:
        logger.warning("Search index deletion failed for document %s", document_id)

    return {"status": "deleted"}
