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
    mock_paragraph = MagicMock()
    mock_paragraph.content = "Extracted paragraph from PDF."
    mock_page = MagicMock()
    mock_result = MagicMock()
    mock_result.content = "Extracted paragraph from PDF."
    mock_result.pages = [mock_page, mock_page]
    mock_result.paragraphs = [mock_paragraph]
    mock_result.figures = None

    mock_poller = MagicMock()
    mock_poller.result.return_value = mock_result

    mock_client = MagicMock()
    mock_client.begin_analyze_document.return_value = mock_poller
    mock_get_client.return_value = mock_client

    result = await extract_text("report.pdf", b"fake-pdf-bytes")

    call_args = mock_client.begin_analyze_document.call_args
    assert call_args[0][0] == "prebuilt-layout"
    assert result["text"] == "Extracted paragraph from PDF."
    assert result["page_count"] == 2
    assert len(result["paragraphs"]) == 1
    assert result["figures"] == []


@pytest.mark.asyncio
@patch("app.documents.parser._get_doc_intel_client")
async def test_extract_text_docx_calls_doc_intelligence(mock_get_client):
    mock_result = MagicMock()
    mock_result.content = "Word document text."
    mock_result.pages = [MagicMock()]
    mock_result.paragraphs = []
    mock_result.figures = None

    mock_poller = MagicMock()
    mock_poller.result.return_value = mock_result

    mock_client = MagicMock()
    mock_client.begin_analyze_document.return_value = mock_poller
    mock_get_client.return_value = mock_client

    result = await extract_text("study.docx", b"fake-docx-bytes")

    mock_client.begin_analyze_document.assert_called_once()
    call_args = mock_client.begin_analyze_document.call_args
    assert call_args[0][0] == "prebuilt-layout"
    assert result["text"] == "Word document text."
    assert result["page_count"] == 1
    assert result["paragraphs"] == []
    assert result["figures"] == []


@pytest.mark.asyncio
@patch("app.documents.parser._fetch_figure_image")
@patch("app.documents.parser._get_doc_intel_client")
async def test_extract_text_pdf_extracts_figures(mock_get_client, mock_fetch_image):
    """PDF extraction should return figures with image bytes."""
    mock_caption = MagicMock()
    mock_caption.content = "Figure 1: IC50 distribution"

    mock_span = MagicMock()
    mock_span.offset = 100

    mock_region = MagicMock()
    mock_region.page_number = 1

    mock_figure = MagicMock()
    mock_figure.id = "1.0"
    mock_figure.caption = mock_caption
    mock_figure.spans = [mock_span]
    mock_figure.bounding_regions = [mock_region]

    mock_paragraph = MagicMock()
    mock_paragraph.content = "Some text content."

    mock_result = MagicMock()
    mock_result.content = "Some text content."
    mock_result.pages = [MagicMock()]
    mock_result.paragraphs = [mock_paragraph]
    mock_result.figures = [mock_figure]

    mock_poller = MagicMock()
    mock_poller.result.return_value = mock_result
    mock_poller.details = {"operation_id": "test-result-id"}

    mock_client = MagicMock()
    mock_client.begin_analyze_document.return_value = mock_poller
    mock_get_client.return_value = mock_client

    mock_fetch_image.return_value = b"fake-png-bytes"

    result = await extract_text("report.pdf", b"fake-pdf-bytes")

    call_args = mock_client.begin_analyze_document.call_args
    assert call_args[0][0] == "prebuilt-layout"

    assert len(result["figures"]) == 1
    fig = result["figures"][0]
    assert fig["id"] == "1.0"
    assert fig["caption"] == "Figure 1: IC50 distribution"
    assert fig["image_bytes"] == b"fake-png-bytes"
    assert fig["page_number"] == 1
    assert fig["span_offset"] == 100

    assert result["text"] == "Some text content."
    assert result["page_count"] == 1


@pytest.mark.asyncio
@patch("app.documents.parser._get_doc_intel_client")
async def test_extract_text_pdf_no_figures(mock_get_client):
    """PDF with no figures should return empty figures list."""
    mock_result = MagicMock()
    mock_result.content = "Text only document."
    mock_result.pages = [MagicMock()]
    mock_result.paragraphs = [MagicMock(content="Text only document.")]
    mock_result.figures = None

    mock_poller = MagicMock()
    mock_poller.result.return_value = mock_result

    mock_client = MagicMock()
    mock_client.begin_analyze_document.return_value = mock_poller
    mock_get_client.return_value = mock_client

    result = await extract_text("report.pdf", b"fake-pdf-bytes")

    assert result["figures"] == []
    assert result["text"] == "Text only document."


@pytest.mark.asyncio
async def test_extract_text_txt_returns_empty_figures():
    """Text files should return empty figures list."""
    content = "Plain text content.\n\nSecond paragraph.".encode("utf-8")
    result = await extract_text("notes.txt", content)
    assert result["figures"] == []
    assert result["text"] == "Plain text content.\n\nSecond paragraph."
