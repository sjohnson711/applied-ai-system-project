import sqlite3
import pytest
from datetime import datetime, date, timedelta

import pawpal.services.database as db_module
from pawpal.services.database import init_db, create_user, get_user, save_owner, load_owner
from pawpal.services.auth import _hash
from pawpal.services.email_service import _build_html, send_schedule_email
from pawpal.services.google_calendar import check_task_conflict, _parse_dt
from pawpal.models import Owner, Pet, Task


# ─── Shared fixture: isolated SQLite database per test ───────────────────────

@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    """Point the database module at a fresh temp file for each test."""
    db_file = str(tmp_path / "test_pawpal.db")
    monkeypatch.setattr(db_module, "_DB", db_file)
    init_db()
    return db_file


@pytest.fixture
def sample_schedule():
    """A minimal (pet, task, reason) schedule list for email tests."""
    pet = Pet(name="Buddy", species="Dog")
    task = Task(
        description="Morning walk",
        time=datetime(2026, 4, 1, 8, 0),
        frequency="daily",
        duration=30,
        priority="high",
    )
    return [(pet, task, "Selected – high priority · 30 min")]


# ─── pawpal/services/database.py :: init_db() ────────────────────────────────

# Tests that init_db() creates all four required tables
def test_init_db_creates_all_tables(tmp_db):
    con = sqlite3.connect(tmp_db)
    tables = {r[0] for r in con.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()}
    con.close()
    assert {"users", "owner_prefs", "pets", "tasks"}.issubset(tables)


# ─── pawpal/services/database.py :: create_user() ────────────────────────────

# Tests that create_user() returns True when a new email is registered
def test_create_user_returns_true_on_success(tmp_db):
    assert create_user("alice@example.com", "Alice", "hash123") is True


# Tests that create_user() returns False when the same email is registered twice
def test_create_user_returns_false_on_duplicate_email(tmp_db):
    create_user("bob@example.com", "Bob", "hash123")
    assert create_user("bob@example.com", "Bob", "hash123") is False


# ─── pawpal/services/database.py :: get_user() ───────────────────────────────

# Tests that get_user() returns a dict with the correct fields after registration
def test_get_user_returns_correct_dict(tmp_db):
    create_user("carol@example.com", "Carol", "secrethash")
    user = get_user("carol@example.com")
    assert user is not None
    assert user["email"] == "carol@example.com"
    assert user["name"] == "Carol"
    assert user["password_hash"] == "secrethash"


# Tests that get_user() returns None for an email that was never registered
def test_get_user_returns_none_for_unknown_email(tmp_db):
    assert get_user("nobody@example.com") is None


# ─── pawpal/services/database.py :: save_owner() / load_owner() ──────────────

# Tests that save_owner() persists and load_owner() reconstructs the full
# Owner → Pet → Task object graph with all field values intact
def test_save_and_load_owner_round_trip(tmp_db):
    create_user("dave@example.com", "Dave", "hash")
    owner = Owner(name="Dave", preferences={"max_tasks_per_day": 3, "available_minutes": 60})
    pet = Pet(name="Rex", species="Dog", breed="Labrador", age=3)
    task = Task(
        description="Morning walk",
        time=datetime(2026, 4, 1, 8, 0),
        frequency="daily",
        duration=30,
        priority="high",
    )
    pet.add_task(task)
    owner.add_pet(pet)

    save_owner(owner, "dave@example.com")
    loaded = load_owner("dave@example.com")

    assert loaded is not None
    assert loaded.name == "Dave"
    assert loaded.preferences["max_tasks_per_day"] == 3
    assert loaded.preferences["available_minutes"] == 60
    assert len(loaded.pets) == 1
    assert loaded.pets[0].name == "Rex"
    assert loaded.pets[0].breed == "Labrador"
    assert len(loaded.pets[0].tasks) == 1
    assert loaded.pets[0].tasks[0].description == "Morning walk"
    assert loaded.pets[0].tasks[0].duration == 30
    assert loaded.pets[0].tasks[0].priority == "high"
    assert loaded.pets[0].tasks[0].frequency == "daily"


# Tests that calling save_owner() twice updates existing records instead of
# inserting duplicates (upsert behaviour)
def test_save_owner_upsert_does_not_duplicate(tmp_db):
    create_user("eve@example.com", "Eve", "hash")
    owner = Owner(name="Eve")
    pet = Pet(name="Luna", species="Cat")
    owner.add_pet(pet)

    save_owner(owner, "eve@example.com")
    save_owner(owner, "eve@example.com")

    loaded = load_owner("eve@example.com")
    assert len(loaded.pets) == 1


# Tests that load_owner() returns None when the email is not in the database
def test_load_owner_returns_none_for_unknown_email(tmp_db):
    assert load_owner("ghost@example.com") is None


# ─── pawpal/services/auth.py :: _hash() ──────────────────────────────────────

