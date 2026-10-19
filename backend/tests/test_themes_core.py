"""Theme service: reply validation, tagging a chunk, reached chunks, provider call."""

import json
import logging

import httpx
import pytest

from app.config import settings
from app.models import (
    MicroSession,
    MicroSessionTagging,
    MicroSessionTheme,
    ReadingSession,
    UserBookProgress,
)
from app.services import themes
from tests.test_themes_service import db, drop_book, make_book, make_user  # noqa: F401


def reply(*pairs):
    return json.dumps({"themes": [{"theme": t, "score": s} for t, s in pairs]})


def stub(content):
    calls = []

    def provider(client, text):
        calls.append(text)
        if isinstance(content, Exception):
            raise content
        return content

    provider.calls = calls
    return provider


def test_parse_reply_accepts_good_replies():
    assert themes.parse_reply(reply(("romance", 5), ("class_money", 3))) == [("romance", 5), ("class_money", 3)]
    assert themes.parse_reply(reply()) == []
    assert len(themes.parse_reply(reply(("romance", 1), ("war_conflict", 2), ("nature_place", 5)))) == 3


@pytest.mark.parametrize(
    "content",
    [
        "I think this passage is about romance.",
        "{not json",
        "",
        None,
        "[]",
        json.dumps({"other": []}),
        json.dumps({"themes": "romance"}),
        json.dumps({"themes": [{"theme": "sadness", "score": 3}]}),
        json.dumps({"themes": [{"theme": "romance", "score": 0}]}),
        json.dumps({"themes": [{"theme": "romance", "score": 6}]}),
        json.dumps({"themes": [{"theme": "romance", "score": "3"}]}),
        json.dumps({"themes": [{"theme": "romance", "score": 3.5}]}),
        json.dumps({"themes": [{"theme": "romance", "score": True}]}),
        json.dumps({"themes": [{"theme": "romance"}]}),
        reply(("romance", 3), ("romance", 4)),
    ],
)
def test_parse_reply_rejects_bad_replies(content):
    with pytest.raises(themes.ThemeReplyError):
        themes.parse_reply(content)


def test_theme_constants():
    assert list(themes.THEMES) == [
        "mystery_detection", "romance", "grief_loss_death", "fear_supernatural", "adventure_travel",
        "war_conflict", "family_childhood", "class_money", "gender_womens_roles", "justice_morality",
        "nature_place", "identity_self", "humour_satire", "madness_mind",
    ]
    assert themes.THEME_LIST_VERSION == 1 and themes.PROMPT_VERSION == 1 and themes.MIN_SHOWN_SCORE == 3


def test_build_messages_lists_every_theme_and_the_passage():
    msgs = themes.build_messages("Call me Ishmael.")
    assert msgs[0]["role"] == "system" and msgs[-1] == {"role": "user", "content": "Call me Ishmael."}
    for theme_id in themes.THEMES:
        assert theme_id in msgs[0]["content"]


def test_response_schema_restricts_themes_to_the_list():
    schema = themes.response_schema()
    item = schema["schema"]["properties"]["themes"]["items"]["properties"]
    assert item["theme"]["enum"] == list(themes.THEMES)
    assert schema["schema"]["properties"]["themes"]["maxItems"] == 3
    assert (item["score"]["minimum"], item["score"]["maximum"]) == (1, 5)


def test_tag_chunk_stores_rows_with_model_and_versions(db, monkeypatch):
    monkeypatch.setattr(settings, "op_model", "test/model:free")
    book, (a, _) = make_book(db)
    try:
        status = themes.tag_chunk(db, a, client=None, provider=stub(reply(("romance", 5), ("class_money", 2))))
        assert status == "done"
        db.expire_all()
        rows = {r.theme: r for r in db.query(MicroSessionTheme).filter_by(micro_session_id=a.id)}
        assert set(rows) == {"romance", "class_money"}
        assert rows["romance"].score == 5 and rows["romance"].source == "llm"
        assert rows["romance"].model == "test/model:free"
        assert (rows["romance"].prompt_version, rows["romance"].theme_list_version) == (1, 1)
        tagging = db.get(MicroSessionTagging, a.id)
        assert (tagging.status, tagging.model, tagging.error) == ("done", "test/model:free", None)
    finally:
        drop_book(db, book.id)


