"""Shipping theme tags with the seed data: export, import, and permanence."""

import json

import pytest

from app.models import Book, MicroSessionTagging, MicroSessionTheme
from app.services import theme_seed, themes
from tests.test_themes_service import db, drop_book, make_book, make_user  # noqa: F401

GID = 987_000_001


def reply(*pairs):
    return json.dumps({"themes": [{"theme": t, "score": s} for t, s in pairs]})


def tag(db, ms, *pairs):
    assert themes.tag_chunk(db, ms, client=None, provider=lambda c, t: reply(*pairs)) == "done"


@pytest.fixture()
def book(db):
    b, chunks = make_book(db, texts=("Lovers met.", "A murder.", "Quiet chapter."))
    b.gutenberg_id = GID
    db.commit()
    yield b, chunks
    drop_book(db, b.id)


def wipe_tags(db, chunks):
    ids = [c.id for c in chunks]
    db.query(MicroSessionTheme).filter(MicroSessionTheme.micro_session_id.in_(ids)).delete(synchronize_session=False)
    db.query(MicroSessionTagging).filter(MicroSessionTagging.micro_session_id.in_(ids)).delete(synchronize_session=False)
    db.commit()


def mine(data):
    """Only the fixture book: the test database also holds the real seeded books."""
    return {"format": data["format"], "books": [b for b in data["books"] if b["gutenberg_id"] == GID]}


def entry(data):
    return next(b for b in data["books"] if b["gutenberg_id"] == GID)


# --------------------------------------------------------------------------
# export
# --------------------------------------------------------------------------


def test_export_keys_chunks_by_book_chapter_and_session_not_by_database_id(db, book):
    b, chunks = book
    tag(db, chunks[0], ("romance", 5), ("class_money", 2))
    data = theme_seed.export_tags(db)
    assert data["format"] == theme_seed.FORMAT
    first = entry(data)["chunks"][0]
    assert (first["chapter"], first["session"]) == (1, 1)
    assert first["hash"] == theme_seed.chunk_hash(chunks[0].text)
    assert [(t["theme"], t["score"]) for t in first["themes"]] == [("romance", 5), ("class_money", 2)]  # low scores kept
    assert first["model"] == themes.settings.llm_model and first["prompt_version"] == themes.PROMPT_VERSION
    assert str(chunks[0].id) not in json.dumps(first)


def test_export_has_only_finished_llm_tags_of_shared_books(db, book):
    b, chunks = book
    tag(db, chunks[0], ("romance", 5))
    db.add(MicroSessionTagging(micro_session_id=chunks[1].id, status="failed", error="x"))
    db.add(MicroSessionTheme(micro_session_id=chunks[0].id, theme="war_conflict", score=4, source="human"))
    db.commit()
    owner = make_user(db)
    up, up_chunks = make_book(db, owner=owner, consent=True)
    up.gutenberg_id = GID + 1
    db.commit()
    try:
        tag(db, up_chunks[0], ("romance", 5))
        data = theme_seed.export_tags(db)
        assert [(c["chapter"], c["session"]) for c in entry(data)["chunks"]] == [(1, 1)]  # not the failed one
        assert "war_conflict" not in json.dumps(entry(data))  # human coder rows stay out
        assert all(b_["gutenberg_id"] != GID + 1 for b_ in data["books"])  # uploads never ship
    finally:
        drop_book(db, up.id)


def test_a_chunk_with_no_clear_theme_is_exported_as_done_and_empty(db, book):
    b, chunks = book
    tag(db, chunks[2])
    chunk = entry(theme_seed.export_tags(db))["chunks"][0]
    assert chunk["themes"] == [] and chunk["session"] == 3


def test_export_is_deterministic(db, book):
    b, chunks = book
    for c in chunks:
        tag(db, c, ("romance", 4), ("nature_place", 4))
    assert theme_seed.dumps(theme_seed.export_tags(db)) == theme_seed.dumps(theme_seed.export_tags(db))


# --------------------------------------------------------------------------
# import
# --------------------------------------------------------------------------


def test_a_fresh_database_gets_the_shipped_tags_back_exactly(db, book):
    b, chunks = book
    tag(db, chunks[0], ("romance", 5), ("class_money", 2))
    tag(db, chunks[1], ("mystery_detection", 5))
    tag(db, chunks[2])
    shipped = json.loads(theme_seed.dumps(mine(theme_seed.export_tags(db))))
    wipe_tags(db, chunks)
    summary = theme_seed.import_tags(db, shipped)
    assert summary == {"imported": 3, "skipped_existing": 0, "mismatched": 0, "invalid": 0, "missing_books": 0}
    db.expire_all()
    assert theme_seed.dumps(mine(theme_seed.export_tags(db))) == theme_seed.dumps(shipped)
    assert themes.needs_tagging(db, chunks[0].id) is False and themes.needs_tagging(db, chunks[2].id) is False


def test_importing_twice_changes_nothing(db, book):
    b, chunks = book
    tag(db, chunks[0], ("romance", 5))
    shipped = mine(theme_seed.export_tags(db))
    wipe_tags(db, chunks)
    theme_seed.import_tags(db, shipped)
    again = theme_seed.import_tags(db, shipped)
    assert again["imported"] == 0 and again["skipped_existing"] == 1
    assert db.query(MicroSessionTheme).filter_by(micro_session_id=chunks[0].id).count() == 1


