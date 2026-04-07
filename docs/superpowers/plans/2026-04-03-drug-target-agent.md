# Drug Target Decision Support Agent — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an Azure AI Foundry Agent-based system that takes a drug target name, searches public data sources (PubMed, ClinicalTrials.gov, Bing), and outputs a structured Go / No-Go / Need More Data recommendation with citations.

**Architecture:** 5 Foundry Agents (1 Orchestrator + 4 sub-agents) backed by 7 Function Tools. A knowledge base (Cosmos DB + AI Search + Blob Storage) stores historical results for reuse. A FastAPI backend exposes the orchestration as an API. A React frontend provides the user interface. Deployed on Azure Container Apps.

**Tech Stack:** Python 3.12, FastAPI, azure-ai-projects SDK, azure-search-documents, azure-cosmos, azure-storage-blob, React (Vite), Docker, Azure Container Apps

**Spec:** See `architecture.md` in project root.

---

## File Structure

```
drug_target_cc/
├── infra/
│   └── provision.sh                    # Azure resource provisioning script
├── backend/
│   ├── pyproject.toml                  # Python project config + dependencies
│   ├── Dockerfile                      # Backend container image
│   ├── app/
│   │   ├── main.py                     # FastAPI app entry point
│   │   ├── config.py                   # Environment config (endpoints, keys)
│   │   ├── tools/
│   │   │   ├── pubmed.py               # search_pubmed + fetch_pubmed_details
│   │   │   ├── clinical_trials.py      # search_clinical_trials + fetch_trial_details
│   │   │   ├── bing_search.py          # bing_search
│   │   │   └── knowledge_base.py       # search_knowledge_base + write_to_knowledge_base
│   │   ├── agents/
│   │   │   ├── definitions.py          # FunctionTool definitions for all 7 tools
│   │   │   ├── setup.py                # Create/get all 5 Foundry Agents
│   │   │   └── orchestrator.py         # Orchestration loop: run agents, handle function calls
│   │   ├── knowledge/
│   │   │   ├── cosmos_client.py        # Cosmos DB read/write operations
│   │   │   ├── blob_client.py          # Blob Storage upload/download
│   │   │   ├── search_client.py        # AI Search index management + query
│   │   │   └── embedding.py            # Generate embeddings via Foundry
│   │   └── export/
│   │       └── report.py               # Export results to Markdown/Word
│   └── tests/
│       ├── test_pubmed.py
│       ├── test_clinical_trials.py
│       ├── test_bing_search.py
│       ├── test_knowledge_base.py
│       ├── test_orchestrator.py
│       └── test_export.py
├── frontend/
│   ├── package.json
│   ├── Dockerfile
│   ├── index.html
│   ├── src/
│   │   ├── main.tsx                    # React entry
│   │   ├── App.tsx                     # Main app layout
│   │   ├── api.ts                      # Backend API client
│   │   ├── components/
│   │   │   ├── SearchForm.tsx          # Target + indication input form
│   │   │   ├── ConfirmDialog.tsx       # Human-in-the-loop confirmation
│   │   │   ├── ResultCard.tsx          # Go/No-Go/Need More Data card
│   │   │   ├── LiteratureTab.tsx       # Literature results tab
│   │   │   ├── ClinicalTrialsTab.tsx   # Clinical trials results tab
│   │   │   ├── CompetitionTab.tsx      # Competition results tab
│   │   │   └── CitationList.tsx        # Citation links list
│   │   └── types.ts                    # TypeScript type definitions
│   └── vite.config.ts
├── architecture.md
└── 基于靶点情报的 药物研发立项决策支持子智能体 PRD.md
```

---

## Task 1: Azure Resource Provisioning

**Files:**
- Create: `infra/provision.sh`
- Create: `backend/app/config.py`

- [ ] **Step 1: Write the provisioning script**

```bash
#!/usr/bin/env bash
set -euo pipefail

# === Configuration ===
SUBSCRIPTION="ME-MngEnv894848-kangminghe-2"
RESOURCE_GROUP="rg-drug-target-agent"
AI_REGION="eastus2"
OTHER_REGION="southeastasia"
PROJECT_PREFIX="drugtarget"

az account set --subscription "$SUBSCRIPTION"

# === Resource Group ===
az group create --name "$RESOURCE_GROUP" --location "$OTHER_REGION"

# === AI Foundry Hub + Project (East US 2) ===
az ml workspace create \
  --kind hub \
  --resource-group "$RESOURCE_GROUP" \
  --name "${PROJECT_PREFIX}-hub" \
  --location "$AI_REGION"

az ml workspace create \
  --kind project \
  --resource-group "$RESOURCE_GROUP" \
  --name "${PROJECT_PREFIX}-project" \
  --hub-id "/subscriptions/$(az account show --query id -o tsv)/resourceGroups/$RESOURCE_GROUP/providers/Microsoft.MachineLearningServices/workspaces/${PROJECT_PREFIX}-hub" \
  --location "$AI_REGION"

# === Model Deployments (East US 2) ===
# GPT-5.4 and text-embedding-3-large are deployed via AI Foundry portal or CLI
# after hub/project creation. The exact CLI depends on model availability.
echo ">>> Deploy GPT-5.4 and text-embedding-3-large in AI Foundry portal for project: ${PROJECT_PREFIX}-project"

# === Bing Search (East US 2, global service) ===
az cognitiveservices account create \
  --name "${PROJECT_PREFIX}-bing" \
  --resource-group "$RESOURCE_GROUP" \
  --kind Bing.Search.v7 \
  --sku S1 \
  --location global \
  --yes

BING_KEY=$(az cognitiveservices account keys list \
  --name "${PROJECT_PREFIX}-bing" \
  --resource-group "$RESOURCE_GROUP" \
  --query key1 -o tsv)

# === Azure AI Search (Southeast Asia) ===
az search service create \
  --name "${PROJECT_PREFIX}-search" \
  --resource-group "$RESOURCE_GROUP" \
  --location "$OTHER_REGION" \
  --sku basic \
  --partition-count 1 \
  --replica-count 1

SEARCH_ENDPOINT="https://${PROJECT_PREFIX}-search.search.windows.net"
SEARCH_KEY=$(az search admin-key show \
  --service-name "${PROJECT_PREFIX}-search" \
  --resource-group "$RESOURCE_GROUP" \
  --query primaryKey -o tsv)

# === Cosmos DB (Southeast Asia) ===
az cosmosdb create \
  --name "${PROJECT_PREFIX}-cosmos" \
  --resource-group "$RESOURCE_GROUP" \
  --locations regionName="$OTHER_REGION" failoverPriority=0 \
  --kind GlobalDocumentDB

az cosmosdb sql database create \
  --account-name "${PROJECT_PREFIX}-cosmos" \
  --resource-group "$RESOURCE_GROUP" \
  --name "drugtargetdb"

az cosmosdb sql container create \
  --account-name "${PROJECT_PREFIX}-cosmos" \
  --resource-group "$RESOURCE_GROUP" \
  --database-name "drugtargetdb" \
  --name "reports" \
  --partition-key-path "/target"

COSMOS_ENDPOINT="https://${PROJECT_PREFIX}-cosmos.documents.azure.com:443/"
COSMOS_KEY=$(az cosmosdb keys list \
  --name "${PROJECT_PREFIX}-cosmos" \
  --resource-group "$RESOURCE_GROUP" \
  --query primaryMasterKey -o tsv)

# === Blob Storage (Southeast Asia) ===
az storage account create \
  --name "${PROJECT_PREFIX}storage" \
  --resource-group "$RESOURCE_GROUP" \
  --location "$OTHER_REGION" \
  --sku Standard_LRS

az storage container create \
  --name "reports" \
  --account-name "${PROJECT_PREFIX}storage"

az storage container create \
  --name "snapshots" \
  --account-name "${PROJECT_PREFIX}storage"

BLOB_CONNECTION=$(az storage account show-connection-string \
  --name "${PROJECT_PREFIX}storage" \
  --resource-group "$RESOURCE_GROUP" \
  --query connectionString -o tsv)

# === Container Registry (Southeast Asia) ===
az acr create \
  --name "${PROJECT_PREFIX}acr" \
  --resource-group "$RESOURCE_GROUP" \
  --location "$OTHER_REGION" \
  --sku Basic \
  --admin-enabled true

# === Container Apps Environment (Southeast Asia) ===
az containerapp env create \
  --name "${PROJECT_PREFIX}-env" \
  --resource-group "$RESOURCE_GROUP" \
  --location "$OTHER_REGION"

# === Application Insights (Southeast Asia) ===
az monitor app-insights component create \
  --app "${PROJECT_PREFIX}-insights" \
  --resource-group "$RESOURCE_GROUP" \
  --location "$OTHER_REGION"

# === Output all keys ===
echo ""
echo "=== Resource Provisioning Complete ==="
echo "BING_SEARCH_KEY=$BING_KEY"
echo "SEARCH_ENDPOINT=$SEARCH_ENDPOINT"
echo "SEARCH_API_KEY=$SEARCH_KEY"
echo "COSMOS_ENDPOINT=$COSMOS_ENDPOINT"
echo "COSMOS_KEY=$COSMOS_KEY"
echo "BLOB_CONNECTION_STRING=$BLOB_CONNECTION"
echo ""
echo ">>> Next: Deploy GPT-5.4 + text-embedding-3-large in AI Foundry portal"
echo ">>> Then: Copy the project endpoint into .env"
```

- [ ] **Step 2: Write config.py for environment variable loading**

