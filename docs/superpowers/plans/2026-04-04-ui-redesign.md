# UI Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restructure the Drug Target Decision Support System from a single-column layout to a left sidebar navigation + right main content area, with Microsoft color scheme, new History and Knowledge Search pages, parallel agent visualization, and real-time partial results.

**Architecture:** Page-based routing via React state (`page: "assess" | "history" | "search"`, `assessStep: "input" | "confirm" | "running" | "done"`). Sidebar always visible with nav + dynamic stepper. Backend adds CRUD endpoints for reports and a `partial_result` SSE event type for real-time agent output previews.

**Tech Stack:** React 19, TypeScript 5.6, Vite 6.0, FastAPI, Azure Cosmos DB, Azure Blob Storage, Azure AI Search

---

### Task 1: Backend — Add list/delete methods to Cosmos and Blob clients

**Files:**
- Modify: `backend/app/knowledge/cosmos_client.py`
- Modify: `backend/app/knowledge/blob_client.py`

- [ ] **Step 1: Add `list_all_reports()` and `delete_report()` to CosmosReportStore**

In `backend/app/knowledge/cosmos_client.py`, add two methods to the `CosmosReportStore` class after the existing `get_report` method:

```python
def list_all_reports(self, max_results: int = 100) -> list[dict]:
    """List all reports, newest first."""
    query = "SELECT c.id, c.target, c.indication, c.status, c.created_at, c.orchestrator_output FROM c ORDER BY c.created_at DESC"
    return list(self.container.query_items(
        query=query, max_item_count=max_results, enable_cross_partition_query=True,
    ))

def delete_report(self, report_id: str, target: str):
    """Delete a report by ID."""
    self.container.delete_item(item=report_id, partition_key=target)
```

- [ ] **Step 2: Add `delete_report()` and `delete_snapshot()` to BlobReportStorage**

In `backend/app/knowledge/blob_client.py`, add two methods after the existing `upload_snapshot` method:

```python
def delete_report(self, report_id: str):
    """Delete a report file from blob storage."""
    blob_name = f"{report_id}.docx"
    blob_client = self.reports_container.get_blob_client(blob_name)
    blob_client.delete_blob(delete_snapshots="include")

def delete_snapshot(self, report_id: str):
    """Delete a snapshot file from blob storage."""
    blob_name = f"{report_id}_snapshot.json"
    blob_client = self.snapshots_container.get_blob_client(blob_name)
    blob_client.delete_blob(delete_snapshots="include")
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/knowledge/cosmos_client.py backend/app/knowledge/blob_client.py
git commit -m "feat: add list and delete methods to Cosmos and Blob clients"
```

---

### Task 2: Backend — Add delete method to search client

**Files:**
- Modify: `backend/app/knowledge/search_client.py`

- [ ] **Step 1: Add `delete_report()` function**

In `backend/app/knowledge/search_client.py`, add a new function after the existing `search_reports()` function:

```python
async def delete_report(report_id: str):
    """Delete a document from AI Search index."""
    client = get_search_client()
    await asyncio.to_thread(
        client.delete_documents, documents=[{"id": report_id}]
    )
```

Make sure `asyncio` is imported at the top of the file (add `import asyncio` if not already present).

- [ ] **Step 2: Commit**

```bash
git add backend/app/knowledge/search_client.py
git commit -m "feat: add delete_report to search client"
```

---

### Task 3: Backend — Add report API endpoints

**Files:**
- Modify: `backend/app/main.py`

- [ ] **Step 1: Add imports and helper**

At the top of `backend/app/main.py`, add imports for the search and blob clients alongside the existing imports:

```python
from app.knowledge.search_client import ensure_index, search_reports, delete_report as delete_search_report
from app.knowledge.blob_client import BlobReportStorage
```

Update the existing `ensure_index` import line — it currently reads:
```python
from app.knowledge.search_client import ensure_index
```

Replace with:
```python
from app.knowledge.search_client import ensure_index, search_reports, delete_report as delete_search_report
```

- [ ] **Step 2: Add GET /api/reports endpoint**

Add the following endpoint after the existing `export_pdf` endpoint and before `health`:

```python
@app.get("/api/reports")
async def list_reports():
    """List all historical reports."""
    import asyncio
    store = CosmosReportStore()
    docs = await asyncio.to_thread(store.list_all_reports)
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
```

- [ ] **Step 3: Add GET /api/reports/{report_id} endpoint**

Add after the list endpoint:

```python
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
```

- [ ] **Step 4: Add DELETE /api/reports/{report_id} endpoint**

Add after the get endpoint:

```python
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
```

- [ ] **Step 5: Add POST /api/knowledge/search endpoint**

Add after the delete endpoint:

```python
class KnowledgeSearchRequest(BaseModel):
    query: str
    top_k: int = 5

@app.post("/api/knowledge/search")
async def knowledge_search(req: KnowledgeSearchRequest):
    """Search the knowledge base."""
    results = await search_reports(query=req.query, top_k=req.top_k)
    return {"results": results, "count": len(results)}
```

- [ ] **Step 6: Commit**

```bash
git add backend/app/main.py
git commit -m "feat: add reports CRUD and knowledge search API endpoints"
```

---

### Task 4: Backend — Add partial_result SSE events to orchestrator

**Files:**
- Modify: `backend/app/agents/orchestrator.py`

- [ ] **Step 1: Yield partial_result after each research agent completes**

In `backend/app/agents/orchestrator.py`, inside the `run_full_pipeline_stream()` function, find the `while pending:` loop (around line 401). After the line that yields the `"completed"` status event for each agent, add a `partial_result` yield. Replace the inner `try` block:

Current code (lines 405-408):
```python
result = task.result()
resolved_map[key] = result
yield {"event": "status", "data": {"stage": key, "status": "completed"}}
```

Replace with:
```python
result = task.result()
resolved_map[key] = result
yield {"event": "status", "data": {"stage": key, "status": "completed"}}
yield {"event": "partial_result", "data": {"stage": key, "result": _safe_parse(result)}}
```

The `_safe_parse` function already exists in the file and handles JSON parsing with fallback.