def test_empty_theme_list_is_valid_and_recorded_done(db):
    book, (a, _) = make_book(db)
    try:
        assert themes.tag_chunk(db, a, client=None, provider=stub(reply())) == "done"
        db.expire_all()
        assert db.query(MicroSessionTheme).filter_by(micro_session_id=a.id).count() == 0
        assert db.get(MicroSessionTagging, a.id).status == "done"
        assert themes.needs_tagging(db, a.id) is False
    finally:
        drop_book(db, book.id)


@pytest.mark.parametrize(
    "content",
    ["prose, not json", reply(("sadness", 3)), themes.ThemeProviderError("boom"), httpx.ReadTimeout("slow")],
)
def test_tag_chunk_failure_stores_failed_and_no_rows_and_does_not_raise(db, content):
    book, (a, _) = make_book(db)
    try:
        assert themes.tag_chunk(db, a, client=None, provider=stub(content)) == "failed"
        db.expire_all()
        assert db.query(MicroSessionTheme).filter_by(micro_session_id=a.id).count() == 0
        tagging = db.get(MicroSessionTagging, a.id)
        assert tagging.status == "failed" and tagging.error
        assert len(tagging.error) <= 200
        assert themes.needs_tagging(db, a.id) is True
    finally:
        drop_book(db, book.id)


def test_failed_chunk_never_stores_the_passage_text_in_the_error(db):
    book, (a, _) = make_book(db, texts=("A very private sentence about someone.", "Other."))
    try:
        themes.tag_chunk(db, a, client=None, provider=stub("A very private sentence about someone."))
        db.expire_all()
        assert "private" not in (db.get(MicroSessionTagging, a.id).error or "")
    finally:
        drop_book(db, book.id)


def test_a_second_pass_leaves_both_the_llm_and_the_human_tags_as_they_were(db):
    book, (a, _) = make_book(db)
    try:
        themes.tag_chunk(db, a, client=None, provider=stub(reply(("romance", 5))))
        db.add(MicroSessionTheme(micro_session_id=a.id, theme="war_conflict", score=4, source="human", model="", prompt_version=0, theme_list_version=1))
        db.commit()
        themes.tag_chunk(db, a, client=None, provider=stub(reply(("class_money", 4))))
        db.expire_all()
        got = {(r.theme, r.source) for r in db.query(MicroSessionTheme).filter_by(micro_session_id=a.id)}
        assert got == {("romance", "llm"), ("war_conflict", "human")}
    finally:
        drop_book(db, book.id)


def test_a_done_chunk_never_needs_tagging_whatever_the_model_or_versions(db):
    book, (a, b) = make_book(db)
    try:
        assert themes.needs_tagging(db, a.id) is True
        themes.tag_chunk(db, a, client=None, provider=stub(reply(("romance", 4))))
        assert themes.needs_tagging(db, a.id) is False
        tagging = db.get(MicroSessionTagging, a.id)
        tagging.prompt_version, tagging.theme_list_version, tagging.model = 0, 0, "some other model"
        db.commit()
        assert themes.needs_tagging(db, a.id) is False  # a tag, once made, is permanent
    finally:
        drop_book(db, book.id)


def test_tagging_a_done_chunk_again_changes_nothing_and_asks_no_model(db):
    book, (a, b) = make_book(db)
    try:
        themes.tag_chunk(db, a, client=None, provider=stub(reply(("romance", 4))))

        def must_not_be_called(client, text):
            raise AssertionError("the model was asked about a chunk that already has tags")

        assert themes.tag_chunk(db, a, client=None, provider=must_not_be_called) == "done"
        db.expire_all()
        rows = db.query(MicroSessionTheme).filter_by(micro_session_id=a.id).all()
        assert [(r.theme, r.score) for r in rows] == [("romance", 4)]
    finally:
        drop_book(db, book.id)


def test_a_reply_with_more_than_three_themes_keeps_the_three_highest_scored():
    four = reply(("romance", 3), ("war_conflict", 5), ("class_money", 4), ("nature_place", 3))
    assert themes.parse_reply(four) == [("war_conflict", 5), ("class_money", 4), ("romance", 3)]


