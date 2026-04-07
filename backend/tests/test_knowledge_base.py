import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from app.knowledge.cosmos_client import CosmosReportStore


@pytest.mark.asyncio
async def test_save_report():
    mock_container = MagicMock()
    mock_container.upsert_item = MagicMock(return_value={"id": "test-id"})

    store = CosmosReportStore.__new__(CosmosReportStore)
    store.container = mock_container

    report = {
        "id": "test-id",
        "target": "GLP-1R",
        "indication": "obesity",
        "status": "completed",
        "orchestrator_output": {"recommendation": "Go"},
    }
    result = await store.save_report(report)
    mock_container.upsert_item.assert_called_once_with(report)
    assert result["id"] == "test-id"


@pytest.mark.asyncio
async def test_query_by_target():
    mock_container = MagicMock()
    mock_items = [{"id": "1", "target": "GLP-1R", "orchestrator_output": {"recommendation": "Go"}}]
    mock_container.query_items = MagicMock(return_value=mock_items)

    store = CosmosReportStore.__new__(CosmosReportStore)
    store.container = mock_container

    results = store.query_by_target("GLP-1R")
    assert len(list(results)) == 1