- [ ] **Step 2: Commit**

```bash
git add backend/app/agents/orchestrator.py
git commit -m "feat: add partial_result SSE events for real-time agent output preview"
```

---

### Task 5: Frontend — Add Vite build-time environment variables

**Files:**
- Modify: `frontend/vite.config.ts`

- [ ] **Step 1: Inject version and build time as define constants**

Replace the contents of `frontend/vite.config.ts` with:

```typescript
import { readFileSync } from "fs";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const pkg = JSON.parse(readFileSync("./package.json", "utf-8"));

export default defineConfig({
  plugins: [react()],
  define: {
    __APP_VERSION__: JSON.stringify(pkg.version),
    __BUILD_TIME__: JSON.stringify(new Date().toISOString()),
  },
  server: {
    proxy: {
      "/api": "http://localhost:8000",
    },
  },
});
```

- [ ] **Step 2: Add type declarations for the constants**

Create `frontend/src/env.d.ts`:

```typescript
declare const __APP_VERSION__: string;
declare const __BUILD_TIME__: string;
```

- [ ] **Step 3: Commit**

```bash
git add frontend/vite.config.ts frontend/src/env.d.ts
git commit -m "feat: inject app version and build time via Vite define"
```

---

### Task 6: Frontend — Add new types for pages and SSE partial results

**Files:**
- Modify: `frontend/src/types.ts`

- [ ] **Step 1: Add page routing types and report list types**

At the bottom of `frontend/src/types.ts`, add:

```typescript
export type Page = "assess" | "history" | "search";
export type AssessStep = "input" | "confirm" | "running" | "done";

export interface ReportListItem {
  id: string;
  target: string;
  indication: string;
  recommendation: string;
  summary: string;
  created_at: string;
  score?: number;
}

export interface SearchResultItem {
  id: string;
  target: string;
  indication: string;
  recommendation: string;
  summary: string;
  created_at: string;
  score: number;
}

export interface PartialResultData {
  stage: string;
  result: Record<string, unknown>;
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/types.ts
git commit -m "feat: add page routing, report list, and partial result types"
```

---

### Task 7: Frontend — Add new API client functions

**Files:**
- Modify: `frontend/src/api.ts`

- [ ] **Step 1: Add report list, get, delete, and knowledge search functions**

At the bottom of `frontend/src/api.ts` (before any closing braces, after the existing `exportPdf` function), add:

```typescript
export async function fetchReports(): Promise<{ reports: import("./types").ReportListItem[] }> {
  const res = await fetch(`${API_BASE}/reports`, { headers: getHeaders() });
  if (!res.ok) throw new Error(`Failed to fetch reports: ${res.status}`);
  return res.json();
}

export async function fetchReport(id: string, target: string): Promise<import("./types").AssessmentResult> {
  const res = await fetch(`${API_BASE}/reports/${id}?target=${encodeURIComponent(target)}`, { headers: getHeaders() });
  if (!res.ok) throw new Error(`Failed to fetch report: ${res.status}`);
  return res.json();
}

export async function deleteReport(id: string, target: string): Promise<void> {
  const res = await fetch(`${API_BASE}/reports/${id}?target=${encodeURIComponent(target)}`, {
    method: "DELETE",
    headers: getHeaders(),
  });
  if (!res.ok) throw new Error(`Failed to delete report: ${res.status}`);
}

export async function searchKnowledge(query: string, topK: number = 5): Promise<{ results: import("./types").SearchResultItem[]; count: number }> {
  const res = await fetch(`${API_BASE}/knowledge/search`, {
    method: "POST",
    headers: { ...getHeaders(), "Content-Type": "application/json" },
    body: JSON.stringify({ query, top_k: topK }),
  });
  if (!res.ok) throw new Error(`Search failed: ${res.status}`);
  return res.json();
}
```

Also, extract the headers helper. Find the existing API_KEY usage pattern. Currently the headers are built inline in each function. Add a helper near the top (after `API_KEY`):

```typescript
function getHeaders(): Record<string, string> {
  const h: Record<string, string> = {};
  if (API_KEY) h["X-API-Key"] = API_KEY;
  return h;
}
```

Then update each existing fetch call to use `getHeaders()` instead of the inline header construction. For example, in `parseAssessment`, replace:
```typescript
headers: {
  "Content-Type": "application/json",
  ...(API_KEY ? { "X-API-Key": API_KEY } : {}),
},
```
with:
```typescript
headers: { ...getHeaders(), "Content-Type": "application/json" },
```

Apply this same change to `confirmAssessmentSSE`, `confirmAssessment`, `assessTarget`, `exportMarkdown`, `exportWord`, and `exportPdf`.

- [ ] **Step 2: Commit**

```bash
git add frontend/src/api.ts
git commit -m "feat: add report CRUD and knowledge search API functions"
```

---

### Task 8: Frontend — Create App.css with Microsoft color scheme and layout

**Files:**
- Create: `frontend/src/App.css`

- [ ] **Step 1: Create the CSS file**

Create `frontend/src/App.css` with the full layout styles:

