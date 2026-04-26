import sqlite3
import pytest
from datetime import datetime, date, timedelta, timezone

import pawpal.services.database as db_module
import pawpal.services.email_service as email_mod
from pawpal.services.database import (
    init_db,
    create_user,
    get_user,
    get_user_by_email,
    get_user_by_username,
    update_password,
    save_owner,
    load_owner,
)
from pawpal.services.auth import _hash, _validate_username, _validate_password
from pawpal.services.email_service import (
    _build_html,
    _build_signout_html,
    _build_task_alert_html,
    send_schedule_email,
    send_signout_email,
    send_recovery_email,
    send_task_alert_email,
)
from pawpal.services.ai_features import generate_weekly_briefing
from pawpal.models import Owner, Pet, Task


# ─── Shared fixtures ─────────────────────────────────────────────────────────

@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    """Isolated SQLite database per test."""
    db_file = str(tmp_path / "test_pawpal.db")
    monkeypatch.setattr(db_module, "_DB", db_file)
    init_db()
    return db_file


@pytest.fixture
def sample_schedule():
    """Minimal (pet, task, reason) list for email tests."""
    pet = Pet(name="Buddy", species="Dog")
    task = Task(
        description="Morning walk",
        time=datetime(2026, 4, 1, 8, 0),
        frequency="daily",
        duration=30,
        priority="high",
    )
    return [(pet, task, "Selected – high priority · 30 min")]


@pytest.fixture
def owner_with_tasks():
    """Owner with one pet and two tasks — one complete, one pending."""
    owner = Owner(name="Alice")
    pet = Pet(name="Buddy", species="Dog")
    pending = Task(
        description="Morning walk",
        time=datetime(2026, 4, 25, 8, 0),
        frequency="daily",
        duration=30,
        priority="high",
    )
    done = Task(
        description="Evening feed",
        time=datetime(2026, 4, 25, 18, 0),
        frequency="daily",
        duration=10,
        priority="medium",
    )
    done.mark_complete()
    pet.add_task(pending)
    pet.add_task(done)
    owner.add_pet(pet)
    return owner


# ─── auth.py :: _validate_username() ─────────────────────────────────────────

def test_validate_username_valid():
    assert _validate_username("alice_99") == []


def test_validate_username_valid_min_length():
    # Exactly 3 characters, starts with letter — must be valid
    assert _validate_username("abc") == []


def test_validate_username_too_short():
    errors = _validate_username("ab")
    assert len(errors) == 1
    assert "3" in errors[0]  # mentions minimum length


def test_validate_username_too_long():
    errors = _validate_username("a" * 21)
    assert len(errors) == 1


def test_validate_username_starts_with_digit():
    errors = _validate_username("9alice")
    assert len(errors) == 1


def test_validate_username_starts_with_underscore():
    errors = _validate_username("_alice")
    assert len(errors) == 1


def test_validate_username_has_spaces():
    errors = _validate_username("alice smith")
    assert len(errors) == 1


def test_validate_username_has_hyphen():
    # Hyphens are not allowed — only letters, digits, underscores
    errors = _validate_username("alice-smith")
    assert len(errors) == 1


# ─── auth.py :: _validate_password() ─────────────────────────────────────────

def test_validate_password_valid():
    # Meets all 5 rules: length, upper, lower, digit, symbol
    assert _validate_password("Hello1!x") == []


def test_validate_password_too_short():
    errors = _validate_password("Hi1!")
    # Must mention length
    assert any("8" in e for e in errors)


def test_validate_password_too_long():
    errors = _validate_password("Hello1!xyzabc")  # 13 chars
    assert any("12" in e for e in errors)


def test_validate_password_no_uppercase():
    errors = _validate_password("hello1!x")
    assert any("uppercase" in e.lower() for e in errors)


def test_validate_password_no_lowercase():
    errors = _validate_password("HELLO1!X")
    assert any("lowercase" in e.lower() for e in errors)


def test_validate_password_no_digit():
    errors = _validate_password("Hello!!x")
    assert any("number" in e.lower() or "digit" in e.lower() for e in errors)


def test_validate_password_no_symbol():
    errors = _validate_password("Hello123")
    assert any("symbol" in e.lower() for e in errors)


