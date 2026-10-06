"""The UI-polish layer adds new event types. They must flow through POST
/events and land in the CSV export without disturbing the existing logging.
"""

import csv
import io
import uuid

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app

# Event types introduced by the UI polish layer and the imagination-only
# visualization checkpoint.
NEW_EVENT_TYPES = [
    "celebration_shown",
    "ambient_sound_on",
    "ambient_sound_off",
    "visualization_vividness_rated",
    "visualization_prompt_dismissed",
]
# A few existing ones, to prove nothing regressed.
EXISTING_EVENT_TYPES = ["session_start", "session_end", "rsvp_start", "nudge_shown"]


@pytest.fixture(scope="module")
def client():
    return TestClient(app)


@pytest.fixture(scope="module")
def auth(client):
    email = f"uievents_{uuid.uuid4().hex[:8]}@test.com"
    resp = client.post("/auth/register", json={"email": email, "password": "pw12345"})
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}, email


def test_new_event_types_are_accepted(client, auth):
    headers, _ = auth
    payload = [
        {"event_type": "celebration_shown", "book_id": 2,
         "metadata": {"celebration_type": "streak_7", "streak_milestone": 7}},
        {"event_type": "ambient_sound_on", "book_id": 2,
         "metadata": {"sound_id": "rain", "volume": 0.4}},
        {"event_type": "ambient_sound_off", "book_id": 2, "metadata": {"sound_id": "rain"}},
        {"event_type": "visualization_vividness_rated", "book_id": 2,
         "metadata": {"rating": 4, "time_to_rate_ms": 3200}},
        {"event_type": "visualization_prompt_dismissed", "book_id": 2,
         "metadata": {"rated": False}},
    ]
    resp = client.post("/events", json=payload, headers=headers)
    assert resp.status_code == 201
    assert resp.json() == {"logged": len(payload)}


def test_existing_event_types_still_work(client, auth):
    headers, _ = auth
    for event_type in EXISTING_EVENT_TYPES:
        resp = client.post("/events", json={"event_type": event_type, "book_id": 2}, headers=headers)
        assert resp.status_code == 201, event_type


def test_new_events_reach_the_csv_export(client, auth):
    _, email = auth
    resp = client.get(f"/admin/export/events.csv?token={settings.admin_token}")
    assert resp.status_code == 200

    rows = list(csv.DictReader(io.StringIO(resp.text)))
    mine = [r for r in rows if r["user_email"] == email]
    logged_types = {r["event_type"] for r in mine}

    for event_type in NEW_EVENT_TYPES:
        assert event_type in logged_types, f"{event_type} missing from CSV export"


def test_celebration_metadata_survives_the_round_trip(client, auth):
    _, email = auth
    resp = client.get(f"/admin/export/events.csv?token={settings.admin_token}")
    rows = [
        r for r in csv.DictReader(io.StringIO(resp.text))
        if r["user_email"] == email and r["event_type"] == "celebration_shown"
    ]
    assert rows, "no celebration_shown row found"
    assert "streak_7" in rows[-1]["metadata"]
    assert "7" in rows[-1]["metadata"]


def test_csv_still_has_the_expected_columns(client):
    resp = client.get(f"/admin/export/events.csv?token={settings.admin_token}")
    header = next(csv.reader(io.StringIO(resp.text)))
    assert header == [
        "id", "user_id", "user_email", "book_id", "chapter_id",
        "micro_session_id", "event_type", "metadata", "created_at",
    ]


def test_vividness_rating_survives_the_round_trip(client, auth):
    """The rating is the replacement for the removed artwork reveal, so it has
    to reach the pilot export intact."""
    _, email = auth
    resp = client.get(f"/admin/export/events.csv?token={settings.admin_token}")
    rows = [
        r for r in csv.DictReader(io.StringIO(resp.text))
        if r["user_email"] == email and r["event_type"] == "visualization_vividness_rated"
    ]
    assert rows, "no visualization_vividness_rated row found"
    assert '"rating": 4' in rows[-1]["metadata"] or '"rating":4' in rows[-1]["metadata"]


def test_artwork_fields_are_gone_from_the_api(client, auth):
    """The reveal was removed deliberately - the reader payload must not carry
    artwork fields any more."""
    headers, _ = auth
    micro = client.get("/books/2/reader", headers=headers).json()["micro_session"]
    for field in ("visualization_image", "visualization_alt", "visualization_attribution"):
        assert field not in micro, f"{field} still exposed by the reader endpoint"
    # the prompt itself stays
    assert "has_visualization_prompt" in micro


def test_artwork_columns_are_gone_from_the_model():
    from app.models import MicroSession

    columns = {c.name for c in MicroSession.__table__.columns}
    assert "has_visualization_prompt" in columns
    assert not {"visualization_image", "visualization_alt", "visualization_attribution"} & columns


def test_book_payload_exposes_a_theme(client, auth):
    headers, _ = auth
    books = client.get("/books", headers=headers).json()
    assert books, "no books seeded"
    for book in books:
        assert book["theme"], f"{book['title']} has no theme"
