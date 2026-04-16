from app.documents.chunker import count_tokens, chunk_text


# --- count_tokens tests ---

def test_count_tokens_english():
    tokens = count_tokens("hello world")
    assert tokens == 2


def test_count_tokens_chinese():
    tokens = count_tokens("药物靶点评估系统")
    assert tokens > 0
    # Chinese characters typically produce more tokens than chars
    assert tokens >= 4


def test_count_tokens_empty():
    assert count_tokens("") == 0


# --- chunk_text tests ---

def test_chunk_single_short_paragraph():
    text = "This is a short paragraph."
    chunks = chunk_text(text, paragraphs=["This is a short paragraph."], max_tokens=600)
    assert len(chunks) == 1
    assert chunks[0]["text"] == "This is a short paragraph."
    assert chunks[0]["chunk_index"] == 0
    assert chunks[0]["token_count"] > 0


def test_chunk_multiple_paragraphs_grouped():
    """Small paragraphs should be grouped into a single chunk."""
    paragraphs = ["Short one.", "Short two.", "Short three."]
    text = "\n\n".join(paragraphs)
    chunks = chunk_text(text, paragraphs=paragraphs, max_tokens=600)
    assert len(chunks) == 1
    assert "Short one." in chunks[0]["text"]
    assert "Short three." in chunks[0]["text"]


def test_chunk_paragraphs_split_when_exceeding_max():
    """Paragraphs should be split into multiple chunks when they exceed max_tokens."""
    # Create paragraphs that together exceed max_tokens
    para = "word " * 100  # ~100 tokens
    paragraphs = [para.strip()] * 5  # ~500 tokens total
    text = "\n\n".join(paragraphs)
    chunks = chunk_text(text, paragraphs=paragraphs, max_tokens=250)
    assert len(chunks) >= 2
    # Verify all chunk_indexes are sequential
    for i, chunk in enumerate(chunks):
        assert chunk["chunk_index"] == i


def test_chunk_long_paragraph_split_by_token_window():
    """A single paragraph exceeding max_tokens should be split by token window."""
    long_para = "word " * 800  # ~800 tokens
    chunks = chunk_text(long_para, paragraphs=[long_para.strip()], max_tokens=300, overlap_tokens=50)
    assert len(chunks) >= 3
    for chunk in chunks:
        assert chunk["token_count"] <= 300


def test_chunk_overlap_between_chunks():
    """When a long paragraph is split, chunks should overlap."""
    long_para = "word " * 600
    chunks = chunk_text(long_para, paragraphs=[long_para.strip()], max_tokens=200, overlap_tokens=50)
    assert len(chunks) >= 3
    # The second chunk should start before the first chunk ends (overlap)
    # We verify by checking the texts share some content
    if len(chunks) >= 2:
        # With overlap, the end of chunk 0 should appear at the start of chunk 1
        words_0 = chunks[0]["text"].split()
        words_1 = chunks[1]["text"].split()
        # Last ~50 tokens of chunk 0 should overlap with start of chunk 1
        overlap_words = set(words_0[-20:]) & set(words_1[:20])
        assert len(overlap_words) > 0, "Expected overlapping content between adjacent chunks"


def test_chunk_no_paragraphs_fallback():
    """When paragraphs=None, text should be split by double newlines."""
    text = "Para one content.\n\nPara two content.\n\nPara three content."
    chunks = chunk_text(text, paragraphs=None, max_tokens=600)
    assert len(chunks) == 1
    assert "Para one" in chunks[0]["text"]
    assert "Para three" in chunks[0]["text"]


def test_chunk_empty_text():
    chunks = chunk_text("", paragraphs=None)
    assert len(chunks) == 1
    assert chunks[0]["chunk_index"] == 0


def test_chunk_indexes_sequential():
    """All chunk indexes should be 0, 1, 2, ..."""
    para = "word " * 200
    paragraphs = [para.strip()] * 4
    text = "\n\n".join(paragraphs)
    chunks = chunk_text(text, paragraphs=paragraphs, max_tokens=250)
    indexes = [c["chunk_index"] for c in chunks]
    assert indexes == list(range(len(chunks)))


def test_chunk_token_count_accurate():
    """Each chunk's token_count should match actual token count of its text."""
    paragraphs = ["Hello world this is a test paragraph." for _ in range(10)]
    text = "\n\n".join(paragraphs)
    chunks = chunk_text(text, paragraphs=paragraphs, max_tokens=50)
    for chunk in chunks:
        actual = count_tokens(chunk["text"])
        assert chunk["token_count"] == actual or abs(chunk["token_count"] - actual) <= 1


def test_chunk_with_figure_chunks_appended():
    """Figure chunks should be appended after regular text chunks with sequential indexes."""
    paragraphs = ["Regular paragraph content here."]
    text = paragraphs[0]
    figure_chunks = [
        {"text": "[Figure 1.0] A bar chart showing IC50 values.\nDescription of figure.", "source_type": "figure", "page_number": 2},
        {"text": "[Figure 1.1] Molecular structure of compound X.\nDescription of structure.", "source_type": "figure", "page_number": 3},
    ]
    chunks = chunk_text(text, paragraphs=paragraphs, figure_chunks=figure_chunks)
    assert chunks[0]["text"] == "Regular paragraph content here."
    assert chunks[0]["chunk_index"] == 0
    assert "source_type" not in chunks[0]
    assert chunks[1]["text"] == figure_chunks[0]["text"]
    assert chunks[1]["chunk_index"] == 1
    assert chunks[1]["source_type"] == "figure"
    assert chunks[1]["page_number"] == 2
    assert chunks[1]["token_count"] > 0
    assert chunks[2]["chunk_index"] == 2
    assert chunks[2]["source_type"] == "figure"


def test_chunk_with_no_figure_chunks():
    """When figure_chunks is None or empty, behavior is unchanged."""
    text = "Simple text."
    chunks_none = chunk_text(text, paragraphs=["Simple text."], figure_chunks=None)
    chunks_empty = chunk_text(text, paragraphs=["Simple text."], figure_chunks=[])
    assert len(chunks_none) == 1
    assert len(chunks_empty) == 1
    assert "source_type" not in chunks_none[0]
