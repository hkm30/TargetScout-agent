# 私有文档上传与知识库集成 - 设计文档

**日期**: 2026-04-07（更新于 2026-04-10）
**状态**: Implemented

## 概述

在"新建靶点评估"流程中，允许用户上传私有文档（PDF/Word/TXT/Markdown），将文档内容与互联网搜索结果综合分析，并将文档持久化存入知识库供后续检索。

## 需求

1. 用户在"新建靶点评估"时可上传最多 5 个私有文档，单文件不超过 10MB
2. 支持格式：PDF、Word (.docx)、TXT、Markdown (.md)
3. 文档提取的文本作为额外上下文注入到文献/临床/竞争 3 个 Agent 的 prompt 中
4. 原文件存储到 Blob Storage，文本分块向量化存入 AI Search
5. 私有文档在"知识库检索"页面也可被语义搜索命中
6. ConfirmationPanel 新增"其他建议"输入框和"取消"按钮

## 整体数据流

```
用户在"新建靶点评估"页面上传文档（最多5个，PDF/Word/TXT/MD）
         ↓
Frontend: multipart POST → /api/documents/upload
         ↓
Backend（快速路径，~1s）:
  1. 校验文件格式 + 大小
  2. SHA-256 内容哈希去重（检查内存 + Cosmos DB）
  3. 文件内容暂存服务器内存（不触碰 Blob/Cosmos/AI Search）
  4. 返回 status: "pending"（或 "duplicate" 如果重复）
         ↓
用户点击"确认并运行"时（confirm 阶段）:
  文档处理与知识库检索并行执行（asyncio.gather）:
  ├── 知识库检索: search_knowledge_base()
  └── 文档处理（每个 pending 文档）:
      1. 原文件 → Blob Storage (private-documents 容器)
      2. PDF/Word → Azure Document Intelligence (prebuilt-read) 解析
         TXT/MD → 直接读取文本
      3. LLM 生成两级摘要（摘要 + 总结）
      4. 文本分块 → text-embedding-3-large 向量化
      5. 分块 + 向量 → AI Search (documents 索引)
      6. 元数据 → Cosmos DB (documents 容器)
         ↓
  两个并行任务完成后:
  - 文档摘要 + 用户"其他建议" 注入 3 个 Agent 的 prompt
  - 3 个 Agent 结合 私有文档 + 网络搜索 综合分析
  - 决策 Agent 汇总时也能看到私有文档摘要和用户建议
         ↓
评估完成后：
  - 报告记录中关联已上传的文档 ID
  - 文档在知识库中持久保存，知识库检索页面可查询

用户取消时:
  - 仅清理服务器内存中的文件内容
  - 不留任何 Azure 服务残留（Blob/Cosmos/AI Search 未被触碰）
```

### 设计要点：延迟处理（Deferred Processing）

文档的重处理（Blob 上传、文本提取、LLM 摘要、分块索引）从上传阶段推迟到确认运行阶段。原因：
1. **用户体验**：上传即时返回（~1s），不必等待 30-60s 的 PDF 解析
2. **资源节约**：用户可能上传后取消，延迟处理避免无谓消耗
3. **并行化**：文档处理与知识库检索并行执行，不增加总体等待时间

### 设计要点：内容去重（Content Deduplication）

基于 SHA-256 文件内容哈希实现去重：
1. 上传时计算哈希，先查内存中的 pending 文件，再查 Cosmos DB 已处理文件
2. 重复文件返回 `status: "duplicate"` + 已有文档的摘要和元数据
3. 重复文档仍可进入评估流程，复用已有的分析结果
4. 前端对重复文档不执行后端删除（保护已有数据）

## 后端设计

### 新增模块

```
backend/app/
├── documents/                    # 新增：文档处理模块
│   ├── parser.py                 # Azure Document Intelligence 调用 + TXT/MD 直读
│   ├── chunker.py                # 文本分块策略
│   └── router.py                 # 文档相关 API 路由
├── knowledge/
│   ├── search_client.py          # 修改：新增 documents 索引的 CRUD + 联合搜索
│   ├── blob_client.py            # 修改：新增 private-documents 容器的上传/下载
│   └── embedding.py              # 复用：为文档分块生成向量
├── agents/
│   ├── orchestrator.py           # 修改：注入文档上下文 + 用户建议到 Agent prompt
│   └── definitions.py            # 修改：Agent instructions 增加私有文档引用说明
└── config.py                     # 修改：新增 Document Intelligence 相关配置
```

### 新增 API 端点

| 端点 | 方法 | 功能 |
|------|------|------|
| `/api/documents/upload` | POST | multipart 上传文档，验证 + 去重 + 暂存内存，返回 pending/duplicate 状态 |
| `/api/documents/{id}` | GET | 获取文档详情（元数据 + 分块摘要） |
| `/api/documents/{id}` | DELETE | 删除文档（Blob + AI Search 分块） |

