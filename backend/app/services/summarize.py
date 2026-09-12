"""Deterministic fallback chapter summaries (no LLM calls).

Used for seed books where a summary wasn't hand-written: takes the first
1-2 sentences of the chapter as a naive extractive summary, capped in length.
"""

import re

SENTENCE_RE = re.compile(r"(?<=[.!?])\s+")
MAX_CHARS = 240


def naive_summary(chapter_text: str) -> str:
    body = chapter_text.strip()
    body = re.sub(r"\s+", " ", body)
    sentences = SENTENCE_RE.split(body)
    summary = ""
    for sentence in sentences:
        candidate = (summary + " " + sentence).strip() if summary else sentence
        if len(candidate) > MAX_CHARS:
            break
        summary = candidate
    return summary or body[:MAX_CHARS]
