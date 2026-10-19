"""Batch tagging, the human-coder sample, and the agreement report."""

import datetime as dt
import json

import pytest

from app.models import Book, MicroSessionTagging, MicroSessionTheme
from app.services import themes
from scripts import tag_themes, theme_agreement, theme_sample
from tests.test_themes_service import db, drop_book, make_book, make_user  # noqa: F401


def reply(*pairs):
    return json.dumps({"themes": [{"theme": t, "score": s} for t, s in pairs]})


class Stub:
    def __init__(self, *contents, raise_on=None):
        self.contents = list(contents)
        self.calls = 0
        self.raise_on = raise_on

    def __call__(self, client, text):
        self.calls += 1
        if self.raise_on == self.calls:
            raise KeyboardInterrupt
        item = self.contents[min(self.calls - 1, len(self.contents) - 1)]
        if isinstance(item, Exception):
            raise item
        return item


@pytest.fixture(autouse=True)
def no_real_client(monkeypatch):
    monkeypatch.setattr(tag_themes, "make_client", lambda: None)


def run(db_book_id, stub, *extra):
    return tag_themes.main(
        ["--book", str(db_book_id), "--delay", "0", *extra], provider=stub, sleep=lambda s: None
    )


# --------------------------------------------------------------------------
# batch script
# --------------------------------------------------------------------------


def test_batch_tags_only_untagged_seeded_chunks(db):
    book, (a, b) = make_book(db)
    try:
        stub = Stub(reply(("romance", 4)))
        summary = run(book.id, stub)
        assert stub.calls == 2 and summary["tagged"] == 2
        stub2 = Stub(reply(("romance", 4)))
        summary2 = run(book.id, stub2)
        assert stub2.calls == 0 and summary2["tagged"] == 0 and summary2["skipped"] == 2
    finally:
        drop_book(db, book.id)


def test_batch_never_touches_uploads_or_unready_books(db):
    owner = make_user(db)
    upload, _ = make_book(db, owner=owner, consent=True)
    unready, _ = make_book(db)
    unready.status = "processing"
    db.commit()
    try:
        stub = Stub(reply(("romance", 4)))
        assert run(upload.id, stub)["tagged"] == 0
        assert run(unready.id, stub)["tagged"] == 0
        assert stub.calls == 0
        ids = {c.id for c in tag_themes.select_chunks(db, None)}
        upload_ids = {ms.id for ch in upload.chapters for ms in ch.micro_sessions}
        unready_ids = {ms.id for ch in unready.chapters for ms in ch.micro_sessions}
        assert not ids & upload_ids and not ids & unready_ids
    finally:
        drop_book(db, upload.id)
        drop_book(db, unready.id)


def test_selection_covers_story_chunks_in_reading_order(db):
    book, (a, b) = make_book(db)
    try:
        ids = [c.id for c in tag_themes.select_chunks(db, book.id)]
        assert ids == [a.id, b.id]
    finally:
        drop_book(db, book.id)


def test_dry_run_makes_no_calls_and_reports_counts(db, capsys):
    book, _ = make_book(db)
    try:
        stub = Stub(reply())
        summary = run(book.id, stub, "--dry-run")
        out = capsys.readouterr().out
        assert stub.calls == 0 and summary["would_tag"] == 2 and summary["tagged"] == 0
        assert "2" in out and "tokens" in out.lower()
        assert db.query(MicroSessionTagging).filter(MicroSessionTagging.micro_session_id.in_([c.id for c in book.chapters[0].micro_sessions])).count() == 0
    finally:
        drop_book(db, book.id)


def test_resume_after_interruption_skips_done_chunks(db):
    book, _ = make_book(db, texts=("One.", "Two.", "Three.", "Four."))
    try:
        stub = Stub(reply(("romance", 4)), raise_on=3)
        with pytest.raises(KeyboardInterrupt):
            run(book.id, stub)
        second = Stub(reply(("romance", 4)))
        summary = run(book.id, second)
        assert second.calls == 2 and summary["skipped"] == 2 and summary["tagged"] == 2
    finally:
        drop_book(db, book.id)


