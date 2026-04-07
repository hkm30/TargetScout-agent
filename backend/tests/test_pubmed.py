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
