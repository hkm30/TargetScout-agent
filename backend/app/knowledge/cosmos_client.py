import asyncio

from azure.cosmos import CosmosClient, PartitionKey
from azure.cosmos.container import ContainerProxy
from azure.identity import DefaultAzureCredential

from app.config import settings


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
