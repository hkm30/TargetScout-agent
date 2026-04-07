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
        raise


async def delete_report(report_id: str):
    """Delete a document from AI Search index."""
    client = get_search_client()
    await asyncio.to_thread(
        client.delete_documents, documents=[{"id": report_id}]
    )