```python
# backend/app/config.py
import os


class Settings:
    # AI Foundry
    PROJECT_ENDPOINT: str = os.environ["AZURE_AI_PROJECT_ENDPOINT"]
    MODEL_DEPLOYMENT: str = os.environ.get("MODEL_DEPLOYMENT", "gpt-5.4")
    EMBEDDING_DEPLOYMENT: str = os.environ.get("EMBEDDING_DEPLOYMENT", "text-embedding-3-large")

    # Bing Search
    BING_SEARCH_KEY: str = os.environ["BING_SEARCH_KEY"]
    BING_SEARCH_ENDPOINT: str = os.environ.get(
        "BING_SEARCH_ENDPOINT", "https://api.bing.microsoft.com/v7.0/search"
    )

    # Azure AI Search
    SEARCH_ENDPOINT: str = os.environ["SEARCH_ENDPOINT"]
    SEARCH_API_KEY: str = os.environ["SEARCH_API_KEY"]
    SEARCH_INDEX_NAME: str = os.environ.get("SEARCH_INDEX_NAME", "drug-target-reports")

    # Cosmos DB
    COSMOS_ENDPOINT: str = os.environ["COSMOS_ENDPOINT"]
    COSMOS_KEY: str = os.environ["COSMOS_KEY"]
    COSMOS_DATABASE: str = os.environ.get("COSMOS_DATABASE", "drugtargetdb")
    COSMOS_CONTAINER: str = os.environ.get("COSMOS_CONTAINER", "reports")

    # Blob Storage
    BLOB_CONNECTION_STRING: str = os.environ["BLOB_CONNECTION_STRING"]
    BLOB_REPORTS_CONTAINER: str = os.environ.get("BLOB_REPORTS_CONTAINER", "reports")
    BLOB_SNAPSHOTS_CONTAINER: str = os.environ.get("BLOB_SNAPSHOTS_CONTAINER", "snapshots")


settings = Settings()
```

- [ ] **Step 3: Create .env.example for reference**

Create `backend/.env.example`:

```
AZURE_AI_PROJECT_ENDPOINT=https://drugtarget-project.eastus2.api.azureml.ms
MODEL_DEPLOYMENT=gpt-5.4
EMBEDDING_DEPLOYMENT=text-embedding-3-large
BING_SEARCH_KEY=your-bing-key
SEARCH_ENDPOINT=https://drugtarget-search.search.windows.net
SEARCH_API_KEY=your-search-key
COSMOS_ENDPOINT=https://drugtarget-cosmos.documents.azure.com:443/
COSMOS_KEY=your-cosmos-key
BLOB_CONNECTION_STRING=DefaultEndpointsProtocol=https;AccountName=drugtargetstorage;...
```

- [ ] **Step 4: Run provisioning script and verify**

```bash
chmod +x infra/provision.sh
./infra/provision.sh
```

Expected: All resources created, keys printed to stdout.

- [ ] **Step 5: Deploy models in AI Foundry portal and update .env**

Manual step: Open AI Foundry portal, deploy GPT-5.4 and text-embedding-3-large in the `drugtarget-project`. Copy the project endpoint into `backend/.env`.

- [ ] **Step 6: Commit**

```bash
git add infra/ backend/app/config.py backend/.env.example
git commit -m "feat: add Azure resource provisioning and config"
```

---

## Task 2: Python Project Setup

**Files:**
- Create: `backend/pyproject.toml`
- Create: `backend/app/__init__.py`
- Create: `backend/app/tools/__init__.py`
- Create: `backend/app/agents/__init__.py`
- Create: `backend/app/knowledge/__init__.py`
- Create: `backend/app/export/__init__.py`
- Create: `backend/tests/__init__.py`

- [ ] **Step 1: Create pyproject.toml**

```toml
# backend/pyproject.toml
[project]
name = "drug-target-agent"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
    "fastapi>=0.115.0",
    "uvicorn[standard]>=0.30.0",
    "azure-ai-projects>=2.0.0b2",
    "azure-identity>=1.17.0",
    "azure-search-documents>=11.6.0",
    "azure-cosmos>=4.7.0",
    "azure-storage-blob>=12.22.0",
    "httpx>=0.27.0",
    "python-dotenv>=1.0.0",
    "python-docx>=1.1.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.24.0",
    "pytest-httpx>=0.30.0",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"
```

- [ ] **Step 2: Create all __init__.py files**

Create empty `__init__.py` in: `backend/app/`, `backend/app/tools/`, `backend/app/agents/`, `backend/app/knowledge/`, `backend/app/export/`, `backend/tests/`.

- [ ] **Step 3: Install dependencies**

```bash
cd backend
uv venv
source .venv/bin/activate
uv pip install -e ".[dev]"
```

Expected: All packages install without errors.

- [ ] **Step 4: Verify imports work**

```bash
python -c "from azure.ai.projects import AIProjectClient; print('OK')"
```

Expected: `OK`

- [ ] **Step 5: Commit**

```bash
git add backend/pyproject.toml backend/app/ backend/tests/
git commit -m "feat: scaffold Python project with dependencies"
```

---

## Task 3: PubMed Function Tools

**Files:**
- Create: `backend/app/tools/pubmed.py`
- Create: `backend/tests/test_pubmed.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_pubmed.py
import json
import pytest
import httpx
from app.tools.pubmed import search_pubmed, fetch_pubmed_details

ESEARCH_XML = """<?xml version="1.0" encoding="UTF-8"?>
<eSearchResult>
  <Count>2</Count>
  <IdList>
    <Id>39000001</Id>
    <Id>39000002</Id>
  </IdList>
</eSearchResult>"""

EFETCH_XML = """<?xml version="1.0" encoding="UTF-8"?>
<PubmedArticleSet>
  <PubmedArticle>
    <MedlineCitation>
      <PMID>39000001</PMID>
      <Article>
        <ArticleTitle>GLP-1R agonists in obesity treatment</ArticleTitle>
        <Abstract>
          <AbstractText>This study demonstrates the efficacy of GLP-1R agonists.</AbstractText>
        </Abstract>
        <AuthorList>
          <Author><LastName>Smith</LastName><Initials>J</Initials></Author>
        </AuthorList>
        <Journal>
          <JournalIssue>
            <PubDate><Year>2025</Year></PubDate>
          </JournalIssue>
        </Journal>
      </Article>
    </MedlineCitation>
  </PubmedArticle>
</PubmedArticleSet>"""


@pytest.mark.asyncio
async def test_search_pubmed_returns_pmids(httpx_mock):
    httpx_mock.add_response(
        url=httpx.URL(
            "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi",
            params={"db": "pubmed", "term": "GLP-1R obesity", "retmax": "5", "retmode": "xml"},
        ),
        text=ESEARCH_XML,
    )
    result = await search_pubmed(query="GLP-1R obesity", max_results=5)
    parsed = json.loads(result)
    assert parsed["pmids"] == ["39000001", "39000002"]
    assert parsed["total_count"] == 2


@pytest.mark.asyncio
async def test_fetch_pubmed_details_returns_paper_info(httpx_mock):
    httpx_mock.add_response(
        url=httpx.URL(
            "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi",
            params={"db": "pubmed", "id": "39000001", "retmode": "xml"},
        ),
        text=EFETCH_XML,
    )
    result = await fetch_pubmed_details(pmids=["39000001"])
    parsed = json.loads(result)
    assert len(parsed["papers"]) == 1
    paper = parsed["papers"][0]
    assert paper["pmid"] == "39000001"
    assert "GLP-1R" in paper["title"]
    assert paper["link"] == "https://pubmed.ncbi.nlm.nih.gov/39000001/"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd backend && python -m pytest tests/test_pubmed.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'app.tools.pubmed'`

- [ ] **Step 3: Implement pubmed.py**

```python
# backend/app/tools/pubmed.py
import json
import xml.etree.ElementTree as ET

import httpx

ESEARCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
EFETCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"


async def search_pubmed(query: str, max_results: int = 10, date_range: str | None = None) -> str:
    """Search PubMed and return a list of PMIDs."""
    params = {"db": "pubmed", "term": query, "retmax": str(max_results), "retmode": "xml"}
    if date_range:
        params["datetype"] = "pdat"
        params["reldate"] = date_range

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(ESEARCH_URL, params=params)
        resp.raise_for_status()

    root = ET.fromstring(resp.text)
    pmids = [id_el.text for id_el in root.findall(".//IdList/Id") if id_el.text]
    count_el = root.find(".//Count")
    total_count = int(count_el.text) if count_el is not None and count_el.text else 0

    return json.dumps({"pmids": pmids, "total_count": total_count})


async def fetch_pubmed_details(pmids: list[str]) -> str:
    """Fetch detailed info for a list of PMIDs."""
    params = {"db": "pubmed", "id": ",".join(pmids), "retmode": "xml"}

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(EFETCH_URL, params=params)
        resp.raise_for_status()

    root = ET.fromstring(resp.text)
    papers = []
    for article in root.findall(".//PubmedArticle"):
        pmid_el = article.find(".//PMID")
        pmid = pmid_el.text if pmid_el is not None and pmid_el.text else ""
        title_el = article.find(".//ArticleTitle")
        title = title_el.text if title_el is not None and title_el.text else ""
        abstract_el = article.find(".//AbstractText")
        abstract = abstract_el.text if abstract_el is not None and abstract_el.text else ""
        year_el = article.find(".//PubDate/Year")
        year = year_el.text if year_el is not None and year_el.text else ""
        authors = []
        for author in article.findall(".//Author"):
            last = author.findtext("LastName", "")
            init = author.findtext("Initials", "")
            if last:
                authors.append(f"{last} {init}".strip())

        papers.append({
            "pmid": pmid,
            "title": title,
            "abstract": abstract,
            "authors": ", ".join(authors),
            "year": year,
            "link": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
            "source_type": "PubMed",
        })

    return json.dumps({"papers": papers})
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd backend && python -m pytest tests/test_pubmed.py -v
```

