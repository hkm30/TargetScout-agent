import pytest
from unittest.mock import MagicMock, patch

from app.documents.parser import validate_file, extract_text


# --- validate_file tests ---

@pytest.mark.parametrize("filename", ["report.pdf", "study.docx", "notes.txt", "readme.md"])
def test_validate_file_supported_extensions(filename):
    assert validate_file(filename, 1024) is None


@pytest.mark.parametrize("filename", ["virus.exe", "photo.jpg", "data.csv", "archive.zip"])
def test_validate_file_unsupported_extension(filename):
    error = validate_file(filename, 1024)
    assert error is not None
    assert "Unsupported file type" in error


def test_validate_file_size_too_large():
    error = validate_file("report.pdf", 11 * 1024 * 1024)  # 11 MB
    assert error is not None
    assert "too large" in error.lower()


def test_validate_file_empty():
    error = validate_file("report.pdf", 0)
    assert error is not None
    assert "empty" in error.lower()


def test_validate_file_ok():
    assert validate_file("report.pdf", 5 * 1024 * 1024) is None


def test_validate_file_at_size_limit():
    """Exactly at limit should pass."""
    assert validate_file("report.pdf", 10 * 1024 * 1024) is None


# --- extract_text tests ---

@pytest.mark.asyncio
async def test_extract_text_txt():
    content = "First paragraph.\n\nSecond paragraph.\n\nThird paragraph.".encode("utf-8")
    result = await extract_text("notes.txt", content)
    assert "First paragraph." in result["text"]
    assert result["page_count"] == 1
    assert len(result["paragraphs"]) == 3
    assert result["paragraphs"][0] == "First paragraph."


@pytest.mark.asyncio
async def test_extract_text_md():
    content = "# Title\n\nSome markdown content.\n\nMore content.".encode("utf-8")
    result = await extract_text("readme.md", content)
    assert "# Title" in result["text"]
    assert result["page_count"] == 1
    assert len(result["paragraphs"]) == 3


@pytest.mark.asyncio
async def test_extract_text_txt_utf8_with_chinese():
    content = "第一段内容。\n\n第二段内容。".encode("utf-8")
    result = await extract_text("notes.txt", content)
    assert "第一段内容" in result["text"]
    assert len(result["paragraphs"]) == 2


@pytest.mark.asyncio
@patch("app.documents.parser._get_doc_intel_client")
async def test_extract_text_pdf_calls_doc_intelligence(mock_get_client):
    # Setup mock Document Intelligence client
    mock_paragraph = MagicMock()
    mock_paragraph.content = "Extracted paragraph from PDF."

    mock_page = MagicMock()

    mock_result = MagicMock()
    mock_result.content = "Extracted paragraph from PDF."
    mock_result.pages = [mock_page, mock_page]  # 2 pages
    mock_result.paragraphs = [mock_paragraph]

    mock_poller = MagicMock()
    mock_poller.result.return_value = mock_result

    mock_client = MagicMock()
    mock_client.begin_analyze_document.return_value = mock_poller
    mock_get_client.return_value = mock_client

    result = await extract_text("report.pdf", b"fake-pdf-bytes")

    mock_client.begin_analyze_document.assert_called_once_with(
        "prebuilt-read",
        analyze_request=b"fake-pdf-bytes",
        content_type="application/octet-stream",
    )
    assert result["text"] == "Extracted paragraph from PDF."
    assert result["page_count"] == 2
    assert len(result["paragraphs"]) == 1


@pytest.mark.asyncio
@patch("app.documents.parser._get_doc_intel_client")
async def test_extract_text_docx_calls_doc_intelligence(mock_get_client):
    mock_result = MagicMock()
    mock_result.content = "Word document text."
    mock_result.pages = [MagicMock()]
    mock_result.paragraphs = []

    mock_poller = MagicMock()
    mock_poller.result.return_value = mock_result

    mock_client = MagicMock()
    mock_client.begin_analyze_document.return_value = mock_poller
    mock_get_client.return_value = mock_client

    result = await extract_text("study.docx", b"fake-docx-bytes")

    mock_client.begin_analyze_document.assert_called_once()
    assert result["text"] == "Word document text."
    assert result["page_count"] == 1
    assert result["paragraphs"] == []
