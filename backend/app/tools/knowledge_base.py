import json
import uuid
from datetime import datetime, timezone

from app.knowledge.cosmos_client import CosmosReportStore
from app.knowledge.blob_client import BlobReportStorage
from app.knowledge.search_client import index_report, search_reports
from app.export.report import generate_word_report

_cosmos: CosmosReportStore | None = None
_blob: BlobReportStorage | None = None


def _get_cosmos() -> CosmosReportStore:
    global _cosmos
    if _cosmos is None:
        _cosmos = CosmosReportStore()
    return _cosmos


def _get_blob() -> BlobReportStorage:
    global _blob
    if _blob is None:
        _blob = BlobReportStorage()
    return _blob


async def search_knowledge_base(
    query: str, target: str | None = None, indication: str | None = None, top_k: int = 5
) -> str:
    """Search historical reports in the knowledge base."""
    search_query = query
    if target:
        search_query = f"{target} {search_query}"
    if indication:
        search_query = f"{search_query} {indication}"

    results = await search_reports(search_query, target=target, top_k=top_k)
    return json.dumps({"historical_reports": results, "count": len(results)})


async def write_to_knowledge_base(report: dict, raw_outputs: dict, report_id: str | None = None) -> str:
    """Write query results to Cosmos DB, Blob Storage, and AI Search."""
    report_id = report_id or str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    # 1. Save to Cosmos DB
    cosmos_doc = {
        "id": report_id,
        "target": report.get("target", ""),
        "indication": report.get("indication", ""),
        "created_at": now,
        "status": "completed",
        "orchestrator_output": report,
        "literature_output": raw_outputs.get("literature", {}),
        "clinical_trials_output": raw_outputs.get("clinical_trials", {}),
        "competition_output": raw_outputs.get("competition", {}),
        "document_ids": report.get("document_ids", []),
    }
    cosmos = _get_cosmos()
    await cosmos.save_report(cosmos_doc)

    # 2. Save snapshot to Blob
    blob = _get_blob()
    snapshot_url = blob.upload_snapshot(report_id, raw_outputs)

    # 3. Generate and upload Word report
    word_bytes = generate_word_report(report)
    report_url = blob.upload_report(report_id, word_bytes)

    # 4. Update Cosmos doc with blob URLs
    cosmos_doc["report_blob_url"] = report_url
    cosmos_doc["snapshot_blob_url"] = snapshot_url
    await cosmos.save_report(cosmos_doc)

    # 5. Index in AI Search
    search_doc = {**report, "id": report_id, "created_at": now}
    await index_report(search_doc)

    return json.dumps({"report_id": report_id, "report_url": report_url, "snapshot_url": snapshot_url})
