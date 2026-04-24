"""End-to-end tests: full user journeys spanning auth → DB → models → schedule → email."""
import pytest
from datetime import datetime, date, timedelta

import pawpal.services.database as db_module
from pawpal.services.database import init_db, create_user, get_user, save_owner, load_owner
from pawpal.services.auth import _hash
from pawpal.services.email_service import _build_html, send_schedule_email
from pawpal.services.google_calendar import check_task_conflict
from pawpal.models import Owner, Pet, Task, Scheduler


@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    db_file = str(tmp_path / "e2e_test.db")
    monkeypatch.setattr(db_module, "_DB", db_file)
    init_db()
    return db_file


# ─── Journey 1: Registration → pet/task setup → schedule generation → DB round-trip ───

def test_full_user_onboarding_and_schedule_generation(tmp_db):
    # Register user
    ok = create_user("jane@example.com", "Jane", _hash("pass123"))
    assert ok is True
    user = get_user("jane@example.com")
    assert user["name"] == "Jane"

    # Build owner + pets + tasks
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

    # Generate schedule — should pick high/medium up to cap
    scheduler = Scheduler(owner)
    schedule = scheduler.generate_schedule()
    assert len(schedule) == 3  # capped at max_tasks_per_day
    priorities = [task.priority for _, task, _ in schedule]
    assert priorities[0] in ("high",)  # first selections are high priority

    # Persist and reload
    save_owner(owner, "jane@example.com")
    loaded = load_owner("jane@example.com")

    assert loaded.name == "Jane"
    assert len(loaded.pets) == 2
    pet_names = {p.name for p in loaded.pets}
    assert pet_names == {"Buddy", "Whiskers"}
    all_tasks = loaded.get_all_tasks()
    assert len(all_tasks) == 4
    descriptions = {t.description for t in all_tasks}
    assert "Morning walk" in descriptions
    assert "Medication" in descriptions

    # Schedule still works after reload
    reloaded_scheduler = Scheduler(loaded)
    reloaded_schedule = reloaded_scheduler.generate_schedule()
    assert len(reloaded_schedule) == 3


# ─── Journey 2: Task completion → auto-reschedule → DB persistence ─────────────────

def test_complete_recurring_task_and_persist(tmp_db):
    create_user("tom@example.com", "Tom", _hash("pw"))
    owner = Owner(name="Tom")
    pet = Pet(name="Rex", species="Dog")
    owner.add_pet(pet)

    task_time = datetime(2026, 4, 1, 9, 0)
    task = Task(description="Walk", time=task_time, frequency="daily", duration=20, priority="high")
    pet.add_task(task)

    scheduler = Scheduler(owner)
    scheduler.complete_task(pet, task)

    # Original marked done, follow-up created in memory
    assert task.completed is True
    assert len(pet.tasks) == 2
    follow_up = pet.tasks[1]
    assert follow_up.description == "Walk"
    assert follow_up.time == task_time + timedelta(days=1)
    assert follow_up.completed is False

    # Persist and reload — follow-up must survive the round-trip
    save_owner(owner, "tom@example.com")
    loaded = load_owner("tom@example.com")

    loaded_tasks = loaded.pets[0].tasks
    assert len(loaded_tasks) == 2
    completed_tasks = [t for t in loaded_tasks if t.completed]
    pending_tasks = [t for t in loaded_tasks if not t.completed]
    assert len(completed_tasks) == 1
    assert len(pending_tasks) == 1
    assert pending_tasks[0].time == task_time + timedelta(days=1)


# ─── Journey 3: Conflict detection → schedule generation pipeline ──────────────────

def test_conflict_detection_then_schedule_generation(tmp_db):
    create_user("sara@example.com", "Sara", _hash("pw"))
    owner = Owner(name="Sara", preferences={"max_tasks_per_day": 5, "available_minutes": 120})
    pet = Pet(name="Milo", species="Dog")
    owner.add_pet(pet)

    conflict_time = datetime(2026, 4, 1, 10, 0)
    t1 = Task(description="Bath", time=conflict_time, frequency="weekly", duration=30, priority="medium")
    t2 = Task(description="Trim nails", time=conflict_time, frequency="monthly", duration=20, priority="low")
    t3 = Task(description="Feed", time=datetime(2026, 4, 1, 8, 0), frequency="daily", duration=10, priority="high")
    for t in [t1, t2, t3]:
        pet.add_task(t)

    scheduler = Scheduler(owner)

    # Conflict detection fires
    warnings = scheduler.detect_conflicts()
    assert len(warnings) == 1
    assert "Bath" in warnings[0] or "Trim nails" in warnings[0]

    # Schedule still generates and picks tasks normally
    schedule = scheduler.generate_schedule()
    assert len(schedule) == 3
    task_descriptions = [t.description for _, t, _ in schedule]
    # High priority feed must appear
    assert "Feed" in task_descriptions

    # Persist after conflict detected — no crash
    save_owner(owner, "sara@example.com")
    loaded = load_owner("sara@example.com")
    assert len(loaded.get_all_tasks()) == 3