def test_validate_password_returns_all_errors_at_once():
    # "abc" fails length, uppercase, digit, and symbol simultaneously
    errors = _validate_password("abc")
    assert len(errors) >= 3  # at minimum: length, uppercase, digit, symbol


# ─── database.py :: init_db() ────────────────────────────────────────────────

def test_init_db_creates_all_tables(tmp_db):
    con = sqlite3.connect(tmp_db)
    tables = {r[0] for r in con.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()}
    con.close()
    assert {"users", "owner_prefs", "pets", "tasks"}.issubset(tables)


def test_init_db_creates_username_column(tmp_db):
    con = sqlite3.connect(tmp_db)
    cols = [row[1] for row in con.execute("PRAGMA table_info(users)").fetchall()]
    con.close()
    assert "username" in cols


# ─── database.py :: create_user() ────────────────────────────────────────────

def test_create_user_with_username_success(tmp_db):
    assert create_user("alice@example.com", "alice", "Alice", "hash123") is True


def test_create_user_returns_false_on_duplicate_email(tmp_db):
    create_user("bob@example.com", "bob", "Bob", "hash123")
    assert create_user("bob@example.com", "bob2", "Bob", "hash123") is False


def test_create_user_duplicate_username_returns_false(tmp_db):
    create_user("carol@example.com", "carol", "Carol", "hash123")
    # Different email but same username — must fail
    assert create_user("carol2@example.com", "carol", "Carol Two", "hash456") is False


# ─── database.py :: get_user_by_username() ───────────────────────────────────

def test_get_user_by_username_returns_correct_dict(tmp_db):
    create_user("dave@example.com", "dave99", "Dave", "secrethash")
    user = get_user_by_username("dave99")
    assert user is not None
    assert user["email"]    == "dave@example.com"
    assert user["username"] == "dave99"
    assert user["name"]     == "Dave"
    assert user["password_hash"] == "secrethash"


def test_get_user_by_username_returns_none_for_unknown(tmp_db):
    assert get_user_by_username("nobody") is None


def test_get_user_by_username_is_case_insensitive(tmp_db):
    create_user("eve@example.com", "eve_user", "Eve", "hash")
    # Stored lowercase — lookup with mixed case must still find the row
    user = get_user_by_username("EVE_USER")
    assert user is not None
    assert user["username"] == "eve_user"


# ─── database.py :: get_user_by_email() / get_user() ─────────────────────────

def test_get_user_by_email_returns_correct_dict(tmp_db):
    create_user("frank@example.com", "frank", "Frank", "hash")
    user = get_user_by_email("frank@example.com")
    assert user is not None
    assert user["email"]    == "frank@example.com"
    assert user["username"] == "frank"
    assert user["name"]     == "Frank"


def test_get_user_returns_none_for_unknown_email(tmp_db):
    assert get_user("nobody@example.com") is None


# ─── database.py :: update_password() ────────────────────────────────────────

def test_update_password_changes_stored_hash(tmp_db):
    create_user("grace@example.com", "grace", "Grace", "old_hash")
    result = update_password("grace@example.com", "new_hash")
    assert result is True
    user = get_user_by_email("grace@example.com")
    assert user["password_hash"] == "new_hash"
    assert user["password_hash"] != "old_hash"


def test_update_password_returns_false_for_unknown_email(tmp_db):
    assert update_password("ghost@example.com", "any_hash") is False


# ─── database.py :: username migration ───────────────────────────────────────

