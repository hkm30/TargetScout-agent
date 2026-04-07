import asyncio
import json
import logging
import random
import uuid
from typing import AsyncGenerator

from openai import RateLimitError
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

from app.agents.setup import get_openai_client
from app.tools.pubmed import search_pubmed, fetch_pubmed_details
from app.tools.clinical_trials import search_clinical_trials, fetch_trial_details
from app.tools.knowledge_base import search_knowledge_base, write_to_knowledge_base
from app.tools.translate import ensure_english

# Map tool names to their async implementations
TOOL_FUNCTIONS = {
    "search_pubmed": search_pubmed,
    "fetch_pubmed_details": fetch_pubmed_details,
    "search_clinical_trials": search_clinical_trials,
    "fetch_trial_details": fetch_trial_details,
    "search_knowledge_base": search_knowledge_base,
    "write_to_knowledge_base": write_to_knowledge_base,
}


# --- Pydantic model for decision agent output validation ---

class DecisionOutput(BaseModel):
    target: str = ""
    indication: str = ""
    literature_summary: str = ""
    clinical_trials_summary: str = ""
    competition_summary: str = ""
    major_risks: list[str] = Field(default_factory=list)
    major_opportunities: list[str] = Field(default_factory=list)
    recommendation: str = ""  # "Go" | "No-Go" | "Need More Data"
    reasoning: str = ""
    uncertainty: str = ""
    citations: list = Field(default_factory=list)


# --- Core functions ---

async def _execute_function_call(name: str, arguments: str) -> str:
    """Execute a function tool call and return the result string."""
    func = TOOL_FUNCTIONS.get(name)
    if func is None:
        return json.dumps({"error": f"Unknown tool: {name}"})

    args = json.loads(arguments)
    return await func(**args)


_MAX_RETRIES = 5
_RETRY_BASE_DELAY = 2.0  # seconds


async def _call_with_retry(func, *args, agent_name: str = "", **kwargs):
    """Call an OpenAI API function with exponential backoff on 429 errors."""
    for attempt in range(_MAX_RETRIES):
        try:
            return await asyncio.to_thread(func, *args, **kwargs)
        except RateLimitError as e:
            if attempt == _MAX_RETRIES - 1:
                raise
            # Exponential backoff with jitter
            delay = _RETRY_BASE_DELAY * (2 ** attempt) + random.uniform(0, 1)
            logger.warning(
                "Agent %s hit rate limit (attempt %d/%d), retrying in %.1fs: %s",
                agent_name, attempt + 1, _MAX_RETRIES, delay, e,
            )
            await asyncio.sleep(delay)


async def _run_agent_with_responses(
    agent_name: str,
    prompt: str,
    max_iterations: int = 20,
    timeout_seconds: float = 300.0,
) -> str:
    """Run an agent using the Foundry Responses API, handling function call loops.

    Args:
        agent_name: The Foundry agent name.
        prompt: The input prompt.
        max_iterations: Max number of tool-call round-trips (prevents infinite loops).
        timeout_seconds: Overall timeout in seconds (default 5 minutes).
    """
    openai = get_openai_client()

    async with asyncio.timeout(timeout_seconds):
        # Initial response request (with retry on 429)
        response = await _call_with_retry(
            openai.responses.create,
            agent_name=agent_name,
            input=prompt,
            extra_body={"agent_reference": {"name": agent_name, "type": "agent_reference"}},
        )

        # Function call loop: agent may call tools multiple times
        iteration = 0
        while True:
            function_calls = [item for item in response.output if item.type == "function_call"]
            if not function_calls:
                break

            iteration += 1
            if iteration > max_iterations:
                logger.warning("Agent %s exceeded max iterations (%d), stopping", agent_name, max_iterations)
                break

            # Execute all function calls
            input_list = []
            for fc in function_calls:
                result = await _execute_function_call(fc.name, fc.arguments)
                input_list.append({
                    "type": "function_call_output",
                    "call_id": fc.call_id,
                    "output": result,
                })

            # Submit function outputs and get next response (with retry on 429)
            response = await _call_with_retry(
                openai.responses.create,
                agent_name=agent_name,
                input=input_list,
                previous_response_id=response.id,
                extra_body={"agent_reference": {"name": agent_name, "type": "agent_reference"}},
            )

    return response.output_text


