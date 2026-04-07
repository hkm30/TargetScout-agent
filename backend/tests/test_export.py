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