def test_reached_ids_follow_position_and_completed_sessions(db):
    user = make_user(db)
    book, (a, b) = make_book(db)
    ch = a.chapter
    c = MicroSession(index=3, text="Third.", word_count=1)
    d = MicroSession(index=4, text="Fourth.", word_count=1)
    ch.micro_sessions.extend([c, d])
    db.commit()
    try:
        db.add(UserBookProgress(user_id=user.id, book_id=book.id, current_chapter_id=ch.id, current_micro_session_id=b.id))
        db.commit()
        assert themes.reached_micro_session_ids(db, user, book) == {a.id, b.id}
        db.add(ReadingSession(user_id=user.id, book_id=book.id, chapter_id=ch.id, micro_session_id=c.id, completed=True))
        db.commit()
        assert themes.reached_micro_session_ids(db, user, book) == {a.id, b.id, c.id}
        assert d.id not in themes.reached_micro_session_ids(db, user, book)
    finally:
        drop_book(db, book.id)


def test_reached_ids_for_a_reader_with_no_progress_is_just_the_first_chunk(db):
    user = make_user(db)
    book, (a, b) = make_book(db)
    try:
        assert themes.reached_micro_session_ids(db, user, book) == {a.id}
    finally:
        drop_book(db, book.id)


def test_reached_ids_include_the_rest_of_a_merged_block(db):
    user = make_user(db)
    user.session_size_level = 2
    db.commit()
    book, (a, b) = make_book(db)
    c = MicroSession(index=3, text="Third.", word_count=1)
    a.chapter.micro_sessions.append(c)
    db.commit()
    try:
        db.add(UserBookProgress(user_id=user.id, book_id=book.id, current_chapter_id=a.chapter_id, current_micro_session_id=a.id))
        db.commit()
        # the reader is shown a and b together, so both count as reached
        assert themes.reached_micro_session_ids(db, user, book) == {a.id, b.id}
    finally:
        drop_book(db, book.id)


def mock_client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler), headers={"Authorization": "Bearer k"})


def ok_response(content):
    return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})


def test_call_model_retries_429_then_succeeds_and_gives_up_after_the_limit(monkeypatch):
    sleeps = []
    monkeypatch.setattr(themes, "_sleep", lambda s: sleeps.append(s))
    monkeypatch.setattr(settings, "op_model", "m")
    seen = {"n": 0}

    def flaky(request):
        seen["n"] += 1
        if seen["n"] < 3:
            return httpx.Response(429, headers={"Retry-After": "2"})
        return ok_response(reply(("romance", 4)))

    assert themes.call_model(mock_client(flaky), "text") == reply(("romance", 4))
    assert seen["n"] == 3 and sleeps[:2] == [2.0, 2.0]

    with pytest.raises(themes.ThemeProviderError):
        themes.call_model(mock_client(lambda r: httpx.Response(503)), "text")


@pytest.mark.parametrize("header", ["-1", "inf", "nan", "soon"])
def test_call_model_ignores_unusable_retry_after_values(monkeypatch, header):
    sleeps = []
    monkeypatch.setattr(themes, "_sleep", sleeps.append)
    seen = {"n": 0}

    def limited(request):
        seen["n"] += 1
        if seen["n"] == 1:
            return httpx.Response(429, headers={"Retry-After": header})
        return ok_response(reply(("romance", 4)))

    assert themes.call_model(mock_client(limited), "text") == reply(("romance", 4))
    assert len(sleeps) == 1 and 0 < sleeps[0] <= themes.MAX_WAIT_SECONDS


def test_call_model_gives_up_at_once_when_the_wait_is_too_long(monkeypatch):
    sleeps, seen = [], {"n": 0}
    monkeypatch.setattr(themes, "_sleep", sleeps.append)

    def daily_limit(request):
        seen["n"] += 1
        return httpx.Response(429, headers={"Retry-After": "3600"})

    with pytest.raises(themes.ThemeProviderError):
        themes.call_model(mock_client(daily_limit), "text")
    assert seen["n"] == 1 and sleeps == []