Expected: All tests PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/tools/pubmed.py backend/tests/test_pubmed.py
git commit -m "feat: implement PubMed search and fetch tools"
```

---

## Task 4: ClinicalTrials.gov Function Tools

**Files:**
- Create: `backend/app/tools/clinical_trials.py`
- Create: `backend/tests/test_clinical_trials.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_clinical_trials.py
import json
import pytest
from app.tools.clinical_trials import search_clinical_trials, fetch_trial_details

CT_SEARCH_RESPONSE = {
    "studies": [
        {
            "protocolSection": {
                "identificationModule": {
                    "nctId": "NCT06000001",
                    "briefTitle": "GLP-1R Agonist for Obesity Phase 3",
                },
                "statusModule": {"overallStatus": "Recruiting"},
                "designModule": {"phases": ["PHASE3"]},
                "conditionsModule": {"conditions": ["Obesity"]},
                "armsInterventionsModule": {
                    "interventions": [{"name": "Semaglutide", "type": "DRUG"}]
                },
                "sponsorCollaboratorsModule": {
                    "leadSponsor": {"name": "Novo Nordisk"}
                },
            }
        }
    ],
    "totalCount": 1,
}

CT_DETAIL_RESPONSE = {
    "studies": [
        {
            "protocolSection": {
                "identificationModule": {
                    "nctId": "NCT06000001",
                    "briefTitle": "GLP-1R Agonist for Obesity Phase 3",
                    "officialTitle": "A Phase 3 Study of GLP-1R Agonist",
                },
                "statusModule": {"overallStatus": "Recruiting"},
                "designModule": {
                    "phases": ["PHASE3"],
                    "enrollmentInfo": {"count": 500},
                },
                "conditionsModule": {"conditions": ["Obesity"]},
                "armsInterventionsModule": {
                    "interventions": [{"name": "Semaglutide", "type": "DRUG"}]
                },
                "sponsorCollaboratorsModule": {
                    "leadSponsor": {"name": "Novo Nordisk"}
                },
            }
        }
    ]
}


@pytest.mark.asyncio
async def test_search_clinical_trials(httpx_mock):
    httpx_mock.add_response(json=CT_SEARCH_RESPONSE)
    result = await search_clinical_trials(query="GLP-1R obesity", max_results=5)
    parsed = json.loads(result)
    assert len(parsed["trials"]) == 1
    assert parsed["trials"][0]["nct_id"] == "NCT06000001"
    assert parsed["trials"][0]["phase"] == "Phase 3"
    assert parsed["total_count"] == 1


@pytest.mark.asyncio
async def test_fetch_trial_details(httpx_mock):
    httpx_mock.add_response(json=CT_DETAIL_RESPONSE)
    result = await fetch_trial_details(nct_ids=["NCT06000001"])
    parsed = json.loads(result)
    assert len(parsed["trials"]) == 1
    trial = parsed["trials"][0]
    assert trial["nct_id"] == "NCT06000001"
    assert trial["sponsor"] == "Novo Nordisk"
    assert "clinicaltrials.gov" in trial["link"]
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd backend && python -m pytest tests/test_clinical_trials.py -v
```

Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement clinical_trials.py**

```python
# backend/app/tools/clinical_trials.py
import json

import httpx

BASE_URL = "https://clinicaltrials.gov/api/v2/studies"

PHASE_MAP = {
    "EARLY_PHASE1": "Early Phase 1",
    "PHASE1": "Phase 1",
    "PHASE2": "Phase 2",
    "PHASE3": "Phase 3",
    "PHASE4": "Phase 4",
    "NA": "N/A",
}


def _parse_trial_summary(study: dict) -> dict:
    proto = study.get("protocolSection", {})
    ident = proto.get("identificationModule", {})
    status = proto.get("statusModule", {})
    design = proto.get("designModule", {})
    conditions = proto.get("conditionsModule", {})
    arms = proto.get("armsInterventionsModule", {})
    sponsor = proto.get("sponsorCollaboratorsModule", {})

    raw_phases = design.get("phases", [])
    phase = ", ".join(PHASE_MAP.get(p, p) for p in raw_phases) if raw_phases else "N/A"

    interventions = [
        {"name": i.get("name", ""), "type": i.get("type", "")}
        for i in arms.get("interventions", [])
    ]

    nct_id = ident.get("nctId", "")
    return {
        "nct_id": nct_id,
        "title": ident.get("briefTitle", ""),
        "phase": phase,
        "status": status.get("overallStatus", ""),
        "conditions": conditions.get("conditions", []),
        "interventions": interventions,
        "sponsor": sponsor.get("leadSponsor", {}).get("name", ""),
        "link": f"https://clinicaltrials.gov/study/{nct_id}",
    }


async def search_clinical_trials(
    query: str, max_results: int = 10, status: str | None = None
) -> str:
    """Search ClinicalTrials.gov v2 API."""
    params: dict = {
        "query.term": query,
        "pageSize": max_results,
        "format": "json",
    }
    if status:
        params["filter.overallStatus"] = status

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(BASE_URL, params=params)
        resp.raise_for_status()

    data = resp.json()
    trials = [_parse_trial_summary(s) for s in data.get("studies", [])]
    return json.dumps({"trials": trials, "total_count": data.get("totalCount", 0)})


async def fetch_trial_details(nct_ids: list[str]) -> str:
    """Fetch detailed info for specific NCT IDs."""
    trials = []
    async with httpx.AsyncClient(timeout=30) as client:
        for nct_id in nct_ids:
            resp = await client.get(f"{BASE_URL}", params={"query.id": nct_id, "format": "json"})
            resp.raise_for_status()
            data = resp.json()
            for study in data.get("studies", []):
                trial = _parse_trial_summary(study)
                # Add extra detail fields
                proto = study.get("protocolSection", {})
                design = proto.get("designModule", {})
                enrollment = design.get("enrollmentInfo", {})
                trial["enrollment"] = enrollment.get("count", 0)
                trial["official_title"] = proto.get("identificationModule", {}).get(
                    "officialTitle", ""
                )
                trials.append(trial)

    return json.dumps({"trials": trials})
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd backend && python -m pytest tests/test_clinical_trials.py -v
```

Expected: All tests PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/tools/clinical_trials.py backend/tests/test_clinical_trials.py
git commit -m "feat: implement ClinicalTrials.gov search and fetch tools"
```

---

## Task 5: Bing Search Function Tool

**Files:**
- Create: `backend/app/tools/bing_search.py`
- Create: `backend/tests/test_bing_search.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_bing_search.py
import json
import pytest
from unittest.mock import patch
from app.tools.bing_search import bing_search

BING_RESPONSE = {
    "webPages": {
        "value": [
            {
                "name": "GLP-1R research breakthrough",
                "snippet": "New findings on GLP-1R agonists show promise.",
                "url": "https://example.com/glp1r",
            },
            {
                "name": "Obesity drug pipeline 2026",
                "snippet": "Multiple GLP-1R drugs in late-stage trials.",
                "url": "https://example.com/obesity",
            },
        ]
    }
}


@pytest.mark.asyncio
async def test_bing_search_returns_results(httpx_mock):
    httpx_mock.add_response(json=BING_RESPONSE)
    result = await bing_search(query="GLP-1R obesity research", count=5)
    parsed = json.loads(result)
    assert len(parsed["results"]) == 2
    assert parsed["results"][0]["title"] == "GLP-1R research breakthrough"
    assert parsed["results"][0]["url"] == "https://example.com/glp1r"


@pytest.mark.asyncio
async def test_bing_search_handles_empty_response(httpx_mock):
    httpx_mock.add_response(json={})
    result = await bing_search(query="nonexistent target xyz123")
    parsed = json.loads(result)
    assert parsed["results"] == []
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd backend && python -m pytest tests/test_bing_search.py -v
```

Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement bing_search.py**

```python
# backend/app/tools/bing_search.py
import json

import httpx

from app.config import settings


async def bing_search(query: str, count: int = 5, market: str = "en-US") -> str:
    """Search the web using Bing Search API v7."""
    headers = {"Ocp-Apim-Subscription-Key": settings.BING_SEARCH_KEY}
    params = {"q": query, "count": count, "mkt": market, "responseFilter": "Webpages"}

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(settings.BING_SEARCH_ENDPOINT, headers=headers, params=params)
        resp.raise_for_status()

    data = resp.json()
    web_pages = data.get("webPages", {}).get("value", [])

    results = [
        {
            "title": page.get("name", ""),
            "snippet": page.get("snippet", ""),
            "url": page.get("url", ""),
            "source_type": "Web",
        }
        for page in web_pages
    ]

    return json.dumps({"results": results})
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd backend && python -m pytest tests/test_bing_search.py -v
```

Expected: All tests PASS. (Note: tests mock the config import; if `settings` requires real env vars, set dummy env vars in a `conftest.py` or use `monkeypatch`.)

- [ ] **Step 5: Create conftest.py for test environment**

```python
# backend/tests/conftest.py
import os
os.environ.setdefault("AZURE_AI_PROJECT_ENDPOINT", "https://test.eastus2.api.azureml.ms")
os.environ.setdefault("BING_SEARCH_KEY", "test-bing-key")
os.environ.setdefault("SEARCH_ENDPOINT", "https://test.search.windows.net")
os.environ.setdefault("SEARCH_API_KEY", "test-search-key")
os.environ.setdefault("COSMOS_ENDPOINT", "https://test.documents.azure.com:443/")
os.environ.setdefault("COSMOS_KEY", "test-cosmos-key")
os.environ.setdefault("BLOB_CONNECTION_STRING", "DefaultEndpointsProtocol=https;AccountName=test")
```

