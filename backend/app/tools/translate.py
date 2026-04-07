"""Translate non-English search queries to English using the LLM."""

import asyncio
import logging
import re

from openai import AzureOpenAI
from azure.identity import DefaultAzureCredential, get_bearer_token_provider

from app.config import settings

logger = logging.getLogger(__name__)

_translate_client: AzureOpenAI | None = None


def _get_client() -> AzureOpenAI:
    global _translate_client
    if _translate_client is None:
        endpoint = settings.PROJECT_ENDPOINT
        if "/api/projects/" in endpoint:
            base_url = endpoint.split("/api/projects/")[0]
        else:
            base_url = endpoint.rstrip("/")
        token_provider = get_bearer_token_provider(
            DefaultAzureCredential(),
            "https://cognitiveservices.azure.com/.default",
        )
        _translate_client = AzureOpenAI(
            azure_endpoint=base_url,
            azure_ad_token_provider=token_provider,
            api_version="2024-06-01",
        )
    return _translate_client


def _has_non_ascii(text: str) -> bool:
    return bool(re.search(r"[^\x00-\x7F]", text))


async def ensure_english(query: str) -> str:
    """If query contains non-ASCII characters (Chinese, etc.), translate to English.

    Returns the original query if it's already pure ASCII.
    """
    if not _has_non_ascii(query):
        return query

    try:
        client = _get_client()
        resp = await asyncio.to_thread(
            client.chat.completions.create,
            model=settings.MODEL_DEPLOYMENT,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a biomedical translator. Translate the following search query to English. "
                        "Keep gene names, drug names, protein names, and technical terms in their standard English form. "
                        "Output ONLY the translated query, nothing else."
                    ),
                },
                {"role": "user", "content": query},
            ],
            temperature=0,
            max_tokens=200,
        )
        translated = resp.choices[0].message.content.strip()
        logger.info("Translated query: '%s' -> '%s'", query, translated)
        return translated
    except Exception as e:
        logger.warning("Translation failed, stripping non-ASCII: %s", e)
        # Fallback: strip non-ASCII characters
        return re.sub(r"[^\x00-\x7F]+", " ", query).strip()