# Tests that hashing the same password twice produces the same output (deterministic)
def test_hash_is_deterministic():
    assert _hash("my_password") == _hash("my_password")


# Tests that two different passwords produce different hashes
def test_hash_different_passwords_produce_different_hashes():
    assert _hash("password_a") != _hash("password_b")


# Tests that _hash() returns a lowercase hex string (PBKDF2 output format)
def test_hash_returns_hex_string():
    result = _hash("test_password")
    assert isinstance(result, str)
    assert all(c in "0123456789abcdef" for c in result)


# ─── pawpal/services/email_service.py :: _build_html() ───────────────────────

# Tests that _build_html() includes the owner's name in the rendered HTML
def test_build_html_contains_owner_name(sample_schedule):
    html = _build_html("Alice", sample_schedule, date(2026, 4, 1))
    assert "Alice" in html


# Tests that _build_html() includes the task description in the rendered HTML
def test_build_html_contains_task_description(sample_schedule):
    html = _build_html("Alice", sample_schedule, date(2026, 4, 1))
    assert "Morning walk" in html


# Tests that _build_html() uses the red colour code for high-priority tasks
def test_build_html_high_priority_uses_red_colour(sample_schedule):
    html = _build_html("Alice", sample_schedule, date(2026, 4, 1))
    assert "#e74c3c" in html


# Tests that _build_html() uses the green colour code for low-priority tasks
def test_build_html_low_priority_uses_green_colour():
    pet = Pet(name="Mittens", species="Cat")
    task = Task(description="Grooming", frequency="weekly", duration=20, priority="low")
    schedule = [(pet, task, "Selected – low priority")]
    html = _build_html("Bob", schedule, date(2026, 4, 1))
    assert "#27ae60" in html


# ─── pawpal/services/email_service.py :: send_schedule_email() ───────────────

# Tests that send_schedule_email() returns (False, …) when no API key is set
def test_send_schedule_email_fails_without_api_key(sample_schedule, monkeypatch):
    monkeypatch.delenv("RESEND_API_KEY", raising=False)
    ok, msg = send_schedule_email(
        "user@example.com", "Alice", sample_schedule, date(2026, 4, 2)
    )
    assert ok is False
    # Fails either because the package is absent or the key is missing
    assert "resend" in msg.lower() or "RESEND_API_KEY" in msg


# ─── pawpal/services/google_calendar.py :: check_task_conflict() ─────────────

# Tests that check_task_conflict() flags an event that overlaps the task window
def test_check_task_conflict_detects_overlap():
    task_time = datetime(2026, 4, 1, 10, 0)
    events = [{
        "summary": "Team meeting",
        "start_dt": datetime(2026, 4, 1, 9, 30),
        "end_dt": datetime(2026, 4, 1, 10, 30),
    }]
    conflicts = check_task_conflict(task_time, 30, events)
    assert "Team meeting" in conflicts


# Tests that check_task_conflict() returns an empty list when no overlap exists
def test_check_task_conflict_no_overlap():
    task_time = datetime(2026, 4, 1, 14, 0)
    events = [{
        "summary": "Lunch",
        "start_dt": datetime(2026, 4, 1, 12, 0),
        "end_dt": datetime(2026, 4, 1, 13, 0),
    }]
    conflicts = check_task_conflict(task_time, 30, events)
    assert conflicts == []


# Tests that check_task_conflict() returns [] when task_time is None
def test_check_task_conflict_no_task_time_returns_empty():
    events = [{
        "summary": "Something",
        "start_dt": datetime(2026, 4, 1, 10, 0),
        "end_dt": datetime(2026, 4, 1, 11, 0),
    }]
    assert check_task_conflict(None, 30, events) == []


# Tests that an event immediately adjacent (end == task start) is not a conflict
def test_check_task_conflict_adjacent_event_is_not_a_conflict():
    task_time = datetime(2026, 4, 1, 11, 0)
    events = [{
        "summary": "Morning standup",
        "start_dt": datetime(2026, 4, 1, 10, 0),
        "end_dt": datetime(2026, 4, 1, 11, 0),
    }]
    assert check_task_conflict(task_time, 30, events) == []


# ─── pawpal/services/google_calendar.py :: _parse_dt() ───────────────────────

# Tests that _parse_dt() correctly parses a UTC ISO-8601 string
def test_parse_dt_handles_utc_iso_string():
    dt = _parse_dt("2026-04-01T10:00:00Z")
    assert dt is not None
    assert dt.year == 2026
    assert dt.month == 4
    assert dt.hour == 10


# Tests that _parse_dt() returns None for an empty string
def test_parse_dt_returns_none_for_empty_string():
    assert _parse_dt("") is None


# Tests that _parse_dt() returns None when passed None
def test_parse_dt_returns_none_for_none():
    assert _parse_dt(None) is None