async def run_sub_agent(agent_name: str, prompt: str) -> str:
    """Run a sub-agent with the given prompt via Responses API."""
    return await _run_agent_with_responses(agent_name, prompt)


SUB_TASK_DEFINITIONS = [
    {
        "agent": "Literature Research Agent",
        "description": "Search PubMed for scientific papers and use web search for supplementary academic evidence.",
        "tools": ["search_pubmed", "fetch_pubmed_details", "web_search"],
    },
    {
        "agent": "Clinical Trials Intelligence Agent",
        "description": "Search ClinicalTrials.gov for relevant trials and use web search for result announcements and FDA updates.",
        "tools": ["search_clinical_trials", "fetch_trial_details", "web_search"],
    },
    {
        "agent": "Competition & Intelligence Agent",
        "description": "Analyze competitive landscape using web search, PubMed research hotspots, and clinical trial activity.",
        "tools": ["web_search", "search_pubmed", "search_clinical_trials"],
    },
    {
        "agent": "Decision Summary Agent",
        "description": "Synthesize all evidence and produce a Go / No-Go / Need More Data recommendation with reasoning.",
        "tools": [],
    },
]


async def parse_user_input(
    target: str,
    indication: str = "",
    synonyms: str = "",
    focus: str = "",
    time_range: str = "",
) -> dict:
    """Parse user input, search knowledge base, and return confirmation payload."""
    query = f"{target} {indication}".strip()
    kb_result = await search_knowledge_base(query=query, target=target, indication=indication)
    kb_data = json.loads(kb_result)

    return {
        "parsed": {
            "target": target,
            "indication": indication,
            "synonyms": synonyms,
            "focus": focus,
            "time_range": time_range,
        },
        "sub_tasks": SUB_TASK_DEFINITIONS,
        "knowledge_base_context": kb_data,
    }


def _build_research_prompt(
    target: str,
    indication: str = "",
    synonyms: str = "",
    focus: str = "",
    time_range: str = "",
) -> str:
    """Build the research prompt shared by all research agents."""
    research_prompt = f"Assess the drug target '{target}'"
    if indication:
        research_prompt += f" for the indication '{indication}'"
    if synonyms:
        research_prompt += f". Also known as: {synonyms}"
    if focus:
        research_prompt += f". Focus area: {focus}"
    if time_range:
        research_prompt += f". Limit search to the past {int(time_range) // 365} years (date_range={time_range})"
    research_prompt += ". Search thoroughly and provide structured analysis."
    return research_prompt


def _build_decision_prompt(
    target: str,
    indication: str,
    lit_result: str,
    clin_result: str,
    comp_result: str,
    kb_data: dict,
) -> str:
    """Build the decision agent prompt."""
    return f"""Based on the following evidence, provide a Go/No-Go/Need More Data recommendation for target '{target}' (indication: {indication or 'not specified'}).

## Literature Evidence
{lit_result}

## Clinical Trials Evidence
{clin_result}

## Competition Intelligence
{comp_result}

## Historical Context
{json.dumps(kb_data.get('historical_reports', []), indent=2)}

Provide your structured assessment. Return ONLY valid JSON with these keys: target, indication, literature_summary, clinical_trials_summary, competition_summary, major_risks (array of strings), major_opportunities (array of strings), recommendation ("Go" or "No-Go" or "Need More Data"), reasoning, uncertainty, citations.

IMPORTANT: All text content (summaries, risks, opportunities, reasoning, uncertainty) MUST be written in Chinese (中文). The recommendation field must remain in English ("Go", "No-Go", or "Need More Data"). Keep drug names, gene names, and technical terms in their original language."""