```css
/* === Reset === */
body {
  margin: 0;
  padding: 0;
}

/* === Layout Shell === */
.app-layout {
  display: flex;
  width: 100vw;
  height: 100vh;
  font-family: "Segoe UI", system-ui, -apple-system, sans-serif;
  overflow: hidden;
}

/* === Sidebar === */
.sidebar {
  width: 240px;
  background: #1B1B1B;
  color: #fff;
  display: flex;
  flex-direction: column;
  flex-shrink: 0;
  overflow-y: auto;
}

.sidebar-header {
  padding: 16px 20px;
  font-size: 14px;
  font-weight: 600;
  border-bottom: 1px solid #333;
  display: flex;
  align-items: center;
  gap: 10px;
}

.sidebar-logo {
  width: 28px;
  height: 28px;
  background: #0078D4;
  border-radius: 5px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 14px;
  flex-shrink: 0;
}

.nav-item {
  padding: 10px 20px;
  color: #ccc;
  font-size: 13px;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 10px;
  transition: background 0.15s, color 0.15s;
}

.nav-item:hover {
  background: rgba(255, 255, 255, 0.05);
  color: #fff;
}

.nav-item.active {
  background: rgba(0, 120, 212, 0.15);
  color: #60CDFF;
  font-weight: 500;
  border-left: 3px solid #0078D4;
  padding-left: 17px;
}

.nav-divider {
  border-top: 1px solid #333;
  margin: 10px 0;
}

.nav-section {
  padding: 6px 20px;
  font-size: 10px;
  color: #888;
  text-transform: uppercase;
  letter-spacing: 0.8px;
}

/* === Progress Stepper === */
.step-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 20px;
  margin: 2px 0;
}

.step-dot {
  width: 18px;
  height: 18px;
  border-radius: 50%;
  font-size: 9px;
  font-weight: 600;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.step-dot--done {
  background: #0078D4;
  color: #fff;
}

.step-dot--current {
  background: #0078D4;
  color: #fff;
}

.step-dot--running {
  background: #f59e0b;
  color: #fff;
}

.step-dot--pending {
  background: #444;
  color: #888;
}

.step-label {
  font-size: 11px;
}

.step-label--done {
  color: #888;
}

.step-label--current {
  color: #fff;
  font-weight: 600;
}

.step-label--pending {
  color: #666;
}

/* === Sidebar Footer === */
.sidebar-footer {
  margin-top: auto;
  border-top: 1px solid #333;
  padding: 12px 20px;
  font-size: 10px;
  color: #666;
  line-height: 1.6;
}

.sidebar-spacer {
  flex: 1;
}

/* === Main Content === */
.main-content {
  flex: 1;
  background: #F5F5F5;
  padding: 24px;
  overflow-y: auto;
}

.content-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}

.content-title {
  font-size: 18px;
  font-weight: 600;
  color: #1B1B1B;
}

/* === Buttons === */
.btn {
  background: #fff;
  border: 1px solid #d1d5db;
  padding: 6px 14px;
  border-radius: 5px;
  font-size: 12px;
  color: #333;
  cursor: pointer;
  font-family: inherit;
}

.btn:hover {
  background: #f0f0f0;
}

.btn-primary {
  background: #0078D4;
  color: #fff;
  border-color: #0078D4;
}

.btn-primary:hover {
  background: #106EBE;
}

.btn-danger {
  color: #ef4444;
  border-color: #fca5a5;
}

.btn-danger:hover {
  background: #fef2f2;
}

.btn-group {
  display: flex;
  gap: 6px;
}

/* === Cards === */
.card {
  background: #fff;
  border-radius: 8px;
  padding: 18px;
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.08);
  margin-bottom: 14px;
}

.card-clickable {
  cursor: pointer;
  transition: box-shadow 0.15s;
}

.card-clickable:hover {
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.12);
}

/* === Badges === */
.badge {
  display: inline-block;
  padding: 3px 14px;
  border-radius: 12px;
  font-size: 12px;
  font-weight: 700;
  color: #fff;
}

.badge--go {
  background: #22c55e;
}

.badge--nogo {
  background: #ef4444;
}

.badge--more {
  background: #f59e0b;
}

/* === Content Tabs === */
.content-tabs {
  display: flex;
  gap: 0;
  margin-bottom: 0;
}

.content-tab {
  padding: 10px 20px;
  font-size: 13px;
  border: 1px solid #d1d5db;
  cursor: pointer;
  background: #F5F5F5;
  color: #666;
  font-family: inherit;
}

.content-tab:first-child {
  border-radius: 8px 0 0 0;
}

.content-tab:last-child {
  border-radius: 0 8px 0 0;
}

.content-tab--active {
  background: #fff;
  color: #0078D4;
  font-weight: 600;
  border-bottom-color: #fff;
}

.tab-panel {
  background: #fff;
  border: 1px solid #d1d5db;
  border-top: none;
  border-radius: 0 0 8px 8px;
  padding: 18px;
}

/* === Search === */
.search-box {
  display: flex;
  gap: 8px;
  margin-bottom: 20px;
}

.search-input {
  flex: 1;
  padding: 10px 16px;
  border: 1px solid #d1d5db;
  border-radius: 6px;
  font-size: 14px;
  font-family: inherit;
  outline: none;
}

.search-input:focus {
  border-color: #0078D4;
  box-shadow: 0 0 0 2px rgba(0, 120, 212, 0.15);
}

/* === Progress View === */
.progress-card {
  background: #fff;
  border-radius: 8px;
  padding: 18px;
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.08);
  margin-bottom: 14px;
}

.progress-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}

.progress-phase {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 0;
  font-size: 13px;
}

.parallel-agents {
  display: flex;
  gap: 8px;
  margin: 10px 0;
}

.agent-card {
  flex: 1;
  border-radius: 8px;
  padding: 10px;
  text-align: center;
  position: relative;
  overflow: hidden;
}

.agent-card--done {
  background: #F0FDF4;
  border: 1px solid #BBF7D0;
}

.agent-card--running {
  background: #FFFBEB;
  border: 1px solid #FDE68A;
}

.agent-card--waiting {
  background: #F9FAFB;
  border: 1px solid #E5E7EB;
  opacity: 0.5;
}

.agent-card__icon {
  font-size: 18px;
  margin-bottom: 4px;
}

.agent-card__label {
  font-size: 11px;
  font-weight: 600;
}

.agent-card__label--done {
  color: #166534;
}

.agent-card__label--running {
  color: #92400E;
}

.agent-card__label--waiting {
  color: #999;
}

.agent-card__status {
  font-size: 10px;
  margin-top: 4px;
}

.agent-card__progress-bar {
  position: absolute;
  bottom: 0;
  left: 0;
  right: 0;
  height: 3px;
  background: #FDE68A;
}

.agent-card__progress-fill {
  height: 100%;
  background: #F59E0B;
  transition: width 0.3s ease;
}

/* === Partial Results === */
.partial-result {
  background: #fff;
  border-left: 3px solid #22c55e;
  border-radius: 0 8px 8px 0;
  padding: 14px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.06);
  margin-bottom: 8px;
}

.partial-result__title {
  font-size: 12px;
  font-weight: 600;
  margin-bottom: 4px;
}

.partial-result__text {
  font-size: 11px;
  color: #555;
  line-height: 1.6;
}

.skeleton {
  background: #F0F0F0;
  border-radius: 4px;
  height: 14px;
  margin-bottom: 8px;
}

/* === Report List (History) === */
.report-card {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 12px;
}

.report-card__body {
  flex: 1;
  min-width: 0;
}

.report-card__title {
  font-weight: 600;
  font-size: 14px;
  color: #1B1B1B;
}

.report-card__summary {
  font-size: 12px;
  color: #555;
  margin: 6px 0 4px;
  line-height: 1.5;
}

.report-card__meta {
  font-size: 10px;
  color: #999;
}

.report-card__actions {
  display: flex;
  flex-direction: column;
  gap: 6px;
  align-items: flex-end;
  flex-shrink: 0;
}

/* === Error === */
.error-banner {
  background: #fef2f2;
  border: 1px solid #fca5a5;
  color: #991b1b;
  padding: 10px 16px;
  border-radius: 6px;
  margin-bottom: 14px;
  font-size: 13px;
}

/* === Utilities === */
.text-secondary {
  color: #666;
  font-size: 12px;
}

.text-muted {
  color: #999;
  font-size: 11px;
}

.mb-0 { margin-bottom: 0; }
.mb-8 { margin-bottom: 8px; }
.mb-16 { margin-bottom: 16px; }

/* === Spinning animation for running step === */
@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

.spin {
  display: inline-block;
  animation: spin 1s linear infinite;
}

/* === Confirm dialog === */
.confirm-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.4);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 100;
}

.confirm-dialog {
  background: #fff;
  border-radius: 8px;
  padding: 24px;
  max-width: 400px;
  width: 90%;
  box-shadow: 0 8px 30px rgba(0, 0, 0, 0.2);
}

.confirm-dialog__title {
  font-size: 16px;
  font-weight: 600;
  margin-bottom: 8px;
}

.confirm-dialog__text {
  font-size: 13px;
  color: #555;
  margin-bottom: 20px;
}

.confirm-dialog__actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/App.css
git commit -m "feat: add App.css with Microsoft color scheme and layout styles"
```

