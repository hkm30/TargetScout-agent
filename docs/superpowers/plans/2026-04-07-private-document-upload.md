# Private Document Upload Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Allow users to upload private documents (PDF/Word/TXT/MD) during target assessment, combine document content with internet search for analysis, and persist documents in the knowledge base for future retrieval.

**Architecture:** Files are uploaded via multipart POST to FastAPI, stored in Blob Storage, parsed via Azure Document Intelligence (PDF/Word) or direct read (TXT/MD), chunked and vectorized into a new AI Search index. LLM generates two-level summaries (摘要 + 总结) which are injected into all research Agent prompts alongside internet search results. The knowledge search page queries both report and document indexes with source type labels.

**Tech Stack:** FastAPI, Azure Document Intelligence (prebuilt-read), Azure Blob Storage, Azure AI Search, text-embedding-3-large, React 19, TypeScript

---

## File Structure

### New files
- `backend/app/documents/__init__.py` — package init
- `backend/app/documents/parser.py` — Document Intelligence for PDF/Word, direct read for TXT/MD
- `backend/app/documents/chunker.py` — text chunking with overlap
- `backend/app/documents/summarizer.py` — LLM two-level summarization (摘要 + 总结)
- `backend/app/documents/router.py` — FastAPI router: upload, get, delete

### Modified files
- `backend/pyproject.toml` — add `azure-ai-documentintelligence`, `tiktoken` dependencies
- `backend/app/config.py` — add Document Intelligence + documents container config
- `backend/app/knowledge/blob_client.py` — add `BlobDocumentStorage` class
- `backend/app/knowledge/search_client.py` — add documents index schema, ensure_documents_index(), index_document_chunks(), search_documents(), unified_search()
- `backend/app/agents/orchestrator.py` — inject document context + user_suggestions into agent prompts, update request flow
- `backend/app/main.py` — register document router, update ConfirmAssessmentRequest model
- `frontend/src/types.ts` — add UploadedDocument, update ParsedInput, SearchResultItem
- `frontend/src/api.ts` — add uploadDocuments(), deleteDocument()
- `frontend/src/components/SearchForm.tsx` — add file upload drop zone
- `frontend/src/components/ConfirmationPanel.tsx` — add uploaded docs, "其他建议" textarea, "取消" button
- `frontend/src/components/SearchPage.tsx` — add source_type badge
- `frontend/src/App.tsx` — wire up document state, onCancel handler

---

## Task 1: Add Dependencies and Config

**Files:**
- Modify: `backend/pyproject.toml:5-18`
- Modify: `backend/app/config.py:1-72`

- [ ] **Step 1: Add Python dependencies**

In `backend/pyproject.toml`, add to the `dependencies` list:

```toml
    "azure-ai-documentintelligence>=1.0.0",
    "tiktoken>=0.7.0",
```

The full dependencies block becomes:

```toml
dependencies = [
    "fastapi>=0.115.0",
    "uvicorn[standard]>=0.30.0",
    "azure-ai-projects>=2.0.0b2",
    "azure-identity>=1.17.0",
    "azure-search-documents>=11.6.0",
    "azure-cosmos>=4.7.0",
    "azure-storage-blob>=12.22.0",
    "httpx>=0.27.0",
    "python-dotenv>=1.0.0",
    "python-docx>=1.1.0",
    "fpdf2>=2.8.0",
    "azure-monitor-opentelemetry>=1.6.0",
    "azure-ai-documentintelligence>=1.0.0",
    "tiktoken>=0.7.0",
]
```

- [ ] **Step 2: Add config settings**

In `backend/app/config.py`, add these new fields to the `Settings` class (after the Blob Storage section, before `@property`):

```python
    # Azure Document Intelligence
    DOC_INTELLIGENCE_ENDPOINT: str = os.environ.get("AZURE_DOC_INTELLIGENCE_ENDPOINT", "")
    DOC_INTELLIGENCE_KEY: str = os.environ.get("AZURE_DOC_INTELLIGENCE_KEY", "")

    # Private documents
    BLOB_DOCUMENTS_CONTAINER: str = os.environ.get("BLOB_DOCUMENTS_CONTAINER", "private-documents")
    SEARCH_DOCUMENTS_INDEX_NAME: str = os.environ.get("AZURE_SEARCH_DOCUMENTS_INDEX_NAME", "drug-target-documents")
    DOC_MAX_FILE_SIZE_MB: int = int(os.environ.get("DOC_MAX_FILE_SIZE_MB", "10"))
    DOC_MAX_FILE_COUNT: int = int(os.environ.get("DOC_MAX_FILE_COUNT", "5"))
```

- [ ] **Step 3: Update conftest.py**

In `backend/tests/conftest.py`, add:

```python
os.environ.setdefault("AZURE_DOC_INTELLIGENCE_ENDPOINT", "https://test.cognitiveservices.azure.com/")
os.environ.setdefault("AZURE_DOC_INTELLIGENCE_KEY", "test-doc-intel-key")
```

- [ ] **Step 4: Install dependencies**

Run: `cd backend && pip install -e ".[dev]"`

- [ ] **Step 5: Commit**

```bash
git add backend/pyproject.toml backend/app/config.py backend/tests/conftest.py
git commit -m "feat: add Document Intelligence and tiktoken dependencies, config settings"
```

---

## Task 2: Document Parser

**Files:**
- Create: `backend/app/documents/__init__.py`
- Create: `backend/app/documents/parser.py`

- [ ] **Step 1: Create documents package**

Create `backend/app/documents/__init__.py` (empty file):

```python
```

- [ ] **Step 2: Create parser.py**

Create `backend/app/documents/parser.py`:

```python
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
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/documents/__init__.py backend/app/documents/parser.py
git commit -m "feat: add document parser with Document Intelligence and text support"
```

