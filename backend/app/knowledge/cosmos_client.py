import asyncio

from azure.cosmos import CosmosClient, PartitionKey
from azure.cosmos.container import ContainerProxy
from azure.identity import DefaultAzureCredential

from app.config import settings


class CosmosDocumentStore:
    """Cosmos DB store for private document metadata (replaces in-memory dict)."""

    def __init__(self):
        client = CosmosClient(settings.COSMOS_ENDPOINT, credential=DefaultAzureCredential())
        database = client.get_database_client(settings.COSMOS_DATABASE)
        self.container: ContainerProxy = database.get_container_client(
            settings.COSMOS_DOCUMENTS_CONTAINER
        )

    async def save_document(self, doc_meta: dict) -> dict:
        """Upsert a document metadata record."""
        return await asyncio.to_thread(self.container.upsert_item, doc_meta)

    async def get_document(self, document_id: str) -> dict | None:
        """Get a document by ID, or None if not found."""
        try:
            return await asyncio.to_thread(
                self.container.read_item, item=document_id, partition_key=document_id
            )
        except Exception:
            return None

    async def delete_document(self, document_id: str):
        """Delete a document by ID."""
        await asyncio.to_thread(
            self.container.delete_item, item=document_id, partition_key=document_id
        )

    async def find_by_content_hash(self, content_hash: str) -> dict | None:
        """Find a document by its SHA-256 content hash. Returns None if not found."""
        query = "SELECT * FROM c WHERE c.content_hash = @hash"
        parameters = [{"name": "@hash", "value": content_hash}]
        items = await asyncio.to_thread(
            lambda: list(self.container.query_items(
                query=query,
                parameters=parameters,
                enable_cross_partition_query=True,
                max_item_count=1,
            ))
        )
        return items[0] if items else None

    async def get_documents_by_ids(self, document_ids: list[str]) -> list[dict]:
        """Fetch multiple documents by ID. Missing documents are silently skipped."""
        docs = []
        for did in document_ids:
            doc = await self.get_document(did)
            if doc:
                docs.append(doc)
        return docs


_cosmos_docs: CosmosDocumentStore | None = None


def _get_cosmos_docs() -> CosmosDocumentStore:
    """Get or create the CosmosDocumentStore singleton."""
    global _cosmos_docs
    if _cosmos_docs is None:
        _cosmos_docs = CosmosDocumentStore()
    return _cosmos_docs


class CosmosReportStore:
    def __init__(self):
        # Use AAD auth (DefaultAzureCredential) — Cosmos DB has local key auth disabled
        client = CosmosClient(settings.COSMOS_ENDPOINT, credential=DefaultAzureCredential())
        database = client.get_database_client(settings.COSMOS_DATABASE)
        self.container: ContainerProxy = database.get_container_client(settings.COSMOS_CONTAINER)

    async def save_report(self, report: dict) -> dict:
        """Upsert a report document."""
        return await asyncio.to_thread(self.container.upsert_item, report)

    def query_by_target(self, target: str, max_results: int = 10):
        """Query reports by target name."""
        query = "SELECT * FROM c WHERE c.target = @target ORDER BY c.created_at DESC"
        parameters = [{"name": "@target", "value": target}]
        return self.container.query_items(
            query=query, parameters=parameters, max_item_count=max_results
        )

    def get_report(self, report_id: str, target: str) -> dict:
        """Get a specific report by ID."""
        return self.container.read_item(item=report_id, partition_key=target)

    def list_all_reports(self, max_results: int = 100) -> list[dict]:
        """List all reports, newest first."""
        query = "SELECT c.id, c.target, c.indication, c.status, c.created_at, c.orchestrator_output FROM c ORDER BY c.created_at DESC"
        return list(self.container.query_items(
            query=query, max_item_count=max_results, enable_cross_partition_query=True,
        ))

    def delete_report(self, report_id: str, target: str):
        """Delete a report by ID."""
        self.container.delete_item(item=report_id, partition_key=target)