---

### Task 9: Frontend — Create Sidebar component

**Files:**
- Create: `frontend/src/components/Sidebar.tsx`

- [ ] **Step 1: Create the Sidebar component**

Create `frontend/src/components/Sidebar.tsx`:

```tsx
import type { Page, AssessStep } from "../types";

interface Props {
  page: Page;
  assessStep: AssessStep;
  onNavigate: (page: Page) => void;
}

const STEPS: { key: AssessStep; label: string }[] = [
  { key: "input", label: "输入参数" },
  { key: "confirm", label: "确认任务" },
  { key: "running", label: "运行分析" },
  { key: "done", label: "查看结果" },
];

const STEP_ORDER: AssessStep[] = ["input", "confirm", "running", "done"];

function stepIndex(s: AssessStep): number {
  return STEP_ORDER.indexOf(s);
}

export function Sidebar({ page, assessStep, onNavigate }: Props) {
  const showStepper = page === "assess" && assessStep !== "input";
  const currentIdx = stepIndex(assessStep);

  return (
    <nav className="sidebar">
      <div className="sidebar-header">
        <div className="sidebar-logo">💊</div>
        药物靶点决策系统
      </div>

      <div
        className={`nav-item${page === "assess" ? " active" : ""}`}
        onClick={() => onNavigate("assess")}
      >
        📝 新建评估
      </div>
      <div
        className={`nav-item${page === "history" ? " active" : ""}`}
        onClick={() => onNavigate("history")}
      >
        📋 历史报告
      </div>
      <div
        className={`nav-item${page === "search" ? " active" : ""}`}
        onClick={() => onNavigate("search")}
      >
        🔍 知识检索
      </div>

      {showStepper && (
        <>
          <div className="nav-divider" />
          <div className="nav-section">当前评估</div>
          {STEPS.map((s, i) => {
            const idx = stepIndex(s.key);
            let dotClass = "step-dot step-dot--pending";
            let labelClass = "step-label step-label--pending";
            let dotContent: string = String(i + 1);

            if (idx < currentIdx) {
              dotClass = "step-dot step-dot--done";
              labelClass = "step-label step-label--done";
              dotContent = "✓";
            } else if (idx === currentIdx) {
              if (s.key === "running") {
                dotClass = "step-dot step-dot--running";
                dotContent = "⟳";
              } else {
                dotClass = "step-dot step-dot--current";
                dotContent = String(i + 1);
              }
              labelClass = "step-label step-label--current";
            }

            return (
              <div key={s.key} className="step-item">
                <div className={dotClass}>
                  {s.key === "running" && idx === currentIdx ? (
                    <span className="spin">{dotContent}</span>
                  ) : (
                    dotContent
                  )}
                </div>
                <span className={labelClass}>{s.label}</span>
              </div>
            );
          })}
        </>
      )}

      <div className="sidebar-spacer" />

      <div className="sidebar-footer">
        v{__APP_VERSION__}<br />
        更新: {new Date(__BUILD_TIME__).toLocaleString("zh-CN", {
          timeZone: "Asia/Shanghai",
          year: "numeric",
          month: "2-digit",
          day: "2-digit",
          hour: "2-digit",
          minute: "2-digit",
        })} CST
      </div>
    </nav>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/Sidebar.tsx
git commit -m "feat: add Sidebar component with nav, stepper, and version footer"
```

---

### Task 10: Frontend — Create RunningView component

**Files:**
- Create: `frontend/src/components/RunningView.tsx`

- [ ] **Step 1: Create the RunningView component**

Create `frontend/src/components/RunningView.tsx`:

