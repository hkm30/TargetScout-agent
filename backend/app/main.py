import base64
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from app.config import settings

# Initialize Azure Monitor telemetry before other imports
if settings.APPLICATIONINSIGHTS_CONNECTION_STRING:
    from azure.monitor.opentelemetry import configure_azure_monitor
    configure_azure_monitor(connection_string=settings.APPLICATIONINSIGHTS_CONNECTION_STRING)

logger = logging.getLogger(__name__)

from app.agents.setup import create_all_agents
from app.agents.orchestrator import run_full_pipeline, run_full_pipeline_stream, parse_user_input
from app.knowledge.cosmos_client import CosmosReportStore
from app.knowledge.search_client import ensure_index, search_reports, delete_report as delete_search_report
from app.knowledge.blob_client import BlobReportStorage
from app.tools.translate import ensure_english
from app.export.report import generate_markdown_report, generate_word_report, generate_pdf_report

# Store agent names after creation
_agent_names: dict[str, str] = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Create agents and search index on startup."""
    global _agent_names
    ensure_index()
    _agent_names = create_all_agents()
    yield


app = FastAPI(title="Drug Target Decision Support Agent", lifespan=lifespan)

# CORS — restrict to known origins in production; fallback to "*" in dev
_cors_origins = os.environ.get("CORS_ORIGINS", "*").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)


class APIKeyMiddleware(BaseHTTPMiddleware):
    """Protect /api/ endpoints with a shared API key."""

    async def dispatch(self, request: Request, call_next):
        # Skip auth for health check and CORS preflight
        if request.url.path == "/api/health" or request.method == "OPTIONS":
            return await call_next(request)
        # No API_KEY configured → dev mode, allow all
        if not settings.API_KEY:
            return await call_next(request)
        # Only protect /api/ routes
        if request.url.path.startswith("/api/"):
            key = request.headers.get("X-API-Key", "")
            if key != settings.API_KEY:
                return JSONResponse(status_code=401, content={"detail": "Invalid API key"})
        return await call_next(request)


app.add_middleware(APIKeyMiddleware)


class AssessmentRequest(BaseModel):
    target: str
    indication: str = ""
    synonyms: str = ""
    focus: str = ""
    time_range: str = ""


class ConfirmAssessmentRequest(BaseModel):
    """Request body for the confirm step — fields may have been edited by the user."""
    target: str
    indication: str = ""
    synonyms: str = ""
    focus: str = ""
    time_range: str = ""


@app.post("/api/assess/parse")
async def assess_parse(req: AssessmentRequest):
    """Step 1: Parse user input, query knowledge base, return confirmation payload."""
    result = await parse_user_input(
        target=req.target,
        indication=req.indication,
        synonyms=req.synonyms,
        focus=req.focus,
        time_range=req.time_range,
    )
    return result


@app.post("/api/assess/confirm")
async def assess_confirm(req: ConfirmAssessmentRequest):
    """Step 2: User confirmed input — stream progress via SSE."""
    if not _agent_names:
        raise HTTPException(status_code=503, detail="Agents not initialized")

    async def event_generator():
        import json as json_mod
        async for event in run_full_pipeline_stream(
            agent_names=_agent_names,
            target=req.target,
            indication=req.indication,
            synonyms=req.synonyms,
            focus=req.focus,
            time_range=req.time_range,
        ):
            event_type = event.get("event", "message")
            data = json_mod.dumps(event.get("data", {}), ensure_ascii=False)
            yield f"event: {event_type}\ndata: {data}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/api/assess")
async def assess_target(req: AssessmentRequest):
    """Direct assessment (backward compatible) — skips confirmation step."""
    if not _agent_names:
        raise HTTPException(status_code=503, detail="Agents not initialized")

    result = await run_full_pipeline(
        agent_names=_agent_names,
        target=req.target,
        indication=req.indication,
        synonyms=req.synonyms,
        focus=req.focus,
        time_range=req.time_range,
    )
    return result


class ExportRequest(BaseModel):
    report_id: str
    target: str


@app.post("/api/export/markdown")
async def export_markdown(req: ExportRequest):
    """Export a stored report as Markdown."""
    store = CosmosReportStore()
    try:
        report = store.get_report(req.report_id, req.target)
    except Exception:
        raise HTTPException(status_code=404, detail="Report not found")
    md = generate_markdown_report(report.get("orchestrator_output", report))
    return {"markdown": md}


@app.post("/api/export/word")
async def export_word(req: ExportRequest):
    """Export a stored report as Word document."""
    store = CosmosReportStore()
    try:
        report = store.get_report(req.report_id, req.target)
    except Exception:
        raise HTTPException(status_code=404, detail="Report not found")
    doc_bytes = generate_word_report(report.get("orchestrator_output", report))
    return Response(
        content=doc_bytes,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f"attachment; filename={req.target}_report.docx"},
    )


@app.post("/api/export/pdf")
async def export_pdf(req: ExportRequest):
    """Export a stored report as PDF document."""
    store = CosmosReportStore()
    try:
        report = store.get_report(req.report_id, req.target)
    except Exception:
        raise HTTPException(status_code=404, detail="Report not found")
    pdf_bytes = generate_pdf_report(report.get("orchestrator_output", report))
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={req.target}_report.pdf"},
    )


@app.get("/api/reports")
async def list_reports():
    """List all historical reports."""
    import asyncio
    try:
        store = CosmosReportStore()
        docs = await asyncio.to_thread(store.list_all_reports)
    except Exception as e:
        logger.error("Failed to list reports: %s", e)
        raise HTTPException(status_code=500, detail=f"无法获取报告列表: {e}")
    reports = []
    for doc in docs:
        output = doc.get("orchestrator_output", {})
        reports.append({
            "id": doc["id"],
            "target": doc.get("target", output.get("target", "")),
            "indication": doc.get("indication", output.get("indication", "")),
            "recommendation": output.get("recommendation", ""),
            "summary": (output.get("literature_summary", "") or "")[:200],
            "created_at": doc.get("created_at", ""),
            "score": output.get("score"),
        })
    return {"reports": reports}


@app.get("/api/reports/{report_id}")
async def get_report(report_id: str, target: str):
    """Fetch a single report's full data."""
    import asyncio
    store = CosmosReportStore()
    try:
        doc = await asyncio.to_thread(store.get_report, report_id, target)
    except Exception:
        raise HTTPException(status_code=404, detail="Report not found")
    output = doc.get("orchestrator_output", {})
    return {
        "report": output,
        "raw_outputs": {
            "literature": doc.get("literature_output", {}),
            "clinical_trials": doc.get("clinical_trials_output", {}),
            "competition": doc.get("competition_output", {}),
        },
        "knowledge_base_context": {"historical_reports": [], "count": 0},
    }