### 文档解析策略 (parser.py)

- **PDF / Word (.docx)** → 调用 Azure Document Intelligence（prebuilt-read 模型），擅长处理复杂排版、表格、扫描件
- **TXT / Markdown (.txt / .md)** → 直接读取文本内容，不需要 Document Intelligence

流程（上传阶段 — 快速路径）：
```
上传文件 (multipart)
  ↓
校验：格式(pdf/docx/txt/md) + 大小(≤10MB) + 数量(≤5)
  ↓
SHA-256 哈希去重：检查内存 pending → 检查 Cosmos DB
  ↓
重复 → 返回 duplicate + 已有元数据
新文件 → 暂存内存 {content, file_name, content_hash}
  ↓
返回 status: "pending"（~1s）
```

流程（确认阶段 — process_pending_document()）：
```
从内存取出文件内容
  ↓
原文件 → Blob Storage
  ↓
TXT/MD → 直接读取文本
PDF/Word → Azure Document Intelligence (prebuilt-read)
  ↓
LLM 生成两级摘要：
  - 摘要（3000-5000 tokens）：详细提炼
  - 总结（1000-2000 tokens）：精炼概要
  ↓
文本分块 → 向量化 → AI Search 索引
  ↓
元数据写入 Cosmos DB，status → "ready"
```

### 分块策略 (chunker.py)

- 按段落优先切分，超长段落按 token 窗口切分
- 每块约 500-800 tokens，相邻块重叠 100 tokens
- 每块保留元数据：文档 ID、文件名、块序号、所在页码

### AI Search documents 索引 schema

```json
{
  "id": "chunk_id (doc_id_chunk_index)",
  "document_id": "关联的文档 UUID",
  "file_name": "原始文件名",
  "target": "关联靶点（可选，来自评估表单）",
  "indication": "关联适应症（可选，来自评估表单）",
  "content": "分块文本内容（全文搜索）",
  "content_vector": "向量 3072 维 (text-embedding-3-large)",
  "chunk_index": "块序号 (int)",
  "page_number": "页码 (int, 可选)",
  "source_type": "private_document (固定值，用于区分历史报告)",
  "created_at": "上传时间 ISO-8601"
}
```

### orchestrator.py 修改

在 `run_full_pipeline_stream()` 中：

1. **并行执行**（Step 1）：知识库检索与文档处理通过 `asyncio.create_task` 并行运行
2. 文档处理调用 `process_pending_document()`：从内存取文件 → Blob → 提取 → 摘要 → 分块索引
3. 两者完成后，将文档的**摘要 + 总结 + 用户建议**注入到 3 个 Agent 的 prompt 前缀中：

```
## 用户提供的私有文档参考资料

### 文档1: filename.pdf

#### 总结
（1000-2000 tokens 精炼概要）

#### 摘要
（3000-5000 tokens 详细提炼）

### 文档2: report.docx

#### 总结
（1000-2000 tokens 精炼概要）

#### 摘要
（3000-5000 tokens 详细提炼）

## 用户补充建议
请关注该靶点在耐药性方面的最新进展，特别是T790M突变...

请结合以上私有文档和用户建议，与你的网络搜索结果进行综合分析。
```

### /api/assess/parse 和 /api/assess/confirm 修改

- `parse` 请求体新增 `document_ids: list[str]`（可选）
- `confirm` 请求体新增 `document_ids: list[str]`（可选）和 `user_suggestions: str`（可选）
- 评估完成后，Cosmos DB 报告记录中新增 `document_ids` 字段关联上传的文档

### /api/knowledge/search 修改

- 同时查询 reports 索引和 documents 索引
- 搜索结果合并返回，每条结果标注 `source_type`（"report" 或 "private_document"）

### config.py 新增配置

| 环境变量 | 用途 | 默认值 |
|----------|------|--------|
| `AZURE_DOC_INTELLIGENCE_ENDPOINT` | Document Intelligence 端点 | 必填 |
| `AZURE_DOC_INTELLIGENCE_KEY` | Document Intelligence API Key（也支持 Managed Identity，与其他服务一致） | 可选 |
| `BLOB_DOCUMENTS_CONTAINER` | 私有文档 Blob 容器名 | "private-documents" |
| `DOC_MAX_FILE_SIZE_MB` | 单文件大小上限 | 10 |
| `DOC_MAX_FILE_COUNT` | 单次上传文件数上限 | 5 |

## 前端设计

### SearchForm.tsx 修改

在现有表单底部新增文档上传区域：

