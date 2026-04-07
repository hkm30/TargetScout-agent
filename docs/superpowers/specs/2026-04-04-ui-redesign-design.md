# UI Redesign: Left Navigation + Microsoft Color Scheme

## Overview

Restructure the Drug Target Decision Support System frontend from a single-column layout to a left sidebar navigation + right main content area layout, with Microsoft official website color scheme.

## Architecture

### Layout Structure

```
┌──────────────────────────────────────────────────┐
│ Full-width app container (100vw × 100vh)         │
├────────────┬─────────────────────────────────────┤
│            │                                     │
│  Sidebar   │         Main Content Area           │
│  (240px)   │         (flex: 1)                   │
│            │                                     │
│  ┌──────┐  │  ┌─────────────────────────────┐    │
│  │ Logo │  │  │  Page Title    [Actions]    │    │
│  │ +Title│  │  ├─────────────────────────────┤    │
│  ├──────┤  │  │                             │    │
│  │ Nav  │  │  │     Page-specific content   │    │
│  │ Items│  │  │                             │    │
│  ├──────┤  │  │                             │    │
│  │Stepper│  │  │                             │    │
│  │(动态) │  │  │                             │    │
│  ├──────┤  │  │                             │    │
│  │Version│  │  │                             │    │
│  └──────┘  │  └─────────────────────────────┘    │
└────────────┴─────────────────────────────────────┘
```

### Color Scheme (Microsoft Official)

| Token | Value | Usage |
|-------|-------|-------|
| Primary Blue | `#0078D4` | Buttons, active states, links, progress bars |
| Primary Blue Hover | `#106EBE` | Button hover state |
| Sidebar BG | `#1B1B1B` | Left navigation background |
| Sidebar Active BG | `rgba(0,120,212,0.15)` | Active nav item background |
| Sidebar Active Text | `#60CDFF` | Active nav item text color |
| Sidebar Active Border | `#0078D4` | Active nav item left border (3px) |
| Sidebar Text | `#CCCCCC` | Inactive nav item text |
| Sidebar Section Label | `#888888` | Section headers (uppercase) |
| Sidebar Divider | `#333333` | Horizontal dividers |
| Content BG | `#F5F5F5` | Main content area background |
| Card BG | `#FFFFFF` | Card/panel background |
| Card Shadow | `0 1px 4px rgba(0,0,0,0.08)` | Card elevation |
| Text Primary | `#1B1B1B` | Headings, primary text |
| Text Secondary | `#666666` | Secondary/descriptive text |
| Text Muted | `#999999` | Metadata, timestamps |
| Border | `#D1D5DB` | Input borders, tab borders |
| Go Badge | `#22C55E` | Go recommendation |
| No-Go Badge | `#EF4444` | No-Go recommendation |
| Need-More Badge | `#F59E0B` | Need More Data recommendation |
| Font Family | `Segoe UI, system-ui, -apple-system, sans-serif` | All text |

## Pages & Components

### 1. Sidebar Navigation (Persistent)

The sidebar is always visible across all pages.

**Structure (top to bottom):**

1. **Header**: App logo (24×24 blue rounded square with 💊) + title "药物靶点决策系统"
2. **Page Navigation**:
   - 📝 新建评估 (default active)
   - 📋 历史报告
   - 🔍 知识检索
3. **Divider** (only visible during/after an assessment)
4. **Dynamic Progress Stepper** (only visible during/after an assessment):
   - "当前评估" section label
   - Step 1: 输入参数
   - Step 2: 确认任务
   - Step 3: 运行分析
   - Step 4: 查看结果
   - Each step has a dot indicator: done (blue ✓), current (blue number), pending (gray number)
5. **Spacer** (fills remaining vertical space)
6. **Footer**: Version number + update timestamp (e.g., "v0.1.0 · 更新: 2026-04-03 14:30 CST")

**Version info source**: Injected via Vite build-time environment variables (`VITE_APP_VERSION`, `VITE_BUILD_TIME`).

### 2. New Assessment Page (新建评估)

**Right content area contains:**
- Page title: "新建靶点评估"
- A card with the SearchForm: target, indication, synonyms, time range, focus fields
- Primary button: "开始分析"

After submission → transitions to **Confirmation view** (same page, replaces form with ConfirmationPanel).
After confirmation → transitions to **Running view**.

### 3. Running Status View (运行中)

**Left sidebar**: Stepper shows step 3 "运行分析" as current (amber spinning icon).

**Right content area** (progress + real-time partial results):