```tsx
import type { PartialResultData } from "../types";

interface Props {
  target: string;
  indication: string;
  agentProgress: Record<string, string>;
  partialResults: Record<string, PartialResultData>;
}

const STAGE_LABELS: Record<string, string> = {
  knowledge_base: "知识库检索",
  literature: "📚 文献研究",
  clinical_trials: "🏥 临床试验分析",
  competition: "🏢 竞争情报",
  decision: "决策综合",
  saving: "保存结果",
};

const PARALLEL_AGENTS = ["literature", "clinical_trials", "competition"] as const;

function stageIcon(status: string | undefined): string {
  if (status === "completed") return "✅";
  if (status === "started") return "⏳";
  if (status === "failed") return "❌";
  return "⬜";
}

function completedCount(progress: Record<string, string>): number {
  return Object.values(progress).filter((s) => s === "completed").length;
}

function summarizeResult(stage: string, data: Record<string, unknown>): string {
  const summary =
    (data.summary as string) ||
    (data.overall_assessment as string) ||
    JSON.stringify(data).slice(0, 200);
  if (typeof summary === "string") return summary.slice(0, 200);
  return String(summary).slice(0, 200);
}

export function RunningView({ target, indication, agentProgress, partialResults }: Props) {
  const done = completedCount(agentProgress);
  const total = 6;

  return (
    <div>
      <div className="content-header">
        <div className="content-title">正在分析中...</div>
      </div>

      {/* Progress card */}
      <div className="progress-card">
        <div className="progress-header">
          <span style={{ fontSize: 14, fontWeight: 600 }}>
            {target}{indication ? ` - ${indication}` : ""}
          </span>
          <span className="text-muted">进度 {done}/{total}</span>
        </div>

        {/* Phase 1: Knowledge base */}
        <div className="progress-phase">
          <span style={{ fontSize: 16 }}>{stageIcon(agentProgress.knowledge_base)}</span>
          <span>{STAGE_LABELS.knowledge_base}</span>
          <span className="text-muted" style={{ marginLeft: "auto" }}>
            {agentProgress.knowledge_base === "completed" ? "完成" : agentProgress.knowledge_base === "started" ? "进行中..." : "等待中"}
          </span>
        </div>

        {/* Phase 2: Parallel agents */}
        <div className="parallel-agents">
          {PARALLEL_AGENTS.map((key) => {
            const status = agentProgress[key];
            let cardClass = "agent-card agent-card--waiting";
            let labelClass = "agent-card__label agent-card__label--waiting";
            let icon = "⬜";
            let statusText = "等待中";

            if (status === "completed") {
              cardClass = "agent-card agent-card--done";
              labelClass = "agent-card__label agent-card__label--done";
              icon = "✅";
              statusText = "完成";
            } else if (status === "started") {
              cardClass = "agent-card agent-card--running";
              labelClass = "agent-card__label agent-card__label--running";
              icon = "⏳";
              statusText = "进行中...";
            } else if (status === "failed") {
              cardClass = "agent-card agent-card--done";
              icon = "❌";
              statusText = "失败";
            }

            return (
              <div key={key} className={cardClass}>
                <div className="agent-card__icon">{icon}</div>
                <div className={labelClass}>{STAGE_LABELS[key]}</div>
                <div className="agent-card__status" style={{ color: status === "started" ? "#92400E" : status === "completed" ? "#166534" : "#999" }}>
                  {statusText}
                </div>
                {status === "started" && (
                  <div className="agent-card__progress-bar">
                    <div className="agent-card__progress-fill" style={{ width: "60%" }} />
                  </div>
                )}
              </div>
            );
          })}
        </div>

        {/* Phase 3: Decision */}
        <div className="progress-phase" style={{ opacity: agentProgress.decision ? 1 : 0.4 }}>
          <span style={{ fontSize: 16 }}>{stageIcon(agentProgress.decision)}</span>
          <span style={{ color: agentProgress.decision ? "#1B1B1B" : "#999" }}>{STAGE_LABELS.decision}</span>
          <span className="text-muted" style={{ marginLeft: "auto" }}>
            {agentProgress.decision === "completed" ? "完成" : agentProgress.decision === "started" ? "进行中..." : "等待中"}
          </span>
        </div>

        {/* Phase 4: Saving */}
        <div className="progress-phase" style={{ opacity: agentProgress.saving ? 1 : 0.4 }}>
          <span style={{ fontSize: 16 }}>{stageIcon(agentProgress.saving)}</span>
          <span style={{ color: agentProgress.saving ? "#1B1B1B" : "#999" }}>{STAGE_LABELS.saving}</span>
          <span className="text-muted" style={{ marginLeft: "auto" }}>
            {agentProgress.saving === "completed" ? "完成" : agentProgress.saving === "started" ? "进行中..." : "等待中"}
          </span>
        </div>
      </div>

      {/* Partial results */}
      {Object.keys(partialResults).length > 0 && (
        <>
          <div style={{ fontSize: 12, fontWeight: 600, color: "#555", marginBottom: 8 }}>
            已完成的分析结果
          </div>
          {Object.entries(partialResults).map(([stage, data]) => (
            <div key={stage} className="partial-result">
              <div className="partial-result__title">{STAGE_LABELS[stage] || stage}</div>
              <div className="partial-result__text">
                {summarizeResult(stage, data.result)}...
              </div>
            </div>
          ))}
        </>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/RunningView.tsx
git commit -m "feat: add RunningView with parallel agent cards and partial results"
```

---

### Task 11: Frontend — Create ResultsView component

**Files:**
- Create: `frontend/src/components/ResultsView.tsx`

- [ ] **Step 1: Create the ResultsView component**

Create `frontend/src/components/ResultsView.tsx`:

