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
                proto = study.get("protocolSection", {})
                design = proto.get("designModule", {})
                enrollment = design.get("enrollmentInfo", {})
                trial["enrollment"] = enrollment.get("count", 0)
                trial["official_title"] = proto.get("identificationModule", {}).get(
                    "officialTitle", ""
                )
                trials.append(trial)

    return json.dumps({"trials": trials})
