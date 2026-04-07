import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import httpx
from fastapi import FastAPI

from app.documents.router import router

# Create a minimal app with just the documents router for testing
_test_app = FastAPI()
_test_app.include_router(router)


def _mock_all_deps():
    """Return a dict of patches for all external dependencies."""
    return {
        "blob": patch("app.documents.router.BlobDocumentStorage"),
        "extract": patch("app.documents.router.extract_text", new_callable=AsyncMock),
        "summarize": patch("app.documents.router.generate_summaries", new_callable=AsyncMock),
        "index": patch("app.documents.router.index_document_chunks", new_callable=AsyncMock),
        "delete_chunks": patch("app.documents.router.delete_document_chunks", new_callable=AsyncMock),
        "cosmos": patch("app.documents.router._get_cosmos_docs"),
    }


def _make_cosmos_mock():
    """Create a mock CosmosDocumentStore with async methods."""
    mock = MagicMock()
    mock.save_document = AsyncMock()
    mock.get_document = AsyncMock(return_value=None)
    mock.delete_document = AsyncMock()
    mock.get_documents_by_ids = AsyncMock(return_value=[])
    return mock


@pytest.mark.asyncio
async def test_upload_success():
    patches = _mock_all_deps()
    with patches["blob"] as mock_blob_cls, \
         patches["extract"] as mock_extract, \
         patches["summarize"] as mock_summarize, \
         patches["index"] as mock_index, \
         patches["cosmos"] as mock_get_cosmos:
        mock_blob_instance = MagicMock()
        mock_blob_instance.upload_document.return_value = "https://blob.test/doc.txt"
        mock_blob_cls.return_value = mock_blob_instance

        mock_cosmos = _make_cosmos_mock()
        mock_get_cosmos.return_value = mock_cosmos

        mock_extract.return_value = {
            "text": "Hello world content.",
            "page_count": 1,
            "paragraphs": ["Hello world content."],
        }
        mock_summarize.return_value = {
            "abstract": "Detailed abstract.",
            "summary": "Brief summary.",
        }

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=_test_app),
            base_url="http://test",
        ) as client:
            resp = await client.post(
                "/api/documents/upload",
                files=[("files", ("notes.txt", b"Hello world content.", "text/plain"))],
            )

        assert resp.status_code == 200
        data = resp.json()
        assert len(data["documents"]) == 1
        doc = data["documents"][0]
        assert doc["status"] == "ready"
        assert doc["file_name"] == "notes.txt"
        assert "id" in doc
        assert doc["abstract"] == "Detailed abstract."
        assert doc["summary"] == "Brief summary."
        mock_index.assert_called_once()
        mock_cosmos.save_document.assert_called_once()


@pytest.mark.asyncio
async def test_upload_unsupported_format():
    patches = _mock_all_deps()
    with patches["blob"], patches["extract"], patches["summarize"], patches["index"], \
         patches["cosmos"]:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=_test_app),
            base_url="http://test",
        ) as client:
            resp = await client.post(
                "/api/documents/upload",
                files=[("files", ("virus.exe", b"malicious content", "application/octet-stream"))],
            )

        assert resp.status_code == 200
        data = resp.json()
        assert len(data["documents"]) == 1
        assert data["documents"][0]["status"] == "failed"
        assert "Unsupported" in data["documents"][0]["error"]


