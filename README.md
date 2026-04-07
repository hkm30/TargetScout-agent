# TargetScout - Drug Target Intelligence Agent

An AI-powered multi-agent system that helps pharmaceutical researchers make informed **Go / No-Go / Need More Data** decisions for drug targets in early-stage development. The system rapidly aggregates and synthesizes evidence from scientific literature, clinical trials, and competitive intelligence to provide structured recommendations.

## Architecture

```
User --> Frontend (React + Vite)
           |
      Backend (FastAPI)
           |
    Orchestrator Agent (Azure AI Foundry / GPT-5.4)
       /        |         \
Literature   Clinical    Competition
  Agent     Trials Agent   Agent
       \        |         /
    Decision Summary Agent
           |
    Knowledge Base (Cosmos DB + AI Search + Blob Storage)
```

### Agent Pipeline

| Agent | Role | Data Sources |
|-------|------|-------------|
| **Orchestrator** | Parses input, coordinates sub-agents, manages human-in-the-loop confirmation | Knowledge Base |
| **Literature Research** | Searches and rates scientific evidence | PubMed, Bing Search |
| **Clinical Trials** | Collects trial phase/status signals | ClinicalTrials.gov |
| **Competition Intelligence** | Assesses competitor landscape and differentiation opportunities | PubMed, Bing, ClinicalTrials.gov |
| **Decision Summary** | Synthesizes all evidence into a structured Go/No-Go recommendation | (LLM reasoning only) |

## Tech Stack

- **Backend**: Python 3.12, FastAPI, Azure AI Foundry Agent Service
- **Frontend**: React 19, TypeScript, Vite 6
- **LLM**: GPT-5.4 (via Azure AI Foundry)
- **Storage**: Azure Cosmos DB, Azure Blob Storage, Azure AI Search
- **Infra**: Azure Container Apps (VNet integrated), Azure Container Registry
- **MCP Server**: Custom Google Scholar search service

## Features

- Multi-agent parallel evidence gathering (literature, clinical trials, competition)
- Human-in-the-loop confirmation before full analysis
- Real-time streaming progress via Server-Sent Events (SSE)
- Persistent knowledge base with vector search for historical context
- Report export in Markdown, Word (.docx), and PDF
- Private network deployment (Cosmos DB via Private Endpoint)

## Getting Started

### Prerequisites

- Python 3.12+
- Node.js 22+
- Azure subscription with the following services:
  - Azure AI Foundry (Agent Service + GPT-5.4 deployment)
  - Azure AI Search
  - Azure Cosmos DB for NoSQL
  - Azure Blob Storage

### Backend

```bash
cd backend
cp .env.example .env
# Edit .env with your Azure credentials
pip install -e .
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### Frontend

```bash
cd frontend
npm ci
npm run dev
```

Access the app at `http://localhost:5173` and API docs at `http://localhost:8000/docs`.

### Environment Variables

See [backend/.env.example](backend/.env.example) for all required configuration:

| Variable | Description |
|----------|-------------|
| `AZURE_AI_PROJECT_ENDPOINT` | Azure AI Foundry project endpoint |
| `MODEL_DEPLOYMENT` | LLM deployment name (default: `gpt-54`) |
| `EMBEDDING_DEPLOYMENT` | Embedding model (default: `text-embedding-3-large`) |
| `SEARCH_ENDPOINT` | Azure AI Search endpoint |
| `SEARCH_API_KEY` | Azure AI Search API key |
| `COSMOS_ENDPOINT` | Azure Cosmos DB endpoint |
| `COSMOS_DATABASE` | Cosmos DB database name |
| `STORAGE_ACCOUNT_NAME` | Azure Blob Storage account |

## Deployment

The project deploys to Azure Container Apps via the included scripts:

```bash
# Configure deployment settings
vi infra/deploy-config.sh

# Deploy backend + frontend
bash infra/deploy.sh
```

Both backend and frontend include Dockerfiles for containerized deployment. The frontend uses a multi-stage build (Node build + Nginx runtime).

## Project Structure

```
.
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI entry, SSE streaming
│   │   ├── config.py            # Environment configuration
│   │   ├── agents/              # Orchestrator + agent definitions
│   │   ├── tools/               # PubMed, ClinicalTrials, search tools
│   │   ├── knowledge/           # Cosmos DB, AI Search, Blob clients
│   │   └── export/              # Report generation (MD/Word/PDF)
│   ├── tests/                   # Unit tests
│   ├── pyproject.toml
│   └── Dockerfile
├── frontend/
│   ├── src/
│   │   ├── App.tsx              # Main app with sidebar layout
│   │   ├── components/          # React components
│   │   ├── api.ts               # Backend API client
│   │   └── types.ts             # TypeScript type definitions
│   ├── package.json
│   └── Dockerfile
├── mcp-google-scholar/          # Custom MCP server for Google Scholar
├── infra/                       # Azure deployment scripts
└── architecture.md              # Detailed architecture documentation
```

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/assess/parse` | Parse target + indication, return confirmation |
| POST | `/api/assess/confirm` | Run full analysis pipeline (SSE stream) |
| POST | `/api/assess` | Direct one-step analysis |
| GET | `/api/knowledge/search` | Search knowledge base |
| GET | `/api/reports` | List historical reports |
| GET | `/api/reports/{id}` | Get single report |
| DELETE | `/api/reports/{id}` | Delete report |
| POST | `/api/export/markdown` | Export as Markdown |
| POST | `/api/export/word` | Export as Word document |
| POST | `/api/export/pdf` | Export as PDF |

## License

This project is for research and educational purposes.