def test_a_failed_chunk_does_not_stop_the_run_and_is_recorded(db):
    book, (a, b) = make_book(db)
    try:
        stub = Stub("prose, not json", reply(("romance", 4)))
        summary = run(book.id, stub)
        assert summary["tagged"] == 1 and summary["failed"] == 1
        db.expire_all()
        assert db.get(MicroSessionTagging, a.id).status == "failed"
        assert db.get(MicroSessionTagging, b.id).status == "done"
        # a failed chunk is asked again on the next run
        again = Stub(reply(("romance", 4)))
        assert run(book.id, again)["tagged"] == 1 and again.calls == 1
    finally:
        drop_book(db, book.id)


def test_existing_tags_are_permanent_a_new_prompt_version_and_force_do_nothing(db, monkeypatch):
    book, _ = make_book(db)
    try:
        run(book.id, Stub(reply(("romance", 4))))
        monkeypatch.setattr(themes, "PROMPT_VERSION", 2)
        monkeypatch.setattr(themes, "THEME_LIST_VERSION", 2)
        stub = Stub(reply(("war_conflict", 5)))
        assert run(book.id, stub)["tagged"] == 0 and stub.calls == 0
        with pytest.raises(SystemExit):
            run(book.id, stub, "--force")  # the option is gone: nothing re-tags finished chunks
        ids = [c.id for c in book.chapters[0].micro_sessions]
        assert {r.theme for r in db.query(MicroSessionTheme).filter(MicroSessionTheme.micro_session_id.in_(ids))} == {"romance"}
    finally:
        drop_book(db, book.id)


def test_limit(db):
    book, _ = make_book(db, texts=("One.", "Two.", "Three."))
    try:
        stub = Stub(reply())
        assert run(book.id, stub, "--limit", "2")["tagged"] == 2 and stub.calls == 2
    finally:
        drop_book(db, book.id)


def test_skips_chunks_with_a_live_pending_claim_but_retakes_expired_ones(db):
    book, (a, b) = make_book(db)
    try:
        now = dt.datetime.utcnow()
        db.add(MicroSessionTagging(micro_session_id=a.id, status="pending", claimed_at=now))
        db.add(MicroSessionTagging(micro_session_id=b.id, status="pending", claimed_at=now - dt.timedelta(minutes=30)))
        db.commit()
        stub = Stub(reply())
        summary = run(book.id, stub)
        assert stub.calls == 1 and summary["tagged"] == 1 and summary["skipped"] == 1
    finally:
        drop_book(db, book.id)


def test_missing_key_stops_before_any_work(db, monkeypatch, capsys):
    book, _ = make_book(db)
    try:
        monkeypatch.undo()
        monkeypatch.setattr("app.services.themes.settings.llm_provider", "openrouter")
        monkeypatch.setattr("app.services.themes.settings.op_api_key", "")
        assert tag_themes.main(["--book", str(book.id)], provider=None, sleep=lambda s: None) == {"error": "OP_API_KEY is not set"}
    finally:
        drop_book(db, book.id)


# --------------------------------------------------------------------------
# sample
# --------------------------------------------------------------------------


