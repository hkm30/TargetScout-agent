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