---

## Task 3: Document Chunker

**Files:**
- Create: `backend/app/documents/chunker.py`

- [ ] **Step 1: Create chunker.py**

Create `backend/app/documents/chunker.py`:

```python
import tiktoken

_encoder = tiktoken.get_encoding("cl100k_base")


def count_tokens(text: str) -> int:
    return len(_encoder.encode(text))


def chunk_text(
    text: str,
    paragraphs: list[str] | None = None,
    max_tokens: int = 600,
    overlap_tokens: int = 100,
) -> list[dict]:
    """Split text into overlapping chunks.

    Strategy:
    1. If paragraphs are provided, group them into chunks up to max_tokens.
    2. If a single paragraph exceeds max_tokens, split it by token window.

    Returns list of {text, chunk_index, token_count}.
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

    return chunks
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/documents/chunker.py
git commit -m "feat: add document text chunker with token-based splitting and overlap"
```

---

## Task 4: Document Summarizer

**Files:**
- Create: `backend/app/documents/summarizer.py`

- [ ] **Step 1: Create summarizer.py**

Create `backend/app/documents/summarizer.py`:

```python
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
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/documents/summarizer.py
git commit -m "feat: add two-level document summarizer (摘要 + 总结) via LLM"
```

---

## Task 5: Documents AI Search Index

**Files:**
- Modify: `backend/app/knowledge/search_client.py`

- [ ] **Step 1: Add documents index schema and functions**

Add the following to `backend/app/knowledge/search_client.py` after the existing `delete_report` function at the bottom of the file:

```python
# ──────────────────────────────────────────────
# Documents index (private document chunks)
# ──────────────────────────────────────────────

def _build_documents_index_fields() -> list:
    """Build index fields for the private documents index."""
    return [
        SimpleField(name="id", type=DT.String, key=True, filterable=True),
        SimpleField(name="document_id", type=DT.String, filterable=True),
        SimpleField(name="file_name", type=DT.String, filterable=True),
        SimpleField(name="target", type=DT.String, filterable=True),
        SimpleField(name="indication", type=DT.String, filterable=True),
        SearchableField(name="content", type=DT.String),
        SimpleField(name="chunk_index", type=DT.Int32, filterable=True, sortable=True),
        SimpleField(name="page_number", type=DT.Int32, filterable=True),
        SimpleField(name="source_type", type=DT.String, filterable=True),
        SimpleField(name="created_at", type=DT.DateTimeOffset, filterable=True, sortable=True),
        SearchField(
            name="content_vector",
            type=SearchFieldDataType.Collection(SearchFieldDataType.Single),
            searchable=True,
            vector_search_dimensions=settings.EMBEDDING_DIMENSIONS,
            vector_search_profile_name="default-profile",
        ),
    ]


def get_documents_search_client() -> SearchClient:
    return SearchClient(
        endpoint=settings.SEARCH_ENDPOINT,
        index_name=settings.SEARCH_DOCUMENTS_INDEX_NAME,
        credential=AzureKeyCredential(settings.SEARCH_API_KEY),
    )


def ensure_documents_index():
    """Create or update the documents search index."""
    try:
        index_client = get_index_client()
        vector_search = VectorSearch(
            algorithms=[HnswAlgorithmConfiguration(name="default-algo")],
            profiles=[VectorSearchProfile(name="default-profile", algorithm_configuration_name="default-algo")],
        )
        index = SearchIndex(
            name=settings.SEARCH_DOCUMENTS_INDEX_NAME,
            fields=_build_documents_index_fields(),
            vector_search=vector_search,
        )
        index_client.create_or_update_index(index)
    except Exception as e:
        logger.warning("Failed to create/update documents index: %s", e)


async def index_document_chunks(document_id: str, file_name: str, chunks: list[dict], target: str = "", indication: str = ""):
    """Index document chunks into the documents AI Search index."""
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc).isoformat()
    docs = []
    for chunk in chunks:
        chunk_id = f"{document_id}_{chunk['chunk_index']}"
        vector = await generate_embedding(chunk["text"])
        docs.append({
            "id": chunk_id,
            "document_id": document_id,
            "file_name": file_name,
            "target": target,
            "indication": indication,
            "content": chunk["text"],
            "chunk_index": chunk["chunk_index"],
            "page_number": chunk.get("page_number", 0),
            "source_type": "private_document",
            "created_at": now,
            "content_vector": vector,
        })

    client = get_documents_search_client()
    # Upload in batches of 16
    for i in range(0, len(docs), 16):
        batch = docs[i:i + 16]
        await asyncio.to_thread(client.upload_documents, batch)


async def search_documents(query: str, top_k: int = 5) -> list[dict]:
    """Search private documents by hybrid search."""
    try:
        vector = await generate_embedding(query)
        vector_query = VectorizedQuery(vector=vector, k_nearest_neighbors=top_k, fields="content_vector")

        client = get_documents_search_client()
        results = await asyncio.to_thread(
            client.search,
            search_text=query,
            vector_queries=[vector_query],
            top=top_k,
        )

        return [
            {
                "id": r.get("id", ""),
                "document_id": r.get("document_id", ""),
                "file_name": r.get("file_name", ""),
                "target": r.get("target", ""),
                "indication": r.get("indication", ""),
                "summary": (r.get("content") or "")[:500],
                "created_at": r.get("created_at", ""),
                "score": r.get("@search.score", 0),
                "source_type": "private_document",
            }
            for r in results
        ]
    except Exception as e:
        logger.error("Search documents failed: %s", e, exc_info=True)
        return []


async def delete_document_chunks(document_id: str):
    """Delete all chunks for a document from the documents index."""
    client = get_documents_search_client()
    # Search for all chunks with this document_id
    results = await asyncio.to_thread(
        client.search,
        search_text="*",
        filter=f"document_id eq '{document_id}'",
        top=1000,
        select=["id"],
    )
    chunk_ids = [{"id": r["id"]} for r in results]
    if chunk_ids:
        await asyncio.to_thread(client.delete_documents, chunk_ids)


async def unified_search(query: str, top_k: int = 5) -> list[dict]:
    """Search both reports and documents indexes, merge and sort by score."""
    report_results, doc_results = await asyncio.gather(
        search_reports(query=query, top_k=top_k),
        search_documents(query=query, top_k=top_k),
    )

    # Add source_type to report results
    for r in report_results:
        r["source_type"] = "report"

    # Merge and sort by score descending
    combined = report_results + doc_results
    combined.sort(key=lambda x: x.get("score", 0), reverse=True)
    return combined[:top_k]
```