def test_import_never_overwrites_an_existing_tag(db, book):
    """Tags are permanent: a chunk that already has tags keeps them, whatever the file says."""
    b, chunks = book
    tag(db, chunks[0], ("romance", 5))
    shipped = mine(theme_seed.export_tags(db))
    entry(shipped)["chunks"][0]["themes"] = [{"theme": "war_conflict", "score": 5}]
    entry(shipped)["chunks"][0]["model"] = "another model"
    summary = theme_seed.import_tags(db, shipped)
    assert summary["skipped_existing"] == 1 and summary["imported"] == 0
    db.expire_all()
    assert [r.theme for r in db.query(MicroSessionTheme).filter_by(micro_session_id=chunks[0].id)] == ["romance"]


def test_import_fills_failed_chunks_but_leaves_finished_ones(db, book):
    b, chunks = book
    tag(db, chunks[0], ("romance", 5))
    tag(db, chunks[1], ("mystery_detection", 5))
    shipped = mine(theme_seed.export_tags(db))
    wipe_tags(db, [chunks[1]])
    db.add(MicroSessionTagging(micro_session_id=chunks[1].id, status="failed", error="x"))
    db.commit()
    summary = theme_seed.import_tags(db, shipped)
    assert summary["imported"] == 1 and summary["skipped_existing"] == 1
    db.expire_all()
    assert db.get(MicroSessionTagging, chunks[1].id).status == "done"


def test_a_chunk_whose_text_changed_is_skipped_not_mislabelled(db, book):
    b, chunks = book
    tag(db, chunks[0], ("romance", 5))
    shipped = mine(theme_seed.export_tags(db))
    wipe_tags(db, chunks)
    chunks[0].text = "The text was edited upstream."
    db.commit()
    summary = theme_seed.import_tags(db, shipped)
    assert summary["mismatched"] == 1 and summary["imported"] == 0
    assert db.query(MicroSessionTheme).filter_by(micro_session_id=chunks[0].id).count() == 0


def test_unknown_books_and_bad_entries_are_counted_and_skipped(db, book):
    b, chunks = book
    tag(db, chunks[0], ("romance", 5))
    tag(db, chunks[1], ("mystery_detection", 5))
    shipped = mine(theme_seed.export_tags(db))
    wipe_tags(db, chunks)
    entry(shipped)["chunks"][0]["themes"] = [{"theme": "not_a_theme", "score": 4}]
    entry(shipped)["chunks"][1]["themes"] = [{"theme": "romance", "score": 9}]
    shipped["books"].append({"gutenberg_id": 111_222_333, "title": "Not seeded", "chunks": []})
    summary = theme_seed.import_tags(db, shipped)
    assert summary["invalid"] == 2 and summary["missing_books"] == 1 and summary["imported"] == 0
    assert db.query(MicroSessionTagging).filter_by(micro_session_id=chunks[0].id).count() == 0


def test_an_unknown_file_format_is_refused(db):
    with pytest.raises(ValueError):
        theme_seed.import_tags(db, {"format": 99, "books": []})


def test_importing_never_touches_uploaded_books(db, book):
    owner = make_user(db)
    up, up_chunks = make_book(db, owner=owner, consent=True)
    up.gutenberg_id = GID + 7
    db.commit()
    try:
        data = {"format": theme_seed.FORMAT, "books": [{"gutenberg_id": GID + 7, "title": "x", "chunks": [
            {"chapter": 1, "session": 1, "hash": theme_seed.chunk_hash(up_chunks[0].text), "model": "m",
             "prompt_version": 1, "theme_list_version": 1, "themes": [{"theme": "romance", "score": 5}]}]}]}
        assert theme_seed.import_tags(db, data)["missing_books"] == 1
        assert db.query(MicroSessionTheme).filter_by(micro_session_id=up_chunks[0].id).count() == 0
    finally:
        drop_book(db, up.id)


# --------------------------------------------------------------------------
# the scripts and the seeding hook
# --------------------------------------------------------------------------


def test_export_script_writes_the_file_and_import_script_restores_it(db, book, tmp_path, capsys):
    from scripts import export_theme_tags, import_theme_tags

    b, chunks = book
    tag(db, chunks[0], ("romance", 5))
    path = tmp_path / "tags.json"
    export_theme_tags.main(["--out", str(path)])
    shipped = json.loads(path.read_text(encoding="utf8"))
    assert entry(shipped)["chunks"][0]["themes"] == [{"theme": "romance", "score": 5}]
    wipe_tags(db, chunks)
    result = import_theme_tags.main(["--file", str(path)])
    assert result["imported"] >= 1
    assert "imported" in capsys.readouterr().out
    db.expire_all()
    assert themes.needs_tagging(db, chunks[0].id) is False


def test_import_script_reports_a_missing_file_clearly(tmp_path, capsys):
    from scripts import import_theme_tags

    assert import_theme_tags.main(["--file", str(tmp_path / "nope.json")]) == {"error": "no such file"}


def test_seeding_loads_the_shipped_tags_when_the_file_exists(db, book, tmp_path, monkeypatch, capsys):
    from scripts import seed_books

    b, chunks = book
    tag(db, chunks[1], ("mystery_detection", 5))
    path = tmp_path / "tags.json"
    path.write_text(theme_seed.dumps(mine(theme_seed.export_tags(db))), encoding="utf8")
    wipe_tags(db, chunks)
    monkeypatch.setattr(theme_seed, "DEFAULT_PATH", path)
    seed_books.import_shipped_tags()
    db.expire_all()
    assert themes.needs_tagging(db, chunks[1].id) is False
    monkeypatch.setattr(theme_seed, "DEFAULT_PATH", tmp_path / "absent.json")
    seed_books.import_shipped_tags()  # no file: seeding still works
