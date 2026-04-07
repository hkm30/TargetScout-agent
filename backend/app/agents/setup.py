from azure.ai.projects import AIProjectClient
from azure.ai.projects.models import PromptAgentDefinition, WebSearchTool
from azure.identity import DefaultAzureCredential
from openai import OpenAI

from app.config import settings
from app.agents.definitions import (
    LITERATURE_AGENT_TOOLS,
    CLINICAL_TRIALS_AGENT_TOOLS,
    COMPETITION_AGENT_TOOLS,
    ORCHESTRATOR_TOOLS,
)

_project_client: AIProjectClient | None = None
_openai_client: OpenAI | None = None


def get_project_client() -> AIProjectClient:
    """Get or create the AIProjectClient singleton."""
    global _project_client
    if _project_client is None:
        _project_client = AIProjectClient(
            endpoint=settings.PROJECT_ENDPOINT,
            credential=DefaultAzureCredential(),
        )
    return _project_client


def get_openai_client() -> OpenAI:
    """Get an OpenAI client from the Foundry project (used for responses and embeddings)."""
    global _openai_client
    if _openai_client is None:
        project = get_project_client()
        _openai_client = project.get_openai_client()
    return _openai_client


LITERATURE_INSTRUCTIONS = """You are a scientific literature research agent for drug target assessment.
Given a target name and optional indication, you must:
1. Use search_pubmed to find relevant scientific papers (up to 10).
2. Use fetch_pubmed_details to get abstracts for the top results.
3. Use web search to find supplementary academic evidence (reviews, research leads not covered by PubMed).
4. Synthesize the literature evidence you have gathered.
5. Summarize the evidence: support strength (strong/moderate/weak), positive and negative findings.
6. Return a structured JSON with: papers list, web_results, summary, support_strength, positive_evidence, negative_evidence, confidence.

If private documents are provided in the prompt, integrate their content into your analysis. When citing information from private documents, add the source tag [文档: filename] at the end of the relevant sentence or paragraph.

IMPORTANT: All summary, analysis, and text fields in your JSON output MUST be written in Chinese (中文). Only keep paper titles, author names, and technical terms in their original language."""

CLINICAL_TRIALS_INSTRUCTIONS = """You are a clinical trials intelligence agent for drug target assessment.
Given a target name and optional indication, you must:
1. Use search_clinical_trials to find relevant trials on ClinicalTrials.gov (up to 10).
2. Use fetch_trial_details for the most relevant trials to get enrollment and detail info.
3. Use web search to find trial result announcements, FDA updates, company press releases, and failure analysis.
4. Analyze phase distribution, status distribution, positive and negative signals.
5. Return a structured JSON with: trials list, web_results, phase_distribution, status_distribution, positive_signals, negative_signals, summary, confidence.

If private documents are provided in the prompt, integrate their content into your analysis. When citing information from private documents, add the source tag [文档: filename] at the end of the relevant sentence or paragraph.

IMPORTANT: All summary, analysis, and text fields in your JSON output MUST be written in Chinese (中文). Only keep trial titles, sponsor names, and technical terms in their original language."""

COMPETITION_INSTRUCTIONS = """You are a competitive intelligence agent for drug target assessment.
Given a target name and optional indication, you must:
1. Use web search to find company pipeline dynamics, press releases, and competitive landscape.
2. Use search_pubmed to find relevant research papers, then use fetch_pubmed_details to get full details (title, abstract, link) for the top results.
3. Use search_clinical_trials to map competitor trial activity, then use fetch_trial_details to get detailed info (enrollment, sponsor, link) for key trials.
4. Assess competition level (high/medium/low), identify major players, crowding signals.
5. Return a structured JSON with: competition_level, major_players, research_hotspots, crowding_signals, differentiation_opportunities, sources, summary, confidence.

The "sources" field MUST be an array of objects, each with:
- "title": source title or description
- "url": full URL link to the source
- "type": one of "pubmed", "clinical_trial", or "web"
Include ALL sources you referenced: PubMed papers (with pubmed links), clinical trials (with clinicaltrials.gov links), and web search results (with their URLs).

If private documents are provided in the prompt, integrate their content into your analysis. When citing information from private documents, add the source tag [文档: filename] at the end of the relevant sentence or paragraph.

IMPORTANT: All summary, analysis, and text fields in your JSON output MUST be written in Chinese (中文). Only keep company names, drug names, and technical terms in their original language."""