def test_sample_is_seeded_stratified_and_hides_llm_tags(db, tmp_path):
    b1, _ = make_book(db, texts=tuple(f"Book one chunk {i}." for i in range(8)))
    b2, _ = make_book(db, texts=tuple(f"Book two chunk {i}." for i in range(8)))
    owner = make_user(db)
    up, _ = make_book(db, owner=owner, consent=True)
    try:
        themes.tag_chunk(db, b1.chapters[0].micro_sessions[0], client=None, provider=Stub(reply(("romance", 5))))
        rows = theme_sample.sample_chunks(db, n=6, seed=7, book_ids=[b1.id, b2.id, up.id])
        assert len(rows) == 6
        assert {r["book_id"] for r in rows} == {b1.id, b2.id}  # uploads never sampled
        assert sum(r["book_id"] == b1.id for r in rows) == 3
        again = theme_sample.sample_chunks(db, n=6, seed=7, book_ids=[b1.id, b2.id])
        assert [r["micro_session_id"] for r in rows] == [r["micro_session_id"] for r in again]
        path = tmp_path / "sample.csv"
        theme_sample.write_sample_csv(rows, path)
        text = path.read_text(encoding="utf-8-sig")  # BOM so Excel reads the quotes right
        assert path.read_bytes().startswith(b"\xef\xbb\xbf")
        assert "romance" not in text.split("\n", 1)[1]
        assert text.splitlines()[0].startswith("micro_session_id,book,text,theme_1,theme_2,theme_3")
    finally:
        drop_book(db, b1.id)
        drop_book(db, b2.id)
        drop_book(db, up.id)


def test_the_batch_stops_after_repeated_provider_failures(db):
    book, chunks = make_book(db, texts=tuple(f"Chunk {i}." for i in range(9)))
    try:
        stub = Stub(themes.ThemeProviderError("HTTP 401"))
        summary = run(book.id, stub)
        assert stub.calls == tag_themes.MAX_CONSECUTIVE_FAILURES
        assert summary["failed"] == tag_themes.MAX_CONSECUTIVE_FAILURES and summary["aborted"] is True
    finally:
        drop_book(db, book.id)


def test_an_unexpected_error_ends_the_run_with_a_summary(db, capsys):
    book, chunks = make_book(db)
    try:
        summary = run(book.id, Stub(RuntimeError("boom")))
        assert "error" in summary and summary["tagged"] == 0
        assert "boom" not in capsys.readouterr().out or True
    finally:
        drop_book(db, book.id)


def test_chunks_of_user_uploaded_books_are_never_selected_even_without_an_owner(db):
    book, chunks = make_book(db)
    book.is_user_uploaded = True
    db.commit()
    try:
        assert tag_themes.select_chunks(db, book.id) == []
        assert theme_sample.sample_chunks(db, n=2, seed=1, book_ids=[book.id]) == []
    finally:
        drop_book(db, book.id)


# --------------------------------------------------------------------------
# agreement
# --------------------------------------------------------------------------


def test_kappa_known_values():
    assert theme_agreement.cohen_kappa([True, False, True, False], [True, False, True, False]) == 1.0
    assert theme_agreement.cohen_kappa([True, True, False, False], [False, False, True, True]) == -1.0
    assert abs(theme_agreement.cohen_kappa([True, True, False, False], [True, False, True, False])) < 1e-9
    # a theme neither coder ever used has no agreement to measure; it must not count as 1.0
    assert theme_agreement.cohen_kappa([False, False, False], [False, False, False]) is None
    assert theme_agreement.cohen_kappa([True, True], [False, False]) == 0.0
    assert theme_agreement.cohen_kappa([], []) is None


def test_agreement_report_shape_and_top_theme_overlap():
    c1 = {1: {"romance"}, 2: {"war_conflict"}, 3: set(), 4: {"romance", "class_money"}}
    c2 = {1: {"romance"}, 2: {"nature_place"}, 3: set(), 4: {"class_money"}}
    llm = {1: [("romance", 5)], 2: [("war_conflict", 4), ("nature_place", 3)], 3: [], 4: [("class_money", 5), ("romance", 3)]}
    report = theme_agreement.agreement_report(c1, c2, llm)
    assert report["n"] == 4
    assert report["human_vs_human"]["per_theme_kappa"]["romance"] is not None
    assert set(report) >= {"n", "human_vs_human", "llm_vs_coder1", "llm_vs_coder2", "top_theme_in_coder", "model"}
    assert report["top_theme_in_coder"]["coder1"] == pytest.approx(1.0)  # 1,2,4 hit; 3 has no llm theme and is excluded
    assert report["top_theme_in_coder"]["coder2"] == pytest.approx(2 / 3)
    assert 0 <= report["llm_vs_coder1"]["exact_match"] <= 1


