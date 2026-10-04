"""Chapter detection against real public-domain books beyond the 5 seeds.

The book text is cached by `python -m scripts.fetch_test_books` and is not
committed, so these tests skip when the cache is absent.

Detection status at the time of writing (see the summary in each case):

    Dracula          CHAPTER I            pass
    Moby Dick        CHAPTER 1. Title     pass
    Jane Eyre        CHAPTER I            pass
    Metamorphosis    bare "I" on a line   pass (was 1 chapter of 21,935 words)
    Tale of Two Cities  "I. The Period"   pass (was 16 of 45 chapters)
    Sherlock Holmes  "ADVENTURE I."       improved, still imperfect
                                          (was 1 chapter of 104,506 words)
"""

from pathlib import Path

import pytest

from app.services.segmentation import (
    FALLBACK_SECTION_WORDS,
    split_into_chapters,
    split_into_fixed_sections,
    strip_boilerplate,
    word_count,
)

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "books"

# gutenberg id -> (label, min chapters, max chapters, max words in any chapter)
EXPECTATIONS = {
    345: ("Dracula", 25, 30, 20_000),
    2701: ("Moby Dick", 120, 145, 20_000),
    1260: ("Jane Eyre", 35, 42, 20_000),
    5200: ("Metamorphosis", 3, 3, 12_000),
    98: ("A Tale of Two Cities", 40, 50, 20_000),
    # Known imperfect: the 12 stories are detected, but front matter adds a few
    # spurious leading chapters. Still a vast improvement on one 104k chapter,
    # and the book is deliberately NOT in the seed set because of it.
    1661: ("The Adventures of Sherlock Holmes", 12, 16, 20_000),
}


def load(gutenberg_id: int) -> str:
    path = FIXTURE_DIR / f"{gutenberg_id}.txt"
    if not path.exists():
        pytest.skip(f"run `python -m scripts.fetch_test_books` to cache {gutenberg_id}.txt")
    return strip_boilerplate(path.read_text(encoding="utf-8"))


@pytest.mark.parametrize("gutenberg_id", sorted(EXPECTATIONS))
def test_chapter_detection_is_in_range(gutenberg_id):
    label, low, high, _ = EXPECTATIONS[gutenberg_id]
    chapters = split_into_chapters(load(gutenberg_id))
    assert low <= len(chapters) <= high, f"{label}: detected {len(chapters)} chapters"


@pytest.mark.parametrize("gutenberg_id", sorted(EXPECTATIONS))
def test_no_chapter_is_absurdly_large(gutenberg_id):
    """The old failure mode was silently returning the whole book as one
    chapter, which makes micro-sessions meaningless."""
    label, _, _, max_words = EXPECTATIONS[gutenberg_id]
    chapters = split_into_chapters(load(gutenberg_id))
    largest = max(word_count(c["text"]) for c in chapters)
    assert largest <= max_words, f"{label}: largest chapter is {largest:,} words"


@pytest.mark.parametrize("gutenberg_id", sorted(EXPECTATIONS))
def test_never_returns_zero_chapters(gutenberg_id):
    assert len(split_into_chapters(load(gutenberg_id))) >= 1


# --- the heuristics themselves, no network needed ---


def _para(word, n):
    return " ".join([word] * n)


def test_long_text_without_headings_falls_back_to_sections():
    text = "\n\n".join(_para("word", 500) for _ in range(40))  # 20,000 words
    chapters = split_into_chapters(text)
    assert len(chapters) > 1
    assert all(word_count(c["text"]) <= FALLBACK_SECTION_WORDS * 1.5 for c in chapters)


def test_short_text_without_headings_stays_one_chapter():
    # a short story is legitimately one chapter - don't chop it up
    text = "\n\n".join(_para("word", 500) for _ in range(4))
    assert len(split_into_chapters(text)) == 1


def test_fixed_sections_preserve_all_paragraphs():
    paragraphs = [_para(f"p{i}", 400) for i in range(10)]
    sections = split_into_fixed_sections("\n\n".join(paragraphs))
    rejoined = "\n\n".join(s["text"] for s in sections)
    assert {p.strip() for p in rejoined.split("\n\n")} == set(paragraphs)


def test_alternative_heading_keyword_is_detected():
    text = (
        "ADVENTURE I. A Scandal\n\n" + _para("alpha", 40)
        + "\n\nADVENTURE II. The League\n\n" + _para("beta", 40)
    )
    chapters = split_into_chapters(text)
    assert len(chapters) == 2
    assert chapters[0]["title"] == "A Scandal"


def test_bare_numeral_on_its_own_line_is_detected():
    text = "I\n\n" + _para("alpha", 40) + "\n\nII\n\n" + _para("beta", 40) + "\n\nIII\n\n" + _para("c", 40)
    assert len(split_into_chapters(text)) == 3


def test_bare_numerals_need_a_plausible_sequence():
    # stray numerals that don't start at 1 and count up are not headings
    text = "IV\n\n" + _para("alpha", 40) + "\n\nIX\n\n" + _para("beta", 40)
    assert len(split_into_chapters(text)) == 1


def test_structural_restart_is_not_mistaken_for_a_table_of_contents():
    """A novel in several Books renumbers from I each time; those earlier
    chapters must not be discarded the way a ToC listing is. Each chapter has
    real prose in it, which is exactly what distinguishes it from a ToC."""
    def book(titles, filler):
        return "\n\n".join(
            f"{numeral}. {title}\n\n" + _para(filler, 400)
            for numeral, title in titles
        )

    book_one = book([("I", "The Period"), ("II", "The Mail"), ("III", "The Shoemaker")], "alpha")
    book_two = book([("I", "Five Years"), ("II", "A Sight"), ("III", "The Shadow")], "gamma")
    chapters = split_into_chapters(book_one + "\n\n" + book_two)

    assert len(chapters) == 6
    assert "alpha" in chapters[0]["text"]
    assert chapters[0]["title"] == "The Period"


def test_dense_listing_is_still_treated_as_a_table_of_contents():
    toc = "\n".join(f"CHAPTER {i}. Title {i}" for i in range(1, 4))
    body = "\n\n".join(f"CHAPTER {i}. Title {i}\n\n" + _para(f"body{i}", 200) for i in range(1, 4))
    chapters = split_into_chapters(toc + "\n\n" + body)
    assert len(chapters) == 3
    assert "body1" in chapters[0]["text"]
