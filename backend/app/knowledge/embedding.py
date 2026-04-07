import asyncio

from openai import AzureOpenAI
from azure.identity import DefaultAzureCredential, get_bearer_token_provider

from app.config import settings

_embedding_client: AzureOpenAI | None = None


def _get_embedding_client() -> AzureOpenAI:
    """Get an AzureOpenAI client for embeddings, pointing directly at the AIServices endpoint."""
    global _embedding_client
    if _embedding_client is None:
        # Extract base AIServices URL from PROJECT_ENDPOINT
        # PROJECT_ENDPOINT looks like: https://<name>.services.ai.azure.com/api/projects/<project>
        # We need: https://<name>.services.ai.azure.com
        endpoint = settings.PROJECT_ENDPOINT
        # Strip /api/projects/... suffix to get the AIServices base URL
        if "/api/projects/" in endpoint:
            base_url = endpoint.split("/api/projects/")[0]
        else:
            base_url = endpoint.rstrip("/")

        token_provider = get_bearer_token_provider(
            DefaultAzureCredential(),
            "https://cognitiveservices.azure.com/.default",
        )
        _embedding_client = AzureOpenAI(
            azure_endpoint=base_url,
            azure_ad_token_provider=token_provider,
            api_version="2024-06-01",
        )
    return _embedding_client


async def generate_embedding(text: str) -> list[float]:
    """Generate embedding vector for text using the AIServices embedding deployment."""
    client = _get_embedding_client()
    response = await asyncio.to_thread(
        client.embeddings.create,
        model=settings.EMBEDDING_DEPLOYMENT,
        input=[text],
    )
    return list(response.data[0].embedding)
