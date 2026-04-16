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


class BlobDocumentStorage:
    """Blob storage for private uploaded documents."""

    _instance: "BlobDocumentStorage | None" = None

    def __new__(cls) -> "BlobDocumentStorage":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
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
        self._initialized = True

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

    def download_document(self, document_id: str, filename: str) -> bytes:
        """Download a document's raw content from blob storage."""
        from pathlib import Path
        ext = Path(filename).suffix.lower()
        blob_name = f"{document_id}{ext}"
        blob_client = self.container.get_blob_client(blob_name)
        return blob_client.download_blob().readall()

    def delete_document(self, document_id: str, filename: str):
        """Delete a document file from blob storage."""
        from pathlib import Path
        ext = Path(filename).suffix.lower()
        blob_name = f"{document_id}{ext}"
        blob_client = self.container.get_blob_client(blob_name)
        blob_client.delete_blob(delete_snapshots="include")