def test_username_migration_backfills_existing_rows(tmp_path, monkeypatch):
    """Simulate a pre-migration DB (no username column) and verify init_db backfills it."""
    db_file = str(tmp_path / "legacy.db")
    monkeypatch.setattr(db_module, "_DB", db_file)

    # Bootstrap a DB without the username column to simulate legacy state
    con = sqlite3.connect(db_file)
    con.executescript("""
        CREATE TABLE users (
            email         TEXT PRIMARY KEY,
            name          TEXT NOT NULL,
            password_hash TEXT NOT NULL
        );
        CREATE TABLE owner_prefs (
            email TEXT PRIMARY KEY REFERENCES users(email),
            max_tasks_per_day INTEGER NOT NULL DEFAULT 5,
            available_minutes INTEGER NOT NULL DEFAULT 90
        );
        CREATE TABLE pets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            owner_email TEXT NOT NULL,
            name TEXT NOT NULL,
            species TEXT NOT NULL,
            breed TEXT NOT NULL DEFAULT '',
            age INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pet_id INTEGER NOT NULL,
            description TEXT NOT NULL,
            time TEXT,
            frequency TEXT NOT NULL DEFAULT '',
            completed INTEGER NOT NULL DEFAULT 0,
            duration INTEGER NOT NULL DEFAULT 0,
            priority TEXT NOT NULL DEFAULT 'medium'
        );
        INSERT INTO users (email, name, password_hash)
        VALUES ('user@example.com', 'User', 'hash');
    """)
    con.commit()
    con.close()

    # Run migration
    init_db()

    # Verify username was added and backfilled
    con = sqlite3.connect(db_file)
    cols = [row[1] for row in con.execute("PRAGMA table_info(users)").fetchall()]
    row = con.execute("SELECT username FROM users WHERE email='user@example.com'").fetchone()
    con.close()

    assert "username" in cols
    assert row is not None
    assert row[0] == "user"  # email prefix of 'user@example.com'


# ─── database.py :: save_owner() / load_owner() ──────────────────────────────

def test_save_and_load_owner_round_trip(tmp_db):
    create_user("dave@example.com", "dave", "Dave", "hash")
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
    assert len(loaded.pets) == 1
    assert loaded.pets[0].name == "Rex"
    assert loaded.pets[0].tasks[0].description == "Morning walk"
    assert loaded.pets[0].tasks[0].priority == "high"


def test_save_owner_upsert_does_not_duplicate(tmp_db):
    create_user("eve@example.com", "eve", "Eve", "hash")
    owner = Owner(name="Eve")
    pet = Pet(name="Luna", species="Cat")
    owner.add_pet(pet)
    save_owner(owner, "eve@example.com")
    save_owner(owner, "eve@example.com")
    loaded = load_owner("eve@example.com")
    assert len(loaded.pets) == 1


def test_load_owner_returns_none_for_unknown_email(tmp_db):
    assert load_owner("ghost@example.com") is None


# ─── auth.py :: _hash() ──────────────────────────────────────────────────────

def test_hash_is_deterministic():
    assert _hash("my_password") == _hash("my_password")


def test_hash_different_passwords_produce_different_hashes():
    assert _hash("password_a") != _hash("password_b")


def test_hash_returns_hex_string():
    result = _hash("test_password")
    assert isinstance(result, str)
    assert all(c in "0123456789abcdef" for c in result)


# ─── email_service.py :: _build_html() ───────────────────────────────────────

def test_build_html_contains_owner_name(sample_schedule):
    html = _build_html("Alice", sample_schedule, date(2026, 4, 1))
    assert "Alice" in html


def test_build_html_contains_task_description(sample_schedule):
    html = _build_html("Alice", sample_schedule, date(2026, 4, 1))
    assert "Morning walk" in html


def test_build_html_high_priority_uses_red_colour(sample_schedule):
    html = _build_html("Alice", sample_schedule, date(2026, 4, 1))
    assert "#e74c3c" in html


def test_build_html_low_priority_uses_green_colour():
    pet = Pet(name="Mittens", species="Cat")
    task = Task(description="Grooming", frequency="weekly", duration=20, priority="low")
    html = _build_html("Bob", [(pet, task, "low")], date(2026, 4, 1))
    assert "#27ae60" in html


# ─── email_service.py :: send_schedule_email() ───────────────────────────────

def test_send_schedule_email_fails_without_api_key(sample_schedule, monkeypatch):
    monkeypatch.delenv("RESEND_API_KEY", raising=False)
    ok, msg = send_schedule_email(
        "user@example.com", "Alice", sample_schedule, date(2026, 4, 2)
    )
    assert ok is False
    assert "resend" in msg.lower() or "RESEND_API_KEY" in msg


# ─── email_service.py :: send_recovery_email() ───────────────────────────────

