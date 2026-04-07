import asyncio
import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, UploadFile, File

from app.config import settings
from app.documents.parser import validate_file, extract_text
from app.documents.chunker import chunk_text
from app.documents.summarizer import generate_summaries
from app.knowledge.blob_client import BlobDocumentStorage
from app.knowledge.cosmos_client import _get_cosmos_docs
from app.knowledge.search_client import index_document_chunks, delete_document_chunks

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/documents", tags=["documents"])


@router.post("/upload")
async def upload_documents(files: list[UploadFile] = File(...)):
    """Upload one or more documents, parse, chunk, summarize, and index them."""
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

        document_id = str(uuid.uuid4())
        try:
            # 1. Upload to Blob Storage
            blob = BlobDocumentStorage()
            blob_url = await asyncio.to_thread(
                blob.upload_document, document_id, filename, content
            )

            # 2. Extract text
            extracted = await extract_text(filename, content)

            # 3. Generate summaries
            summaries = await generate_summaries(extracted["text"], filename)

            # 4. Chunk and index
            chunks = chunk_text(
                text=extracted["text"],
                paragraphs=extracted.get("paragraphs"),
            )
            await index_document_chunks(document_id, filename, chunks)

            # 5. Store metadata
            now = datetime.now(timezone.utc).isoformat()
            doc_meta = {
                "id": document_id,
                "file_name": filename,
                "file_size": len(content),
                "blob_url": blob_url,
                "page_count": extracted.get("page_count", 0),
                "chunk_count": len(chunks),
                "abstract": summaries["abstract"],
                "summary": summaries["summary"],
                "status": "ready",
                "created_at": now,
            }
            await _get_cosmos_docs().save_document(doc_meta)

            results.append({
                "id": document_id,
                "file_name": filename,
                "file_size": len(content),
                "status": "ready",
                "abstract": summaries["abstract"],
                "summary": summaries["summary"],
                "created_at": now,
            })
        except Exception as e:
            logger.error("Failed to process document %s: %s", filename, e, exc_info=True)
            results.append({"file_name": filename, "status": "failed", "error": str(e)})

    return {"documents": results}


@router.get("/{document_id}")
async def get_document(document_id: str):
    """Get document metadata and summaries."""
    doc = await _get_cosmos_docs().get_document(document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    return doc


@router.delete("/{document_id}")
async def delete_document(document_id: str):
    """Delete a document from Blob Storage and AI Search."""
    doc = await _get_cosmos_docs().get_document(document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    # Delete from Cosmos DB
    try:
        await _get_cosmos_docs().delete_document(document_id)
    except Exception:
        logger.warning("Cosmos DB deletion failed for document %s", document_id)

    # Delete from Blob
    try:
        blob = BlobDocumentStorage()
        await asyncio.to_thread(blob.delete_document, document_id, doc["file_name"])
    except Exception:
        logger.warning("Blob deletion failed for document %s", document_id)

    # Delete from AI Search
    try:
        await delete_document_chunks(document_id)
    except Exception:
        logger.warning("Search index deletion failed for document %s", document_id)

    return {"status": "deleted"}
