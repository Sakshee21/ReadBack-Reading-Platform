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

# Event types introduced by the UI polish layer.
NEW_EVENT_TYPES = ["celebration_shown", "ambient_sound_on", "ambient_sound_off"]
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
    ]
    resp = client.post("/events", json=payload, headers=headers)
    assert resp.status_code == 201
    assert resp.json() == {"logged": 3}


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


def test_book_payload_exposes_a_theme(client, auth):
    headers, _ = auth
    books = client.get("/books", headers=headers).json()
    assert books, "no books seeded"
    for book in books:
        assert book["theme"], f"{book['title']} has no theme"