DECISION_INSTRUCTIONS = """You are a decision summary agent for drug target Go/No-Go assessment.
You receive evidence from three research agents (literature, clinical trials, competition) and optional historical data.
You must:
1. Evaluate all evidence objectively.
2. Apply these rules:
   - Go: strong literature support + positive clinical signals + manageable competition
   - No-Go: weak evidence + clinical failures + saturated competition
   - Need More Data: insufficient or mixed evidence
3. Return a structured JSON with: target, indication, literature_summary, clinical_trials_summary, competition_summary, major_risks, major_opportunities, recommendation (Go/No-Go/Need More Data), reasoning, uncertainty, citations.

If private documents were provided to research agents, include them in your citations list with type "private_document" and the file name as the title.

IMPORTANT: All summary, analysis, reasoning, uncertainty, risks, and opportunities text MUST be written in Chinese (中文). The recommendation field must still be one of: "Go", "No-Go", or "Need More Data" (in English). Only keep drug names, gene names, and technical terms in their original language."""

ORCHESTRATOR_INSTRUCTIONS = """You are the orchestrator agent for drug target assessment.
Your workflow:
1. Parse the user's query to extract target name and indication.
2. Use search_knowledge_base to check for historical assessments.
3. Present your understanding back to the user for confirmation.
4. After confirmation, you will coordinate sub-agents (handled by the backend).
5. After receiving sub-agent results and the decision summary, use write_to_knowledge_base to save.
6. Present the final report to the user."""


def create_all_agents() -> dict[str, str]:
    """Create all 5 agents via Foundry Agent Service and return their names."""
    project = get_project_client()
    agents = {}

    literature = project.agents.create_version(
        agent_name="literature-research-agent",
        definition=PromptAgentDefinition(
            model=settings.MODEL_DEPLOYMENT,
            instructions=LITERATURE_INSTRUCTIONS,
            tools=LITERATURE_AGENT_TOOLS + [WebSearchTool()],
        ),
    )
    agents["literature"] = literature.name

    clinical = project.agents.create_version(
        agent_name="clinical-trials-agent",
        definition=PromptAgentDefinition(
            model=settings.MODEL_DEPLOYMENT,
            instructions=CLINICAL_TRIALS_INSTRUCTIONS,
            tools=CLINICAL_TRIALS_AGENT_TOOLS + [WebSearchTool()],
        ),
    )
    agents["clinical_trials"] = clinical.name

    competition = project.agents.create_version(
        agent_name="competition-intel-agent",
        definition=PromptAgentDefinition(
            model=settings.MODEL_DEPLOYMENT,
            instructions=COMPETITION_INSTRUCTIONS,
            tools=COMPETITION_AGENT_TOOLS + [WebSearchTool()],
        ),
    )
    agents["competition"] = competition.name

    decision = project.agents.create_version(
        agent_name="decision-summary-agent",
        definition=PromptAgentDefinition(
            model=settings.MODEL_DEPLOYMENT,
            instructions=DECISION_INSTRUCTIONS,
            tools=[],
        ),
    )
    agents["decision"] = decision.name

    orchestrator = project.agents.create_version(
        agent_name="orchestrator-agent",
        definition=PromptAgentDefinition(
            model=settings.MODEL_DEPLOYMENT,
            instructions=ORCHESTRATOR_INSTRUCTIONS,
            tools=ORCHESTRATOR_TOOLS,
        ),
    )
    agents["orchestrator"] = orchestrator.name

    return agents
