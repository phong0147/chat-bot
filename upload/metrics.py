"""Transparent local estimates, never a claim about Gemini's internal chunks."""

ESTIMATE_METHOD = "raw_markdown_whitespace_windows"
ESTIMATE_NOTE = (
    "Local estimate from raw Markdown split on whitespace, using fixed-size "
    "overlapping windows. Gemini may parse or split content differently. "
    "This is not the actual number of embedded chunks returned by Gemini."
)


def estimate_chunks(text, max_tokens=512, overlap_tokens=64):
    if max_tokens < 1 or overlap_tokens < 0 or overlap_tokens >= max_tokens:
        raise ValueError("Require max_tokens > 0 and 0 <= overlap_tokens < max_tokens")
    words = len(text.split())
    if words == 0:
        return 0
    remaining = max(0, words - max_tokens)
    step = max_tokens - overlap_tokens
    return 1 + (remaining + step - 1) // step
