# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

TargetScout is a multi-agent drug target intelligence system that performs Go/No-Go assessments for drug development. It uses an orchestrator agent that coordinates three parallel specialist agents (literature, clinical trials, competition) followed by a decision summary agent, all backed by Azure AI Foundry.

All agent output (summaries, analysis, reasoning) is in **Chinese (中文)**, except technical terms, drug/gene names, and the recommendation field (Go / No-Go / Need More Data).

## Commands

### Backend

```bash
# Install dependencies (from backend/)
cd backend && python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# Run dev server
cd backend && .venv/bin/python -m uvicorn app.main:app --reload --port 8000

# Run all tests
cd backend && .venv/bin/python -m pytest tests/ -v

# Run a single test file
cd backend && .venv/bin/python -m pytest tests/test_pubmed.py -v

# Skip PDF export tests (requires CJK fonts installed at build time)
cd backend && .venv/bin/python -m pytest tests/ -v --ignore=tests/test_export.py
```

### Frontend

```bash
# Install dependencies (from frontend/)
cd frontend && npm install

# Dev server (proxies /api to localhost:8000)
cd frontend && npm run dev

# Type-check and build
cd frontend && npm run build
```

### Deployment

```bash
# Build and deploy to Azure Container Apps
cd infra && bash deploy.sh
```

Docker builds must use `--no-cache` to avoid deploying stale cached layers.

## Architecture

### Agent Pipeline

```
User Input → Orchestrator Agent
                ├── Literature Agent    (PubMed + web search)
                ├── Clinical Trials Agent (ClinicalTrials.gov + web search)  [parallel]
                └── Competition Agent   (web search + PubMed + ClinicalTrials.gov)
             → Decision Summary Agent → Knowledge Base + Export
```

The orchestrator runs a two-phase flow:
1. **Parse phase** (`POST /api/assess/parse`): Extracts target/indication, queries knowledge base for historical context, returns structured understanding for user confirmation.
2. **Confirm phase** (`POST /api/assess/confirm`): First runs knowledge base search and document processing in parallel, then runs the three specialist agents in parallel via `asyncio.gather`, feeds results to the decision agent, saves to knowledge base. Streams progress via SSE.

### Backend (`backend/app/`)

- **`agents/setup.py`** — Singleton `AIProjectClient` and `OpenAI` client from Azure Foundry. All agents are created via `create_all_agents()` at app startup (lifespan).
- **`agents/definitions.py`** — FunctionTool definitions and tool groupings per agent.
- **`agents/orchestrator.py`** — Core execution: `run_agent_turn()` loop with tool dispatch, retry logic for rate limits, and SSE streaming via `run_assessment_stream()`.
- **`tools/`** — Async tool implementations: `pubmed.py` (E-utilities API), `clinical_trials.py` (ClinicalTrials.gov v2 API), `knowledge_base.py` (Cosmos + AI Search + Blob), `translate.py` (Chinese→English query translation).
- **`knowledge/`** — Azure service clients: `cosmos_client.py`, `search_client.py`, `blob_client.py`, `embedding.py`.
- **`documents/`** — Private document upload pipeline: `router.py` (endpoints + deferred processing), `parser.py` (Azure Document Intelligence), `chunker.py` (token-based with tiktoken), `summarizer.py` (LLM summarization). Upload only validates and holds files in memory; heavy processing (blob upload, text extraction, summarization, chunking, indexing) is deferred to the confirm phase and runs in parallel with knowledge base search. Content-based deduplication via SHA-256 hash. Delete endpoint implements always-cleanup semantics: cleans up AI Search chunks even when Cosmos DB record is already gone, preventing orphaned index entries.
- **`export/`** — Report generation in Markdown, Word (.docx), and PDF with CJK font support.

### Frontend (`frontend/src/`)

Single-page React 19 app with no routing library. Page state managed in `App.tsx` (`"search" | "running" | "results" | "history"`). The `api.ts` module handles all backend communication including SSE streaming via `ReadableStream`.

### Key External Services

- **Azure AI Foundry** — Agent hosting, OpenAI-compatible API (GPT-5.4 + text-embedding-3)
- **Azure Cosmos DB** — Report storage (AAD auth via DefaultAzureCredential, key auth disabled)
- **Azure AI Search** — Vector + keyword hybrid search for evidence and documents
- **Azure Blob Storage** — Raw search snapshots and uploaded documents
- **PubMed E-utilities** — Literature search (no API key required)
- **ClinicalTrials.gov v2 API** — Clinical trial data (no API key required)

## Environment

Backend requires a `.env` file (see `.env.example`). The critical variables are:
- `AZURE_AI_PROJECT_ENDPOINT` — Foundry project endpoint
- `MODEL_DEPLOYMENT` — LLM model name (default: `gpt-54`)
- `SEARCH_ENDPOINT` / `SEARCH_API_KEY` — Azure AI Search
- `COSMOS_ENDPOINT` — Cosmos DB (uses DefaultAzureCredential)
- `STORAGE_ACCOUNT_NAME` — Blob Storage (uses DefaultAzureCredential)

Tests use mock environment variables set in `backend/tests/conftest.py` and do not require real Azure credentials.