def test_call_model_does_not_sleep_after_the_final_attempt(monkeypatch):
    sleeps = []
    monkeypatch.setattr(themes, "_sleep", sleeps.append)
    with pytest.raises(themes.ThemeProviderError):
        themes.call_model(mock_client(lambda r: httpx.Response(503)), "text")
    assert len(sleeps) == themes.MAX_ATTEMPTS - 1


def test_call_model_retries_transport_errors_then_raises(monkeypatch):
    monkeypatch.setattr(themes, "_sleep", lambda s: None)

    def boom(request):
        raise httpx.ConnectError("reset")

    with pytest.raises(themes.ThemeProviderError):
        themes.call_model(mock_client(boom), "text")


def test_call_model_rejects_client_errors_without_retry(monkeypatch):
    monkeypatch.setattr(themes, "_sleep", lambda s: None)
    seen = {"n": 0}

    def bad_key(request):
        seen["n"] += 1
        return httpx.Response(401, json={"error": "no"})

    with pytest.raises(themes.ThemeProviderError):
        themes.call_model(mock_client(bad_key), "text")
    assert seen["n"] == 1


def test_call_model_sends_model_schema_and_text_and_never_the_key(monkeypatch, caplog):
    monkeypatch.setattr(themes, "_sleep", lambda s: None)
    monkeypatch.setattr(settings, "op_model", "nvidia/x:free")
    monkeypatch.setattr(settings, "op_api_key", "sk-secret-key")
    sent = {}

    def capture(request):
        sent["body"] = json.loads(request.content)
        return ok_response(reply())

    themes.call_model(mock_client(capture), "The passage text.")
    body = sent["body"]
    assert body["model"] == "nvidia/x:free"
    assert body["response_format"]["type"] == "json_schema"
    assert body["messages"][-1]["content"] == "The passage text."
    assert "sk-secret-key" not in json.dumps(body)

    with caplog.at_level(logging.DEBUG):
        with pytest.raises(themes.ThemeProviderError) as err:
            themes.call_model(mock_client(lambda r: httpx.Response(500)), "The passage text.")
    assert "sk-secret-key" not in caplog.text and "sk-secret-key" not in str(err.value)
    assert "The passage text." not in caplog.text and "The passage text." not in str(err.value)


def test_make_client_requires_a_key_and_a_model_and_sets_auth(monkeypatch):
    monkeypatch.setattr(settings, "op_api_key", "")
    monkeypatch.setattr(settings, "op_model", "m")
    with pytest.raises(themes.ThemeProviderError):
        themes.make_client()
    monkeypatch.setattr(settings, "op_api_key", "abc")
    monkeypatch.setattr(settings, "op_model", "")
    with pytest.raises(themes.ThemeProviderError):
        themes.make_client()
    monkeypatch.setattr(settings, "op_model", "m")
    client = themes.make_client()
    assert client.headers["Authorization"] == "Bearer abc"
    client.close()


def test_parse_reply_accepts_a_reply_wrapped_in_code_fences():
    fenced = "```json\n" + reply(("romance", 4)) + "\n```"
    assert themes.parse_reply(fenced) == [("romance", 4)]
    assert themes.parse_reply("```\n" + reply() + "\n```") == []


def test_call_model_retries_a_200_that_carries_a_provider_error(monkeypatch):
    sleeps, seen = [], {"n": 0}
    monkeypatch.setattr(themes, "_sleep", sleeps.append)

    def flaky(request):
        seen["n"] += 1
        if seen["n"] == 1:
            return httpx.Response(200, json={"error": {"message": "upstream down", "code": 502}})
        return ok_response(reply(("romance", 4)))

    assert themes.call_model(mock_client(flaky), "text") == reply(("romance", 4))
    assert seen["n"] == 2 and len(sleeps) == 1