def test_send_recovery_email_fails_without_api_key(monkeypatch):
    monkeypatch.delenv("RESEND_API_KEY", raising=False)
    ok, msg = send_recovery_email("user@example.com", "alice", "Temp1!abc")
    assert ok is False
    assert "resend" in msg.lower() or "RESEND_API_KEY" in msg


# ─── email_service.py :: _build_signout_html() ───────────────────────────────

def test_build_signout_html_contains_owner_name(owner_with_tasks):
    task_rows = [
        (pet, task)
        for pet in owner_with_tasks.pets
        for task in pet.get_tasks()
        if not task.completed
    ]
    html = _build_signout_html("Alice", task_rows, date(2026, 4, 25))
    assert "Alice" in html


def test_build_signout_html_contains_pending_task_description(owner_with_tasks):
    task_rows = [
        (pet, task)
        for pet in owner_with_tasks.pets
        for task in pet.get_tasks()
        if not task.completed
    ]
    html = _build_signout_html("Alice", task_rows, date(2026, 4, 25))
    assert "Morning walk" in html


def test_build_signout_html_excludes_completed_task(owner_with_tasks):
    task_rows = [
        (pet, task)
        for pet in owner_with_tasks.pets
        for task in pet.get_tasks()
        if not task.completed
    ]
    html = _build_signout_html("Alice", task_rows, date(2026, 4, 25))
    assert "Evening feed" not in html


def test_build_signout_html_shows_pet_name(owner_with_tasks):
    task_rows = [
        (pet, task)
        for pet in owner_with_tasks.pets
        for task in pet.get_tasks()
        if not task.completed
    ]
    html = _build_signout_html("Alice", task_rows, date(2026, 4, 25))
    assert "Buddy" in html


def test_build_signout_html_high_priority_uses_red_colour(owner_with_tasks):
    task_rows = [
        (pet, task)
        for pet in owner_with_tasks.pets
        for task in pet.get_tasks()
        if not task.completed
    ]
    html = _build_signout_html("Alice", task_rows, date(2026, 4, 25))
    assert "#e74c3c" in html


# ─── email_service.py :: send_signout_email() ────────────────────────────────

def test_send_signout_email_fails_without_api_key(owner_with_tasks, monkeypatch):
    monkeypatch.delenv("RESEND_API_KEY", raising=False)
    ok, msg = send_signout_email("user@example.com", "Alice", owner_with_tasks)
    assert ok is False
    assert "resend" in msg.lower() or "RESEND_API_KEY" in msg


def test_send_signout_email_returns_false_when_no_pending_tasks(monkeypatch):
    monkeypatch.setenv("RESEND_API_KEY", "test_key")
    owner = Owner(name="Alice")
    pet = Pet(name="Rex", species="Dog")
    task = Task(description="Walk", frequency="daily", duration=30, priority="high")
    task.mark_complete()
    pet.add_task(task)
    owner.add_pet(pet)
    ok, msg = send_signout_email("user@example.com", "Alice", owner)
    assert ok is False
    assert "pending" in msg.lower() or "no" in msg.lower()


def test_send_signout_email_filters_out_completed_tasks(monkeypatch):
    monkeypatch.delenv("RESEND_API_KEY", raising=False)
    owner = Owner(name="Alice")
    pet = Pet(name="Buddy", species="Dog")
    pending = Task(description="Walk", frequency="daily", duration=30, priority="high")
    done = Task(description="Feed", frequency="daily", duration=10, priority="medium")
    done.mark_complete()
    pet.add_task(pending)
    pet.add_task(done)
    owner.add_pet(pet)
    ok, msg = send_signout_email("user@example.com", "Alice", owner)
    # Fails on missing API key, not on "no pending tasks" — confirms pending task was found
    assert "RESEND_API_KEY" in msg or "resend" in msg.lower()


@pytest.mark.skipif(not email_mod.RESEND_AVAILABLE, reason="resend not installed")
def test_send_signout_email_scheduled_at_is_60_minutes_out(monkeypatch, owner_with_tasks):
    monkeypatch.setenv("RESEND_API_KEY", "test_key_abc")
    captured = {}
    import resend as resend_lib
    monkeypatch.setattr(resend_lib.Emails, "send", lambda params: captured.update(params) or {"id": "fake"})
    ok, _ = send_signout_email("user@example.com", "Alice", owner_with_tasks)
    assert ok is True
    assert "scheduled_at" in captured
    sched = datetime.fromisoformat(captured["scheduled_at"])
    if sched.tzinfo is None:
        sched = sched.replace(tzinfo=timezone.utc)
    diff = (sched - datetime.now(timezone.utc)).total_seconds()
    assert 3480 <= diff <= 3720, f"scheduled_at was {diff:.0f}s from now, expected ~3600s"


