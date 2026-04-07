from azure.ai.projects.models import FunctionTool, Tool


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
)

# Tool groups per agent
LITERATURE_AGENT_TOOLS: list[Tool] = [search_pubmed_tool, fetch_pubmed_details_tool]
CLINICAL_TRIALS_AGENT_TOOLS: list[Tool] = [search_clinical_trials_tool, fetch_trial_details_tool]
COMPETITION_AGENT_TOOLS: list[Tool] = [search_pubmed_tool, fetch_pubmed_details_tool, search_clinical_trials_tool, fetch_trial_details_tool]
ORCHESTRATOR_TOOLS: list[Tool] = [search_knowledge_base_tool, write_to_knowledge_base_tool]