```tsx
import { useState } from "react";
import type { AssessmentResult } from "../types";
import { ResultCard } from "./ResultCard";
import { LiteratureTab } from "./LiteratureTab";
import { ClinicalTrialsTab } from "./ClinicalTrialsTab";
import { CompetitionTab } from "./CompetitionTab";
import { CitationList } from "./CitationList";
import { HistoricalContext } from "./HistoricalContext";

type Tab = "literature" | "trials" | "competition";

interface Props {
  result: AssessmentResult;
  onNewAssessment: () => void;
  onExportWord: () => void;
  onExportPdf: () => void;
  onExportMarkdown: () => void;
}

/** Safely convert a summary field to string */
function safeSummary(val: unknown): string {
  if (!val) return "";
  if (typeof val === "string") return val;
  if (typeof val === "object") {
    const obj = val as Record<string, unknown>;
    return (obj.overall_assessment as string) || (obj.summary as string) || JSON.stringify(val);
  }
  return String(val);
}

export function ResultsView({ result, onNewAssessment, onExportWord, onExportPdf, onExportMarkdown }: Props) {
  const [tab, setTab] = useState<Tab>("literature");

  return (
    <div>
      <div className="content-header">
        <div className="content-title">评估结果</div>
        <div className="btn-group">
          <button className="btn" onClick={onNewAssessment}>新建评估</button>
          <button className="btn" onClick={onExportWord}>导出 Word</button>
          <button className="btn" onClick={onExportPdf}>导出 PDF</button>
          <button className="btn" onClick={onExportMarkdown}>导出 Markdown</button>
        </div>
      </div>

      {/* Partial failures warning */}
      {result.partial_failures && result.partial_failures.length > 0 && (
        <div className="error-banner" style={{ background: "#fef3c7", borderColor: "#f59e0b", color: "#92400E" }}>
          <strong>警告：</strong>部分数据源出错，结果可能不完整。
          <ul style={{ margin: "8px 0 0", paddingLeft: 20 }}>
            {result.partial_failures.map((f, i) => (
              <li key={i} style={{ fontSize: "0.9em" }}>{f}</li>
            ))}
          </ul>
        </div>
      )}

      {/* Result card */}
      <ResultCard report={result.report} />

      {/* Historical context */}
      <HistoricalContext reports={result.knowledge_base_context?.historical_reports || []} />

      {/* Tab bar */}
      <div className="content-tabs">
        {([
          { key: "literature" as Tab, label: "📚 文献研究" },
          { key: "trials" as Tab, label: "🏥 临床试验" },
          { key: "competition" as Tab, label: "🏢 竞争分析" },
        ]).map((t) => (
          <div
            key={t.key}
            className={`content-tab${tab === t.key ? " content-tab--active" : ""}`}
            onClick={() => setTab(t.key)}
          >
            {t.label}
          </div>
        ))}
      </div>

      <div className="tab-panel">
        {tab === "literature" && (
          <LiteratureTab
            papers={Array.isArray(result.raw_outputs.literature?.papers) ? result.raw_outputs.literature.papers : []}
            summary={safeSummary(result.raw_outputs.literature?.summary)}
            decisionSummary={result.report.literature_summary || ""}
          />
        )}
        {tab === "trials" && (
          <ClinicalTrialsTab
            trials={Array.isArray(result.raw_outputs.clinical_trials?.trials) ? result.raw_outputs.clinical_trials.trials : []}
            summary={safeSummary(result.raw_outputs.clinical_trials?.summary)}
            decisionSummary={result.report.clinical_trials_summary || ""}
          />
        )}
        {tab === "competition" && (
          <CompetitionTab
            summary={safeSummary(result.raw_outputs.competition?.summary)}
            players={Array.isArray(result.raw_outputs.competition?.major_players) ? result.raw_outputs.competition.major_players : []}
            decisionSummary={result.report.competition_summary || ""}
          />
        )}
      </div>

      {/* Citations */}
      <div style={{ marginTop: 14 }}>
        <CitationList citations={result.report.citations || []} />
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/ResultsView.tsx
git commit -m "feat: add ResultsView component wrapping existing result tabs"
```

---

### Task 12: Frontend — Create HistoryPage component

**Files:**
- Create: `frontend/src/components/HistoryPage.tsx`

- [ ] **Step 1: Create the HistoryPage component**

Create `frontend/src/components/HistoryPage.tsx`:

```tsx
import { useEffect, useState } from "react";
import { fetchReports, deleteReport, exportWord } from "../api";
import type { ReportListItem } from "../types";

interface Props {
  onViewReport: (id: string, target: string) => void;
}

function badgeClass(rec: string): string {
  const r = rec.toLowerCase();
  if (r === "go") return "badge badge--go";
  if (r === "no-go" || r === "nogo") return "badge badge--nogo";
  return "badge badge--more";
}

function badgeLabel(rec: string): string {
  const r = rec.toLowerCase();
  if (r === "go") return "Go";
  if (r === "no-go" || r === "nogo") return "No-Go";
  return "需更多数据";
}

export function HistoryPage({ onViewReport }: Props) {
  const [reports, setReports] = useState<ReportListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [deleteConfirm, setDeleteConfirm] = useState<ReportListItem | null>(null);

  const loadReports = async () => {
    setLoading(true);
    setError("");
    try {
      const data = await fetchReports();
      setReports(data.reports);
    } catch (e: any) {
      setError(e.message || "加载失败");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadReports();
  }, []);

  const handleDelete = async (report: ReportListItem) => {
    try {
      await deleteReport(report.id, report.target);
      setReports((prev) => prev.filter((r) => r.id !== report.id));
    } catch (e: any) {
      alert("删除失败: " + (e.message || "未知错误"));
    }
    setDeleteConfirm(null);
  };

  const handleExport = async (report: ReportListItem) => {
    try {
      await exportWord(report.id, report.target);
    } catch {
      alert("导出失败，请稍后重试。");
    }
  };

  return (
    <div>
      <div className="content-header">
        <div className="content-title">历史评估报告</div>
      </div>

      {error && <div className="error-banner">{error}</div>}

      {loading && <div className="text-secondary">加载中...</div>}

      {!loading && reports.length === 0 && !error && (
        <div className="text-secondary">暂无历史报告。</div>
      )}

      {reports.map((report) => (
        <div
          key={report.id}
          className="card card-clickable"
          onClick={() => onViewReport(report.id, report.target)}
        >
          <div className="report-card">
            <div className="report-card__body">
              <div className="report-card__title">
                {report.target}{report.indication ? ` - ${report.indication}` : ""}
              </div>
              <div className="report-card__summary">{report.summary || "暂无摘要"}</div>
              <div className="report-card__meta">
                {report.created_at ? new Date(report.created_at).toLocaleDateString("zh-CN") : ""}
                {report.score != null ? ` | 综合评分: ${report.score}` : ""}
              </div>
            </div>
            <div className="report-card__actions">
              {report.recommendation && (
                <span className={badgeClass(report.recommendation)}>
                  {badgeLabel(report.recommendation)}
                </span>
              )}
              <button
                className="btn"
                onClick={(e) => { e.stopPropagation(); handleExport(report); }}
              >
                导出
              </button>
              <button
                className="btn btn-danger"
                onClick={(e) => { e.stopPropagation(); setDeleteConfirm(report); }}
              >
                删除
              </button>
            </div>
          </div>
        </div>
      ))}

      {/* Delete confirmation dialog */}
      {deleteConfirm && (
        <div className="confirm-overlay" onClick={() => setDeleteConfirm(null)}>
          <div className="confirm-dialog" onClick={(e) => e.stopPropagation()}>
            <div className="confirm-dialog__title">确认删除</div>
            <div className="confirm-dialog__text">
              确定要删除「{deleteConfirm.target}{deleteConfirm.indication ? ` - ${deleteConfirm.indication}` : ""}」的评估报告吗？此操作不可撤销。
            </div>
            <div className="confirm-dialog__actions">
              <button className="btn" onClick={() => setDeleteConfirm(null)}>取消</button>
              <button
                className="btn btn-danger"
                style={{ background: "#ef4444", color: "#fff", borderColor: "#ef4444" }}
                onClick={() => handleDelete(deleteConfirm)}
              >
                删除
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/HistoryPage.tsx
git commit -m "feat: add HistoryPage with report list, export, and delete"
```

