# 药物研发立项决策支持子智能体 — 技术架构方案

- **版本**：v0.2
- **基于**：PRD v0.1
- **日期**：2026-04-07（v0.2 增加私有网络架构）

## 1. 技术决策

| 决策项 | 选择 |
|--------|------|
| Agent 框架 | Azure AI Foundry Agent Service（Microsoft Agent Framework） |
| LLM | GPT-5.4（通过 Foundry 部署） |
| Embedding 模型 | text-embedding-3-large（通过 Foundry 部署） |
| 知识库检索 | Azure AI Search（向量 + 全文混合检索） |
| 结构化存储 | Azure Cosmos DB for NoSQL |
| 文件存储 | Azure Blob Storage |
| Web 搜索 | Bing Search API（替代 Google Scholar） |
| 外部数据源 | PubMed E-utilities、ClinicalTrials.gov API |
| 部署 | Azure Container Apps + Azure Container Registry |
| 网络 | Azure VNet + Private Endpoint + Private DNS Zone |
| 监控 | Azure Application Insights |

## 1.1 Azure 部署配置

| 配置项 | 值 |
|--------|------|
| 订阅名称 | ME-MngEnv894848-kangminghe-2 |
| 资源组 | rg-drug-target-agent |
| AI 服务 Region | East US 2 |
| 其他服务 Region | Southeast Asia |

> **跨区域延迟警告**：AI 服务（East US 2）与其他服务（Southeast Asia）分布在不同区域。
> 每次 Agent 调用知识库工具或生成 Embedding 时，请求都会跨越太平洋，增加 50-200ms 延迟。
> 由于 Pipeline 中包含多次顺序调用（Embedding 生成、Search 查询、Agent 响应），跨区域延迟会显著累积。
> **建议**：当目标区域支持所需模型时，应将所有资源部署在同一 Azure 区域以最小化延迟。

### Azure 托管资源组

除了 `rg-drug-target-agent` 外，Azure 平台会自动创建以下托管资源组（Managed Resource Groups）来承载底层基础设施。这些资源组由 Azure 自动管理，**不应手动修改或删除其中的内容**。