async def _background_kb_write(report: dict, raw_outputs: dict, report_id: str):
    """Write to knowledge base in the background — failures are logged, not raised."""
    try:
        kb_result_str = await write_to_knowledge_base(
            report=report, raw_outputs=raw_outputs, report_id=report_id
        )
        if kb_result_str:
            kb_ids = json.loads(kb_result_str)
            logger.info("KB write successful: %s", kb_ids.get("report_id", ""))
    except Exception as e:
        logger.error("Background KB write failed: %s", e)


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
        logger.warning("Failed to parse agent output as JSON (length=%d)", len(text))
        return {"raw_text": text}


def _parse_and_validate(text: str) -> dict:
    """Parse JSON from agent output and validate against DecisionOutput schema."""
    parsed = _safe_parse(text)
    if "raw_text" not in parsed:
        try:
            validated = DecisionOutput.model_validate(parsed)
            return validated.model_dump()
        except Exception as e:
            logger.warning("Pydantic validation failed (using raw parsed): %s", e)
    return parsed


# --- Synchronous pipeline (backward compatible) ---

async def run_full_pipeline(
    agent_names: dict[str, str],
    target: str,
    indication: str = "",
    synonyms: str = "",
    focus: str = "",
    time_range: str = "",
) -> dict:
    """Run the complete assessment pipeline (non-streaming version)."""
    query = f"{target} {indication}".strip()

    # Step 1: Check knowledge base
    kb_result = await search_knowledge_base(query=query, target=target, indication=indication)
    kb_data = json.loads(kb_result)

    # Step 2: Translate inputs to English for external API searches
    en_target = await ensure_english(target)
    en_indication = await ensure_english(indication) if indication else indication
    en_synonyms = await ensure_english(synonyms) if synonyms else synonyms
    en_focus = await ensure_english(focus) if focus else focus

    # Run 3 research agents in parallel (staggered to avoid 429)
    research_prompt = _build_research_prompt(en_target, en_indication, en_synonyms, en_focus, time_range)

    async def _staggered_agent(key: str, delay: float):
        if delay > 0:
            await asyncio.sleep(delay)
        return await run_sub_agent(agent_names[key], research_prompt)

    results = await asyncio.gather(
        _staggered_agent("literature", 0),
        _staggered_agent("clinical_trials", 2),
        _staggered_agent("competition", 4),
        return_exceptions=True,
    )

    partial_failures: list[str] = []
    agent_keys = ["literature", "clinical_trials", "competition"]
    resolved: list[str] = []
    for name, res in zip(agent_keys, results):
        if isinstance(res, Exception):
            logger.error("Agent %s failed: %s", name, res)
            partial_failures.append(f"{name}: {res}")
            resolved.append(json.dumps({"error": str(res), "partial_failure": True}))
        else:
            resolved.append(res)
    lit_result, clin_result, comp_result = resolved

    # Step 3: Run decision summary agent
    decision_prompt = _build_decision_prompt(target, indication, lit_result, clin_result, comp_result, kb_data)
    decision_result = await run_sub_agent(agent_names["decision"], decision_prompt)

    # Parse and validate
    report = _parse_and_validate(decision_result)

    # Retry once if JSON parsing failed
    if "raw_text" in report:
        logger.info("Decision agent returned non-JSON, retrying once...")
        retry_prompt = decision_prompt + "\n\nIMPORTANT: You MUST return valid JSON only, no markdown or extra text."
        decision_result = await run_sub_agent(agent_names["decision"], retry_prompt)
        report = _parse_and_validate(decision_result)

    raw_outputs = {
        "literature": _safe_parse(lit_result),
        "clinical_trials": _safe_parse(clin_result),
        "competition": _safe_parse(comp_result),
    }
    report["target"] = target
    report["indication"] = indication

    # Step 4: Write to knowledge base (background, non-blocking)
    report_id = str(uuid.uuid4())
    report["report_id"] = report_id
    asyncio.create_task(_background_kb_write(report.copy(), raw_outputs, report_id))

    return {
        "report": report,
        "raw_outputs": raw_outputs,
        "knowledge_base_context": kb_data,
        "partial_failures": partial_failures,
    }


# --- SSE streaming pipeline ---

