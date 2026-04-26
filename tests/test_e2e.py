"""End-to-end tests: full user journeys spanning auth → DB → models → schedule → email."""
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
from pawpal.services.email_service import _build_html, send_schedule_email, send_signout_email
from pawpal.models import Owner, Pet, Task, Scheduler


@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    db_file = str(tmp_path / "e2e_test.db")
    monkeypatch.setattr(db_module, "_DB", db_file)
    init_db()
    return db_file


# ─── Journey 1: Registration → pet/task setup → schedule generation → DB round-trip ───

def test_full_user_onboarding_and_schedule_generation(tmp_db):
    ok = create_user("jane@example.com", "jane99", "Jane", _hash("Hello1!x"))
    assert ok is True
    user = get_user("jane@example.com")
    assert user["name"] == "Jane"
    assert user["username"] == "jane99"

    owner = Owner(name="Jane", preferences={"max_tasks_per_day": 3, "available_minutes": 60})
    dog = Pet(name="Buddy", species="Dog", breed="Labrador", age=2)
    cat = Pet(name="Whiskers", species="Cat", age=4)
    owner.add_pet(dog)
    owner.add_pet(cat)

    dog.add_task(Task(description="Morning walk", time=datetime(2026, 4, 1, 8, 0),
                      frequency="daily", duration=30, priority="high"))
    dog.add_task(Task(description="Evening feed", time=datetime(2026, 4, 1, 18, 0),
                      frequency="daily", duration=10, priority="medium"))
    cat.add_task(Task(description="Medication", time=datetime(2026, 4, 1, 9, 0),
                      frequency="daily", duration=5, priority="high"))
    cat.add_task(Task(description="Grooming", frequency="weekly", duration=25, priority="low"))

    scheduler = Scheduler(owner)
    schedule = scheduler.generate_schedule()
    assert len(schedule) == 3
    assert schedule[0][1].priority == "high"

    save_owner(owner, "jane@example.com")
    loaded = load_owner("jane@example.com")

    assert loaded.name == "Jane"
    assert len(loaded.pets) == 2
    assert {p.name for p in loaded.pets} == {"Buddy", "Whiskers"}
    all_tasks = loaded.get_all_tasks()
    assert len(all_tasks) == 4
    assert {t.description for t in all_tasks} >= {"Morning walk", "Medication"}

    assert len(Scheduler(loaded).generate_schedule()) == 3


# ─── Journey 2: Task completion → auto-reschedule → DB persistence ─────────────────

def test_complete_recurring_task_and_persist(tmp_db):
    create_user("tom@example.com", "tom_user", "Tom", _hash("Hello1!x"))
    owner = Owner(name="Tom")
    pet = Pet(name="Rex", species="Dog")
    owner.add_pet(pet)

    task_time = datetime(2026, 4, 1, 9, 0)
    task = Task(description="Walk", time=task_time, frequency="daily", duration=20, priority="high")
    pet.add_task(task)

    Scheduler(owner).complete_task(pet, task)

    assert task.completed is True
    assert len(pet.tasks) == 2
    follow_up = pet.tasks[1]
    assert follow_up.time == task_time + timedelta(days=1)
    assert follow_up.completed is False

    save_owner(owner, "tom@example.com")
    loaded = load_owner("tom@example.com")

    loaded_tasks = loaded.pets[0].tasks
    assert len(loaded_tasks) == 2
    assert len([t for t in loaded_tasks if t.completed]) == 1
    assert len([t for t in loaded_tasks if not t.completed]) == 1
    assert next(t for t in loaded_tasks if not t.completed).time == task_time + timedelta(days=1)


# ─── Journey 3: Conflict detection → schedule generation pipeline ──────────────────

def test_conflict_detection_then_schedule_generation(tmp_db):
    create_user("sara@example.com", "sara_s", "Sara", _hash("Hello1!x"))
    owner = Owner(name="Sara", preferences={"max_tasks_per_day": 5, "available_minutes": 120})
    pet = Pet(name="Milo", species="Dog")
    owner.add_pet(pet)

    conflict_time = datetime(2026, 4, 1, 10, 0)
    t1 = Task(description="Bath",       time=conflict_time,                     frequency="weekly",  duration=30, priority="medium")
    t2 = Task(description="Trim nails", time=conflict_time,                     frequency="monthly", duration=20, priority="low")
    t3 = Task(description="Feed",       time=datetime(2026, 4, 1, 8, 0),        frequency="daily",   duration=10, priority="high")
    for t in [t1, t2, t3]:
        pet.add_task(t)

    scheduler = Scheduler(owner)
    warnings = scheduler.detect_conflicts()
    assert len(warnings) == 1
    assert "Bath" in warnings[0] or "Trim nails" in warnings[0]

    schedule = scheduler.generate_schedule()
    assert len(schedule) == 3
    assert "Feed" in [t.description for _, t, _ in schedule]

    save_owner(owner, "sara@example.com")
    assert len(load_owner("sara@example.com").get_all_tasks()) == 3


