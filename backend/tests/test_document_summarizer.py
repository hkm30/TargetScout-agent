import pytest
from unittest.mock import MagicMock, patch

from app.documents.summarizer import _parse_summaries, generate_summaries


# --- _parse_summaries tests ---

def test_parse_summaries_normal_format():
    text = """一些前文
---摘要---
这是摘要内容，详细提炼文档核心。
---总结---
这是总结内容，精炼概要。"""
    result = _parse_summaries(text)
    assert "摘要内容" in result["abstract"]
    assert "总结内容" in result["summary"]


def test_parse_summaries_fallback_without_delimiters():
    text = "This is plain text without any delimiters, just a long document summary."
    result = _parse_summaries(text)
    # Fallback: abstract = full text, summary = first half
    assert result["abstract"] == text
    assert len(result["summary"]) > 0


def test_parse_summaries_empty():
    result = _parse_summaries("")
    assert result["abstract"] == ""
    assert result["summary"] == ""


def test_parse_summaries_only_abstract_delimiter():
    """Text with only one delimiter should use fallback."""
    text = "---摘要---\nSome abstract content here."
    result = _parse_summaries(text)
    # No ---总结--- delimiter, so fallback
    assert result["abstract"] == text
    assert len(result["summary"]) > 0


def test_parse_summaries_multiline_sections():
    text = """---摘要---
第一行摘要。
第二行摘要。
第三行摘要。
---总结---
第一行总结。
第二行总结。"""
    result = _parse_summaries(text)
    assert "第一行摘要" in result["abstract"]
    assert "第三行摘要" in result["abstract"]
    assert "第一行总结" in result["summary"]
    assert "第二行总结" in result["summary"]


# --- generate_summaries tests ---

@pytest.mark.asyncio
@patch("app.documents.summarizer.get_openai_client")
async def test_generate_summaries_calls_llm(mock_get_client):
    mock_choice = MagicMock()
    mock_choice.message.content = """---摘要---
详细摘要内容
---总结---
精炼总结内容"""

    mock_response = MagicMock()
    mock_response.choices = [mock_choice]

    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = mock_response
    mock_get_client.return_value = mock_client

    result = await generate_summaries("Some document text about drug targets.", "report.pdf")

    mock_client.chat.completions.create.assert_called_once()
    call_kwargs = mock_client.chat.completions.create.call_args
    messages = call_kwargs.kwargs.get("messages") or call_kwargs[1].get("messages")
    assert any("drug targets" in m["content"] for m in messages)
    assert "摘要内容" in result["abstract"]
    assert "总结内容" in result["summary"]


@pytest.mark.asyncio
@patch("app.documents.summarizer.get_openai_client")
async def test_generate_summaries_truncates_long_input(mock_get_client):
    mock_choice = MagicMock()
    mock_choice.message.content = "---摘要---\ntruncated abstract\n---总结---\ntruncated summary"

    mock_response = MagicMock()
    mock_response.choices = [mock_choice]

    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = mock_response
    mock_get_client.return_value = mock_client

    # Generate text that exceeds 12000 tokens
    long_text = "word " * 50000  # ~50000 tokens

    result = await generate_summaries(long_text, "huge.txt")

    # Verify the LLM was called with truncated input
    call_kwargs = mock_client.chat.completions.create.call_args
    messages = call_kwargs.kwargs.get("messages") or call_kwargs[1].get("messages")
    prompt_content = messages[0]["content"]
    assert "文档内容已截断" in prompt_content
    assert result["abstract"] == "truncated abstract"


@pytest.mark.asyncio
@patch("app.documents.summarizer.get_openai_client")
async def test_generate_summaries_llm_returns_no_delimiters(mock_get_client):
    """When LLM doesn't follow format, fallback parsing should handle it."""
    mock_choice = MagicMock()
    mock_choice.message.content = "This is just plain text without proper delimiters from the LLM."

    mock_response = MagicMock()
    mock_response.choices = [mock_choice]

    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = mock_response
    mock_get_client.return_value = mock_client

    result = await generate_summaries("Some text.", "file.txt")

    # Should use fallback: abstract = full, summary = partial
    assert "plain text" in result["abstract"]
    assert len(result["summary"]) > 0