- [ ] **Step 2: Update ensure_index call in main.py lifespan**

In `backend/app/main.py`, update the lifespan function to also create the documents index. Change:

```python
from app.knowledge.search_client import ensure_index, search_reports, delete_report as delete_search_report
```

to:

```python
from app.knowledge.search_client import ensure_index, ensure_documents_index, search_reports, delete_report as delete_search_report
```

And update the lifespan:

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Create agents and search index on startup."""
    global _agent_names
    ensure_index()
    ensure_documents_index()
    _agent_names = create_all_agents()
    yield
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/knowledge/search_client.py backend/app/main.py
git commit -m "feat: add documents AI Search index with chunk CRUD and unified search"
```

---

## Task 6: Blob Storage for Documents

**Files:**
- Modify: `backend/app/knowledge/blob_client.py`

- [ ] **Step 1: Add BlobDocumentStorage class**

Add to the end of `backend/app/knowledge/blob_client.py`:

```python
class BlobDocumentStorage:
    """Blob storage for private uploaded documents."""

    def __init__(self):
        account_url = settings.BLOB_ACCOUNT_URL
        if not account_url:
            raise ValueError("STORAGE_ACCOUNT_NAME must be set for blob storage")
        self.service = BlobServiceClient(account_url=account_url, credential=DefaultAzureCredential())
        self.container = self.service.get_container_client(settings.BLOB_DOCUMENTS_CONTAINER)
        # Ensure container exists
        try:
            self.container.get_container_properties()
        except Exception:
            self.container.create_container()

    def upload_document(self, document_id: str, filename: str, content: bytes, content_type: str = "application/octet-stream") -> str:
        """Upload a document file and return its URL."""
        from pathlib import Path
        ext = Path(filename).suffix.lower()
        blob_name = f"{document_id}{ext}"
        blob_client = self.container.get_blob_client(blob_name)
        blob_client.upload_blob(
            content,
            overwrite=True,
            content_settings=ContentSettings(content_type=content_type),
        )
        return blob_client.url

    def delete_document(self, document_id: str, filename: str):
        """Delete a document file from blob storage."""
        from pathlib import Path
        ext = Path(filename).suffix.lower()
        blob_name = f"{document_id}{ext}"
        blob_client = self.container.get_blob_client(blob_name)
        blob_client.delete_blob(delete_snapshots="include")
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/knowledge/blob_client.py
git commit -m "feat: add BlobDocumentStorage for private document uploads"
```

---

## Task 7: Document Router (Backend API)

**Files:**
- Create: `backend/app/documents/router.py`
- Modify: `backend/app/main.py`

- [ ] **Step 1: Create document router**

Create `backend/app/documents/router.py`:

```python
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
from app.knowledge.search_client import index_document_chunks, delete_document_chunks

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/documents", tags=["documents"])

# In-memory document metadata store (keyed by document_id)
# In production this would be stored in Cosmos DB; kept simple for this feature.
_document_store: dict[str, dict] = {}


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
            _document_store[document_id] = doc_meta

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
    doc = _document_store.get(document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    return doc


@router.delete("/{document_id}")
async def delete_document(document_id: str):
    """Delete a document from Blob Storage and AI Search."""
    doc = _document_store.pop(document_id, None)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

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
```

- [ ] **Step 2: Register router in main.py**

In `backend/app/main.py`, add after the existing imports (around line 29):

```python
from app.documents.router import router as documents_router
```

Then after `app.add_middleware(APIKeyMiddleware)` (around line 75), add:

```python
app.include_router(documents_router)
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/documents/router.py backend/app/main.py
git commit -m "feat: add document upload/get/delete API endpoints"
```

---

## Task 8: Orchestrator — Inject Document Context and User Suggestions

**Files:**
- Modify: `backend/app/agents/orchestrator.py`
- Modify: `backend/app/main.py`

- [ ] **Step 1: Add document context builder to orchestrator.py**

Add this function to `backend/app/agents/orchestrator.py` after the `_build_research_prompt` function (after line 210):

```python
def _build_document_context(documents: list[dict], user_suggestions: str = "") -> str:
    """Build the private document + user suggestions context block for agent prompts."""
    parts = []

    if documents:
        parts.append("## 用户提供的私有文档参考资料\n")
        for doc in documents:
            parts.append(f"### 文档: {doc.get('file_name', 'unknown')}\n")
            summary = doc.get("summary", "")
            abstract = doc.get("abstract", "")
            if summary:
                parts.append(f"#### 总结\n{summary}\n")
            if abstract:
                parts.append(f"#### 摘要\n{abstract}\n")

    if user_suggestions:
        parts.append(f"## 用户补充建议\n{user_suggestions}\n")

    if parts:
        parts.append("请结合以上私有文档和用户建议，与你的网络搜索结果进行综合分析。\n")

    return "\n".join(parts)
```

- [ ] **Step 2: Update run_full_pipeline_stream to accept documents and user_suggestions**

In `backend/app/agents/orchestrator.py`, modify the `run_full_pipeline_stream` function signature (line 367) to accept two new parameters:

Change:
```python
async def run_full_pipeline_stream(
    agent_names: dict[str, str],
    target: str,
    indication: str = "",
    synonyms: str = "",
    focus: str = "",
    time_range: str = "",
) -> AsyncGenerator[dict, None]:
```

to:

```python
async def run_full_pipeline_stream(
    agent_names: dict[str, str],
    target: str,
    indication: str = "",
    synonyms: str = "",
    focus: str = "",
    time_range: str = "",
    document_ids: list[str] | None = None,
    user_suggestions: str = "",
) -> AsyncGenerator[dict, None]:
```

Then, after the research_prompt is built (after line 391 `research_prompt = _build_research_prompt(...)`), add the document context injection:

```python
    # Inject private document context and user suggestions if provided
    doc_context = ""
    if document_ids:
        from app.documents.router import _document_store
        docs = [_document_store[did] for did in document_ids if did in _document_store]
        doc_context = _build_document_context(docs, user_suggestions)
    elif user_suggestions:
        doc_context = _build_document_context([], user_suggestions)

    if doc_context:
        research_prompt = doc_context + "\n" + research_prompt
```

Also update the `_build_decision_prompt` call (around line 435) to include document context:

Change:
```python
    decision_prompt = _build_decision_prompt(target, indication, lit_result, clin_result, comp_result, kb_data)
```

to:

```python
    decision_prompt = _build_decision_prompt(target, indication, lit_result, clin_result, comp_result, kb_data)
    if doc_context:
        decision_prompt = doc_context + "\n" + decision_prompt
```

- [ ] **Step 3: Update run_full_pipeline (non-streaming) similarly**

In the `run_full_pipeline` function (line 282), add the same two parameters and context injection. Change the signature to:

```python
async def run_full_pipeline(
    agent_names: dict[str, str],
    target: str,
    indication: str = "",
    synonyms: str = "",
    focus: str = "",
    time_range: str = "",
    document_ids: list[str] | None = None,
    user_suggestions: str = "",
) -> dict:
```

After the research_prompt is built (after line 304), add:

```python
    # Inject private document context and user suggestions
    doc_context = ""
    if document_ids:
        from app.documents.router import _document_store
        docs = [_document_store[did] for did in document_ids if did in _document_store]
        doc_context = _build_document_context(docs, user_suggestions)
    elif user_suggestions:
        doc_context = _build_document_context([], user_suggestions)

    if doc_context:
        research_prompt = doc_context + "\n" + research_prompt
```

And before the decision_prompt call (around line 331), add:

```python
    if doc_context:
        decision_prompt = doc_context + "\n" + decision_prompt
```

- [ ] **Step 4: Update main.py ConfirmAssessmentRequest and endpoint**

In `backend/app/main.py`, update the `ConfirmAssessmentRequest` model (line 86):

```python
class ConfirmAssessmentRequest(BaseModel):
    """Request body for the confirm step — fields may have been edited by the user."""
    target: str
    indication: str = ""
    synonyms: str = ""
    focus: str = ""
    time_range: str = ""
    document_ids: list[str] = []
    user_suggestions: str = ""
```

Update the SSE streaming call in `assess_confirm` (around line 116) to pass the new fields:

Change:
```python
        async for event in run_full_pipeline_stream(
            agent_names=_agent_names,
            target=req.target,
            indication=req.indication,
            synonyms=req.synonyms,
            focus=req.focus,
            time_range=req.time_range,
        ):
```

to:

```python
        async for event in run_full_pipeline_stream(
            agent_names=_agent_names,
            target=req.target,
            indication=req.indication,
            synonyms=req.synonyms,
            focus=req.focus,
            time_range=req.time_range,
            document_ids=req.document_ids,
            user_suggestions=req.user_suggestions,
        ):
```

- [ ] **Step 5: Update knowledge_search endpoint to use unified_search**

In `backend/app/main.py`, update the import (around line 27):

Change:
```python
from app.knowledge.search_client import ensure_index, ensure_documents_index, search_reports, delete_report as delete_search_report
```

to:

```python
from app.knowledge.search_client import ensure_index, ensure_documents_index, search_reports, unified_search, delete_report as delete_search_report
```

Update the `knowledge_search` endpoint (around line 277):

Change:
```python
        results = await search_reports(query=en_query, top_k=req.top_k)
```

to:

```python
        results = await unified_search(query=en_query, top_k=req.top_k)
```

- [ ] **Step 6: Commit**

```bash
git add backend/app/agents/orchestrator.py backend/app/main.py
git commit -m "feat: inject document context and user suggestions into agent prompts, unified search"
```

---

## Task 9: Frontend Types and API

**Files:**
- Modify: `frontend/src/types.ts`
- Modify: `frontend/src/api.ts`

- [ ] **Step 1: Update types.ts**

Add `UploadedDocument` interface and update existing types. In `frontend/src/types.ts`, add after the `Paper` interface (after line 41):

```typescript
export interface UploadedDocument {
  id: string;
  file_name: string;
  file_size: number;
  status: "uploading" | "parsing" | "ready" | "failed";
  error?: string;
  abstract?: string;
  summary?: string;
  created_at?: string;
}
```

Update `ParsedInput` (line 49) to include document_ids and user_suggestions:

```typescript
export interface ParsedInput {
  target: string;
  indication: string;
  synonyms: string;
  focus: string;
  time_range: string;
  document_ids?: string[];
  user_suggestions?: string;
}
```

Update `SearchResultItem` (line 93) to include source_type:

```typescript
export interface SearchResultItem {
  id: string;
  target: string;
  indication: string;
  recommendation: string;
  summary: string;
  created_at: string;
  score: number;
  source_type?: "report" | "private_document";
  file_name?: string;
  document_id?: string;
}
```

- [ ] **Step 2: Add document API functions to api.ts**

Add at the end of `frontend/src/api.ts`:

```typescript
export interface UploadDocumentsResponse {
  documents: import("./types").UploadedDocument[];
}

export async function uploadDocuments(files: File[]): Promise<UploadDocumentsResponse> {
  const formData = new FormData();
  files.forEach((file) => formData.append("files", file));
  const res = await fetch(`${API_BASE}/documents/upload`, {
    method: "POST",
    headers: getHeaders(),
    body: formData,
  });
  if (!res.ok) throw new Error(`Upload failed: ${res.status}`);
  return res.json();
}

export async function deleteDocument(id: string): Promise<void> {
  const res = await fetch(`${API_BASE}/documents/${id}`, {
    method: "DELETE",
    headers: getHeaders(),
  });
  if (!res.ok) throw new Error(`Delete failed: ${res.status}`);
}
```

- [ ] **Step 3: Update confirmAssessmentSSE to pass document_ids and user_suggestions**

In `frontend/src/api.ts`, the `confirmAssessmentSSE` function (line 41) already accepts `ParsedInput` which now includes `document_ids` and `user_suggestions`. The `JSON.stringify(parsed)` call will automatically include these fields. No code change needed.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/types.ts frontend/src/api.ts
git commit -m "feat: add document upload types and API client functions"
```

---

## Task 10: SearchForm — File Upload Area

**Files:**
- Modify: `frontend/src/components/SearchForm.tsx`

- [ ] **Step 1: Add file upload to SearchForm**

Replace the entire `frontend/src/components/SearchForm.tsx` with:

```tsx
import { useState, useRef } from "react";
import type { UploadedDocument } from "../types";
import { uploadDocuments, deleteDocument } from "../api";

interface Props {
  onSubmit: (target: string, indication: string, synonyms: string, focus: string, timeRange: string, documents: UploadedDocument[]) => void;
  loading: boolean;
}

const ACCEPTED_TYPES = ".pdf,.docx,.txt,.md";
const MAX_FILES = 5;
const MAX_SIZE_MB = 10;

export function SearchForm({ onSubmit, loading }: Props) {
  const [target, setTarget] = useState("");
  const [indication, setIndication] = useState("");
  const [synonyms, setSynonyms] = useState("");
  const [focus, setFocus] = useState("");
  const [timeRange, setTimeRange] = useState("");
  const [documents, setDocuments] = useState<UploadedDocument[]>([]);
  const [uploading, setUploading] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleFiles = async (fileList: FileList | null) => {
    if (!fileList || fileList.length === 0) return;

    const files = Array.from(fileList);
    const remaining = MAX_FILES - documents.length;
    if (files.length > remaining) {
      alert(`最多上传 ${MAX_FILES} 个文件，还可上传 ${remaining} 个`);
      return;
    }

    // Validate sizes
    for (const f of files) {
      if (f.size > MAX_SIZE_MB * 1024 * 1024) {
        alert(`文件 ${f.name} 超过 ${MAX_SIZE_MB}MB 限制`);
        return;
      }
    }

    // Add placeholders
    const placeholders: UploadedDocument[] = files.map((f) => ({
      id: "",
      file_name: f.name,
      file_size: f.size,
      status: "uploading" as const,
    }));
    setDocuments((prev) => [...prev, ...placeholders]);
    setUploading(true);

    try {
      const resp = await uploadDocuments(files);
      setDocuments((prev) => {
        // Replace placeholders with actual results
        const existing = prev.filter((d) => d.status !== "uploading");
        const uploaded = resp.documents.map((d) => ({
          ...d,
          status: d.status as UploadedDocument["status"],
        }));
        return [...existing, ...uploaded];
      });
    } catch {
      setDocuments((prev) => prev.filter((d) => d.status !== "uploading"));
      alert("文件上传失败，请重试");
    } finally {
      setUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  };

  const handleRemove = async (docId: string) => {
    if (docId) {
      try {
        await deleteDocument(docId);
      } catch {
        // Best effort
      }
    }
    setDocuments((prev) => prev.filter((d) => d.id !== docId));
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    handleFiles(e.dataTransfer.files);
  };

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        if (target.trim())
          onSubmit(target.trim(), indication.trim(), synonyms.trim(), focus.trim(), timeRange, documents.filter((d) => d.status === "ready"));
      }}
      style={{ display: "flex", flexDirection: "column", gap: "12px", maxWidth: "500px" }}
    >
      <label>
        靶点名称 *
        <input
          type="text"
          value={target}
          onChange={(e) => setTarget(e.target.value)}
          placeholder="例如 GLP-1R、TL1A、PCSK9"
          required
          style={{ display: "block", width: "100%", padding: "8px", marginTop: "4px" }}
        />
      </label>
      <label>
        适应症（可选）
        <input
          type="text"
          value={indication}
          onChange={(e) => setIndication(e.target.value)}
          placeholder="例如 肥胖症、炎症性肠病、高胆固醇血症"
          style={{ display: "block", width: "100%", padding: "8px", marginTop: "4px" }}
        />
      </label>
      <label>
        同义词 / 别名（可选）
        <input
          type="text"
          value={synonyms}
          onChange={(e) => setSynonyms(e.target.value)}
          placeholder="例如 GLP1R、胰高血糖素样肽-1受体"
          style={{ display: "block", width: "100%", padding: "8px", marginTop: "4px" }}
        />
      </label>
      <label>
        研究重点（可选）
        <select
          value={focus}
          onChange={(e) => setFocus(e.target.value)}
          style={{ display: "block", width: "100%", padding: "8px", marginTop: "4px" }}
        >
          <option value="">全部领域</option>
          <option value="literature">文献 / 基础研究</option>
          <option value="clinical">临床信号</option>
          <option value="competition">竞争格局</option>
        </select>
      </label>
      <label>
        时间范围（可选）
        <select
          value={timeRange}
          onChange={(e) => setTimeRange(e.target.value)}
          style={{ display: "block", width: "100%", padding: "8px", marginTop: "4px" }}
        >
          <option value="">默认（5 年）</option>
          <option value="1095">近 3 年</option>
          <option value="1825">近 5 年</option>
          <option value="3650">近 10 年</option>
        </select>
      </label>

      {/* File Upload Area */}
      <div>
        <label style={{ display: "block", marginBottom: "4px" }}>上传私有文档（可选）</label>
        <div
          onDrop={handleDrop}
          onDragOver={(e) => e.preventDefault()}
          onClick={() => fileInputRef.current?.click()}
          style={{
            border: "2px dashed #d1d5db",
            borderRadius: "8px",
            padding: "20px",
            textAlign: "center",
            cursor: "pointer",
            background: "#f9fafb",
          }}
        >
          <div style={{ color: "#6b7280", fontSize: "0.9em" }}>
            拖拽文件到此处或点击上传
          </div>
          <div style={{ color: "#9ca3af", fontSize: "0.8em", marginTop: "4px" }}>
            支持 PDF / Word / TXT / Markdown，最多 {MAX_FILES} 个文件，单文件 ≤ {MAX_SIZE_MB}MB
          </div>
          <input
            ref={fileInputRef}
            type="file"
            accept={ACCEPTED_TYPES}
            multiple
            onChange={(e) => handleFiles(e.target.files)}
            style={{ display: "none" }}
          />
        </div>

        {/* File list */}
        {documents.length > 0 && (
          <div style={{ marginTop: "8px", display: "flex", flexDirection: "column", gap: "4px" }}>
            {documents.map((doc, i) => (
              <div
                key={doc.id || `uploading-${i}`}
                style={{
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-between",
                  padding: "6px 10px",
                  background: doc.status === "failed" ? "#fef2f2" : "#f0fdf4",
                  borderRadius: "4px",
                  fontSize: "0.85em",
                }}
              >
                <span>
                  {doc.status === "ready" && "✓ "}
                  {doc.status === "uploading" && "⏳ "}
                  {doc.status === "failed" && "✗ "}
                  {doc.file_name}
                  <span style={{ color: "#9ca3af", marginLeft: "8px" }}>
                    ({(doc.file_size / 1024 / 1024).toFixed(1)}MB)
                  </span>
                  {doc.status === "uploading" && <span style={{ color: "#6b7280", marginLeft: "8px" }}>上传解析中...</span>}
                  {doc.status === "failed" && <span style={{ color: "#dc2626", marginLeft: "8px" }}>{doc.error || "失败"}</span>}
                </span>
                {doc.status !== "uploading" && (
                  <button
                    type="button"
                    onClick={(e) => { e.stopPropagation(); handleRemove(doc.id); }}
                    style={{ background: "none", border: "none", cursor: "pointer", color: "#9ca3af", fontSize: "1em" }}
                  >
                    ✕
                  </button>
                )}
              </div>
            ))}
          </div>
        )}
      </div>

      <button type="submit" disabled={loading || uploading || !target.trim()} style={{ padding: "10px 20px" }}>
        {loading ? "解析中..." : "开始评估"}
      </button>
    </form>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/SearchForm.tsx
git commit -m "feat: add file upload drop zone to SearchForm"
```

---

## Task 11: ConfirmationPanel — Documents, Suggestions, Cancel

**Files:**
- Modify: `frontend/src/components/ConfirmationPanel.tsx`

- [ ] **Step 1: Update ConfirmationPanel**

Replace the entire `frontend/src/components/ConfirmationPanel.tsx` with:

```tsx
import { useState } from "react";
import type { ParseResult, ParsedInput, SubTask, UploadedDocument } from "../types";
import { HistoricalContext } from "./HistoricalContext";

interface Props {
  parseResult: ParseResult;
  documents: UploadedDocument[];
  onConfirm: (modified: ParsedInput) => void;
  onBack: () => void;
  onCancel: () => void;
  onRemoveDocument: (docId: string) => void;
  loading: boolean;
}

export function ConfirmationPanel({ parseResult, documents, onConfirm, onBack, onCancel, onRemoveDocument, loading }: Props) {
  const [target, setTarget] = useState(parseResult.parsed.target);
  const [indication, setIndication] = useState(parseResult.parsed.indication);
  const [synonyms, setSynonyms] = useState(parseResult.parsed.synonyms);
  const [focus, setFocus] = useState(parseResult.parsed.focus);
  const [timeRange, setTimeRange] = useState(parseResult.parsed.time_range);
  const [userSuggestions, setUserSuggestions] = useState("");

  const handleConfirm = () => {
    onConfirm({
      target,
      indication,
      synonyms,
      focus,
      time_range: timeRange,
      document_ids: documents.filter((d) => d.status === "ready").map((d) => d.id),
      user_suggestions: userSuggestions,
    });
  };

  const inputStyle = {
    display: "block" as const,
    width: "100%",
    padding: "8px",
    marginTop: "4px",
    border: "1px solid #d1d5db",
    borderRadius: "4px",
  };

  return (
    <div>
      <h2 style={{ marginBottom: "8px" }}>确认查询参数</h2>
      <p style={{ color: "#666", marginBottom: "16px" }}>
        请审核解析结果和任务规划，可修改任意字段后运行。
      </p>

      {/* Editable parsed input */}
      <div
        style={{
          background: "#f9fafb",
          border: "1px solid #e5e7eb",
          borderRadius: "8px",
          padding: "16px",
          marginBottom: "16px",
        }}
      >
        <h3 style={{ margin: "0 0 12px", fontSize: "1em" }}>解析结果</h3>
        <div style={{ display: "flex", flexDirection: "column", gap: "10px", maxWidth: "500px" }}>
          <label>
            靶点名称 *
            <input type="text" value={target} onChange={(e) => setTarget(e.target.value)} style={inputStyle} />
          </label>
          <label>
            适应症
            <input type="text" value={indication} onChange={(e) => setIndication(e.target.value)} style={inputStyle} />
          </label>
          <label>
            同义词 / 别名
            <input type="text" value={synonyms} onChange={(e) => setSynonyms(e.target.value)} style={inputStyle} />
          </label>
          <label>
            研究重点
            <select value={focus} onChange={(e) => setFocus(e.target.value)} style={inputStyle}>
              <option value="">全部领域</option>
              <option value="literature">文献 / 基础研究</option>
              <option value="clinical">临床信号</option>
              <option value="competition">竞争格局</option>
            </select>
          </label>
          <label>
            时间范围
            <select value={timeRange} onChange={(e) => setTimeRange(e.target.value)} style={inputStyle}>
              <option value="">默认（5 年）</option>
              <option value="1095">近 3 年</option>
              <option value="1825">近 5 年</option>
              <option value="3650">近 10 年</option>
            </select>
          </label>
        </div>
      </div>

      {/* Uploaded Documents */}
      {documents.length > 0 && (
        <div
          style={{
            background: "#eff6ff",
            border: "1px solid #bfdbfe",
            borderRadius: "8px",
            padding: "16px",
            marginBottom: "16px",
          }}
        >
          <h3 style={{ margin: "0 0 12px", fontSize: "1em" }}>已上传文档</h3>
          {documents.map((doc) => (
            <div
              key={doc.id}
              style={{
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                padding: "8px 12px",
                background: "#fff",
                borderRadius: "4px",
                marginBottom: "6px",
                fontSize: "0.9em",
              }}
            >
              <span>
                {doc.status === "ready" ? "✓" : doc.status === "failed" ? "✗" : "⏳"}{" "}
                {doc.file_name}
                <span style={{ color: "#9ca3af", marginLeft: "8px" }}>
                  ({(doc.file_size / 1024 / 1024).toFixed(1)}MB)
                </span>
              </span>
              <button
                type="button"
                onClick={() => onRemoveDocument(doc.id)}
                disabled={loading}
                style={{ background: "none", border: "none", cursor: "pointer", color: "#9ca3af" }}
              >
                ✕
              </button>
            </div>
          ))}
        </div>
      )}

      {/* Sub-tasks plan */}
      <div
        style={{
          background: "#f0fdf4",
          border: "1px solid #86efac",
          borderRadius: "8px",
          padding: "16px",
          marginBottom: "16px",
        }}
      >
        <h3 style={{ margin: "0 0 12px", fontSize: "1em" }}>计划执行的子任务</h3>
        {parseResult.sub_tasks.map((task: SubTask, i: number) => (
          <div
            key={i}
            style={{
              background: "#fff",
              border: "1px solid #d1fae5",
              borderRadius: "6px",
              padding: "10px 14px",
              marginBottom: "8px",
            }}
          >
            <strong>{task.agent}</strong>
            <p style={{ margin: "4px 0", fontSize: "0.9em", color: "#555" }}>{task.description}</p>
            <div style={{ display: "flex", gap: "4px", flexWrap: "wrap" }}>
              {task.tools.map((tool, j) => (
                <span
                  key={j}
                  style={{
                    padding: "2px 8px",
                    background: "#e0f2fe",
                    borderRadius: "4px",
                    fontSize: "0.75em",
                    color: "#0369a1",
                  }}
                >
                  {tool}
                </span>
              ))}
              {task.tools.length === 0 && (
                <span style={{ fontSize: "0.75em", color: "#888" }}>无外部工具（仅 LLM 推理）</span>
              )}
            </div>
          </div>
        ))}
      </div>

      {/* Historical context */}
      <HistoricalContext reports={parseResult.knowledge_base_context?.historical_reports || []} />

      {/* User suggestions */}
      <div
        style={{
          background: "#fefce8",
          border: "1px solid #fde68a",
          borderRadius: "8px",
          padding: "16px",
          marginBottom: "16px",
          marginTop: "16px",
        }}
      >
        <h3 style={{ margin: "0 0 8px", fontSize: "1em" }}>其他建议（可选）</h3>
        <p style={{ color: "#666", fontSize: "0.85em", margin: "0 0 8px" }}>
          您可以在此输入专业见解或补充信息，这些内容将作为分析的重要参考。
        </p>
        <textarea
          value={userSuggestions}
          onChange={(e) => setUserSuggestions(e.target.value)}
          placeholder="例如：请关注该靶点在耐药性方面的最新进展，特别是T790M突变..."
          rows={4}
          style={{
            ...inputStyle,
            resize: "vertical",
          }}
        />
      </div>

      {/* Action buttons: [确认并运行] [返回修改] [取消] */}
      <div style={{ display: "flex", gap: "8px", marginTop: "16px" }}>
        <button
          onClick={handleConfirm}
          disabled={loading || !target.trim()}
          style={{
            padding: "10px 24px",
            background: "#2563eb",
            color: "#fff",
            border: "none",
            borderRadius: "6px",
            cursor: loading ? "not-allowed" : "pointer",
            fontWeight: 600,
          }}
        >
          {loading ? "分析运行中..." : "确认并运行"}
        </button>
        <button
          onClick={onBack}
          disabled={loading}
          style={{
            padding: "10px 24px",
            background: "#fff",
            border: "1px solid #d1d5db",
            borderRadius: "6px",
            cursor: "pointer",
          }}
        >
          返回修改
        </button>
        <button
          onClick={onCancel}
          disabled={loading}
          style={{
            padding: "10px 24px",
            background: "#fff",
            border: "1px solid #d1d5db",
            borderRadius: "6px",
            cursor: "pointer",
            color: "#dc2626",
          }}
        >
          取消
        </button>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/ConfirmationPanel.tsx
git commit -m "feat: add uploaded docs, user suggestions textarea, and cancel button to ConfirmationPanel"
```

---

## Task 12: SearchPage — Source Type Badge

**Files:**
- Modify: `frontend/src/components/SearchPage.tsx`

- [ ] **Step 1: Add source_type badge to search results**

In `frontend/src/components/SearchPage.tsx`, add a source type label in the result cards. Replace the result mapping section (lines 74-98) with:

```tsx
      {results.map((item) => (
        <div
          key={item.id}
          className="card card-clickable"
          onClick={() => item.source_type !== "private_document" ? onViewReport(item.id, item.target) : undefined}
          style={{ cursor: item.source_type === "private_document" ? "default" : "pointer" }}
        >
          <div className="report-card">
            <div className="report-card__body">
              <div className="report-card__title" style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                {item.source_type === "private_document" ? (item as any).file_name || "私有文档" : (
                  <>{item.target}{item.indication ? ` - ${item.indication}` : ""}</>
                )}
                <span
                  style={{
                    padding: "2px 8px",
                    borderRadius: "4px",
                    fontSize: "0.7em",
                    fontWeight: 500,
                    background: item.source_type === "private_document" ? "#dbeafe" : "#f0fdf4",
                    color: item.source_type === "private_document" ? "#1d4ed8" : "#166534",
                  }}
                >
                  {item.source_type === "private_document" ? "私有文档" : "历史报告"}
                </span>
              </div>
              <div className="report-card__summary">{item.summary || "暂无摘要"}</div>
              <div className="report-card__meta">
                {item.created_at ? new Date(item.created_at).toLocaleDateString("zh-CN") : ""}
                {item.score != null ? ` | 相关度: ${item.score.toFixed(2)}` : ""}
              </div>
            </div>
            {item.recommendation && (
              <span className={badgeClass(item.recommendation)}>
                {badgeLabel(item.recommendation)}
              </span>
            )}
          </div>
        </div>
      ))}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/SearchPage.tsx
git commit -m "feat: add source type badge (历史报告/私有文档) to search results"
```

---

## Task 13: App.tsx — Wire Up Document State

**Files:**
- Modify: `frontend/src/App.tsx`

- [ ] **Step 1: Update App.tsx**

In `frontend/src/App.tsx`, make the following changes:

Add import for `UploadedDocument` type and `deleteDocument`:

```typescript
import type {
  AssessmentResult,
  ParseResult,
  ParsedInput,
  Page,
  AssessStep,
  PartialResultData,
  UploadedDocument,
} from "./types";
```

Add `deleteDocument` to the api import:

```typescript
import {
  parseAssessment,
  confirmAssessmentSSE,
  exportMarkdown,
  exportWord,
  exportPdf,
  fetchReport,
  deleteDocument,
} from "./api";
```

Add documents state after the existing state declarations (around line 38):

```typescript
  const [uploadedDocuments, setUploadedDocuments] = useState<UploadedDocument[]>([]);
```

Update `handleReset` to clear documents:

```typescript
  const handleReset = () => {
    setPage("assess");
    setAssessStep("input");
    setResult(null);
    setParseResult(null);
    setError("");
    setAgentProgress({});
    setPartialResults({});
    setUploadedDocuments([]);
  };
```

Update `handleSubmit` to accept documents:

```typescript
  const handleSubmit = async (
    target: string,
    indication: string,
    synonyms: string,
    focus: string,
    timeRange: string,
    documents: UploadedDocument[],
  ) => {
    setLoading(true);
    setError("");
    setResult(null);
    setParseResult(null);
    setUploadedDocuments(documents);
    try {
      const data = await parseAssessment(target, indication, synonyms, focus, timeRange);
      setParseResult(data);
      setAssessStep("confirm");
    } catch (e: any) {
      setError(e.message || "解析失败");
    } finally {
      setLoading(false);
    }
  };
```

Add `handleCancel` function (after `handleBack`):

```typescript
  const handleCancel = () => {
    handleReset();
  };
```

Add `handleRemoveDocument`:

```typescript
  const handleRemoveDocument = async (docId: string) => {
    try {
      await deleteDocument(docId);
    } catch {
      // Best effort
    }
    setUploadedDocuments((prev) => prev.filter((d) => d.id !== docId));
  };
```

Update the ConfirmationPanel usage in JSX (around line 187):

```tsx
            <ConfirmationPanel
              parseResult={parseResult}
              documents={uploadedDocuments}
              onConfirm={handleConfirm}
              onBack={handleBack}
              onCancel={handleCancel}
              onRemoveDocument={handleRemoveDocument}
              loading={loading}
            />
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/App.tsx
git commit -m "feat: wire up document upload state and cancel handler in App.tsx"
```

---

## Task 14: Verify and Final Commit

- [ ] **Step 1: Verify backend syntax**

Run: `cd backend && python -c "from app.config import settings; from app.documents.parser import validate_file; from app.documents.chunker import chunk_text; print('OK')"`

Expected: `OK`

- [ ] **Step 2: Verify frontend builds**

Run: `cd frontend && npx tsc --noEmit`

Expected: No errors (or only pre-existing ones)

- [ ] **Step 3: Run existing tests**

Run: `cd backend && python -m pytest tests/ -v --timeout=30`

Expected: Existing tests pass (new features don't break old tests)

- [ ] **Step 4: Final commit if any fixes were needed**

```bash
git add -A
git commit -m "fix: address any build or test issues from document upload feature"
```