@pytest.mark.asyncio
async def test_upload_empty_file():
    patches = _mock_all_deps()
    with patches["blob"], patches["extract"], patches["summarize"], patches["index"], \
         patches["cosmos"]:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=_test_app),
            base_url="http://test",
        ) as client:
            resp = await client.post(
                "/api/documents/upload",
                files=[("files", ("empty.txt", b"", "text/plain"))],
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["documents"][0]["status"] == "failed"
        assert "empty" in data["documents"][0]["error"].lower()


@pytest.mark.asyncio
async def test_upload_too_many_files():
    patches = _mock_all_deps()
    with patches["blob"], patches["extract"], patches["summarize"], patches["index"], \
         patches["cosmos"]:
        files = [("files", (f"file{i}.txt", b"content", "text/plain")) for i in range(6)]
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=_test_app),
            base_url="http://test",
        ) as client:
            resp = await client.post("/api/documents/upload", files=files)

        assert resp.status_code == 400
        assert "Too many files" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_get_document_found():
    patches = _mock_all_deps()
    with patches["cosmos"] as mock_get_cosmos:
        mock_cosmos = _make_cosmos_mock()
        mock_cosmos.get_document.return_value = {
            "id": "test-doc-id",
            "file_name": "report.pdf",
            "file_size": 1024,
            "status": "ready",
        }
        mock_get_cosmos.return_value = mock_cosmos

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=_test_app),
            base_url="http://test",
        ) as client:
            resp = await client.get("/api/documents/test-doc-id")

        assert resp.status_code == 200
        assert resp.json()["id"] == "test-doc-id"
        assert resp.json()["file_name"] == "report.pdf"


@pytest.mark.asyncio
async def test_get_document_not_found():
    patches = _mock_all_deps()
    with patches["cosmos"] as mock_get_cosmos:
        mock_cosmos = _make_cosmos_mock()
        mock_get_cosmos.return_value = mock_cosmos

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=_test_app),
            base_url="http://test",
        ) as client:
            resp = await client.get("/api/documents/nonexistent-id")

        assert resp.status_code == 404


@pytest.mark.asyncio
async def test_delete_document():
    patches = _mock_all_deps()
    with patches["blob"] as mock_blob_cls, patches["delete_chunks"] as mock_delete, \
         patches["cosmos"] as mock_get_cosmos:
        mock_blob_instance = MagicMock()
        mock_blob_cls.return_value = mock_blob_instance

        mock_cosmos = _make_cosmos_mock()
        mock_cosmos.get_document.return_value = {
            "id": "del-doc-id",
            "file_name": "old.txt",
            "file_size": 512,
            "status": "ready",
        }
        mock_get_cosmos.return_value = mock_cosmos

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=_test_app),
            base_url="http://test",
        ) as client:
            resp = await client.delete("/api/documents/del-doc-id")

        assert resp.status_code == 200
        assert resp.json()["status"] == "deleted"
        mock_cosmos.delete_document.assert_called_once_with("del-doc-id")
        mock_delete.assert_called_once_with("del-doc-id")


@pytest.mark.asyncio
async def test_delete_document_not_found():
    patches = _mock_all_deps()
    with patches["cosmos"] as mock_get_cosmos:
        mock_cosmos = _make_cosmos_mock()
        mock_get_cosmos.return_value = mock_cosmos

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=_test_app),
            base_url="http://test",
        ) as client:
            resp = await client.delete("/api/documents/nonexistent-id")

        assert resp.status_code == 404


@pytest.mark.asyncio
async def test_upload_mixed_valid_and_invalid():
    """Upload a mix of valid and invalid files — valid ones should succeed."""
    patches = _mock_all_deps()
    with patches["blob"] as mock_blob_cls, \
         patches["extract"] as mock_extract, \
         patches["summarize"] as mock_summarize, \
         patches["index"], \
         patches["cosmos"] as mock_get_cosmos:
        mock_blob_instance = MagicMock()
        mock_blob_instance.upload_document.return_value = "https://blob.test/doc"
        mock_blob_cls.return_value = mock_blob_instance

        mock_cosmos = _make_cosmos_mock()
        mock_get_cosmos.return_value = mock_cosmos

        mock_extract.return_value = {
            "text": "content",
            "page_count": 1,
            "paragraphs": ["content"],
        }
        mock_summarize.return_value = {"abstract": "abs", "summary": "sum"}

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=_test_app),
            base_url="http://test",
        ) as client:
            resp = await client.post(
                "/api/documents/upload",
                files=[
                    ("files", ("good.txt", b"valid content", "text/plain")),
                    ("files", ("bad.exe", b"invalid", "application/octet-stream")),
                ],
            )

        assert resp.status_code == 200
        docs = resp.json()["documents"]
        assert len(docs) == 2
        statuses = {d["file_name"]: d["status"] for d in docs}
        assert statuses["good.txt"] == "ready"
        assert statuses["bad.exe"] == "failed"