Top section — progress card reflecting the actual pipeline structure:
- Target name + indication + overall progress (X/6)
- **Phase 1** (sequential): 知识库检索 — single row with status icon
- **Phase 2** (parallel): 文献研究 / 临床试验分析 / 竞争情报 — displayed as **three horizontal cards side by side**, each with its own status icon, label, and bottom progress bar. This visually communicates that the three agents run simultaneously.
  - Completed agent: green background (#F0FDF4), green border, ✅ icon
  - Running agent: amber background (#FFFBEB), amber border, ⏳ icon, animated bottom progress bar
  - Waiting agent: gray background, ⬜ icon
- **Phase 3** (sequential): 决策综合 — single row, grayed out until phase 2 completes
- **Phase 4** (sequential): 保存结果 — single row, grayed out until phase 3 completes

Bottom section — real-time partial results:
- Section title: "已完成的分析结果"
- As each research agent completes, its result preview card appears with a green left border
- Incomplete stages show as grayed-out skeleton cards
- Cards display: stage icon + name, brief summary text from the agent result

**Backend change required**: The SSE stream currently only emits `status` events. To support partial result previews, add a new `partial_result` event type that includes the agent's output data when each stage completes:
```
event: partial_result
data: {"stage": "literature", "result": { ... agent output ... }}
```

After all stages complete → auto-transitions to **Results view**.

### 4. Results Page (评估结果)

**Left sidebar**: Stepper shows step 4 "查看结果" as current, all previous steps done.

**Right content area:**

Top bar:
- Title: "评估结果"
- Action buttons (right-aligned): "新建评估", "导出 Word", "导出 PDF", "导出 Markdown"

Result summary card:
- Recommendation badge (GO / No-Go / 需更多数据) with color coding
- Target name + indication
- Score + confidence level

Historical context (if available): HistoricalContext component (existing)

Horizontal tab bar:
- 📚 文献研究 | 🏥 临床试验 | 🏢 竞争分析
- Active tab: blue bottom border + blue text
- Tab content panel below with existing tab components (LiteratureTab, ClinicalTrialsTab, CompetitionTab)

Citations: CitationList component at the bottom (existing)

### 5. Historical Reports Page (历史报告)

**New page** — displays all past assessment reports from the knowledge base.

**Right content area:**
- Page title: "历史评估报告"
- Report cards in a vertical list, each card showing:
  - Target name + indication (bold title)
  - Summary text (truncated to ~200 chars)
  - Created date + score
  - Recommendation badge (Go / No-Go / 需更多数据)
  - **Two action buttons** (right side of card or bottom-right):
    - "导出" — exports the report (Word format, uses existing export API)
    - "删除" — deletes the report from knowledge base (with confirmation dialog)
- Clicking a card (outside the action buttons) fetches the full report via `GET /api/reports/{id}` and displays it in the results view (switches to assess page in "done" state with the loaded report data)

**Backend API needed**:
- `GET /api/reports` — list all reports (from Cosmos DB), sorted by `created_at` descending
- `GET /api/reports/{id}` — fetch a single report's full data (from Cosmos DB), including raw outputs for tab display
- `DELETE /api/reports/{id}` — delete a report from Cosmos DB, Blob Storage, and AI Search index (with confirmation dialog on frontend)

### 6. Knowledge Search Page (知识检索)

**New page** — standalone search interface for the Azure AI Search knowledge base.

**Right content area:**
- Page title: "知识库检索"
- Search bar: text input + "搜索" primary button
- Result count: "找到 X 条相关记录"
- Result cards: same format as historical reports (target, indication, summary, date, relevance score, recommendation badge)
- Clicking a result card fetches the full report via `GET /api/reports/{id}` and displays it in the results view

**Backend API**: Uses existing `search_knowledge_base()` function. Need a new endpoint:
- `POST /api/knowledge/search` — accepts `{ query: string, top_k?: number }`, returns search results

## State Management

Transition from step-based state to **page-based routing** using React state (no React Router needed, keeping it simple):

```typescript
type Page = "assess" | "history" | "search";
type AssessStep = "input" | "confirm" | "running" | "done";
```

- `page` controls which page nav item is active and what the right content area shows
- `assessStep` controls the stepper state within the assessment workflow
- The stepper section in the sidebar is only visible when `page === "assess"` and `assessStep !== "input"`

## Component Structure

```
App.tsx (layout shell: sidebar + content area)
├── Sidebar.tsx (new)
│   ├── Nav items (page switching)
│   ├── ProgressStepper.tsx (new, dynamic)
│   └── Version footer
├── AssessPage.tsx (new, wraps existing assessment flow)
│   ├── SearchForm.tsx (existing)
│   ├── ConfirmationPanel.tsx (existing)
│   ├── RunningView.tsx (new, progress + partial results)
│   └── ResultsView.tsx (new, wraps existing result components)
│       ├── ResultCard.tsx (existing)
│       ├── LiteratureTab.tsx (existing)
│       ├── ClinicalTrialsTab.tsx (existing)
│       ├── CompetitionTab.tsx (existing)
│       ├── CitationList.tsx (existing)
│       └── HistoricalContext.tsx (existing)
├── HistoryPage.tsx (new)
│   └── ReportCard.tsx (new, with delete + export buttons)
└── SearchPage.tsx (new)
```

## Styling Approach

Migrate from inline styles to a CSS file (`App.css`) for:
- Sidebar layout and theme colors
- Shared card/button/input styles
- Page layout (flexbox)

Keep inline styles for component-specific dynamic values (e.g., badge colors based on recommendation).

## Backend Changes

1. **SSE partial_result event**: In `run_full_pipeline_stream()`, yield `partial_result` events containing agent output data after each stage completes.

2. **New endpoints**:
   - `GET /api/reports` — list all reports from Cosmos DB, sorted by `created_at` descending
   - `GET /api/reports/{id}` — fetch a single report's full data including raw outputs
   - `DELETE /api/reports/{id}` — delete a report from Cosmos DB, Blob Storage, and AI Search index
   - `POST /api/knowledge/search` — search knowledge base, accepts `{ query: string, top_k?: number }`

3. **Version endpoint** (optional): Add version info to `/api/health` response, or inject via Vite env vars at build time.

## Migration Strategy

- Existing components (SearchForm, ConfirmationPanel, ResultCard, LiteratureTab, etc.) are reused as-is inside the new layout structure
- The main refactor is in `App.tsx` — replacing the single-column layout with the sidebar + content area shell
- New components: Sidebar, ProgressStepper, RunningView, ResultsView, HistoryPage, SearchPage, ReportCard
- Inline styles in existing components will be gradually migrated to CSS classes for consistency, but this is not blocking — existing components work inside the new layout without style changes