- [ ] **Step 6: Commit**

```bash
git add backend/app/tools/bing_search.py backend/tests/test_bing_search.py backend/tests/conftest.py
git commit -m "feat: implement Bing Search tool with test config"
```

---

## Task 6: Knowledge Base — Cosmos DB Client

**Files:**
- Create: `backend/app/knowledge/cosmos_client.py`
- Create: `backend/tests/test_knowledge_base.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_knowledge_base.py
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from app.knowledge.cosmos_client import CosmosReportStore


@pytest.mark.asyncio
async def test_save_report():
    mock_container = MagicMock()
    mock_container.upsert_item = AsyncMock(return_value={"id": "test-id"})

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
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd backend && python -m pytest tests/test_knowledge_base.py -v
```

Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement cosmos_client.py**

```python
# backend/app/knowledge/cosmos_client.py
from azure.cosmos import CosmosClient, PartitionKey
from azure.cosmos.container import ContainerProxy

from app.config import settings


class CosmosReportStore:
    def __init__(self):
        client = CosmosClient(settings.COSMOS_ENDPOINT, credential=settings.COSMOS_KEY)
        database = client.get_database_client(settings.COSMOS_DATABASE)
        self.container: ContainerProxy = database.get_container_client(settings.COSMOS_CONTAINER)

    async def save_report(self, report: dict) -> dict:
        """Upsert a report document."""
        return self.container.upsert_item(report)

    def query_by_target(self, target: str, max_results: int = 10):
        """Query reports by target name."""
        query = "SELECT * FROM c WHERE c.target = @target ORDER BY c.created_at DESC"
        parameters = [{"name": "@target", "value": target}]
        return self.container.query_items(
            query=query, parameters=parameters, max_item_count=max_results
        )

    def get_report(self, report_id: str, target: str) -> dict:
        """Get a specific report by ID."""
        return self.container.read_item(item=report_id, partition_key=target)
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd backend && python -m pytest tests/test_knowledge_base.py -v
```

Expected: All tests PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/knowledge/cosmos_client.py backend/tests/test_knowledge_base.py
git commit -m "feat: implement Cosmos DB report store"
```

---

## Task 7: Knowledge Base — Blob Storage Client

**Files:**
- Create: `backend/app/knowledge/blob_client.py`

- [ ] **Step 1: Implement blob_client.py**

```python
# backend/app/knowledge/blob_client.py
import json

from azure.storage.blob import BlobServiceClient, ContentSettings

from app.config import settings


class BlobReportStorage:
    def __init__(self):
        self.service = BlobServiceClient.from_connection_string(settings.BLOB_CONNECTION_STRING)
        self.reports_container = self.service.get_container_client(settings.BLOB_REPORTS_CONTAINER)
        self.snapshots_container = self.service.get_container_client(
            settings.BLOB_SNAPSHOTS_CONTAINER
        )

    def upload_report(self, report_id: str, content: bytes, content_type: str = "application/vnd.openxmlformats-officedocument.wordprocessingml.document") -> str:
        """Upload a report file (Word/PDF) and return its URL."""
        blob_name = f"{report_id}.docx"
        blob_client = self.reports_container.get_blob_client(blob_name)
        blob_client.upload_blob(
            content,
            overwrite=True,
            content_settings=ContentSettings(content_type=content_type),
        )
        return blob_client.url

    def upload_snapshot(self, report_id: str, raw_data: dict) -> str:
        """Upload raw API response snapshot as JSON."""
        blob_name = f"{report_id}_snapshot.json"
        blob_client = self.snapshots_container.get_blob_client(blob_name)
        blob_client.upload_blob(
            json.dumps(raw_data, ensure_ascii=False, indent=2),
            overwrite=True,
            content_settings=ContentSettings(content_type="application/json"),
        )
        return blob_client.url
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/knowledge/blob_client.py
git commit -m "feat: implement Blob Storage client for reports and snapshots"
```

---

## Task 8: Knowledge Base — AI Search Index + Embedding

**Files:**
- Create: `backend/app/knowledge/embedding.py`
- Create: `backend/app/knowledge/search_client.py`

- [ ] **Step 1: Implement embedding.py**

```python
# backend/app/knowledge/embedding.py
from azure.ai.projects import AIProjectClient
from azure.identity import DefaultAzureCredential

from app.config import settings

_client: AIProjectClient | None = None


def _get_client() -> AIProjectClient:
    global _client
    if _client is None:
        _client = AIProjectClient(
            endpoint=settings.PROJECT_ENDPOINT,
            credential=DefaultAzureCredential(),
        )
    return _client


async def generate_embedding(text: str) -> list[float]:
    """Generate embedding vector for text using Foundry deployment."""
    client = _get_client()
    response = client.inference.get_embeddings_client().embed(
        model_id=settings.EMBEDDING_DEPLOYMENT,
        input=[text],
    )
    return list(response.data[0].embedding)
```

- [ ] **Step 2: Implement search_client.py**

```python
# backend/app/knowledge/search_client.py
from azure.core.credentials import AzureKeyCredential
from azure.search.documents import SearchClient
from azure.search.documents.indexes import SearchIndexClient
from azure.search.documents.indexes.models import (
    SearchIndex,
    SearchField,
    SearchFieldDataType,
    SimpleField,
    SearchableField,
    VectorSearch,
    HnswAlgorithmConfiguration,
    VectorSearchProfile,
    SearchFieldDataType as DT,
)
from azure.search.documents.models import VectorizedQuery

from app.config import settings
from app.knowledge.embedding import generate_embedding

INDEX_FIELDS = [
    SimpleField(name="id", type=DT.String, key=True, filterable=True),
    SimpleField(name="target", type=DT.String, filterable=True, sortable=True),
    SimpleField(name="indication", type=DT.String, filterable=True),
    SimpleField(name="recommendation", type=DT.String, filterable=True),
    SearchableField(name="summary_text", type=DT.String),
    SearchableField(name="literature_summary", type=DT.String),
    SearchableField(name="clinical_summary", type=DT.String),
    SearchableField(name="competition_summary", type=DT.String),
    SimpleField(name="created_at", type=DT.DateTimeOffset, filterable=True, sortable=True),
    SearchField(
        name="summary_vector",
        type=SearchFieldDataType.Collection(SearchFieldDataType.Single),
        searchable=True,
        vector_search_dimensions=3072,  # text-embedding-3-large
        vector_search_profile_name="default-profile",
    ),
]


def get_index_client() -> SearchIndexClient:
    return SearchIndexClient(
        endpoint=settings.SEARCH_ENDPOINT,
        credential=AzureKeyCredential(settings.SEARCH_API_KEY),
    )


def get_search_client() -> SearchClient:
    return SearchClient(
        endpoint=settings.SEARCH_ENDPOINT,
        index_name=settings.SEARCH_INDEX_NAME,
        credential=AzureKeyCredential(settings.SEARCH_API_KEY),
    )


def ensure_index():
    """Create or update the search index."""
    index_client = get_index_client()
    vector_search = VectorSearch(
        algorithms=[HnswAlgorithmConfiguration(name="default-algo")],
        profiles=[VectorSearchProfile(name="default-profile", algorithm_configuration_name="default-algo")],
    )
    index = SearchIndex(
        name=settings.SEARCH_INDEX_NAME,
        fields=INDEX_FIELDS,
        vector_search=vector_search,
    )
    index_client.create_or_update_index(index)


async def index_report(report: dict):
    """Generate embedding and upload document to AI Search."""
    summary_text = (
        f"{report.get('literature_summary', '')} "
        f"{report.get('clinical_trials_summary', '')} "
        f"{report.get('competition_summary', '')}"
    )
    vector = await generate_embedding(summary_text)

    doc = {
        "id": report["id"],
        "target": report.get("target", ""),
        "indication": report.get("indication", ""),
        "recommendation": report.get("recommendation", ""),
        "summary_text": summary_text,
        "literature_summary": report.get("literature_summary", ""),
        "clinical_summary": report.get("clinical_trials_summary", ""),
        "competition_summary": report.get("competition_summary", ""),
        "created_at": report.get("created_at", ""),
        "summary_vector": vector,
    }
    client = get_search_client()
    client.upload_documents([doc])


async def search_reports(query: str, target: str | None = None, top_k: int = 5) -> list[dict]:
    """Hybrid search: vector similarity + keyword matching."""
    vector = await generate_embedding(query)
    vector_query = VectorizedQuery(vector=vector, k_nearest_neighbors=top_k, fields="summary_vector")

    filter_expr = f"target eq '{target}'" if target else None

    client = get_search_client()
    results = client.search(
        search_text=query,
        vector_queries=[vector_query],
        filter=filter_expr,
        top=top_k,
        select=["id", "target", "indication", "recommendation", "summary_text", "created_at"],
    )

    return [
        {
            "id": r["id"],
            "target": r["target"],
            "indication": r["indication"],
            "recommendation": r["recommendation"],
            "summary": r["summary_text"][:500],
            "created_at": r["created_at"],
            "score": r["@search.score"],
        }
        for r in results
    ]
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/knowledge/embedding.py backend/app/knowledge/search_client.py
git commit -m "feat: implement AI Search index and embedding for knowledge base"
```

---

## Task 9: Knowledge Base Function Tools (for Agents)

**Files:**
- Create: `backend/app/tools/knowledge_base.py`

- [ ] **Step 1: Implement knowledge_base.py**

```python
# backend/app/tools/knowledge_base.py
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


