# Update Log

---

## March 23, 2026 — Phase 1: Design & Skeleton

- Designed and implemented the core UML for PawPal+, including Owner, Pet, Task, Constraint, Schedule, and Scheduler classes.
- Generated Python class skeletons in pawpal_system.py with type hints, unique IDs for Pet and Task, and clarified method signatures.
- Updated reflection.md with a summary of these design changes for future reference.

---

## Phase 2: Core Implementation

- Implemented all four core classes: `Task`, `Pet`, `Owner`, `Scheduler` with full method bodies.
- **Scheduler algorithms:** `sort_by_time()` (sorted + lambda), `filter_tasks()`, `filter_by_pet_name()`, `complete_task()` with auto-rescheduling for daily/weekly tasks using `timedelta`.
- **Scheduling intelligence:** `generate_schedule()` picks tasks by priority + time, capped by `max_tasks_per_day` and `available_minutes` preferences; `detect_conflicts()` flags same-pet/same-time collisions; `explain_plan()` outputs a plain-text summary.
- **Streamlit UI (app.py):** Auth gate, session bootstrap, add pets, schedule preferences, Google Calendar section, task management, build schedule with Done buttons, email tomorrow's schedule.
- **SQLite persistence (database.py):** Four-table schema (users, owner_prefs, pets, tasks); `save_owner()` upserts full object graph; `load_owner()` reconstructs Owner → Pet → Task from flat rows.
- **Authentication (auth.py):** PBKDF2-HMAC-SHA256 password hashing, Streamlit dialog with Sign In / Create Account tabs, session-state login gate.
- **Email service (email_service.py):** Resend API integration with HTML email template, colour-coded priority badges.
- **Google Calendar integration (google_calendar.py):** OAuth 2.0 flow, calendar event fetch, duration-aware conflict detection.
- **Tests (tests/test_pawpal.py):** 9 tests covering task completion, sorting, recurring task auto-schedule, conflict detection, schedule generation with priority and time-budget constraints.

---

## April 23, 2026 — Phase 3: Professional File Structure

- Reorganised all source files into a proper Python package with separation of concerns.
- **`pawpal/models.py`** — All four core domain classes (`Task`, `Pet`, `Owner`, `Scheduler`), moved from root-level `pawpal_system.py`.
- **`pawpal/services/`** — External integrations and infrastructure isolated into their own modules:
  - `auth.py` — authentication logic
  - `database.py` — SQLite persistence
  - `email_service.py` — Resend email delivery
  - `google_calendar.py` — Google Calendar OAuth + conflict check
- **`pawpal/__init__.py`** — Re-exports `Task`, `Pet`, `Owner`, `Scheduler` for convenience.
- **`scripts/demo.py`** — Feature demo script, moved from root-level `main.py`.
- **`tests/__init__.py`** — Added to make tests a proper package.
- Updated all imports in `app.py`, `tests/test_pawpal.py`, and all service modules to use the new package paths.
- Deleted the old flat root-level files (`pawpal_system.py`, `database.py`, `auth.py`, `email_service.py`, `google_calendar.py`, `main.py`).
- **New test suite (tests/test_services.py):** 23 tests covering all service-layer functions:
  - `database.py` — `init_db`, `create_user`, `get_user`, `save_owner`, `load_owner` (including full round-trip and upsert verification; isolated with per-test temp SQLite files via `monkeypatch`)
  - `auth.py` — `_hash` determinism, uniqueness, and output format
  - `email_service.py` — `_build_html` content and colour coding; `send_schedule_email` failure without credentials
  - `google_calendar.py` — `check_task_conflict` overlap, no-overlap, adjacent, and None-time cases; `_parse_dt` UTC parsing and None handling
- **Total test coverage: 32 tests, all passing.**

## Current File Structure

```
app.py                          ← Streamlit entry point (streamlit run app.py)
pawpal/
  __init__.py
  models.py                     ← Task, Pet, Owner, Scheduler
  services/
    auth.py
    database.py
    email_service.py
    google_calendar.py
scripts/
  demo.py                       ← feature demo (python scripts/demo.py)
tests/
  __init__.py
  test_pawpal.py                ← 9 model/scheduler tests
  test_services.py              ← 23 service-layer tests
```
## Phase 4: AI Daily Briefing (Claude API)

**Goal:** Add a natural-language daily briefing powered by Claude Haiku that summarizes the day's schedule, flags overdue tasks, and surfaces priority nudges — generated once per session with prompt caching to keep costs near zero.

**New file:** `pawpal/services/ai_service.py`
- Takes an `Owner` object, builds context string from `Scheduler.explain_plan()` + serialized task list
- Calls `claude-haiku-4-5-20251001` via the Anthropic SDK
- Sets `cache_control: {"type": "ephemeral"}` on the system prompt block (pet/task context) so repeated calls within the session hit the cache
- Returns a plain-text briefing string

**Modified files:**
- `app.py` — add a "Today's Briefing" expander panel near the top of the dashboard that calls `ai_service.generate_briefing(owner)` and renders the result; gate the call so it only fires once per session via `st.session_state`
- `requirements.txt` — add `anthropic`
- `.env` / secrets — add `ANTHROPIC_API_KEY`

**Model:** `claude-haiku-4-5-20251001` (~$0.002–0.005 per briefing)

**Cost control:** Prompt caching on the system prompt; briefing generated once at login, not on every rerender.

**Tests:** Add 2–3 tests in `tests/test_services.py` for `ai_service.py` — mock the Anthropic client, assert the briefing is a non-empty string, assert `cache_control` is set on the system prompt block.

**Verification:**
1. `streamlit run app.py` → log in → confirm briefing panel appears with natural-language summary
2. Check Anthropic dashboard for cache hit rate after first session
3. `python -m pytest` → all 34+ tests pass