| 托管资源组 | 创建者 | 用途 |
|-----------|--------|------|
| `ME_drugtarget-env-v2_rg-drug-target-agent_southeastasia` | Azure Container Apps | 当 Container Apps Environment 部署到自定义 VNet 时自动创建，包含平台管理的基础设施组件（公共 IP 地址、负载均衡器等）。命名规则：`ME_{环境名}_{父资源组}_{区域}`。参见 [官方文档](https://learn.microsoft.com/en-us/azure/container-apps/custom-virtual-networks#managed-resources)。 |
| `ai_drugtarget-insights_<ApplicationId>_managed` | Azure Application Insights | 创建 Application Insights（`drugtarget-insights`）时自动生成的托管资源组，包含一个 Log Analytics Workspace（`managed-drugtarget-insights-ws`）作为 Application Insights 的后端日志存储。命名中的 GUID 为 Application Insights 的 ApplicationId。 |

> **注意**：删除 `rg-drug-target-agent` 中的 Container Apps Environment 或 Application Insights 资源时，对应的托管资源组预期会被一并清理。

### Region 分配

| Region | 服务 |
|--------|------|
| **East US 2** | Azure AI Foundry (Agent Service)、GPT-5.4 部署、text-embedding-3-large 部署、Bing Search API |
| **Southeast Asia** | Azure VNet、Azure AI Search、Azure Cosmos DB（Private Endpoint）、Azure Blob Storage、Azure Container Apps（VNet 集成）、Azure Container Registry、Application Insights |

## 1.2 网络架构

Container Apps 通过 VNet 集成 + Private Endpoint 访问 Cosmos DB，Cosmos DB 禁用公网访问，确保数据面流量不经过公共互联网。

```
┌─────────────────────── drugtarget-vnet (10.0.0.0/16) ───────────────────────┐
│                                                                             │
│  ┌─── snet-cae (10.0.0.0/23) ──────────┐  ┌─── snet-pe (10.0.2.0/24) ──┐  │
│  │                                      │  │                            │  │
│  │  Container App Environment (v2)      │  │  Private Endpoint          │  │
│  │  ├── drugtarget-backend (internal)   │──│──→ Cosmos DB               │  │
│  │  └── drugtarget-frontend (external)  │  │     (10.0.2.4)             │  │
│  │                                      │  │                            │  │
│  └──────────────────────────────────────┘  └────────────────────────────┘  │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                          Private DNS Zone
                   privatelink.documents.azure.com
                   drugtarget-cosmos → 10.0.2.4
```

### 网络配置详情

| 配置项 | 值 |
|--------|------|
| VNet 名称 | drugtarget-vnet |
| VNet 地址空间 | 10.0.0.0/16 |
| Container App 子网 | snet-cae (10.0.0.0/23)，委托给 Microsoft.App/environments |
| Private Endpoint 子网 | snet-pe (10.0.2.0/24) |
| Container App Environment | drugtarget-env-v2（绑定 snet-cae） |
| Cosmos DB Private Endpoint | pe-cosmos-drugtarget（位于 snet-pe） |
| Private DNS Zone | privatelink.documents.azure.com（链接到 drugtarget-vnet） |
| Cosmos DB 公网访问 | Disabled |

### 网络安全要点

- Cosmos DB **禁用公网访问**，仅通过 Private Endpoint 可达
- Container App 通过 VNet 内部 DNS 解析 `drugtarget-cosmos.documents.azure.com` 到私有 IP
- Backend 使用 `DefaultAzureCredential`（Managed Identity）进行 RBAC 认证，无需存储密钥
- Frontend 通过 Container App Environment 内部网络访问 Backend（internal ingress）

## 2. 架构总览

```
用户 → Frontend (Container Apps, external ingress)
         ↓  (VNet 内部通信)
   Backend (Container Apps, internal ingress)
         ↓
   Orchestrator Agent (Foundry Agent Service, GPT-5.4)
         ↓
   用户确认（Human-in-the-loop）
         ↓
   ┌── 并行 ──┐
   ↓          ↓
 ① 知识库   ② 文档处理
   检索     （Blob→提取→摘要→分块索引）
   └────┬─────┘
         ↓
   ┌─────────┼──────────────┐
   ↓         ↓              ↓
文献 Agent  临床 Agent   竞争 Agent
（含私有文档上下文）
   ↓         ↓              ↓
PubMed    ClinicalTrials   Bing Search
Bing       .gov API        PubMed
Search    Bing Search      ClinicalTrials
         ↓
   决策总结 Agent（独立评估 + 推理）
         ↓
   GPT-5.4 输出固定结构结论
         ↓
   ┌─────┼─────────┐
   ↓     ↓         ↓
Cosmos DB  AI Search  Blob Storage
(Private   (向量+全文  (报告+快照)
Endpoint)  索引)
```

## 3. Agent 设计

### 3.1 Agent 清单

共 5 个 Foundry Agent：1 个 Orchestrator + 4 个子 Agent。

| Agent | 职责 | Tools |
|-------|------|-------|
| Orchestrator | 调度、知识库读写、Human-in-the-loop 确认 | `search_knowledge_base`、`write_to_knowledge_base`、调用 4 个子 Agent 的 function tools |
| 文献研究 Agent | PubMed + 学术补充检索 | `search_pubmed`、`fetch_pubmed_details`、`bing_search` |
| 临床试验情报 Agent | 临床试验结构化数据 + 补充情报 | `search_clinical_trials`、`fetch_trial_details`、`bing_search` |
| 竞争与情报 Agent | 多源二次归纳竞争格局 | `bing_search`、`search_pubmed`、`search_clinical_trials` |
| 决策总结 Agent | 独立做证据评估 + Go/No-Go 推理 | 无外部 Tool，输入是前 3 个 Agent 的输出 + 知识库历史情报 |

### 3.2 Orchestrator 流程

```
1. 解析用户输入（靶点 + 适应症）
2. 用户确认：返回解析结果和子任务规划，等待用户确认（Human-in-the-loop）
3. 并行执行（asyncio.gather）：
   a. 知识库检索：调用 search_knowledge_base 检索历史情报
   b. 文档处理（如有上传）：Blob 上传 → 文本+图表提取(prebuilt-layout) → GPT-5.4 视觉理解图表 → 图表描述合并文本流 → LLM 摘要 → 分块索引（含独立 figure chunks）
4. 并行调用：文献研究 Agent / 临床试验情报 Agent / 竞争与情报 Agent
   （私有文档摘要 + 用户建议注入 Agent prompt）
5. 决策推理：将 3 个 Agent 输出 + 知识库历史情报 → 传给决策总结 Agent
6. 决策总结 Agent 返回固定结构结论
7. 写回知识库：调用 write_to_knowledge_base 存储本次结果
```

### 3.3 文献研究 Agent

#### 输入

- 靶点名称
- 疾病/适应症（可选）

#### Tools

- `search_pubmed`：通过 PubMed E-utilities esearch 接口检索，返回 PMID 列表
- `fetch_pubmed_details`：通过 efetch 获取论文标题、摘要、作者、发表日期、PMID 链接
- `bing_search`：补充学术搜索广度，弥补 PubMed 以外的综述、研究线索

#### 输出（JSON）

```json
{
  "source": "literature_agent",
  "papers": [
    {
      "title": "...",
      "authors": "...",
      "abstract_summary": "...",
      "pmid": "...",
      "link": "https://pubmed.ncbi.nlm.nih.gov/...",
      "source_type": "PubMed",
      "relevance": "high/medium/low"
    }
  ],
  "web_results": [
    {
      "title": "...",
      "snippet": "...",
      "link": "...",
      "source_type": "Web"
    }
  ],
  "summary": "文献支持总结...",
  "support_strength": "strong/moderate/weak",
  "positive_evidence": ["..."],
  "negative_evidence": ["..."],
  "confidence": "high/medium/low"
}
```

### 3.4 临床试验情报 Agent

#### 输入

- 靶点名称
- 疾病/适应症（可选）

#### Tools

- `search_clinical_trials`：通过 ClinicalTrials.gov v2 API 检索试验
- `fetch_trial_details`：获取试验详情（NCT 号、阶段、状态、适应症、干预方式）
- `bing_search`：补充试验结果公告、公司新闻稿、FDA 审评动态、会议报道、失败原因分析

#### 输出（JSON）

```json
{
  "source": "clinical_trials_agent",
  "trials": [
    {
      "nct_id": "NCT...",
      "title": "...",
      "phase": "Phase 1/2/3",
      "status": "Recruiting/Completed/Terminated/...",
      "conditions": ["..."],
      "interventions": ["..."],
      "sponsor": "...",
      "link": "https://clinicaltrials.gov/study/..."
    }
  ],
  "web_results": [
    {
      "title": "...",
      "snippet": "...",
      "link": "...",
      "source_type": "Web"
    }
  ],
  "phase_distribution": {"Phase 1": 0, "Phase 2": 0, "Phase 3": 0},
  "status_distribution": {"Recruiting": 0, "Completed": 0, "Terminated": 0},
  "positive_signals": ["..."],
  "negative_signals": ["..."],
  "summary": "临床试验总结...",
  "confidence": "high/medium/low"
}
```

### 3.5 竞争与情报 Agent

#### 输入

- 靶点名称
- 疾病/适应症（可选）

#### Tools

- `bing_search`：公开网页、公司管线动态、新闻稿
- `search_pubmed`：相关研究热点二次归纳
- `search_clinical_trials`：竞争者试验分布

#### 输出（JSON）

```json
{
  "source": "competition_agent",
  "competition_level": "high/medium/low",
  "major_players": ["..."],
  "research_hotspots": ["..."],
  "crowding_signals": ["..."],
  "differentiation_opportunities": ["..."],
  "web_results": [
    {
      "title": "...",
      "snippet": "...",
      "link": "...",
      "source_type": "Web"
    }
  ],
  "summary": "竞争格局总结...",
  "confidence": "high/medium/low"
}
```

### 3.6 决策总结 Agent

#### 输入

- 文献研究 Agent 输出
- 临床试验情报 Agent 输出
- 竞争与情报 Agent 输出
- 知识库历史情报（如有）

#### 无外部 Tool

纯 LLM 推理，基于证据做评估。

#### 决策规则

偏向 **Go**：
- PubMed 中存在较多高相关研究
- 有明确正向生物学机制支持
- ClinicalTrials.gov 中已有积极临床信号
- 竞争未完全饱和

偏向 **No-Go**：
- 文献支持弱
- 缺少清晰机制证据
- 相关临床多失败/终止
- 竞争极度拥挤且差异化不明显

证据不足则输出 **Need More Data**。

#### 输出（固定结构）

```json
{
  "target": "靶点名称",
  "indication": "适应症",
  "literature_summary": "文献支持总结",
  "clinical_trials_summary": "临床试验总结",
  "competition_summary": "竞争格局总结",
  "major_risks": ["..."],
  "major_opportunities": ["..."],
  "recommendation": "Go / No-Go / Need More Data",
  "reasoning": "结论原因说明",
  "uncertainty": "不确定性说明",
  "citations": [
    {
      "title": "...",
      "link": "...",
      "source_type": "PubMed / ClinicalTrials / Web"
    }
  ]
}
```

## 4. Function Tools 定义

### 4.1 search_pubmed

- **用途**：通过 PubMed E-utilities esearch 检索文献
- **参数**：`query` (str)、`max_results` (int, 默认 10)、`date_range` (str, 可选)
- **返回**：PMID 列表

### 4.2 fetch_pubmed_details

- **用途**：通过 PubMed E-utilities efetch 获取文献详情
- **参数**：`pmids` (list[str])
- **返回**：标题、摘要、作者、发表日期、链接

### 4.3 search_clinical_trials

- **用途**：通过 ClinicalTrials.gov v2 API 检索临床试验
- **参数**：`query` (str)、`max_results` (int, 默认 10)、`status` (str, 可选)
- **返回**：试验列表（NCT 号、标题、阶段、状态）

### 4.4 fetch_trial_details

- **用途**：通过 ClinicalTrials.gov v2 API 获取试验详情
- **参数**：`nct_ids` (list[str])
- **返回**：适应症、干预方式、sponsor、结果摘要

### 4.5 bing_search

- **用途**：通过 Bing Search API 做 Web 搜索
- **参数**：`query` (str)、`count` (int, 默认 5)、`market` (str, 默认 "en-US")
- **返回**：标题、摘要片段、URL

### 4.6 search_knowledge_base

- **用途**：检索 Azure AI Search 知识库中的历史情报
- **参数**：`query` (str)、`target` (str, 可选)、`indication` (str, 可选)、`top_k` (int, 默认 5)
- **返回**：历史报告摘要、相关结论、引用

### 4.7 write_to_knowledge_base

- **用途**：将本次查询结果写入知识库
- **参数**：`report` (dict, 决策总结 Agent 的完整输出)、`raw_outputs` (dict, 各子 Agent 的原始输出)
- **处理**：写 Cosmos DB（结构化记录）→ 写 Blob Storage（报告文件）→ 生成 embedding → 写 AI Search 索引

## 5. 知识库架构

### 5.1 存储分层

| 层次 | 服务 | 存储内容 |
|------|------|----------|
| 结构化记录 | Cosmos DB for NoSQL | 任务记录、Agent 输出 JSON、引用清单、Go/No-Go 结论 |
| 文件存储 | Blob Storage | 导出的 Word/PDF 报告、原始 API 响应快照 |
| 检索索引 | Azure AI Search | 报告结论和文献摘要的向量索引（embedding）+ 结构化字段的全文索引 |

### 5.2 Cosmos DB 数据模型

```json
{
  "id": "uuid",
  "target": "GLP-1R",
  "indication": "肥胖",
  "created_at": "2026-04-03T10:00:00Z",
  "status": "completed",
  "orchestrator_output": { "...决策总结 Agent 完整输出..." },
  "literature_output": { "...文献研究 Agent 输出..." },
  "clinical_trials_output": { "...临床试验情报 Agent 输出..." },
  "competition_output": { "...竞争与情报 Agent 输出..." },
  "knowledge_base_context": { "...查询时检索到的历史情报..." },
  "report_blob_url": "https://...blob.core.windows.net/reports/..."
}
```

### 5.3 Azure AI Search 索引字段

| 字段 | 类型 | 用途 |
|------|------|------|
| id | string | 文档 ID |
| target | string, filterable | 靶点名称 |
| indication | string, filterable | 适应症 |
| recommendation | string, filterable | Go/No-Go/Need More Data |
| summary_text | string, searchable | 报告结论全文（全文检索） |
| summary_vector | vector | 报告结论 embedding（向量检索） |
| literature_summary | string, searchable | 文献总结 |
| clinical_summary | string, searchable | 临床总结 |
| competition_summary | string, searchable | 竞争总结 |
| citations | collection | 引用列表 |
| created_at | datetime, sortable | 创建时间 |

### 5.4 数据写入流程

```
Agent 输出 JSON
    ↓
① 写入 Cosmos DB — 结构化记录（任务、输出、引用、结论）
    ↓
② 写入 Blob Storage — Word/PDF 报告 + 原始 API 响应快照
    ↓
③ text-embedding-3-large 生成 embedding
    ↓
④ 写入 Azure AI Search — 向量索引 + 全文索引
```

### 5.5 数据检索流程

```
Orchestrator 收到新查询
    ↓
调用 search_knowledge_base()
    ↓
Azure AI Search 混合检索（向量相似 + 关键词匹配）
    ↓
有历史情报 → 传给 Orchestrator 作为补充上下文，标注为"历史参考"
无历史情报 → 跳过，直接调子 Agent
```

### 5.6 知识库价值场景

- **同一靶点复查**：对比历史结论，标注变化
- **跨靶点比较**：如"对比 GLP-1R 和 GIPR 在肥胖领域的情报"
- **趋势追踪**：同一靶点多次查询的结论变化时间线
- **团队共享**：不同人查过的靶点情报自动沉淀，避免重复工作

## 6. Azure 服务清单

| 服务 | 用途 | Region |
|------|------|--------|
| Azure AI Foundry Agent Service | Orchestrator + 4 个子 Agent | East US 2 |
| GPT-5.4 (Foundry 部署) | 所有 Agent 的推理引擎 | East US 2 |
| text-embedding-3-large (Foundry 部署) | 知识库向量化 | East US 2 |
| Bing Search API | 三个子 Agent 共用的 Web 搜索 | East US 2 |
| Azure Virtual Network | Container Apps + Private Endpoint 网络隔离 | Southeast Asia |
| Azure Private DNS Zone | Cosmos DB 私有域名解析 (privatelink.documents.azure.com) | Global |
| Azure AI Search | 知识库检索层（向量 + 全文混合） | Southeast Asia |
| Azure Cosmos DB for NoSQL | 结构化存储（通过 Private Endpoint 访问，公网禁用） | Southeast Asia |
| Azure Blob Storage | 文件存储 + 报告导出 | Southeast Asia |
| Azure Document Intelligence (S0) | PDF/Word 文档解析（prebuilt-layout + 图表提取），Managed Identity 认证 | Southeast Asia |
| Azure Container Apps | 前后端部署（VNet 集成，drugtarget-env-v2） | Southeast Asia |
| Azure Container Registry | 镜像管理 | Southeast Asia |
| Azure Application Insights | 监控 + 日志 | Southeast Asia |

## 7. 前端展示

简单单页应用，**中文界面**，**单页滚动布局**（输入区 → 确认区 → 运行状态 → 结果区在同一页面纵向排列，不做页面跳转）。

### 输入区

- 靶点名称（必填）
- 适应症（可选）
- 同义词/别名（可选）
- 研究重点（可选）
- 时间范围（可选）
- 查询按钮

### 输出区

1. **总体建议卡片**：Go / No-Go / Need More Data + 原因摘要
2. **文献支持 Tab**：3~5 条核心摘要 + 关键文献引用
3. **临床试验情报 Tab**：试验表格 + 阶段/状态统计
4. **竞争与风险 Tab**：主要竞争点 + 主要风险点
5. **引用区**：PubMed 链接、ClinicalTrials.gov 链接、Web 搜索结果链接
6. **历史情报参考**（如有）：知识库中的历史查询结论

### 报告导出

- Markdown / Word / PDF 格式

## 8. 实现阶段

### 第一阶段：全链路打通（已完成）

- 5 个 Foundry Agent 创建（Orchestrator + 文献 + 临床 + 竞争 + 决策总结）
- 7 个 Function Tools 实现
- 知识库搭建：Cosmos DB + AI Search 索引 + Blob Storage
- Orchestrator 编排逻辑 + Human-in-the-loop
- GPT-5.4 汇总输出固定结构结论

### 第二阶段：前端 + 报告导出（已完成）

- 前端单页应用（左侧导航 + 右侧内容区）
- 报告导出 Word/Markdown/PDF
- 部署到 Container Apps
- Application Insights 接入

### 第三阶段：私有网络加固（已完成 2026-04-07）

- 创建 VNet (drugtarget-vnet) + 子网 (snet-cae, snet-pe)
- 新建 Container App Environment (drugtarget-env-v2) 绑定 VNet
- 创建 Cosmos DB Private Endpoint + Private DNS Zone
- 迁移 Backend / Frontend 到新 VNet 环境
- 分配 Managed Identity RBAC 角色（Cosmos DB + AI Foundry）
- Cosmos DB 公网访问已禁用，所有数据面流量通过私有网络

### 第四阶段：私有文档上传与分析（已完成 2026-04-10）

- 支持上传最多 5 个文件（PDF/Word/TXT/MD），单文件 ≤ 10MB
- 上传即时返回（~1s），仅验证 + 存内存，无 Azure 服务调用
- 确认运行时文档处理与知识库检索并行：Blob 上传 → Document Intelligence 提取(prebuilt-layout + 图表) → GPT-5.4 视觉理解图表 → 描述合并文本流 → LLM 摘要 → 分块索引（含独立 figure chunks）
- 基于 SHA-256 内容哈希的文件去重（检查内存 pending + Cosmos 已处理）
- 删除时全链路清理（内存 + Cosmos + Blob + AI Search），即使 Cosmos 记录已不存在也会清理 AI Search 残留索引
- RunningView 中"知识库检索"和"文档解析"以并排卡片形式展示，直观体现并行执行
- Azure Document Intelligence 使用 Managed Identity 认证（Cognitive Services User RBAC）

## 9. 非功能需求

- **可解释性**：每条关键结论有来源，不能只给答案不给证据
- **成本控制**：每个数据源只取前 5 条结果，避免无限检索
- **稳定性**：某个数据源失败时提示而不崩溃，允许部分结果返回
- **响应时间**：用户输入后 10 分钟内得到结果

## 10. 输出格式（固定结构）

```
- 目标靶点
- 适应症
- 文献支持总结
- 临床试验总结
- 竞争格局总结
- 主要风险
- 主要机会
- 结论建议：Go / No-Go / Need More Data
- 原因说明
- 不确定性说明
- 引用列表（含原文链接）
```