---

### Task 13: Frontend — Create SearchPage component

**Files:**
- Create: `frontend/src/components/SearchPage.tsx`

- [ ] **Step 1: Create the SearchPage component**

Create `frontend/src/components/SearchPage.tsx`:

```tsx
import { useState } from "react";
import { searchKnowledge } from "../api";
import type { SearchResultItem } from "../types";

interface Props {
  onViewReport: (id: string, target: string) => void;
}

function badgeClass(rec: string): string {
  const r = rec.toLowerCase();
  if (r === "go") return "badge badge--go";
  if (r === "no-go" || r === "nogo") return "badge badge--nogo";
  return "badge badge--more";
}

function badgeLabel(rec: string): string {
  const r = rec.toLowerCase();
  if (r === "go") return "Go";
  if (r === "no-go" || r === "nogo") return "No-Go";
  return "需更多数据";
}

export function SearchPage({ onViewReport }: Props) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<SearchResultItem[]>([]);
  const [count, setCount] = useState<number | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const handleSearch = async () => {
    if (!query.trim()) return;
    setLoading(true);
    setError("");
    try {
      const data = await searchKnowledge(query.trim());
      setResults(data.results);
      setCount(data.count);
    } catch (e: any) {
      setError(e.message || "搜索失败");
    } finally {
      setLoading(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter") handleSearch();
  };

  return (
    <div>
      <div className="content-header">
        <div className="content-title">知识库检索</div>
      </div>

      <div className="search-box">
        <input
          className="search-input"
          placeholder="输入搜索关键词，例如：EGFR 耐药机制"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={handleKeyDown}
        />
        <button className="btn btn-primary" style={{ padding: "10px 24px", fontSize: 14 }} onClick={handleSearch} disabled={loading}>
          {loading ? "搜索中..." : "搜索"}
        </button>
      </div>

      {error && <div className="error-banner">{error}</div>}

      {count !== null && (
        <div className="text-secondary mb-16">找到 {count} 条相关记录</div>
      )}

      {results.map((item) => (
        <div
          key={item.id}
          className="card card-clickable"
          onClick={() => onViewReport(item.id, item.target)}
        >
          <div className="report-card">
            <div className="report-card__body">
              <div className="report-card__title">
                {item.target}{item.indication ? ` - ${item.indication}` : ""}
              </div>
              <div className="report-card__summary">{item.summary || "暂无摘要"}</div>
              <div className="report-card__meta">
                {item.created_at ? new Date(item.created_at).toLocaleDateString("zh-CN") : ""}
                {item.score != null ? ` | 相关度: ${item.score.toFixed(2)}` : ""}
              </div>
            </div>
            {item.recommendation && (
              <span className={badgeClass(item.recommendation)}>
                {badgeLabel(item.recommendation)}
              </span>
            )}
          </div>
        </div>
      ))}
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/SearchPage.tsx
git commit -m "feat: add SearchPage with knowledge base search"
```

---

### Task 14: Frontend — Rewrite App.tsx with sidebar layout and page routing

This is the main integration task that ties everything together. The existing `App.tsx` is completely replaced with the new layout shell.

**Files:**
- Modify: `frontend/src/App.tsx`

- [ ] **Step 1: Rewrite App.tsx**

Replace the entire contents of `frontend/src/App.tsx` with:

