import pytest
from unittest.mock import MagicMock, patch


@pytest.mark.asyncio
@patch("app.documents.vision.get_openai_client")
async def test_describe_figure_returns_description(mock_get_client):
    from app.documents.vision import describe_figure

    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = "这是一张柱状图，展示了IC50值的分布。"

    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = mock_response
    mock_get_client.return_value = mock_client

    result = await describe_figure(b"fake-png-bytes", caption="Figure 1: IC50 values")

    assert "IC50" in result
    mock_client.chat.completions.create.assert_called_once()
    call_kwargs = mock_client.chat.completions.create.call_args
    messages = call_kwargs.kwargs.get("messages") or call_kwargs[1].get("messages") or call_kwargs[0][1] if len(call_kwargs[0]) > 1 else call_kwargs.kwargs["messages"]
    user_msg = messages[0]
    assert user_msg["role"] == "user"
    assert isinstance(user_msg["content"], list)
    assert user_msg["content"][1]["type"] == "image_url"


@pytest.mark.asyncio
@patch("app.documents.vision.get_openai_client")
async def test_describe_figure_with_context(mock_get_client):
    from app.documents.vision import describe_figure

    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = "该图展示了EGFR通路的激活机制。"

    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = mock_response
    mock_get_client.return_value = mock_client

    result = await describe_figure(
        b"fake-png-bytes",
        caption="Figure 2: EGFR pathway",
        context="The study examined EGFR mutations in NSCLC patients.",
    )

    assert "EGFR" in result
    call_kwargs = mock_client.chat.completions.create.call_args
    messages = call_kwargs.kwargs.get("messages", call_kwargs[1].get("messages", []))
    prompt_text = messages[0]["content"][0]["text"]
    assert "EGFR pathway" in prompt_text
    assert "EGFR mutations" in prompt_text


@pytest.mark.asyncio
@patch("app.documents.vision.get_openai_client")
async def test_describe_figure_api_failure_returns_fallback(mock_get_client):
    from app.documents.vision import describe_figure

    mock_client = MagicMock()
    mock_client.chat.completions.create.side_effect = Exception("API error")
    mock_get_client.return_value = mock_client

    result = await describe_figure(b"fake-png-bytes", caption="Figure 1: IC50 values")

    assert "Figure 1: IC50 values" in result


@pytest.mark.asyncio
@patch("app.documents.vision.get_openai_client")
async def test_describe_all_figures_concurrent(mock_get_client):
    from app.documents.vision import describe_all_figures

    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = "描述内容"

    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = mock_response
    mock_get_client.return_value = mock_client

    figures = [
        {"id": "1.0", "page_number": 1, "caption": "Fig 1", "image_bytes": b"png1", "span_offset": 50},
        {"id": "1.1", "page_number": 2, "caption": "Fig 2", "image_bytes": b"png2", "span_offset": 200},
    ]
    paragraphs = ["Intro paragraph about the study.", "Methods section details.", "Results show improvement."]

    result = await describe_all_figures(figures, paragraphs)

    assert len(result) == 2
    assert result[0]["description"] == "描述内容"
    assert result[1]["description"] == "描述内容"
    assert mock_client.chat.completions.create.call_count == 2