async def write_to_knowledge_base(report: dict, raw_outputs: dict) -> str:
    """Write query results to Cosmos DB, Blob Storage, and AI Search."""
    report_id = str(uuid.uuid4())
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
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/tools/knowledge_base.py
git commit -m "feat: implement knowledge base function tools for agents"
```

---

## Task 10: Report Export

**Files:**
- Create: `backend/app/export/report.py`
- Create: `backend/tests/test_export.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_export.py
import io
from docx import Document
from app.export.report import generate_word_report, generate_markdown_report


def test_generate_markdown_report():
    report = {
        "target": "GLP-1R",
        "indication": "Obesity",
        "literature_summary": "Strong evidence from 15 studies.",
        "clinical_trials_summary": "3 Phase 3 trials active.",
        "competition_summary": "Competitive but differentiable.",
        "major_risks": ["High competition"],
        "major_opportunities": ["Large unmet need"],
        "recommendation": "Go",
        "reasoning": "Strong biology and clinical signals.",
        "uncertainty": "Long-term safety data limited.",
        "citations": [
            {"title": "Study A", "link": "https://pubmed.ncbi.nlm.nih.gov/123/", "source_type": "PubMed"}
        ],
    }
    md = generate_markdown_report(report)
    assert "# Drug Target Assessment Report" in md
    assert "GLP-1R" in md
    assert "Go" in md
    assert "https://pubmed.ncbi.nlm.nih.gov/123/" in md


def test_generate_word_report():
    report = {
        "target": "GLP-1R",
        "indication": "Obesity",
        "literature_summary": "Strong evidence.",
        "clinical_trials_summary": "Active trials.",
        "competition_summary": "Moderate.",
        "major_risks": ["Risk A"],
        "major_opportunities": ["Opportunity A"],
        "recommendation": "Go",
        "reasoning": "Solid evidence base.",
        "uncertainty": "Limited data.",
        "citations": [
            {"title": "Paper 1", "link": "https://example.com", "source_type": "Web"}
        ],
    }
    doc_bytes = generate_word_report(report)
    assert isinstance(doc_bytes, bytes)
    doc = Document(io.BytesIO(doc_bytes))
    full_text = "\n".join(p.text for p in doc.paragraphs)
    assert "GLP-1R" in full_text
    assert "Go" in full_text
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd backend && python -m pytest tests/test_export.py -v
```

Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement report.py**

```python
# backend/app/export/report.py
import io

from docx import Document


def generate_markdown_report(report: dict) -> str:
    """Generate a Markdown report from the decision output."""
    citations = report.get("citations", [])
    citation_lines = "\n".join(
        f"- [{c['title']}]({c['link']}) ({c['source_type']})" for c in citations
    )
    risks = "\n".join(f"- {r}" for r in report.get("major_risks", []))
    opportunities = "\n".join(f"- {o}" for o in report.get("major_opportunities", []))

    return f"""# Drug Target Assessment Report

## Target: {report.get('target', '')}
## Indication: {report.get('indication', '')}

---

## Literature Summary
{report.get('literature_summary', '')}

## Clinical Trials Summary
{report.get('clinical_trials_summary', '')}

## Competition Summary
{report.get('competition_summary', '')}

## Major Risks
{risks}

## Major Opportunities
{opportunities}

## Recommendation: {report.get('recommendation', '')}

**Reasoning:** {report.get('reasoning', '')}

**Uncertainty:** {report.get('uncertainty', '')}

## Citations
{citation_lines}
"""


def generate_word_report(report: dict) -> bytes:
    """Generate a Word document from the decision output."""
    doc = Document()
    doc.add_heading("Drug Target Assessment Report", level=0)

    doc.add_heading(f"Target: {report.get('target', '')}", level=1)
    doc.add_heading(f"Indication: {report.get('indication', '')}", level=1)

    doc.add_heading("Literature Summary", level=2)
    doc.add_paragraph(report.get("literature_summary", ""))

    doc.add_heading("Clinical Trials Summary", level=2)
    doc.add_paragraph(report.get("clinical_trials_summary", ""))

    doc.add_heading("Competition Summary", level=2)
    doc.add_paragraph(report.get("competition_summary", ""))

    doc.add_heading("Major Risks", level=2)
    for risk in report.get("major_risks", []):
        doc.add_paragraph(risk, style="List Bullet")

    doc.add_heading("Major Opportunities", level=2)
    for opp in report.get("major_opportunities", []):
        doc.add_paragraph(opp, style="List Bullet")

    doc.add_heading(f"Recommendation: {report.get('recommendation', '')}", level=1)
    doc.add_paragraph(f"Reasoning: {report.get('reasoning', '')}")
    doc.add_paragraph(f"Uncertainty: {report.get('uncertainty', '')}")

    doc.add_heading("Citations", level=2)
    for c in report.get("citations", []):
        doc.add_paragraph(f"{c['title']} - {c['link']} ({c['source_type']})")

    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd backend && python -m pytest tests/test_export.py -v
```

Expected: All tests PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/export/report.py backend/tests/test_export.py
git commit -m "feat: implement Markdown and Word report export"
```

---

## Task 11: Agent Definitions and Setup

**Files:**
- Create: `backend/app/agents/definitions.py`
- Create: `backend/app/agents/setup.py`

- [ ] **Step 1: Implement FunctionTool definitions**

```python
# backend/app/agents/definitions.py
from azure.ai.projects.models import FunctionTool


search_pubmed_tool = FunctionTool(
    name="search_pubmed",
    description="Search PubMed for scientific literature related to a drug target or disease.",
    parameters={
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Search query combining target and/or indication"},
            "max_results": {"type": "integer", "description": "Maximum number of results to return", "default": 10},
            "date_range": {"type": "string", "description": "Relative date range in days, e.g. '1825' for 5 years"},
        },
        "required": ["query"],
        "additionalProperties": False,
    },
    strict=True,
)

fetch_pubmed_details_tool = FunctionTool(
    name="fetch_pubmed_details",
    description="Fetch detailed information (title, abstract, authors, year) for specific PubMed articles by PMID.",
    parameters={
        "type": "object",
        "properties": {
            "pmids": {
                "type": "array",
                "items": {"type": "string"},
                "description": "List of PubMed IDs to fetch details for",
            },
        },
        "required": ["pmids"],
        "additionalProperties": False,
    },
    strict=True,
)

search_clinical_trials_tool = FunctionTool(
    name="search_clinical_trials",
    description="Search ClinicalTrials.gov for clinical trials related to a drug target or disease.",
    parameters={
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Search query combining target and/or indication"},
            "max_results": {"type": "integer", "description": "Maximum number of results", "default": 10},
            "status": {"type": "string", "description": "Filter by trial status, e.g. 'RECRUITING'"},
        },
        "required": ["query"],
        "additionalProperties": False,
    },
    strict=True,
)

fetch_trial_details_tool = FunctionTool(
    name="fetch_trial_details",
    description="Fetch detailed information for specific clinical trials by NCT ID.",
    parameters={
        "type": "object",
        "properties": {
            "nct_ids": {
                "type": "array",
                "items": {"type": "string"},
                "description": "List of NCT IDs to fetch details for",
            },
        },
        "required": ["nct_ids"],
        "additionalProperties": False,
    },
    strict=True,
)

bing_search_tool = FunctionTool(
    name="bing_search",
    description="Search the web using Bing for supplementary information like news, company announcements, and research reports.",
    parameters={
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Web search query"},
            "count": {"type": "integer", "description": "Number of results to return", "default": 5},
            "market": {"type": "string", "description": "Market code, e.g. 'en-US'", "default": "en-US"},
        },
        "required": ["query"],
        "additionalProperties": False,
    },
    strict=True,
)

search_knowledge_base_tool = FunctionTool(
    name="search_knowledge_base",
    description="Search the historical knowledge base for previous assessment reports on drug targets.",
    parameters={
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Search query for knowledge base"},
            "target": {"type": "string", "description": "Filter by target name"},
            "indication": {"type": "string", "description": "Filter by indication"},
            "top_k": {"type": "integer", "description": "Number of results to return", "default": 5},
        },
        "required": ["query"],
        "additionalProperties": False,
    },
    strict=True,
)

write_to_knowledge_base_tool = FunctionTool(
    name="write_to_knowledge_base",
    description="Save the assessment results to the knowledge base for future reference.",
    parameters={
        "type": "object",
        "properties": {
            "report": {"type": "object", "description": "The decision summary agent's full output"},
            "raw_outputs": {"type": "object", "description": "Raw outputs from all sub-agents"},
        },
        "required": ["report", "raw_outputs"],
        "additionalProperties": False,
    },
    strict=True,
)

# Tool groups per agent
LITERATURE_AGENT_TOOLS = [search_pubmed_tool, fetch_pubmed_details_tool, bing_search_tool]
CLINICAL_TRIALS_AGENT_TOOLS = [search_clinical_trials_tool, fetch_trial_details_tool, bing_search_tool]
COMPETITION_AGENT_TOOLS = [bing_search_tool, search_pubmed_tool, search_clinical_trials_tool]
ORCHESTRATOR_TOOLS = [search_knowledge_base_tool, write_to_knowledge_base_tool]
```

- [ ] **Step 2: Implement agent setup**

