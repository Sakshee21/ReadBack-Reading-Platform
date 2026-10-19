"""Side-by-side comparison of two models on the same chunks (no database writes)."""

import json

from scripts import theme_compare
from tests.test_themes_service import db, drop_book, make_book  # noqa: F401


def reply(*pairs):
    return json.dumps({"themes": [{"theme": t, "score": s} for t, s in pairs]})


def chunks(n):
    return [{"micro_session_id": i, "book": "B", "text": f"text {i}"} for i in range(1, n + 1)]


def test_compare_reports_agreement_and_failures_per_model():
    answers_a = {
        "text 1": reply(("romance", 5)),
        "text 2": reply(("war_conflict", 4), ("class_money", 3)),
        "text 3": "not json",
        "text 4": reply(("romance", 2)),  # below the shown cut
    }
    answers_b = {
        "text 1": reply(("romance", 4)),
        "text 2": reply(("war_conflict", 5)),
        "text 3": reply(("nature_place", 4)),
        "text 4": reply(("humour_satire", 5)),
    }
    rows, summary = theme_compare.compare(chunks(4), lambda t: answers_a[t], lambda t: answers_b[t])
    assert summary["n"] == 4 and summary["a_failed"] == 1 and summary["b_failed"] == 0
    assert summary["compared"] == 3  # chunk 3 failed for A
    assert summary["top_theme_match"] == 2 / 3  # chunks 1 and 2 agree, chunk 4 does not
    assert abs(summary["mean_overlap"] - ((1.0 + 0.5 + 0.0) / 3)) < 1e-9
    assert rows[0]["a_themes"] == "romance" and rows[1]["a_themes"] == "war_conflict;class_money"
    assert rows[2]["a_themes"] == "" and rows[2]["a_status"] == "failed"


def test_compare_never_sends_the_key_or_stores_anything(db):
    book, (a, b) = make_book(db)
    try:
        rows, _ = theme_compare.compare(
            [{"micro_session_id": a.id, "book": "B", "text": a.text}], lambda t: reply(), lambda t: reply()
        )
        assert rows and "key" not in json.dumps(rows).lower()
        from app.models import MicroSessionTheme

        assert db.query(MicroSessionTheme).filter_by(micro_session_id=a.id).count() == 0
    finally:
        drop_book(db, book.id)


def test_csv_has_the_text_so_a_human_can_judge(tmp_path):
    rows, summary = theme_compare.compare(chunks(1), lambda t: reply(("romance", 5)), lambda t: reply(("grief_loss_death", 5)))
    path = tmp_path / "cmp.csv"
    theme_compare.write_csv(rows, path)
    text = path.read_text(encoding="utf-8-sig")
    assert text.splitlines()[0].startswith("micro_session_id,book,text,a_themes,b_themes")
    assert "text 1" in text
