import os

from dotenv import load_dotenv

load_dotenv()


class Settings:
    # AI Foundry Project endpoint (e.g. https://<hub>.services.ai.azure.com/api/projects/<project>)
    PROJECT_ENDPOINT: str = os.environ.get("AZURE_AI_PROJECT_ENDPOINT", os.environ.get("PROJECT_ENDPOINT", ""))
    MODEL_DEPLOYMENT: str = os.environ.get("AZURE_AI_MODEL_DEPLOYMENT", os.environ.get("MODEL_DEPLOYMENT", "gpt-54"))
    EMBEDDING_DEPLOYMENT: str = os.environ.get("AZURE_AI_EMBEDDING_DEPLOYMENT", os.environ.get("EMBEDDING_DEPLOYMENT", "text-embedding-3-small"))

    # API key for endpoint protection (empty = no auth, for dev only)
    API_KEY: str = os.environ.get("API_KEY", "")

    # Embedding dimension mapping
    _EMBEDDING_DIMS: dict[str, int] = {
        "text-embedding-3-small": 1536,
        "text-embedding-3-large": 3072,
        "text-embedding-ada-002": 1536,
    }

    # Azure AI Search
    SEARCH_ENDPOINT: str = os.environ.get("AZURE_SEARCH_ENDPOINT", os.environ.get("SEARCH_ENDPOINT", ""))
    SEARCH_API_KEY: str = os.environ.get("AZURE_SEARCH_API_KEY", os.environ.get("SEARCH_API_KEY", ""))
    SEARCH_INDEX_NAME: str = os.environ.get("AZURE_SEARCH_INDEX_NAME", os.environ.get("SEARCH_INDEX_NAME", "drug-target-evidence"))

    # Cosmos DB — uses DefaultAzureCredential (key auth disabled)
    # Extract endpoint from connection string if COSMOS_ENDPOINT not set directly
    COSMOS_CONNECTION_STRING: str = os.environ.get("COSMOS_CONNECTION_STRING", "")
    COSMOS_ENDPOINT: str = os.environ.get("COSMOS_ENDPOINT", "")
    COSMOS_DATABASE: str = os.environ.get("COSMOS_DATABASE_NAME", os.environ.get("COSMOS_DATABASE", "drugtargetdb"))
    COSMOS_CONTAINER: str = os.environ.get("COSMOS_RESULTS_CONTAINER_NAME", os.environ.get("COSMOS_CONTAINER", "reports"))

    # MCP Server URLs
    GOOGLE_SCHOLAR_MCP_URL: str = os.environ.get("GOOGLE_SCHOLAR_MCP_URL", "")

    # Application Insights
    APPLICATIONINSIGHTS_CONNECTION_STRING: str = os.environ.get("APPLICATIONINSIGHTS_CONNECTION_STRING", "")

    # Blob Storage — uses DefaultAzureCredential (key auth disabled)
    STORAGE_ACCOUNT_NAME: str = os.environ.get("STORAGE_ACCOUNT_NAME", "")
    BLOB_REPORTS_CONTAINER: str = os.environ.get("BLOB_REPORTS_CONTAINER", "reports")
    BLOB_SNAPSHOTS_CONTAINER: str = os.environ.get("BLOB_SNAPSHOTS_CONTAINER", "raw-search-snapshots")

    # Azure Document Intelligence
    DOC_INTELLIGENCE_ENDPOINT: str = os.environ.get("AZURE_DOC_INTELLIGENCE_ENDPOINT", "")
    DOC_INTELLIGENCE_KEY: str = os.environ.get("AZURE_DOC_INTELLIGENCE_KEY", "")

    # Private documents
    BLOB_DOCUMENTS_CONTAINER: str = os.environ.get("BLOB_DOCUMENTS_CONTAINER", "private-documents")
    SEARCH_DOCUMENTS_INDEX_NAME: str = os.environ.get("AZURE_SEARCH_DOCUMENTS_INDEX_NAME", "drug-target-documents")
    DOC_MAX_FILE_SIZE_MB: int = int(os.environ.get("DOC_MAX_FILE_SIZE_MB", "10"))
    DOC_MAX_FILE_COUNT: int = int(os.environ.get("DOC_MAX_FILE_COUNT", "5"))

    @property
    def EMBEDDING_DIMENSIONS(self) -> int:
        override = int(os.environ.get("EMBEDDING_DIMENSIONS", "0"))
        if override:
            return override
        return self._EMBEDDING_DIMS.get(self.EMBEDDING_DEPLOYMENT, 1536)

    def __init__(self):
        # Derive Cosmos endpoint from connection string if not set directly
        if not self.COSMOS_ENDPOINT and self.COSMOS_CONNECTION_STRING:
            import re
            m = re.search(r"AccountEndpoint=(https://[^;]+)", self.COSMOS_CONNECTION_STRING)
            if m:
                self.COSMOS_ENDPOINT = m.group(1)

        # Derive Blob account URL from STORAGE_ACCOUNT_NAME
        if self.STORAGE_ACCOUNT_NAME:
            self.BLOB_ACCOUNT_URL = f"https://{self.STORAGE_ACCOUNT_NAME}.blob.core.windows.net"
        else:
            self.BLOB_ACCOUNT_URL = ""


settings = Settings()
