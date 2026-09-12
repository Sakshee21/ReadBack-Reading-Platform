"""Content pipeline: strip Gutenberg boilerplate, split into chapters, then
split each chapter into ~2-3 minute micro-sessions at paragraph boundaries.
"""

import re

START_MARKERS = [
    re.compile(r"\*\*\*\s*START OF (THE|THIS) PROJECT GUTENBERG EBOOK.*?\*\*\*", re.IGNORECASE | re.DOTALL),
]
END_MARKERS = [
    re.compile(r"\*\*\*\s*END OF (THE|THIS) PROJECT GUTENBERG EBOOK.*", re.IGNORECASE | re.DOTALL),
]

# Matches lines like "CHAPTER I", "Chapter 1.", "CHAPTER ONE", "CHAPTER I. THE RABBIT-HOLE"
# Deliberately uses horizontal whitespace ([ \t], never \s) around the optional
# title so the match can never bleed across a newline onto the next line -
# otherwise a bare "CHAPTER 1" heading with nothing else on its line ends up
# swallowing the next line (often another heading entirely) as its "title".
CHAPTER_HEADING_RE = re.compile(
    r"^[ \t]*(CHAPTER|Chapter)[ \t]+([IVXLCDM]+|\d+|[A-Za-z]+)\.?[ \t]*[:.\-]?[ \t]*(.*)$",
    re.MULTILINE,
)

WORDS_PER_MINUTE = 200


def strip_boilerplate(raw_text: str) -> str:
    text = raw_text
    for pattern in START_MARKERS:
        match = pattern.search(text)
        if match:
            text = text[match.end() :]
            break
    for pattern in END_MARKERS:
        match = pattern.search(text)
        if match:
            text = text[: match.start()]
            break
    return text.strip()


def word_count(text: str) -> int:
    return len(text.split())


ROMAN_VALUES = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100, "D": 500, "M": 1000}


def _roman_to_int(token: str) -> int | None:
    token = token.upper()
    if not token or any(ch not in ROMAN_VALUES for ch in token):
        return None
    total = 0
    prev = 0
    for ch in reversed(token):
        value = ROMAN_VALUES[ch]
        total += -value if value < prev else value
        prev = max(prev, value)
    return total


def _parse_chapter_number(token: str) -> int | None:
    if token.isdigit():
        return int(token)
    return _roman_to_int(token)


def _find_real_chapters_start(matches: list[re.Match]) -> int:
    """A Table of Contents lists every chapter heading again, numbered
    1..N, before the real chapters repeat that same 1..N sequence. Rather
    than guessing from surrounding whitespace, use that restart itself as
    the signal: find the *last* heading numbered 1/I (the start of the real
    sequence) and discard everything before it. Books with no ToC at all
    have their real "Chapter 1" as the only/first such match, so nothing is
    discarded. Headings with non-numeric titles (unparseable) leave the
    heuristic a no-op."""
    restart_index = 0
    for i, match in enumerate(matches):
        if _parse_chapter_number(match.group(2)) == 1:
            restart_index = i
    return restart_index


def _looks_like_listing(text: str, min_lines: int = 8, avg_word_threshold: float = 5.0) -> bool:
    """A Table of Contents or illustrations list is many short lines (a title
    or caption each); real narrative prose runs long, paragraph-wrapped
    lines. Used to keep list-like filler out of the "lead-in" chapter."""
    lines = [line.strip() for line in text.split("\n") if line.strip()]
    if len(lines) < min_lines:
        return False
    avg_words = sum(len(line.split()) for line in lines) / len(lines)
    return avg_words < avg_word_threshold


def split_into_chapters(clean_text: str) -> list[dict]:
    """Split on CHAPTER headings. Falls back to one chapter if no heading found
    (e.g. short stories like *The Yellow Wallpaper*)."""
    all_matches = list(CHAPTER_HEADING_RE.finditer(clean_text))
    if not all_matches:
        return [{"title": "", "text": clean_text.strip()}]

    restart_index = _find_real_chapters_start(all_matches)
    matches = all_matches[restart_index:]

    # Some books (e.g. Tom Sawyer) carry the descriptive chapter title only in
    # the ToC listing, leaving the real in-body heading bare ("CHAPTER I").
    # Recover those by number so real chapters can reuse them.
    toc_titles: dict[int, str] = {}
    for toc_match in all_matches[:restart_index]:
        number = _parse_chapter_number(toc_match.group(2))
        toc_title = toc_match.group(3).strip() if toc_match.group(3) else ""
        if number is not None and toc_title:
            toc_titles[number] = toc_title

    chapters = []
    for i, match in enumerate(matches):
        start = match.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(clean_text)
        heading_line = match.group(0).strip()
        same_line_title = re.sub(r"^[\]\)\s]+", "", match.group(3).strip()) if match.group(3) else ""
        number = _parse_chapter_number(match.group(2))
        title = same_line_title or toc_titles.get(number, "")

        # Drop the heading match itself from the stored body (its title is
        # already tracked on the chapter), plus - when the title actually
        # came from the ToC rather than this line - a standalone next line
        # that just repeats it (some editions print the title again on its
        # own line directly under a bare in-body heading).
        after_heading = clean_text[match.end() : end].lstrip("\n")
        if title and not same_line_title:
            first_line, _, rest = after_heading.partition("\n")
            if first_line.strip().lower() == title.strip().lower():
                after_heading = rest
        body = after_heading.strip()
        chapters.append({"title": title or heading_line, "text": body})

    # Text before the ToC even begins (title page, publisher info) plus any
    # genuine narrative sitting between the ToC and the real first chapter
    # (e.g. Frankenstein's framing letters) - but not the ToC/illustrations
    # list itself, which reads as a run of short lines rather than prose.
    pre_toc = clean_text[: all_matches[0].start()]
    transition = clean_text[all_matches[restart_index - 1].end() : matches[0].start()] if restart_index > 0 else ""
    lead_in_parts = [pre_toc] + ([] if _looks_like_listing(transition) else [transition])
    lead_in = "\n\n".join(p.strip() for p in lead_in_parts if p.strip())

    if word_count(lead_in) > 50:
        chapters.insert(0, {"title": "", "text": lead_in})

    return chapters