```python
# backend/app/agents/setup.py
from azure.ai.projects import AIProjectClient
from azure.identity import DefaultAzureCredential

from app.config import settings
from app.agents.definitions import (
    LITERATURE_AGENT_TOOLS,
    CLINICAL_TRIALS_AGENT_TOOLS,
    COMPETITION_AGENT_TOOLS,
    ORCHESTRATOR_TOOLS,
)

_client: AIProjectClient | None = None


def get_project_client() -> AIProjectClient:
    global _client
    if _client is None:
        _client = AIProjectClient(
            endpoint=settings.PROJECT_ENDPOINT,
            credential=DefaultAzureCredential(),
        )
    return _client


LITERATURE_INSTRUCTIONS = """You are a scientific literature research agent for drug target assessment.
Given a target name and optional indication, you must:
1. Use search_pubmed to find relevant scientific papers (up to 10).
2. Use fetch_pubmed_details to get abstracts for the top results.
3. Use bing_search to find supplementary academic evidence (reviews, meta-analyses).
4. Summarize the evidence: support strength (strong/moderate/weak), positive and negative findings.
5. Return a structured JSON with: papers list, web_results, summary, support_strength, positive_evidence, negative_evidence, confidence."""

CLINICAL_TRIALS_INSTRUCTIONS = """You are a clinical trials intelligence agent for drug target assessment.
Given a target name and optional indication, you must:
1. Use search_clinical_trials to find relevant trials on ClinicalTrials.gov (up to 10).
2. Use fetch_trial_details for the most relevant trials to get enrollment and detail info.
3. Use bing_search to find trial result announcements, FDA updates, and failure analyses.
4. Analyze phase distribution, status distribution, positive and negative signals.
5. Return a structured JSON with: trials list, web_results, phase_distribution, status_distribution, positive_signals, negative_signals, summary, confidence."""

COMPETITION_INSTRUCTIONS = """You are a competitive intelligence agent for drug target assessment.
Given a target name and optional indication, you must:
1. Use bing_search to find company pipeline news, competitive landscape reports.
2. Use search_pubmed to identify research hotspots and trending areas.
3. Use search_clinical_trials to map competitor trial activity.
4. Assess competition level (high/medium/low), identify major players, crowding signals.
5. Return a structured JSON with: competition_level, major_players, research_hotspots, crowding_signals, differentiation_opportunities, web_results, summary, confidence."""

DECISION_INSTRUCTIONS = """You are a decision summary agent for drug target Go/No-Go assessment.
You receive evidence from three research agents (literature, clinical trials, competition) and optional historical data.
You must:
1. Evaluate all evidence objectively.
2. Apply these rules:
   - Go: strong literature support + positive clinical signals + manageable competition
   - No-Go: weak evidence + clinical failures + saturated competition
   - Need More Data: insufficient or mixed evidence
3. Return a structured JSON with: target, indication, literature_summary, clinical_trials_summary, competition_summary, major_risks, major_opportunities, recommendation (Go/No-Go/Need More Data), reasoning, uncertainty, citations."""

ORCHESTRATOR_INSTRUCTIONS = """You are the orchestrator agent for drug target assessment.
Your workflow:
1. Parse the user's query to extract target name and indication.
2. Use search_knowledge_base to check for historical assessments.
3. Present your understanding back to the user for confirmation.
4. After confirmation, you will coordinate sub-agents (handled by the backend).
5. After receiving sub-agent results and the decision summary, use write_to_knowledge_base to save.
6. Present the final report to the user."""


def create_all_agents() -> dict[str, str]:
    """Create all 5 agents and return their IDs."""
    client = get_project_client()
    agents = {}

    literature = client.agents.create_agent(
        model=settings.MODEL_DEPLOYMENT,
        name="literature-research-agent",
        instructions=LITERATURE_INSTRUCTIONS,
        tools=[t.as_dict() for t in LITERATURE_AGENT_TOOLS],
    )
    agents["literature"] = literature.id

    clinical = client.agents.create_agent(
        model=settings.MODEL_DEPLOYMENT,
        name="clinical-trials-agent",
        instructions=CLINICAL_TRIALS_INSTRUCTIONS,
        tools=[t.as_dict() for t in CLINICAL_TRIALS_AGENT_TOOLS],
    )
    agents["clinical_trials"] = clinical.id

    competition = client.agents.create_agent(
        model=settings.MODEL_DEPLOYMENT,
        name="competition-intel-agent",
        instructions=COMPETITION_INSTRUCTIONS,
        tools=[t.as_dict() for t in COMPETITION_AGENT_TOOLS],
    )
    agents["competition"] = competition.id

    decision = client.agents.create_agent(
        model=settings.MODEL_DEPLOYMENT,
        name="decision-summary-agent",
        instructions=DECISION_INSTRUCTIONS,
        tools=[],  # No external tools — pure LLM reasoning
    )
    agents["decision"] = decision.id

    orchestrator = client.agents.create_agent(
        model=settings.MODEL_DEPLOYMENT,
        name="orchestrator-agent",
        instructions=ORCHESTRATOR_INSTRUCTIONS,
        tools=[t.as_dict() for t in ORCHESTRATOR_TOOLS],
    )
    agents["orchestrator"] = orchestrator.id

    return agents
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/agents/definitions.py backend/app/agents/setup.py
git commit -m "feat: define all FunctionTools and agent setup for 5 Foundry Agents"
```

---

## Task 12: Orchestrator Logic

**Files:**
- Create: `backend/app/agents/orchestrator.py`

- [ ] **Step 1: Implement orchestrator.py**

This is the core orchestration loop that runs agents, handles function calls, and coordinates the full pipeline.

```python
# backend/app/agents/orchestrator.py
import asyncio
import json
import time

from azure.ai.projects import AIProjectClient
from azure.ai.projects.models import (
    ThreadMessage,
    SubmitToolOutputsAction,
    RequiredFunctionToolCall,
    ToolOutput,
)

from app.agents.setup import get_project_client
from app.tools.pubmed import search_pubmed, fetch_pubmed_details
from app.tools.clinical_trials import search_clinical_trials, fetch_trial_details
from app.tools.bing_search import bing_search
from app.tools.knowledge_base import search_knowledge_base, write_to_knowledge_base

# Map tool names to their implementations
TOOL_FUNCTIONS = {
    "search_pubmed": search_pubmed,
    "fetch_pubmed_details": fetch_pubmed_details,
    "search_clinical_trials": search_clinical_trials,
    "fetch_trial_details": fetch_trial_details,
    "bing_search": bing_search,
    "search_knowledge_base": search_knowledge_base,
    "write_to_knowledge_base": write_to_knowledge_base,
}


async def _execute_tool_call(tool_call: RequiredFunctionToolCall) -> str:
    """Execute a single function tool call and return the result string."""
    func = TOOL_FUNCTIONS.get(tool_call.function.name)
    if func is None:
        return json.dumps({"error": f"Unknown tool: {tool_call.function.name}"})

    args = json.loads(tool_call.function.arguments)
    return await func(**args)


async def _run_agent_to_completion(
    client: AIProjectClient, agent_id: str, thread_id: str
) -> str:
    """Run an agent on a thread, handle all function calls, and return the final message."""
    run = client.agents.runs.create(thread_id=thread_id, agent_id=agent_id)

    while run.status in ("queued", "in_progress", "requires_action"):
        if run.status == "requires_action" and isinstance(
            run.required_action, SubmitToolOutputsAction
        ):
            tool_calls = run.required_action.submit_tool_outputs.tool_calls
            tool_outputs = []
            for tc in tool_calls:
                if isinstance(tc, RequiredFunctionToolCall):
                    result = await _execute_tool_call(tc)
                    tool_outputs.append(ToolOutput(tool_call_id=tc.id, output=result))

            client.agents.runs.submit_tool_outputs(
                thread_id=thread_id, run_id=run.id, tool_outputs=tool_outputs
            )

        time.sleep(1)
        run = client.agents.runs.get(thread_id=thread_id, run_id=run.id)

    if run.status != "completed":
        return json.dumps({"error": f"Agent run failed with status: {run.status}"})

    messages = client.agents.messages.list(thread_id=thread_id)
    for msg in messages:
        if msg.role == "assistant":
            for content in msg.content:
                if hasattr(content, "text"):
                    return content.text.value
    return json.dumps({"error": "No assistant message found"})


async def run_sub_agent(agent_id: str, prompt: str) -> str:
    """Run a sub-agent in its own thread with the given prompt."""
    client = get_project_client()
    thread = client.agents.threads.create()
    client.agents.messages.create(thread_id=thread.id, role="user", content=prompt)
    return await _run_agent_to_completion(client, agent_id, thread.id)


async def run_full_pipeline(
    agent_ids: dict[str, str],
    target: str,
    indication: str = "",
) -> dict:
    """Run the complete assessment pipeline.

    Steps:
    1. Search knowledge base for historical data
    2. Run literature, clinical trials, competition agents in parallel
    3. Run decision summary agent with all evidence
    4. Write results to knowledge base
    """
    client = get_project_client()
    query = f"{target} {indication}".strip()

    # Step 1: Check knowledge base
    kb_result = await search_knowledge_base(query=query, target=target, indication=indication)
    kb_data = json.loads(kb_result)

    # Step 2: Run 3 research agents in parallel
    research_prompt = f"Assess the drug target '{target}'"
    if indication:
        research_prompt += f" for the indication '{indication}'"
    research_prompt += ". Search thoroughly and provide structured analysis."

    literature_task = run_sub_agent(agent_ids["literature"], research_prompt)
    clinical_task = run_sub_agent(agent_ids["clinical_trials"], research_prompt)
    competition_task = run_sub_agent(agent_ids["competition"], research_prompt)

    lit_result, clin_result, comp_result = await asyncio.gather(
        literature_task, clinical_task, competition_task
    )

    # Step 3: Run decision summary agent
    decision_prompt = f"""Based on the following evidence, provide a Go/No-Go/Need More Data recommendation for target '{target}' (indication: {indication or 'not specified'}).

## Literature Evidence
{lit_result}

## Clinical Trials Evidence
{clin_result}

## Competition Intelligence
{comp_result}

## Historical Context
{json.dumps(kb_data.get('historical_reports', []), indent=2)}

Provide your structured assessment."""

    decision_result = await run_sub_agent(agent_ids["decision"], decision_prompt)

    # Parse results
    raw_outputs = {
        "literature": _safe_parse(lit_result),
        "clinical_trials": _safe_parse(clin_result),
        "competition": _safe_parse(comp_result),
    }
    report = _safe_parse(decision_result)
    report.setdefault("target", target)
    report.setdefault("indication", indication)

    # Step 4: Write to knowledge base
    await write_to_knowledge_base(report=report, raw_outputs=raw_outputs)

    return {
        "report": report,
        "raw_outputs": raw_outputs,
        "knowledge_base_context": kb_data,
    }


def _safe_parse(text: str) -> dict:
    """Try to parse JSON from agent output, handling markdown code blocks."""
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        lines = [l for l in lines if not l.startswith("```")]
        text = "\n".join(lines)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {"raw_text": text}
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/agents/orchestrator.py
git commit -m "feat: implement orchestrator logic with parallel sub-agent execution"
```

---

## Task 13: FastAPI Backend

**Files:**
- Create: `backend/app/main.py`

- [ ] **Step 1: Implement main.py**

```python
# backend/app/main.py
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app.agents.setup import create_all_agents
from app.agents.orchestrator import run_full_pipeline
from app.knowledge.search_client import ensure_index
from app.export.report import generate_markdown_report, generate_word_report