# ─── Journey 4: Schedule → email HTML generation ───────────────────────────────────

def test_schedule_to_email_html_pipeline(tmp_db):
    create_user("alex@example.com", "alex_a", "Alex", _hash("Hello1!x"))
    owner = Owner(name="Alex", preferences={"max_tasks_per_day": 5, "available_minutes": 120})
    pet = Pet(name="Luna", species="Cat")
    owner.add_pet(pet)
    pet.add_task(Task(description="Medication", time=datetime(2026, 4, 2, 8, 0),
                      frequency="daily", duration=5, priority="high"))
    pet.add_task(Task(description="Playtime",   time=datetime(2026, 4, 2, 17, 0),
                      frequency="daily", duration=20, priority="low"))

    schedule = Scheduler(owner).generate_schedule()
    assert len(schedule) == 2

    html = _build_html("Alex", schedule, date(2026, 4, 2))
    assert "Alex" in html
    assert "Medication" in html
    assert "Playtime" in html
    assert "#e74c3c" in html
    assert "#27ae60" in html

    ok, msg = send_schedule_email("alex@example.com", "Alex", schedule, date(2026, 4, 2))
    assert ok is False
    assert isinstance(msg, str)


# ─── Journey 5: Sign-out email — pending vs completed task filtering ────────────────

def test_signout_email_only_includes_pending_tasks(monkeypatch):
    monkeypatch.delenv("RESEND_API_KEY", raising=False)

    owner = Owner(name="Kim")
    pet = Pet(name="Noodle", species="Dog")
    pending = Task(description="Walk", time=datetime(2026, 4, 3, 10, 0),
                   frequency="daily", duration=30, priority="high")
    done = Task(description="Bath", time=datetime(2026, 4, 3, 14, 0),
                frequency="weekly", duration=45, priority="low")
    done.mark_complete()
    pet.add_task(pending)
    pet.add_task(done)
    owner.add_pet(pet)

    # Fails on missing key, NOT on "no pending tasks" — proves the pending task was found
    ok, msg = send_signout_email("kim@example.com", "Kim", owner)
    assert ok is False
    assert "RESEND_API_KEY" in msg or "resend" in msg.lower()


def test_signout_email_returns_false_when_all_tasks_completed(monkeypatch):
    monkeypatch.setenv("RESEND_API_KEY", "test_key")
    owner = Owner(name="Pat")
    pet = Pet(name="Coco", species="Cat")
    task = Task(description="Feed", frequency="daily", duration=10, priority="medium")
    task.mark_complete()
    pet.add_task(task)
    owner.add_pet(pet)
    ok, msg = send_signout_email("pat@example.com", "Pat", owner)
    assert ok is False
    assert "pending" in msg.lower() or "no" in msg.lower()


@pytest.mark.skipif(not email_mod.RESEND_AVAILABLE, reason="resend not installed")
def test_signout_email_e2e_with_db_round_trip(tmp_db, monkeypatch):
    create_user("robin@example.com", "robin_r", "Robin", _hash("Hello1!x"))
    owner = Owner(name="Robin")
    pet = Pet(name="Scout", species="Dog")
    walk = Task(description="Walk", time=datetime(2026, 4, 25, 8, 0),
                frequency="daily", duration=30, priority="high")
    feed = Task(description="Feed", time=datetime(2026, 4, 25, 18, 0),
                frequency="daily", duration=10, priority="medium")
    pet.add_task(walk)
    pet.add_task(feed)
    owner.add_pet(pet)

    Scheduler(owner).complete_task(pet, feed)

    save_owner(owner, "robin@example.com")
    loaded = load_owner("robin@example.com")

    pending = [t for t in loaded.get_all_tasks() if not t.completed]
    assert "Walk" in {t.description for t in pending}

    captured = {}
    import resend as resend_lib
    monkeypatch.setattr(resend_lib.Emails, "send", lambda params: captured.update(params) or {"id": "x"})
    monkeypatch.setenv("RESEND_API_KEY", "test_key")

    ok, _ = send_signout_email("robin@example.com", "Robin", loaded)
    assert ok is True
    assert "Walk" in captured.get("html", "")
    assert "scheduled_at" in captured


