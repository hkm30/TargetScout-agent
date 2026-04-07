import json

from azure.storage.blob import BlobServiceClient, ContentSettings
from azure.identity import DefaultAzureCredential

from app.config import settings


class BlobReportStorage:
    def __init__(self):
        # Use AAD auth — storage account has key-based auth disabled
        account_url = settings.BLOB_ACCOUNT_URL
        if not account_url:
            raise ValueError("STORAGE_ACCOUNT_NAME must be set for blob storage")
        self.service = BlobServiceClient(account_url=account_url, credential=DefaultAzureCredential())
        self.reports_container = self.service.get_container_client(settings.BLOB_REPORTS_CONTAINER)
        self.snapshots_container = self.service.get_container_client(
            settings.BLOB_SNAPSHOTS_CONTAINER
        )

    def upload_report(self, report_id: str, content: bytes, content_type: str = "application/vnd.openxmlformats-officedocument.wordprocessingml.document") -> str:
        """Upload a report file (Word/PDF) and return its URL."""
        blob_name = f"{report_id}.docx"
        blob_client = self.reports_container.get_blob_client(blob_name)
        blob_client.upload_blob(
            content,
            overwrite=True,
            content_settings=ContentSettings(content_type=content_type),
        )
        return blob_client.url

    def upload_snapshot(self, report_id: str, raw_data: dict) -> str:
        """Upload raw API response snapshot as JSON."""
        blob_name = f"{report_id}_snapshot.json"
        blob_client = self.snapshots_container.get_blob_client(blob_name)
        blob_client.upload_blob(
            json.dumps(raw_data, ensure_ascii=False, indent=2),
            overwrite=True,
            content_settings=ContentSettings(content_type="application/json"),
        )
        return blob_client.url

    def delete_report(self, report_id: str):
        """Delete a report file from blob storage."""
        blob_name = f"{report_id}.docx"
        blob_client = self.reports_container.get_blob_client(blob_name)
        blob_client.delete_blob(delete_snapshots="include")

    def delete_snapshot(self, report_id: str):
        """Delete a snapshot file from blob storage."""
        blob_name = f"{report_id}_snapshot.json"
        blob_client = self.snapshots_container.get_blob_client(blob_name)
        blob_client.delete_blob(delete_snapshots="include")
