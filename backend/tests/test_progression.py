from types import SimpleNamespace

from app.services.progression import build_block, size_level_for


def test_size_level_thresholds():
    assert size_level_for(0) == 1
    assert size_level_for(4) == 1
    assert size_level_for(5) == 2
    assert size_level_for(14) == 2
    assert size_level_for(15) == 3
    assert size_level_for(100) == 3


def _ms(id, chapter_id, cliff=False):
    return SimpleNamespace(id=id, chapter_id=chapter_id, is_cliffhanger_break=cliff, word_count=100)


# Chapter 1: ids 1,2,3 (3 is the chapter-end cliffhanger).
# Chapter 2: ids 4,5 (5 is the chapter-end cliffhanger).
ORDERED = [
    _ms(1, 10),
    _ms(2, 10),
    _ms(3, 10, cliff=True),
    _ms(4, 20),
    _ms(5, 20, cliff=True),
]


def test_size_one_never_merges():
    block, nxt = build_block(ORDERED, 1, size=1)
    assert [m.id for m in block] == [1]
    assert nxt.id == 2


def test_size_two_merges_two():
    block, nxt = build_block(ORDERED, 1, size=2)
    assert [m.id for m in block] == [1, 2]
    assert nxt.id == 3


def test_block_stops_at_cliffhanger():
    # Starting at id 2, a size-3 block would reach the chapter-end cliffhanger
    # (id 3) and must stop there rather than crossing into chapter 2.
    block, nxt = build_block(ORDERED, 2, size=3)
    assert [m.id for m in block] == [2, 3]
    assert nxt.id == 4


def test_block_does_not_cross_chapters():
    block, nxt = build_block(ORDERED, 4, size=3)
    assert [m.id for m in block] == [4, 5]
    assert nxt is None


def test_last_block_has_no_next():
    block, nxt = build_block(ORDERED, 5, size=2)
    assert [m.id for m in block] == [5]
    assert nxt is None


def test_unknown_start_id():
    block, nxt = build_block(ORDERED, 999, size=2)
    assert block == []
    assert nxt is None