# ─── Journey 6: Multi-pet owner with preferences update → explain_plan text ────────

def test_multi_pet_explain_plan_reflects_preferences(tmp_db):
    create_user("pat@example.com", "pat_p", "Pat", _hash("Hello1!x"))
    owner = Owner(name="Pat", preferences={"max_tasks_per_day": 2, "available_minutes": 40})
    dog = Pet(name="Bruno", species="Dog")
    cat = Pet(name="Simba", species="Cat")
    owner.add_pet(dog)
    owner.add_pet(cat)
    dog.add_task(Task(description="Walk",     frequency="daily",  duration=30, priority="high"))
    dog.add_task(Task(description="Bath",     frequency="weekly", duration=45, priority="low"))
    cat.add_task(Task(description="Feed",     frequency="daily",  duration=5,  priority="high"))
    cat.add_task(Task(description="Brushing", frequency="weekly", duration=10, priority="medium"))

    scheduler = Scheduler(owner)
    plan_text = scheduler.explain_plan()

    assert isinstance(plan_text, str) and len(plan_text) > 0
    assert plan_text.count("\n  1.") == 1
    assert plan_text.count("\n  2.") == 1
    assert plan_text.count("\n  3.") == 0

    owner.set_preferences({"max_tasks_per_day": 4, "available_minutes": 120})
    assert scheduler.explain_plan().count("\n  3.") == 1


# ─── Journey 7: Duplicate registration is rejected ─────────────────────────────────

def test_duplicate_registration_rejected(tmp_db):
    assert create_user("dup@example.com", "dup_user", "First", _hash("Hello1!x")) is True
    assert create_user("dup@example.com", "dup_user2", "Second", _hash("Hello1!x")) is False
    user = get_user("dup@example.com")
    assert user["name"] == "First"


# ─── Journey 8: Username sign-in full flow ─────────────────────────────────────────

def test_username_signin_full_flow(tmp_db):
    """Register with a username, look up by username, verify password hash matches."""
    pw = "Hello1!x"
    ok = create_user("member@example.com", "member99", "Member", _hash(pw))
    assert ok is True

    # Sign-in path: look up by username, check hash
    user = get_user_by_username("member99")
    assert user is not None
    assert user["email"]    == "member@example.com"
    assert user["username"] == "member99"
    assert user["name"]     == "Member"
    # The stored hash must match the same password
    assert user["password_hash"] == _hash(pw)
    # A wrong password must not match
    assert user["password_hash"] != _hash("wrongpassword")


def test_username_lookup_after_db_round_trip(tmp_db):
    """Username is preserved through a full save_owner / load_owner cycle."""
    create_user("loop@example.com", "loopuser", "Loop", _hash("Hello1!x"))
    owner = Owner(name="Loop")
    pet = Pet(name="Paw", species="Dog")
    owner.add_pet(pet)
    save_owner(owner, "loop@example.com")

    # Username must still be retrievable after persistence round-trip
    user = get_user_by_username("loopuser")
    assert user is not None
    assert user["email"] == "loop@example.com"


# ─── Journey 9: Account recovery updates password ─────────────────────────────────

def test_account_recovery_updates_password(tmp_db):
    """update_password changes the stored hash; old hash no longer matches."""
    original_pw = "Hello1!x"
    new_pw      = "NewPass9!"
    create_user("recover@example.com", "recoverme", "Recover", _hash(original_pw))

    result = update_password("recover@example.com", _hash(new_pw))
    assert result is True

    user = get_user_by_email("recover@example.com")
    # New password matches
    assert user["password_hash"] == _hash(new_pw)
    # Old password no longer matches
    assert user["password_hash"] != _hash(original_pw)


def test_account_recovery_unknown_email_returns_false(tmp_db):
    assert update_password("nobody@example.com", _hash("Hello1!x")) is False


# ─── Journey 10: Validation guards the registration path ──────────────────────────

def test_registration_rejected_by_weak_password():
    """Weak passwords are caught before any DB write."""
    errors = _validate_password("password")  # no uppercase, no symbol
    assert len(errors) >= 2


def test_registration_rejected_by_invalid_username():
    """Usernames starting with a digit are rejected before any DB write."""
    errors = _validate_username("9badname")
    assert len(errors) == 1


def test_valid_credentials_pass_both_validators():
    assert _validate_username("gooduser") == []
    assert _validate_password("Hello1!x") == []