```tsx
import { useState } from "react";
import "./App.css";
import {
  parseAssessment,
  confirmAssessmentSSE,
  exportMarkdown,
  exportWord,
  exportPdf,
  fetchReport,
} from "./api";
import type {
  AssessmentResult,
  ParseResult,
  ParsedInput,
  Page,
  AssessStep,
  PartialResultData,
} from "./types";
import { Sidebar } from "./components/Sidebar";
import { SearchForm } from "./components/SearchForm";
import { ConfirmationPanel } from "./components/ConfirmationPanel";
import { RunningView } from "./components/RunningView";
import { ResultsView } from "./components/ResultsView";
import { HistoryPage } from "./components/HistoryPage";
import { SearchPage } from "./components/SearchPage";

export default function App() {
  // Page routing
  const [page, setPage] = useState<Page>("assess");
  const [assessStep, setAssessStep] = useState<AssessStep>("input");

  // Assessment state
  const [parseResult, setParseResult] = useState<ParseResult | null>(null);
  const [result, setResult] = useState<AssessmentResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [agentProgress, setAgentProgress] = useState<Record<string, string>>({});
  const [partialResults, setPartialResults] = useState<Record<string, PartialResultData>>({});

  const handleNavigate = (p: Page) => {
    setPage(p);
    setError("");
  };

  const handleReset = () => {
    setPage("assess");
    setAssessStep("input");
    setResult(null);
    setParseResult(null);
    setError("");
    setAgentProgress({});
    setPartialResults({});
  };

  const handleSubmit = async (
    target: string,
    indication: string,
    synonyms: string,
    focus: string,
    timeRange: string,
  ) => {
    setLoading(true);
    setError("");
    setResult(null);
    setParseResult(null);
    try {
      const data = await parseAssessment(target, indication, synonyms, focus, timeRange);
      setParseResult(data);
      setAssessStep("confirm");
    } catch (e: any) {
      setError(e.message || "解析失败");
    } finally {
      setLoading(false);
    }
  };

  const handleConfirm = async (modified: ParsedInput) => {
    setLoading(true);
    setError("");
    setAssessStep("running");
    setAgentProgress({});
    setPartialResults({});
    try {
      const data = await confirmAssessmentSSE(modified, (event) => {
        if (event.event === "status") {
          setAgentProgress((prev) => ({
            ...prev,
            [event.data.stage]: event.data.status,
          }));
        }
        if (event.event === "partial_result") {
          setPartialResults((prev) => ({
            ...prev,
            [event.data.stage]: event.data,
          }));
        }
      });
      setResult(data);
      setAssessStep("done");
    } catch (e: any) {
      setError(e.message || "评估失败");
      setAssessStep("confirm");
    } finally {
      setLoading(false);
    }
  };

  const handleBack = () => {
    setAssessStep("input");
    setParseResult(null);
    setError("");
  };

  const handleViewReport = async (id: string, target: string) => {
    setLoading(true);
    setError("");
    try {
      const data = await fetchReport(id, target);
      setResult(data);
      setPage("assess");
      setAssessStep("done");
    } catch (e: any) {
      setError(e.message || "加载报告失败");
    } finally {
      setLoading(false);
    }
  };

  const handleExportMarkdown = async () => {
    if (!result) return;
    try {
      const md = await exportMarkdown(result.report.report_id || result.report.target, result.report.target);
      const blob = new Blob([md], { type: "text/markdown" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${result.report.target}_report.md`;
      a.click();
      URL.revokeObjectURL(url);
    } catch {
      alert("Markdown 导出失败，报告可能尚未保存。");
    }
  };

  const handleExportWord = async () => {
    if (!result) return;
    try {
      await exportWord(result.report.report_id || result.report.target, result.report.target);
    } catch {
      alert("Word 导出失败，报告可能尚未保存。");
    }
  };

  const handleExportPdf = async () => {
    if (!result) return;
    try {
      await exportPdf(result.report.report_id || result.report.target, result.report.target);
    } catch {
      alert("PDF 导出失败，报告可能尚未保存。");
    }
  };

  return (
    <div className="app-layout">
      <Sidebar page={page} assessStep={assessStep} onNavigate={handleNavigate} />

      <main className="main-content">
        {error && <div className="error-banner">{error}</div>}

        {/* Assess Page */}
        {page === "assess" && assessStep === "input" && (
          <div>
            <div className="content-header">
              <div className="content-title">新建靶点评估</div>
            </div>
            <div className="card">
              <SearchForm onSubmit={handleSubmit} loading={loading} />
            </div>
          </div>
        )}

        {page === "assess" && assessStep === "confirm" && parseResult && (
          <div>
            <div className="content-header">
              <div className="content-title">确认评估参数</div>
            </div>
            <ConfirmationPanel
              parseResult={parseResult}
              onConfirm={handleConfirm}
              onBack={handleBack}
              loading={loading}
            />
          </div>
        )}

        {page === "assess" && assessStep === "running" && parseResult && (
          <RunningView
            target={parseResult.parsed.target}
            indication={parseResult.parsed.indication}
            agentProgress={agentProgress}
            partialResults={partialResults}
          />
        )}

        {page === "assess" && assessStep === "done" && result && (
          <ResultsView
            result={result}
            onNewAssessment={handleReset}
            onExportWord={handleExportWord}
            onExportPdf={handleExportPdf}
            onExportMarkdown={handleExportMarkdown}
          />
        )}

        {/* History Page */}
        {page === "history" && (
          <HistoryPage onViewReport={handleViewReport} />
        )}

        {/* Search Page */}
        {page === "search" && (
          <SearchPage onViewReport={handleViewReport} />
        )}
      </main>
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/App.tsx frontend/src/App.css
git commit -m "feat: rewrite App.tsx with sidebar layout and page-based routing"
```

---

### Task 15: Frontend — Build verification

**Files:**
- No file changes — verification only

- [ ] **Step 1: Run TypeScript compiler to check for type errors**

```bash
cd frontend && npx tsc --noEmit
```

Expected: No errors. If there are errors, fix them.

- [ ] **Step 2: Run Vite build**

```bash
cd frontend && npm run build
```

Expected: Build succeeds, outputs to `frontend/dist/`.

- [ ] **Step 3: Fix any build errors**

If there are TypeScript or build errors, fix them and re-run. Common issues:
- Missing imports (check all new component imports in App.tsx)
- Type mismatches between new types and existing components
- The `__APP_VERSION__` and `__BUILD_TIME__` globals need the `env.d.ts` declarations from Task 5

- [ ] **Step 4: Commit any fixes**

```bash
git add -A
git commit -m "fix: resolve build errors from UI redesign"
```

---

### Task 16: Backend — Verification

**Files:**
- No file changes — verification only

- [ ] **Step 1: Check Python syntax**

```bash
cd backend && python -c "from app.main import app; print('OK')"
```

Expected: `OK` (imports succeed). If there are import errors, fix them.

- [ ] **Step 2: Run existing tests**

```bash
cd backend && python -m pytest tests/ -v --timeout=30 2>&1 | head -50
```

Expected: Existing tests still pass. New endpoints don't break anything since they use separate routes.

- [ ] **Step 3: Fix any test failures**

If tests fail due to the changes, fix and commit.

- [ ] **Step 4: Commit any fixes**

```bash
git add -A
git commit -m "fix: resolve backend issues from new endpoints"
```