async def run_full_pipeline_stream(
    agent_names: dict[str, str],
    target: str,
    indication: str = "",
    synonyms: str = "",
    focus: str = "",
    time_range: str = "",
) -> AsyncGenerator[dict, None]:
    """Run the pipeline, yielding SSE event dicts as progress occurs."""
    query = f"{target} {indication}".strip()

    # Step 1: Knowledge base search
    yield {"event": "status", "data": {"stage": "knowledge_base", "status": "started"}}
    kb_result = await search_knowledge_base(query=query, target=target, indication=indication)
    kb_data = json.loads(kb_result)
    yield {"event": "status", "data": {"stage": "knowledge_base", "status": "completed"}}

    # Step 2: Translate inputs to English for external API searches
    en_target = await ensure_english(target)
    en_indication = await ensure_english(indication) if indication else indication
    en_synonyms = await ensure_english(synonyms) if synonyms else synonyms
    en_focus = await ensure_english(focus) if focus else focus

    # Run 3 research agents in parallel, report completions individually
    research_prompt = _build_research_prompt(en_target, en_indication, en_synonyms, en_focus, time_range)

    agent_keys = ["literature", "clinical_trials", "competition"]
    stagger_delays = {"literature": 0, "clinical_trials": 2, "competition": 4}

    async def _staggered_agent(key: str):
        delay = stagger_delays[key]
        if delay > 0:
            await asyncio.sleep(delay)
        return await run_sub_agent(agent_names[key], research_prompt)

    tasks = {}
    for key in agent_keys:
        task = asyncio.create_task(_staggered_agent(key))
        tasks[task] = key

    for key in agent_keys:
        yield {"event": "status", "data": {"stage": key, "status": "started"}}

    partial_failures: list[str] = []
    resolved_map: dict[str, str] = {}
    pending = set(tasks.keys())

    while pending:
        done, pending = await asyncio.wait(pending, return_when=asyncio.FIRST_COMPLETED)
        for task in done:
            key = tasks[task]
            try:
                result = task.result()
                resolved_map[key] = result
                yield {"event": "status", "data": {"stage": key, "status": "completed"}}
                yield {"event": "partial_result", "data": {"stage": key, "result": _safe_parse(result)}}
            except Exception as e:
                logger.error("Agent %s failed: %s", key, e)
                partial_failures.append(f"{key}: {e}")
                resolved_map[key] = json.dumps({"error": str(e), "partial_failure": True})
                yield {"event": "status", "data": {"stage": key, "status": "failed", "error": str(e)}}

    lit_result = resolved_map["literature"]
    clin_result = resolved_map["clinical_trials"]
    comp_result = resolved_map["competition"]

    # Step 3: Decision agent
    yield {"event": "status", "data": {"stage": "decision", "status": "started"}}
    decision_prompt = _build_decision_prompt(target, indication, lit_result, clin_result, comp_result, kb_data)
    decision_result = await run_sub_agent(agent_names["decision"], decision_prompt)

    report = _parse_and_validate(decision_result)

    # Retry once if JSON parsing failed
    if "raw_text" in report:
        logger.info("Decision agent returned non-JSON, retrying once...")
        retry_prompt = decision_prompt + "\n\nIMPORTANT: You MUST return valid JSON only, no markdown or extra text."
        decision_result = await run_sub_agent(agent_names["decision"], retry_prompt)
        report = _parse_and_validate(decision_result)

    yield {"event": "status", "data": {"stage": "decision", "status": "completed"}}

    raw_outputs = {
        "literature": _safe_parse(lit_result),
        "clinical_trials": _safe_parse(clin_result),
        "competition": _safe_parse(comp_result),
    }
    report["target"] = target
    report["indication"] = indication

    # Step 4: KB write (background)
    report_id = str(uuid.uuid4())
    report["report_id"] = report_id
    yield {"event": "status", "data": {"stage": "saving", "status": "started"}}
    asyncio.create_task(_background_kb_write(report.copy(), raw_outputs, report_id))

    # Final result
    yield {
        "event": "result",
        "data": {
            "report": report,
            "raw_outputs": raw_outputs,
            "knowledge_base_context": kb_data,
            "partial_failures": partial_failures,
        },
    }