def test_reached_ids_use_the_words_actually_read_not_todays_session_size(db):
    user = make_user(db)
    user.session_size_level = 3
    db.commit()
    book, (a, b) = make_book(db)
    ch = a.chapter
    c, d, e = (MicroSession(index=i, text=f"Chunk {i}.", word_count=4) for i in (3, 4, 5))
    ch.micro_sessions.extend([c, d, e])
    db.commit()
    try:
        db.add(UserBookProgress(user_id=user.id, book_id=book.id, current_chapter_id=ch.id, current_micro_session_id=a.id))
        # the reader once finished a one-chunk session at d, back when blocks were small
        db.add(ReadingSession(user_id=user.id, book_id=book.id, chapter_id=ch.id, micro_session_id=d.id,
                              completed=True, words_read=d.word_count))
        db.commit()
        # current block a,b,c plus the d they finished; today's size 3 must not drag e in
        assert themes.reached_micro_session_ids(db, user, book) == {a.id, b.id, c.id, d.id}
    finally:
        drop_book(db, book.id)


# --------------------------------------------------------------------------
# choosing the model provider (OpenRouter or Ollama)
# --------------------------------------------------------------------------


@pytest.fixture()
def ollama(monkeypatch):
    monkeypatch.setattr(settings, "llm_provider", "ollama")
    monkeypatch.setattr(settings, "ollama_api_key", "ol-secret")
    monkeypatch.setattr(settings, "ollama_model", "gemma4:31b")
    monkeypatch.setattr(themes, "_sleep", lambda s: None)


def test_the_active_model_follows_the_provider(monkeypatch):
    monkeypatch.setattr(settings, "op_model", "nvidia/x:free")
    monkeypatch.setattr(settings, "ollama_model", "gemma4:31b")
    monkeypatch.setattr(settings, "llm_provider", "openrouter")
    assert settings.llm_model == "nvidia/x:free"
    monkeypatch.setattr(settings, "llm_provider", "ollama")
    assert settings.llm_model == "gemma4:31b"


def test_ollama_requests_use_its_chat_endpoint_schema_format_and_bearer_key(ollama):
    sent = {}

    def capture(request):
        sent["url"] = str(request.url)
        sent["auth"] = request.headers.get("authorization")
        sent["body"] = json.loads(request.content)
        return httpx.Response(200, json={"message": {"role": "assistant", "content": reply(("romance", 4))}})

    client = themes.make_client()
    client._transport = httpx.MockTransport(capture)
    assert themes.call_model(client, "The passage.") == reply(("romance", 4))
    body = sent["body"]
    assert sent["url"] == settings.ollama_url and sent["auth"] == "Bearer ol-secret"
    assert body["model"] == "gemma4:31b" and body["stream"] is False
    assert body["format"] == themes.response_schema()["schema"]
    assert "response_format" not in body and body["messages"][-1]["content"] == "The passage."
    assert "ol-secret" not in json.dumps(body)


def test_ollama_needs_its_own_key_and_model(monkeypatch):
    monkeypatch.setattr(settings, "llm_provider", "ollama")
    monkeypatch.setattr(settings, "ollama_api_key", "")
    with pytest.raises(themes.ThemeProviderError) as err:
        themes.make_client()
    assert "OLLAMA_API_KEY" in str(err.value)
    monkeypatch.setattr(settings, "ollama_api_key", "k")
    monkeypatch.setattr(settings, "ollama_model", "")
    with pytest.raises(themes.ThemeProviderError) as err:
        themes.make_client()
    assert "OLLAMA_MODEL" in str(err.value)


def test_ollama_replies_are_retried_like_openrouter_ones(ollama):
    seen = {"n": 0}

    def flaky(request):
        seen["n"] += 1
        if seen["n"] == 1:
            return httpx.Response(429)
        if seen["n"] == 2:
            return httpx.Response(200, json={"error": "model busy"})
        return httpx.Response(200, json={"message": {"content": reply(("war_conflict", 5))}})

    assert themes.call_model(mock_client(flaky), "text") == reply(("war_conflict", 5))
    assert seen["n"] == 3


def test_tags_record_the_model_that_made_them(db, ollama):
    book, (a, _b) = make_book(db)
    try:
        assert themes.tag_chunk(db, a, client=None, provider=lambda c, t: reply(("romance", 4))) == "done"
        db.expire_all()
        assert db.query(MicroSessionTheme).filter_by(micro_session_id=a.id).one().model == "gemma4:31b"
    finally:
        drop_book(db, book.id)