SCENE_SHIFT_RE = re.compile(r"\n\s*(\*\s*\*\s*\*|-{3,}|_{3,})\s*\n")


def split_paragraphs(text: str) -> list[str]:
    paragraphs = re.split(r"\n\s*\n", text)
    return [p.strip() for p in paragraphs if p.strip()]


SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")


def _split_oversized_paragraph(paragraph: str, max_words: int) -> list[str]:
    """A paragraph far larger than a whole micro-session (no blank-line break
    to pack around) gets sub-divided on sentence boundaries, falling back to a
    hard word-count split if it has no sentence punctuation either."""
    if word_count(paragraph) <= max_words * 1.5:
        return [paragraph]

    sentences = SENTENCE_SPLIT_RE.split(paragraph)
    chunks: list[str] = []
    current: list[str] = []
    current_words = 0
    for sentence in sentences:
        sentence_words = word_count(sentence)
        if current and current_words + sentence_words > max_words:
            chunks.append(" ".join(current))
            current, current_words = [], 0
        current.append(sentence)
        current_words += sentence_words
    if current:
        chunks.append(" ".join(current))

    if len(chunks) == 1 and word_count(chunks[0]) > max_words * 1.5:
        words = chunks[0].split()
        chunks = [" ".join(words[i : i + max_words]) for i in range(0, len(words), max_words)]

    return chunks


def split_into_micro_sessions(
    chapter_text: str,
    min_words: int = 400,
    max_words: int = 600,
) -> list[dict]:
    """Greedily pack paragraphs into ~400-600 word chunks, breaking at paragraph
    boundaries. The last chunk of a chapter is always flagged as a cliffhanger
    break; a chunk ending right before a scene-shift marker (***, ---, ___) is
    flagged too, since those are natural narrative pause points."""
    paragraphs = split_paragraphs(chapter_text)
    if not paragraphs:
        return []

    expanded_paragraphs = []
    for paragraph in paragraphs:
        expanded_paragraphs.extend(_split_oversized_paragraph(paragraph, max_words))
    paragraphs = expanded_paragraphs

    scene_shift_after = {
        i for i, p in enumerate(paragraphs) if SCENE_SHIFT_RE.search("\n" + p + "\n")
    }

    sessions: list[dict] = []
    current: list[str] = []
    current_words = 0

    def flush(is_cliffhanger: bool):
        nonlocal current, current_words
        if not current:
            return
        sessions.append(
            {
                "text": "\n\n".join(current),
                "word_count": current_words,
                "is_cliffhanger_break": is_cliffhanger,
                "has_visualization_prompt": False,
            }
        )
        current = []
        current_words = 0

    for i, para in enumerate(paragraphs):
        para_words = word_count(para)
        if current_words + para_words > max_words and current_words >= min_words:
            flush(is_cliffhanger=False)

        current.append(para)
        current_words += para_words

        is_last_paragraph = i == len(paragraphs) - 1
        at_scene_shift = i in scene_shift_after
        if current_words >= min_words and (at_scene_shift or is_last_paragraph):
            flush(is_cliffhanger=at_scene_shift or is_last_paragraph)
        elif current_words >= max_words * 1.5:
            # very long paragraph(s) with no natural break: force a split
            flush(is_cliffhanger=False)

    flush(is_cliffhanger=True)

    if sessions:
        sessions[-1]["is_cliffhanger_break"] = True

    # Sprinkle a visualization checkpoint at every scene-shift boundary and
    # roughly every 3rd micro-session as a fallback so long chapters get some.
    for idx, session in enumerate(sessions):
        if session["is_cliffhanger_break"] or (idx > 0 and idx % 3 == 0):
            session["has_visualization_prompt"] = True

    for idx, session in enumerate(sessions):
        session["index"] = idx

    return sessions