```
┌─────────────────────────────────────┐
│  靶点名称:  [______________]        │
│  适应症:    [______________]        │
│  同义词:    [______________]        │
│  关注领域:  [______________]        │
│  时间范围:  [______________]        │
│                                     │
│  ┌─ 上传私有文档（可选）──────────┐ │
│  │  拖拽文件到此处或点击上传      │ │
│  │  支持 PDF/Word/TXT/Markdown    │ │
│  │  最多5个文件，单文件 ≤ 10MB    │ │
│  │                                │ │
│  │  ✓ report.pdf      (2.3MB)  ✕ │ │
│  │  ✓ study.docx      (1.1MB)  ✕ │ │
│  │  ⏳ notes.txt       解析中... │ │
│  └────────────────────────────────┘ │
│                                     │
│         [ 开始评估 ]                │
└─────────────────────────────────────┘
```

交互：
1. 用户选择/拖拽文件 → 立即上传到 `/api/documents/upload`（~1s 返回）
2. 返回后显示 ✓ + 文件名 + 大小 + "已上传"（pending 状态，绿色背景）
3. 重复文件显示 ✓ + "xxx文件已经上传过"（duplicate 状态，黄色背景）
4. 可点击 ✕ 移除文件（pending 文件清理内存，duplicate 文件不删后端数据）
5. 上传的文档 ID 列表（pending + duplicate + ready）随表单一起传给 `/api/assess/parse`

### ConfirmationPanel.tsx 修改

```
┌─ 确认评估信息 ──────────────────────┐
│  靶点: EGFR    适应症: 非小细胞肺癌  │
│  同义词: ErbB1, HER1               │
│  关注领域: 文献 + 临床 + 竞争       │
│  时间范围: 近5年                    │
│                                     │
│  已上传文档:                        │
│   ✓ report.pdf (2.3MB)          ✕  │
│   ✓ study.docx (1.1MB)          ✕  │
│                                     │
│  子任务计划:                        │
│   1. 文献研究  2. 临床试验  3. 竞争  │
│                                     │
│  历史相关评估:                      │
│   - EGFR/NSCLC (2025-12-01)        │
│                                     │
│  其他建议（可选）:                   │
│  ┌────────────────────────────────┐ │
│  │ 请关注该靶点在耐药性方面的最新  │ │
│  │ 进展，特别是T790M突变...       │ │
│  └────────────────────────────────┘ │
│                                     │
│  [确认并运行]  [返回修改]  [取消]   │
└─────────────────────────────────────┘
```

改动点：
- 新增已上传文档列表展示（可移除）
- 新增"其他建议"多行文本输入框（可选），内容作为 `user_suggestions` 传给后端
- 新增"取消"按钮，和"确认并运行"、"返回修改"并列，按钮顺序：[确认并运行] [返回修改] [取消]
- 点击"取消"放弃本次评估，回到初始页面

### ResultsView.tsx 修改

各 Tab 输出如果引用了私有文档内容，标注来源为"私有文档: filename.pdf"，与 PubMed / ClinicalTrials / Web 来源做区分。

### SearchPage.tsx（知识库检索）修改

搜索结果列表中增加来源类型标签：
- 现有结果标记为"历史报告"
- 私有文档分块结果标记为"私有文档"

### types.ts 新增/修改

新增类型：
```typescript
interface UploadedDocument {
  id: string
  file_name: string
  file_size: number
  status: 'uploading' | 'parsing' | 'pending' | 'ready' | 'failed' | 'duplicate'
  error?: string
  message?: string     // 去重提示信息
  abstract?: string
  summary?: string
  created_at?: string
}
```

状态说明：
- `uploading` — 前端正在上传到后端
- `pending` — 已验证，暂存内存，等待确认运行时处理
- `duplicate` — 内容已存在（基于 SHA-256 哈希），复用已有文档
- `ready` — 处理完成（文本提取、摘要、分块索引均完成）
- `failed` — 处理失败

修改：
- `ParseResult` 新增 `document_ids: string[]`
- `AssessmentResult` 新增 `document_ids: string[]`
- 搜索结果类型新增 `source_type: 'report' | 'private_document'`

### api.ts 新增

```typescript
uploadDocuments(files: File[]): Promise<UploadedDocument[]>
getDocument(id: string): Promise<UploadedDocument>
deleteDocument(id: string): Promise<void>
```

## 依赖新增

### 后端 (Python)
- `azure-ai-documentintelligence` — Azure Document Intelligence SDK
- `tiktoken` — token 计数，用于分块策略

### 前端
- 无新增外部依赖，使用原生 `<input type="file">` + `fetch` multipart 上传

## Azure 资源新增

| 资源 | 用途 |
|------|------|
| Azure Document Intelligence (S0) | PDF/Word 文档解析 |
| Blob Storage 新容器 `private-documents` | 存储上传的原始文件 |
| AI Search 新索引 `documents` | 文档分块向量索引 |