@app.delete("/api/reports/{report_id}")
async def delete_report_endpoint(report_id: str, target: str):
    """Delete a report from Cosmos DB, Blob Storage, and AI Search."""
    import asyncio
    store = CosmosReportStore()
    # Delete from Cosmos DB
    try:
        await asyncio.to_thread(store.delete_report, report_id, target)
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"Report not found: {e}")
    # Delete from Blob Storage (best-effort)
    try:
        blob = BlobReportStorage()
        await asyncio.to_thread(blob.delete_report, report_id)
        await asyncio.to_thread(blob.delete_snapshot, report_id)
    except Exception:
        logger.warning("Blob deletion failed for %s (may not exist)", report_id)
    # Delete from AI Search (best-effort)
    try:
        await delete_search_report(report_id)
    except Exception:
        logger.warning("Search index deletion failed for %s", report_id)
    return {"status": "deleted"}


class KnowledgeSearchRequest(BaseModel):
    query: str
    top_k: int = 5

@app.post("/api/knowledge/search")
async def knowledge_search(req: KnowledgeSearchRequest):
    """Search the knowledge base (translates non-English queries first)."""
    try:
        en_query = await ensure_english(req.query)
        results = await search_reports(query=en_query, top_k=req.top_k)
        return {"results": results, "count": len(results)}
    except Exception as e:
        logger.error("Knowledge search failed: %s", e)
        raise HTTPException(status_code=500, detail=f"搜索失败: {e}")


@app.get("/api/health")
async def health():
    return {
        "status": "ok",
        "agents_ready": bool(_agent_names),
        "build_tag": os.environ.get("BUILD_TAG", "dev"),
        "build_time": os.environ.get("BUILD_TIME", ""),
    }


# Serve frontend static files (combined Docker image)
_static_dir = Path(__file__).resolve().parent.parent / "static"
if _static_dir.is_dir():
    app.mount("/assets", StaticFiles(directory=str(_static_dir / "assets")), name="static-assets")

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        """Serve the SPA index.html for all non-API routes."""
        file_path = _static_dir / full_path
        if file_path.is_file():
            return FileResponse(str(file_path))
        return FileResponse(str(_static_dir / "index.html"))
