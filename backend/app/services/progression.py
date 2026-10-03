"""Progressive session length.

Readers start on single ~2-3 min micro-sessions and graduate to longer blocks
as they build the habit: 2 merged after 5 completed sessions, 3 after 15.
Blocks are merged at *read time* from the existing micro-sessions - the book is
never re-segmented - and a block never runs past a cliffhanger break or a
chapter boundary, so the dramatic pacing is preserved.
"""

# (completed-session threshold, resulting block size), highest first.
SIZE_THRESHOLDS = [(15, 3), (5, 2)]


def size_level_for(completed_count: int) -> int:
    for threshold, size in SIZE_THRESHOLDS:
        if completed_count >= threshold:
            return size
    return 1


def ordered_micro_sessions(book) -> list:
    """Every micro-session of a book in reading order (chapter, then index)."""
    result = []
    for chapter in sorted(book.chapters, key=lambda c: c.index):
        for ms in sorted(chapter.micro_sessions, key=lambda m: m.index):
            result.append(ms)
    return result


def build_block(ordered: list, start_id: int, size: int):
    """Greedily merge up to ``size`` consecutive micro-sessions starting at
    ``start_id``. Stops early when it hits a cliffhanger break or the end of a
    chapter. Returns ``(block, next_micro_session)`` where ``next_micro_session``
    is the first micro-session after the block (or None at the end of the book).
    """
    start_idx = next((i for i, ms in enumerate(ordered) if ms.id == start_id), None)
    if start_idx is None:
        return [], None

    block = [ordered[start_idx]]
    i = start_idx
    while len(block) < size:
        if block[-1].is_cliffhanger_break:
            break
        j = i + 1
        if j >= len(ordered):
            break
        nxt = ordered[j]
        if nxt.chapter_id != block[-1].chapter_id:
            break
        block.append(nxt)
        i = j

    next_idx = start_idx + len(block)
    next_ms = ordered[next_idx] if next_idx < len(ordered) else None
    return block, next_ms