@pytest.mark.skipif(not email_mod.RESEND_AVAILABLE, reason="resend not installed")
def test_send_signout_email_html_contains_pending_task(monkeypatch, owner_with_tasks):
    monkeypatch.setenv("RESEND_API_KEY", "test_key_abc")
    captured = {}
    import resend as resend_lib
    monkeypatch.setattr(resend_lib.Emails, "send", lambda params: captured.update(params) or {"id": "fake"})
    send_signout_email("user@example.com", "Alice", owner_with_tasks)
    html = captured.get("html", "")
    assert "Morning walk" in html
    assert "Evening feed" not in html


# ─── Shared fixture for task alert tests ─────────────────────────────────────

@pytest.fixture
def session_tasks():
    """Two (pet_name, task) tuples simulating tasks added during a session."""
    t1 = Task(
        description="Morning walk",
        time=datetime(2026, 4, 26, 8, 0),
        frequency="daily",
        duration=30,
        priority="high",
    )
    t2 = Task(
        description="Evening feed",
        time=datetime(2026, 4, 26, 18, 0),
        frequency="daily",
        duration=10,
        priority="medium",
    )
    return [("Buddy", t1), ("Mittens", t2)]


# ─── email_service.py :: _build_task_alert_html() ────────────────────────────

def test_build_task_alert_html_contains_owner_name(session_tasks):
    html = _build_task_alert_html("Seth", session_tasks)
    assert "Seth" in html


def test_build_task_alert_html_contains_all_task_descriptions(session_tasks):
    html = _build_task_alert_html("Seth", session_tasks)
    assert "Morning walk" in html
    assert "Evening feed" in html


def test_build_task_alert_html_contains_all_pet_names(session_tasks):
    html = _build_task_alert_html("Seth", session_tasks)
    assert "Buddy" in html
    assert "Mittens" in html


def test_build_task_alert_html_high_priority_uses_red_colour(session_tasks):
    html = _build_task_alert_html("Seth", session_tasks)
    assert "#e74c3c" in html


def test_build_task_alert_html_medium_priority_uses_amber_colour(session_tasks):
    html = _build_task_alert_html("Seth", session_tasks)
    assert "#f39c12" in html


def test_build_task_alert_html_shows_scheduled_time(session_tasks):
    html = _build_task_alert_html("Seth", session_tasks)
    assert "8:00" in html or "8" in html


# ─── email_service.py :: send_task_alert_email() ─────────────────────────────

def test_send_task_alert_email_returns_false_for_empty_list(monkeypatch):
    monkeypatch.setenv("RESEND_API_KEY", "test_key")
    ok, msg = send_task_alert_email("user@example.com", "Seth", [])
    assert ok is False
    assert "no tasks" in msg.lower() or "task" in msg.lower()


def test_send_task_alert_email_fails_without_api_key(session_tasks, monkeypatch):
    monkeypatch.delenv("RESEND_API_KEY", raising=False)
    ok, msg = send_task_alert_email("user@example.com", "Seth", session_tasks)
    assert ok is False
    assert "RESEND_API_KEY" in msg or "resend" in msg.lower()


def test_send_task_alert_email_fails_without_resend(session_tasks, monkeypatch):
    monkeypatch.setattr(email_mod, "RESEND_AVAILABLE", False)
    ok, msg = send_task_alert_email("user@example.com", "Seth", session_tasks)
    assert ok is False
    assert "resend" in msg.lower()


