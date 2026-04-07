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