# ─── Journey 4: Schedule → email HTML generation ───────────────────────────────────

def test_schedule_to_email_html_pipeline(tmp_db):
    create_user("alex@example.com", "Alex", _hash("pw"))
    owner = Owner(name="Alex", preferences={"max_tasks_per_day": 5, "available_minutes": 120})
    pet = Pet(name="Luna", species="Cat")
    owner.add_pet(pet)

    pet.add_task(Task(description="Medication", time=datetime(2026, 4, 2, 8, 0),
                      frequency="daily", duration=5, priority="high"))
    pet.add_task(Task(description="Playtime", time=datetime(2026, 4, 2, 17, 0),
                      frequency="daily", duration=20, priority="low"))

    scheduler = Scheduler(owner)
    schedule = scheduler.generate_schedule()
    assert len(schedule) == 2

    # Build email HTML from the generated schedule
    html = _build_html("Alex", schedule, date(2026, 4, 2))
    assert "Alex" in html
    assert "Medication" in html
    assert "Playtime" in html
    # High priority → red badge, low priority → green badge
    assert "#e74c3c" in html
    assert "#27ae60" in html

    # send_schedule_email returns failure gracefully without a real API key
    ok, msg = send_schedule_email("alex@example.com", "Alex", schedule, date(2026, 4, 2))
    assert ok is False
    assert isinstance(msg, str)


# ─── Journey 5: Google Calendar conflict check integrated with task scheduling ─────

def test_calendar_conflict_check_integrated_with_schedule(tmp_db):
    create_user("kim@example.com", "Kim", _hash("pw"))
    owner = Owner(name="Kim", preferences={"max_tasks_per_day": 5, "available_minutes": 120})
    pet = Pet(name="Noodle", species="Dog")
    owner.add_pet(pet)

    walk_time = datetime(2026, 4, 3, 10, 0)
    feed_time = datetime(2026, 4, 3, 14, 0)
    pet.add_task(Task(description="Walk", time=walk_time, frequency="daily", duration=30, priority="high"))
    pet.add_task(Task(description="Feed", time=feed_time, frequency="daily", duration=10, priority="medium"))

    calendar_events = [
        {
            "summary": "Vet appointment",
            "start_dt": datetime(2026, 4, 3, 9, 45),
            "end_dt": datetime(2026, 4, 3, 10, 45),
        }
    ]

    scheduler = Scheduler(owner)
    schedule = scheduler.generate_schedule()

    # Check each scheduled task against calendar events
    conflicts_found = {}
    for _, task, _ in schedule:
        conflicts = check_task_conflict(task.time, task.duration, calendar_events)
        if conflicts:
            conflicts_found[task.description] = conflicts

    # Walk overlaps the vet appointment; Feed does not
    assert "Walk" in conflicts_found
    assert "Vet appointment" in conflicts_found["Walk"]
    assert "Feed" not in conflicts_found


# ─── Journey 6: Multi-pet owner with preferences update → explain_plan text ────────

def test_multi_pet_explain_plan_reflects_preferences(tmp_db):
    create_user("pat@example.com", "Pat", _hash("pw"))
    owner = Owner(name="Pat", preferences={"max_tasks_per_day": 2, "available_minutes": 40})
    dog = Pet(name="Bruno", species="Dog")
    cat = Pet(name="Simba", species="Cat")
    owner.add_pet(dog)
    owner.add_pet(cat)

    dog.add_task(Task(description="Walk", frequency="daily", duration=30, priority="high"))
    dog.add_task(Task(description="Bath", frequency="weekly", duration=45, priority="low"))
    cat.add_task(Task(description="Feed", frequency="daily", duration=5, priority="high"))
    cat.add_task(Task(description="Brushing", frequency="weekly", duration=10, priority="medium"))

    scheduler = Scheduler(owner)
    plan_text = scheduler.explain_plan()

    # explain_plan must return a non-empty string with task details
    assert isinstance(plan_text, str)
    assert len(plan_text) > 0
    # Capped at 2 tasks — only 2 numbered entries
    assert plan_text.count("\n  1.") == 1
    assert plan_text.count("\n  2.") == 1
    assert plan_text.count("\n  3.") == 0

    # Update preferences and verify the plan changes
    owner.set_preferences({"max_tasks_per_day": 4, "available_minutes": 120})
    expanded_plan = scheduler.explain_plan()
    assert expanded_plan.count("\n  3.") == 1  # now picks more tasks


# ─── Journey 7: Duplicate registration is rejected ─────────────────────────────────

def test_duplicate_registration_rejected(tmp_db):
    assert create_user("dup@example.com", "First", _hash("pw")) is True
    assert create_user("dup@example.com", "Second", _hash("pw")) is False
    # Only the first registration's data is stored
    user = get_user("dup@example.com")
    assert user["name"] == "First"