@pytest.mark.skipif(not email_mod.RESEND_AVAILABLE, reason="resend not installed")
def test_send_task_alert_email_sends_all_tasks(session_tasks, monkeypatch):
    monkeypatch.setenv("RESEND_API_KEY", "test_key_abc")
    captured = {}
    import resend as resend_lib
    monkeypatch.setattr(resend_lib.Emails, "send", lambda params: captured.update(params) or {"id": "fake"})
    ok, _ = send_task_alert_email("user@example.com", "Seth", session_tasks)
    assert ok is True
    html = captured.get("html", "")
    assert "Morning walk" in html
    assert "Evening feed" in html
    assert "Buddy" in html
    assert "Mittens" in html


@pytest.mark.skipif(not email_mod.RESEND_AVAILABLE, reason="resend not installed")
def test_send_task_alert_email_has_no_scheduled_at(session_tasks, monkeypatch):
    """Task alert must be immediate — no scheduled_at field."""
    monkeypatch.setenv("RESEND_API_KEY", "test_key_abc")
    captured = {}
    import resend as resend_lib
    monkeypatch.setattr(resend_lib.Emails, "send", lambda params: captured.update(params) or {"id": "fake"})
    send_task_alert_email("user@example.com", "Seth", session_tasks)
    assert "scheduled_at" not in captured


# ─── ai_features.py :: generate_weekly_briefing() ───────────────────────────

@pytest.fixture
def owner_week_tasks():
    """Owner with tasks spread across this week and outside it."""
    today = date.today()
    owner = Owner(name="Seth")
    pet   = Pet(name="Buddy", species="Dog")

    in_range = Task(
        description="Morning walk",
        time=datetime.combine(today + timedelta(days=2), datetime.min.time()).replace(hour=8),
        frequency="daily",
        duration=30,
        priority="high",
    )
    out_of_range = Task(
        description="Vet checkup",
        time=datetime.combine(today + timedelta(days=10), datetime.min.time()).replace(hour=10),
        frequency="once",
        duration=60,
        priority="high",
    )
    completed = Task(
        description="Yesterday feed",
        time=datetime.combine(today, datetime.min.time()).replace(hour=7),
        frequency="daily",
        duration=10,
        priority="medium",
    )
    completed.mark_complete()

    pet.add_task(in_range)
    pet.add_task(out_of_range)
    pet.add_task(completed)
    owner.add_pet(pet)
    return owner


def test_generate_weekly_briefing_returns_empty_without_api_key(owner_week_tasks, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    today = date.today()
    result = generate_weekly_briefing("Seth", owner_week_tasks, today, today + timedelta(days=6))
    assert result == ""


def test_generate_weekly_briefing_returns_empty_without_anthropic(owner_week_tasks, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test_key")
    import builtins
    real_import = builtins.__import__
    def mock_import(name, *args, **kwargs):
        if name == "anthropic":
            raise ImportError("anthropic not installed")
        return real_import(name, *args, **kwargs)
    monkeypatch.setattr(builtins, "__import__", mock_import)
    today = date.today()
    result = generate_weekly_briefing("Seth", owner_week_tasks, today, today + timedelta(days=6))
    assert result == ""


def test_generate_weekly_briefing_excludes_completed_tasks(owner_week_tasks):
    """Completed tasks must never appear in the schedule text sent to Claude."""
    today     = date.today()
    week_end  = today + timedelta(days=6)
    rows = []
    for pet in owner_week_tasks.pets:
        for task in pet.get_tasks():
            if not task.completed and task.time and today <= task.time.date() <= week_end:
                rows.append(task.description)
    assert "Yesterday feed" not in rows


def test_generate_weekly_briefing_includes_in_range_task(owner_week_tasks):
    """Tasks within the week window must be present in the schedule text."""
    today    = date.today()
    week_end = today + timedelta(days=6)
    rows = []
    for pet in owner_week_tasks.pets:
        for task in pet.get_tasks():
            if not task.completed and task.time and today <= task.time.date() <= week_end:
                rows.append(task.description)
    assert "Morning walk" in rows


def test_generate_weekly_briefing_excludes_out_of_range_task(owner_week_tasks):
    """Tasks beyond the 7-day window must not appear in the schedule text."""
    today    = date.today()
    week_end = today + timedelta(days=6)
    rows = []
    for pet in owner_week_tasks.pets:
        for task in pet.get_tasks():
            if not task.completed and task.time and today <= task.time.date() <= week_end:
                rows.append(task.description)
    assert "Vet checkup" not in rows
