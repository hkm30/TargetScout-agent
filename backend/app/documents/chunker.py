import tiktoken

_encoder = tiktoken.get_encoding("cl100k_base")


def count_tokens(text: str) -> int:
    return len(_encoder.encode(text))


def chunk_text(
    text: str,
    paragraphs: list[str] | None = None,
    max_tokens: int = 600,
    overlap_tokens: int = 100,
    figure_chunks: list[dict] | None = None,
) -> list[dict]:
    """Split text into overlapping chunks.

    Strategy:
    1. If paragraphs are provided, group them into chunks up to max_tokens.
    2. If a single paragraph exceeds max_tokens, split it by token window.
    3. If figure_chunks are provided, append them after text chunks with
       sequential chunk_index values and computed token_count.

    Returns list of {text, chunk_index, token_count} for text chunks, plus
    {text, chunk_index, token_count, source_type, page_number} for figure chunks.
    """
    if not paragraphs:
        paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    if not paragraphs:
        paragraphs = [text]

    chunks: list[dict] = []
    current_parts: list[str] = []
    current_tokens = 0
    chunk_index = 0

    for para in paragraphs:
        para_tokens = count_tokens(para)

        # If single paragraph exceeds max, split it by token window
        if para_tokens > max_tokens:
            # Flush current buffer first
            if current_parts:
                chunk_text_str = "\n\n".join(current_parts)
                chunks.append({"text": chunk_text_str, "chunk_index": chunk_index, "token_count": current_tokens})
                chunk_index += 1
                current_parts = []
                current_tokens = 0

            # Split long paragraph by token window
            tokens = _encoder.encode(para)
            start = 0
            while start < len(tokens):
                end = min(start + max_tokens, len(tokens))
                chunk_tokens = tokens[start:end]
                chunk_str = _encoder.decode(chunk_tokens)
                chunks.append({"text": chunk_str, "chunk_index": chunk_index, "token_count": len(chunk_tokens)})
                chunk_index += 1
                start = end - overlap_tokens if end < len(tokens) else end
            continue

        # Would this paragraph overflow the current chunk?
        if current_tokens + para_tokens > max_tokens and current_parts:
            chunk_text_str = "\n\n".join(current_parts)
            chunks.append({"text": chunk_text_str, "chunk_index": chunk_index, "token_count": current_tokens})
            chunk_index += 1

            # Overlap: keep last part if it fits
            last_part = current_parts[-1]
            last_tokens = count_tokens(last_part)
            if last_tokens <= overlap_tokens:
                current_parts = [last_part]
                current_tokens = last_tokens
            else:
                current_parts = []
                current_tokens = 0

        current_parts.append(para)
        current_tokens += para_tokens

    # Flush remaining
    if current_parts:
        chunk_text_str = "\n\n".join(current_parts)
        chunks.append({"text": chunk_text_str, "chunk_index": chunk_index, "token_count": current_tokens})
        chunk_index += 1

    # Append figure chunks with sequential indexes continuing from text chunks
    if figure_chunks:
        for fig in figure_chunks:
            chunks.append({
                "text": fig["text"],
                "chunk_index": chunk_index,
                "token_count": count_tokens(fig["text"]),
                "source_type": fig["source_type"],
                "page_number": fig["page_number"],
            })
            chunk_index += 1

    return chunks
