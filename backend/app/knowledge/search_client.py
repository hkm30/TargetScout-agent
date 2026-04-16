import asyncio
import logging

from azure.core.credentials import AzureKeyCredential
from azure.search.documents import SearchClient
from azure.search.documents.indexes import SearchIndexClient
from azure.search.documents.indexes.models import (
    SearchIndex,
    SearchField,
    SearchFieldDataType,
    SimpleField,
    SearchableField,
    VectorSearch,
    HnswAlgorithmConfiguration,
    VectorSearchProfile,
    SearchFieldDataType as DT,
)
from azure.search.documents.models import VectorizedQuery

logger = logging.getLogger(__name__)

from app.config import settings
from app.knowledge.embedding import generate_embedding

def _build_index_fields() -> list:
    """Build index fields lazily so embedding dimensions are read from config at call time."""
    return [
        SimpleField(name="id", type=DT.String, key=True, filterable=True),
        SimpleField(name="target", type=DT.String, filterable=True, sortable=True),
        SimpleField(name="indication", type=DT.String, filterable=True),
        SimpleField(name="recommendation", type=DT.String, filterable=True),
        SearchableField(name="summary_text", type=DT.String),
        SearchableField(name="literature_summary", type=DT.String),
        SearchableField(name="clinical_summary", type=DT.String),
        SearchableField(name="competition_summary", type=DT.String),
        SearchableField(name="citations", type=DT.String),
        SimpleField(name="created_at", type=DT.DateTimeOffset, filterable=True, sortable=True),
        SearchField(
            name="summary_vector",
            type=SearchFieldDataType.Collection(SearchFieldDataType.Single),
            searchable=True,
            vector_search_dimensions=settings.EMBEDDING_DIMENSIONS,
            vector_search_profile_name="default-profile",
        ),
    ]


def get_index_client() -> SearchIndexClient:
    return SearchIndexClient(
        endpoint=settings.SEARCH_ENDPOINT,
        credential=AzureKeyCredential(settings.SEARCH_API_KEY),
    )


def get_search_client() -> SearchClient:
    return SearchClient(
        endpoint=settings.SEARCH_ENDPOINT,
        index_name=settings.SEARCH_INDEX_NAME,
        credential=AzureKeyCredential(settings.SEARCH_API_KEY),
    )


def ensure_index():
    """Create or update the search index. Non-fatal on failure — index may already exist."""
    try:
        index_client = get_index_client()
        vector_search = VectorSearch(
            algorithms=[HnswAlgorithmConfiguration(name="default-algo")],
            profiles=[VectorSearchProfile(name="default-profile", algorithm_configuration_name="default-algo")],
        )
        index = SearchIndex(
            name=settings.SEARCH_INDEX_NAME,
            fields=_build_index_fields(),
            vector_search=vector_search,
        )
        index_client.create_or_update_index(index)
    except Exception as e:
        logger.warning("Failed to create/update search index (may already exist): %s", e)


async def index_report(report: dict):
    """Generate embedding and upload document to AI Search."""
    summary_text = (
        f"{report.get('literature_summary', '')} "
        f"{report.get('clinical_trials_summary', '')} "
        f"{report.get('competition_summary', '')}"
    )
    vector = await generate_embedding(summary_text)

    # Serialize citations as searchable text
    citations = report.get("citations", [])
    citations_text = " | ".join(
        (f"{c.get('title', '')} ({c.get('source_type', '')}) {c.get('link', '')}" if isinstance(c, dict) else str(c))
        for c in citations
    ) if citations else ""

    doc = {
        "id": report["id"],
        "target": report.get("target", ""),
        "indication": report.get("indication", ""),
        "recommendation": report.get("recommendation", ""),
        "summary_text": summary_text,
        "literature_summary": report.get("literature_summary", ""),
        "clinical_summary": report.get("clinical_trials_summary", ""),
        "competition_summary": report.get("competition_summary", ""),
        "citations": citations_text,
        "created_at": report.get("created_at", ""),
        "summary_vector": vector,
    }
    client = get_search_client()
    await asyncio.to_thread(client.upload_documents, [doc])


async def search_reports(query: str, target: str | None = None, top_k: int = 5) -> list[dict]:
    """Hybrid search: vector similarity + keyword matching. Returns empty list on failure."""
    try:
        vector = await generate_embedding(query)
        vector_query = VectorizedQuery(vector=vector, k_nearest_neighbors=top_k, fields="summary_vector")

        filter_expr = None
        if target:
            sanitized = target.replace("'", "''")
            filter_expr = f"target eq '{sanitized}'"

        client = get_search_client()
        results = await asyncio.to_thread(
            client.search,
            search_text=query,
            vector_queries=[vector_query],
            filter=filter_expr,
            top=top_k,
        )

        return [
            {
                "id": r.get("id", ""),
                "target": r.get("target", ""),
                "indication": r.get("indication", ""),
                "recommendation": r.get("recommendation", ""),
                "summary": (r.get("summary_text") or "")[:500],
                "created_at": r.get("created_at", ""),
                "score": r.get("@search.score", 0),
            }
            for r in results
        ]
    except Exception as e:
        logger.error("Search reports failed: %s", e, exc_info=True)
        return []


async def delete_report(report_id: str):
    """Delete a document from AI Search index."""
    client = get_search_client()
    await asyncio.to_thread(
        client.delete_documents, documents=[{"id": report_id}]
    )


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
            "source_type": chunk.get("source_type", "private_document"),
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
    sanitized_id = document_id.replace("'", "''")
    results = await asyncio.to_thread(
        client.search,
        search_text="*",
        filter=f"document_id eq '{sanitized_id}'",
        top=1000,
        select=["id"],
    )
    chunk_ids = [{"id": r["id"]} for r in results]
    logger.info("delete_document_chunks: document_id=%s, found %d chunks: %s",
                document_id, len(chunk_ids), [c["id"] for c in chunk_ids[:10]])
    if chunk_ids:
        await asyncio.to_thread(client.delete_documents, chunk_ids)
        logger.info("delete_document_chunks: deleted %d chunks for %s", len(chunk_ids), document_id)


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