# Store agent IDs after creation
_agent_ids: dict[str, str] = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Create agents and search index on startup."""
    global _agent_ids
    ensure_index()
    _agent_ids = create_all_agents()
    yield


app = FastAPI(title="Drug Target Decision Support Agent", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class AssessmentRequest(BaseModel):
    target: str
    indication: str = ""


class ConfirmRequest(BaseModel):
    target: str
    indication: str = ""
    confirmed: bool = True


@app.post("/api/assess")
async def assess_target(req: AssessmentRequest):
    """Run the full assessment pipeline for a drug target."""
    if not _agent_ids:
        raise HTTPException(status_code=503, detail="Agents not initialized")

    result = await run_full_pipeline(
        agent_ids=_agent_ids,
        target=req.target,
        indication=req.indication,
    )
    return result


@app.post("/api/export/markdown")
async def export_markdown(req: AssessmentRequest):
    """Re-export a report as Markdown (uses latest assessment data)."""
    result = await run_full_pipeline(
        agent_ids=_agent_ids,
        target=req.target,
        indication=req.indication,
    )
    md = generate_markdown_report(result["report"])
    return {"markdown": md}


@app.get("/api/health")
async def health():
    return {"status": "ok", "agents_ready": bool(_agent_ids)}
```

- [ ] **Step 2: Test locally**

```bash
cd backend
cp .env.example .env  # fill in real values
source .venv/bin/activate
uvicorn app.main:app --reload --port 8000
```

Then:
```bash
curl http://localhost:8000/api/health
```

Expected: `{"status":"ok","agents_ready":true}`

- [ ] **Step 3: Commit**

```bash
git add backend/app/main.py
git commit -m "feat: implement FastAPI backend with assessment and export endpoints"
```

---

## Task 14: Frontend — React App

**Files:**
- Create: `frontend/package.json`
- Create: `frontend/vite.config.ts`
- Create: `frontend/index.html`
- Create: `frontend/src/main.tsx`
- Create: `frontend/src/App.tsx`
- Create: `frontend/src/types.ts`
- Create: `frontend/src/api.ts`
- Create: `frontend/src/components/SearchForm.tsx`
- Create: `frontend/src/components/ResultCard.tsx`
- Create: `frontend/src/components/LiteratureTab.tsx`
- Create: `frontend/src/components/ClinicalTrialsTab.tsx`
- Create: `frontend/src/components/CompetitionTab.tsx`
- Create: `frontend/src/components/CitationList.tsx`

- [ ] **Step 1: Scaffold frontend project**

```bash
cd frontend
npm create vite@latest . -- --template react-ts
npm install
```

- [ ] **Step 2: Create types.ts**

```typescript
// frontend/src/types.ts
export interface Citation {
  title: string;
  link: string;
  source_type: "PubMed" | "ClinicalTrials" | "Web";
}

export interface Report {
  target: string;
  indication: string;
  literature_summary: string;
  clinical_trials_summary: string;
  competition_summary: string;
  major_risks: string[];
  major_opportunities: string[];
  recommendation: "Go" | "No-Go" | "Need More Data";
  reasoning: string;
  uncertainty: string;
  citations: Citation[];
}

export interface Trial {
  nct_id: string;
  title: string;
  phase: string;
  status: string;
  conditions: string[];
  interventions: { name: string; type: string }[];
  sponsor: string;
  link: string;
}

export interface Paper {
  pmid: string;
  title: string;
  abstract: string;
  authors: string;
  year: string;
  link: string;
  source_type: string;
}

export interface AssessmentResult {
  report: Report;
  raw_outputs: {
    literature: { papers?: Paper[]; summary?: string };
    clinical_trials: { trials?: Trial[]; summary?: string };
    competition: { summary?: string; major_players?: string[] };
  };
  knowledge_base_context: { historical_reports: any[]; count: number };
}
```

- [ ] **Step 3: Create api.ts**

```typescript
// frontend/src/api.ts
import type { AssessmentResult } from "./types";

const API_BASE = import.meta.env.VITE_API_BASE || "/api";

export async function assessTarget(
  target: string,
  indication: string
): Promise<AssessmentResult> {
  const resp = await fetch(`${API_BASE}/assess`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ target, indication }),
  });
  if (!resp.ok) throw new Error(`API error: ${resp.status}`);
  return resp.json();
}
```

- [ ] **Step 4: Create SearchForm.tsx**

```tsx
// frontend/src/components/SearchForm.tsx
import { useState } from "react";

interface Props {
  onSubmit: (target: string, indication: string) => void;
  loading: boolean;
}

export function SearchForm({ onSubmit, loading }: Props) {
  const [target, setTarget] = useState("");
  const [indication, setIndication] = useState("");

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        if (target.trim()) onSubmit(target.trim(), indication.trim());
      }}
      style={{ display: "flex", flexDirection: "column", gap: "12px", maxWidth: "500px" }}
    >
      <label>
        Target Name *
        <input
          type="text"
          value={target}
          onChange={(e) => setTarget(e.target.value)}
          placeholder="e.g. GLP-1R, TL1A, PCSK9"
          required
          style={{ display: "block", width: "100%", padding: "8px", marginTop: "4px" }}
        />
      </label>
      <label>
        Indication (optional)
        <input
          type="text"
          value={indication}
          onChange={(e) => setIndication(e.target.value)}
          placeholder="e.g. Obesity, IBD, Hypercholesterolemia"
          style={{ display: "block", width: "100%", padding: "8px", marginTop: "4px" }}
        />
      </label>
      <button type="submit" disabled={loading || !target.trim()} style={{ padding: "10px 20px" }}>
        {loading ? "Analyzing..." : "Assess Target"}
      </button>
    </form>
  );
}
```

- [ ] **Step 5: Create ResultCard.tsx**

```tsx
// frontend/src/components/ResultCard.tsx
import type { Report } from "../types";

const COLORS = { Go: "#22c55e", "No-Go": "#ef4444", "Need More Data": "#f59e0b" };

export function ResultCard({ report }: { report: Report }) {
  return (
    <div
      style={{
        border: `3px solid ${COLORS[report.recommendation]}`,
        borderRadius: "12px",
        padding: "24px",
        marginBottom: "20px",
      }}
    >
      <h2 style={{ color: COLORS[report.recommendation], margin: 0 }}>
        {report.recommendation}
      </h2>
      <p>
        <strong>Target:</strong> {report.target} | <strong>Indication:</strong>{" "}
        {report.indication || "N/A"}
      </p>
      <p>{report.reasoning}</p>
      <p>
        <em>Uncertainty: {report.uncertainty}</em>
      </p>
    </div>
  );
}
```

- [ ] **Step 6: Create LiteratureTab, ClinicalTrialsTab, CompetitionTab, CitationList**

```tsx
// frontend/src/components/LiteratureTab.tsx
import type { Paper } from "../types";

export function LiteratureTab({ papers, summary }: { papers: Paper[]; summary: string }) {
  return (
    <div>
      <h3>Literature Summary</h3>
      <p>{summary}</p>
      <h4>Key Papers</h4>
      {papers.map((p) => (
        <div key={p.pmid} style={{ borderBottom: "1px solid #eee", padding: "8px 0" }}>
          <a href={p.link} target="_blank" rel="noreferrer">
            {p.title}
          </a>
          <br />
          <small>
            {p.authors} ({p.year}) — PMID: {p.pmid}
          </small>
          <p style={{ fontSize: "0.9em", color: "#555" }}>{p.abstract?.slice(0, 200)}...</p>
        </div>
      ))}
    </div>
  );
}
```

```tsx
// frontend/src/components/ClinicalTrialsTab.tsx
import type { Trial } from "../types";

export function ClinicalTrialsTab({ trials, summary }: { trials: Trial[]; summary: string }) {
  return (
    <div>
      <h3>Clinical Trials Summary</h3>
      <p>{summary}</p>
      <table style={{ width: "100%", borderCollapse: "collapse" }}>
        <thead>
          <tr style={{ borderBottom: "2px solid #333", textAlign: "left" }}>
            <th>NCT ID</th>
            <th>Title</th>
            <th>Phase</th>
            <th>Status</th>
            <th>Sponsor</th>
          </tr>
        </thead>
        <tbody>
          {trials.map((t) => (
            <tr key={t.nct_id} style={{ borderBottom: "1px solid #eee" }}>
              <td>
                <a href={t.link} target="_blank" rel="noreferrer">
                  {t.nct_id}
                </a>
              </td>
              <td>{t.title}</td>
              <td>{t.phase}</td>
              <td>{t.status}</td>
              <td>{t.sponsor}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
```

```tsx
// frontend/src/components/CompetitionTab.tsx
export function CompetitionTab({
  summary,
  players,
}: {
  summary: string;
  players: string[];
}) {
  return (
    <div>
      <h3>Competition Summary</h3>
      <p>{summary}</p>
      {players.length > 0 && (
        <>
          <h4>Major Players</h4>
          <ul>
            {players.map((p, i) => (
              <li key={i}>{p}</li>
            ))}
          </ul>
        </>
      )}
    </div>
  );
}
```

```tsx
// frontend/src/components/CitationList.tsx
import type { Citation } from "../types";

const BADGE = { PubMed: "#3b82f6", ClinicalTrials: "#8b5cf6", Web: "#6b7280" };

export function CitationList({ citations }: { citations: Citation[] }) {
  return (
    <div>
      <h3>Citations</h3>
      {citations.map((c, i) => (
        <div key={i} style={{ padding: "4px 0" }}>
          <span
            style={{
              background: BADGE[c.source_type] || "#999",
              color: "#fff",
              padding: "2px 8px",
              borderRadius: "4px",
              fontSize: "0.8em",
              marginRight: "8px",
            }}
          >
            {c.source_type}
          </span>
          <a href={c.link} target="_blank" rel="noreferrer">
            {c.title}
          </a>
        </div>
      ))}
    </div>
  );
}
```

- [ ] **Step 7: Create App.tsx**

```tsx
// frontend/src/App.tsx
import { useState } from "react";
import { assessTarget } from "./api";
import type { AssessmentResult } from "./types";
import { SearchForm } from "./components/SearchForm";
import { ResultCard } from "./components/ResultCard";
import { LiteratureTab } from "./components/LiteratureTab";
import { ClinicalTrialsTab } from "./components/ClinicalTrialsTab";
import { CompetitionTab } from "./components/CompetitionTab";
import { CitationList } from "./components/CitationList";

type Tab = "literature" | "trials" | "competition";

export default function App() {
  const [result, setResult] = useState<AssessmentResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [tab, setTab] = useState<Tab>("literature");

  const handleSubmit = async (target: string, indication: string) => {
    setLoading(true);
    setError("");
    setResult(null);
    try {
      const data = await assessTarget(target, indication);
      setResult(data);
    } catch (e: any) {
      setError(e.message || "Assessment failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ maxWidth: "900px", margin: "0 auto", padding: "20px", fontFamily: "system-ui" }}>
      <h1>Drug Target Decision Support</h1>
      <p>Enter a drug target to get a Go / No-Go / Need More Data recommendation.</p>

      <SearchForm onSubmit={handleSubmit} loading={loading} />

      {error && <p style={{ color: "red" }}>{error}</p>}

      {result && (
        <>
          <ResultCard report={result.report} />

          <div style={{ display: "flex", gap: "8px", marginBottom: "16px" }}>
            {(["literature", "trials", "competition"] as Tab[]).map((t) => (
              <button
                key={t}
                onClick={() => setTab(t)}
                style={{
                  padding: "8px 16px",
                  background: tab === t ? "#333" : "#eee",
                  color: tab === t ? "#fff" : "#333",
                  border: "none",
                  borderRadius: "6px",
                  cursor: "pointer",
                }}
              >
                {t === "literature" ? "Literature" : t === "trials" ? "Clinical Trials" : "Competition"}
              </button>
            ))}
          </div>

          {tab === "literature" && (
            <LiteratureTab
              papers={result.raw_outputs.literature?.papers || []}
              summary={result.raw_outputs.literature?.summary || ""}
            />
          )}
          {tab === "trials" && (
            <ClinicalTrialsTab
              trials={result.raw_outputs.clinical_trials?.trials || []}
              summary={result.raw_outputs.clinical_trials?.summary || ""}
            />
          )}
          {tab === "competition" && (
            <CompetitionTab
              summary={result.raw_outputs.competition?.summary || ""}
              players={result.raw_outputs.competition?.major_players || []}
            />
          )}

          <CitationList citations={result.report.citations || []} />
        </>
      )}
    </div>
  );
}
```

- [ ] **Step 8: Update main.tsx**

```tsx
// frontend/src/main.tsx
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>
);
```

- [ ] **Step 9: Test frontend locally**

```bash
cd frontend && npm run dev
```

Expected: Opens at http://localhost:5173 with search form visible.

- [ ] **Step 10: Commit**

```bash
git add frontend/
git commit -m "feat: implement React frontend with search, results, and tabs"
```

---

## Task 15: Docker + Deployment

**Files:**
- Create: `backend/Dockerfile`
- Create: `frontend/Dockerfile`
- Create: `infra/deploy.sh`

- [ ] **Step 1: Create backend Dockerfile**

```dockerfile
# backend/Dockerfile
FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml .
RUN pip install --no-cache-dir .

COPY app/ app/

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

- [ ] **Step 2: Create frontend Dockerfile**

```dockerfile
# frontend/Dockerfile
FROM node:22-alpine AS build
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
```

Create `frontend/nginx.conf`:

```nginx
server {
    listen 80;
    location / {
        root /usr/share/nginx/html;
        try_files $uri /index.html;
    }
    location /api/ {
        proxy_pass http://drugtarget-backend:8000/api/;
    }
}
```

- [ ] **Step 3: Create deployment script**

```bash
#!/usr/bin/env bash
# infra/deploy.sh
set -euo pipefail

RESOURCE_GROUP="rg-drug-target-agent"
ACR_NAME="drugtargetacr"
ENV_NAME="drugtarget-env"

# Login to ACR
az acr login --name "$ACR_NAME"

# Build and push backend
cd backend
docker build -t "$ACR_NAME.azurecr.io/backend:latest" .
docker push "$ACR_NAME.azurecr.io/backend:latest"
cd ..

# Build and push frontend
cd frontend
docker build -t "$ACR_NAME.azurecr.io/frontend:latest" .
docker push "$ACR_NAME.azurecr.io/frontend:latest"
cd ..

# Deploy backend
az containerapp create \
  --name drugtarget-backend \
  --resource-group "$RESOURCE_GROUP" \
  --environment "$ENV_NAME" \
  --image "$ACR_NAME.azurecr.io/backend:latest" \
  --registry-server "$ACR_NAME.azurecr.io" \
  --target-port 8000 \
  --ingress internal \
  --min-replicas 1 \
  --max-replicas 3 \
  --env-vars \
    AZURE_AI_PROJECT_ENDPOINT=secretref:project-endpoint \
    BING_SEARCH_KEY=secretref:bing-key \
    SEARCH_ENDPOINT=secretref:search-endpoint \
    SEARCH_API_KEY=secretref:search-key \
    COSMOS_ENDPOINT=secretref:cosmos-endpoint \
    COSMOS_KEY=secretref:cosmos-key \
    BLOB_CONNECTION_STRING=secretref:blob-conn

# Deploy frontend
az containerapp create \
  --name drugtarget-frontend \
  --resource-group "$RESOURCE_GROUP" \
  --environment "$ENV_NAME" \
  --image "$ACR_NAME.azurecr.io/frontend:latest" \
  --registry-server "$ACR_NAME.azurecr.io" \
  --target-port 80 \
  --ingress external \
  --min-replicas 1 \
  --max-replicas 3

FRONTEND_URL=$(az containerapp show \
  --name drugtarget-frontend \
  --resource-group "$RESOURCE_GROUP" \
  --query properties.configuration.ingress.fqdn -o tsv)

echo ""
echo "=== Deployment Complete ==="
echo "Frontend: https://$FRONTEND_URL"
```

- [ ] **Step 4: Commit**

```bash
git add backend/Dockerfile frontend/Dockerfile frontend/nginx.conf infra/deploy.sh
git commit -m "feat: add Docker and Azure Container Apps deployment"
```

---

## Task 16: End-to-End Test

- [ ] **Step 1: Run all unit tests**

```bash
cd backend && python -m pytest tests/ -v
```

Expected: All tests PASS.

- [ ] **Step 2: Start backend locally and test API**

```bash
cd backend && uvicorn app.main:app --port 8000
```

```bash
curl -X POST http://localhost:8000/api/assess \
  -H "Content-Type: application/json" \
  -d '{"target": "GLP-1R", "indication": "obesity"}'
```

Expected: JSON response with `report.recommendation` being one of Go/No-Go/Need More Data, with citations.

- [ ] **Step 3: Start frontend and verify UI**

```bash
cd frontend && npm run dev
```

Visit http://localhost:5173, enter "GLP-1R" as target and "obesity" as indication. Verify:
- Loading state shows
- Result card appears with Go/No-Go/Need More Data
- Literature, Clinical Trials, Competition tabs show data
- Citations list shows clickable links

- [ ] **Step 4: Deploy to Azure and verify**

```bash
chmod +x infra/deploy.sh
./infra/deploy.sh
```

Visit the printed frontend URL and repeat the test.

- [ ] **Step 5: Final commit**

```bash
git add -A
git commit -m "feat: complete drug target decision support agent system"
```