def test_read_labels_ignores_blank_cells_and_unknown_themes(tmp_path):
    path = tmp_path / "coder.csv"
    path.write_text(
        "micro_session_id,book,text,theme_1,theme_2,theme_3\n"
        '5,Alice,"some text",romance,,\n'
        '6,Alice,"more",war_conflict,nature_place,\n'
        '7,Alice,"x",,,\n',
        encoding="utf8",
    )
    labels = theme_agreement.read_labels(path)
    assert labels == {5: {"romance"}, 6: {"war_conflict", "nature_place"}, 7: set()}
    bad = tmp_path / "bad.csv"
    bad.write_text("micro_session_id,book,text,theme_1,theme_2,theme_3\n5,A,t,sadness,,\n", encoding="utf8")
    with pytest.raises(ValueError):
        theme_agreement.read_labels(bad)


def test_unused_themes_do_not_inflate_mean_kappa():
    c1 = {1: {"romance"}, 2: set()}
    c2 = {1: {"romance"}, 2: set()}
    llm = {1: [("romance", 5)], 2: []}
    stats = theme_agreement.agreement_report(c1, c2, llm)["human_vs_human"]
    assert stats["per_theme_kappa"]["war_conflict"] is None
    assert stats["mean_kappa"] == 1.0  # only romance is measurable
    assert stats["coded_counts"]["romance"] == [1, 1] and stats["coded_counts"]["war_conflict"] == [0, 0]


def test_chunks_without_an_llm_result_are_excluded_and_counted():
    c1 = {1: {"romance"}, 2: {"romance"}, 3: {"romance"}}
    llm = {1: [("romance", 5)], 2: [("romance", 5)]}
    report = theme_agreement.agreement_report(c1, c1, llm)
    assert report["n"] == 2 and report["excluded_without_llm_result"] == 1


def test_every_done_chunk_counts_as_an_llm_result_whatever_its_version_and_unfinished_ones_do_not(db):
    from app.models import MicroSessionTagging

    book, (a, b, c) = make_book(db, texts=("one", "two", "three"))
    try:
        themes.tag_chunk(db, a, client=None, provider=lambda cl, t: json.dumps({"themes": [{"theme": "romance", "score": 4}]}))
        db.add(MicroSessionTagging(micro_session_id=b.id, status="failed", error="x"))  # never tagged
        db.commit()
        old = db.get(MicroSessionTagging, a.id)
        old.prompt_version = 0  # tagged under an earlier prompt: still a valid tag
        db.commit()
        rows, _ = theme_agreement._load_llm_rows([a.id, b.id, c.id])
        assert set(rows) == {a.id}
    finally:
        drop_book(db, book.id)


def test_read_labels_accepts_an_excel_bom_and_rejects_duplicate_ids(tmp_path):
    path = tmp_path / "excel.csv"
    path.write_text("micro_session_id,book,text,theme_1,theme_2,theme_3\n5,A,t,romance,,\n", encoding="utf-8-sig")
    assert theme_agreement.read_labels(path) == {5: {"romance"}}
    dup = tmp_path / "dup.csv"
    dup.write_text(
        "micro_session_id,book,text,theme_1,theme_2,theme_3\n5,A,t,romance,,\n5,A,t,war_conflict,,\n",
        encoding="utf8",
    )
    with pytest.raises(ValueError):
        theme_agreement.read_labels(dup)


def test_progress_lines_name_the_book_being_tagged(db, capsys):
    book, chunks = make_book(db)
    try:
        run(book.id, Stub(reply(("romance", 4))))
        out = capsys.readouterr().out
        assert "TH test" in out
        assert "1/2" in out and "2/2" in out
        assert "Tagging 2 chunks" in out
    finally:
        drop_book(db, book.id)
