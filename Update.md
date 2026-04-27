# Update Log

---

## ✅ March 23, 2026 — Phase 1: Design & Skeleton

- Designed and implemented the core UML for PawPal+, including Owner, Pet, Task, Constraint, Schedule, and Scheduler classes.
- Generated Python class skeletons in pawpal_system.py with type hints, unique IDs for Pet and Task, and clarified method signatures.
- Updated reflection.md with a summary of these design changes for future reference.

---

## ✅ Phase 2: Core Implementation

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

## ✅ April 23, 2026 — Phase 3: Professional File Structure

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
## ✅ Phase 4: AI Daily Briefing (Claude API)

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
 
> ✅ **Completed April 25, 2026.** `pawpal/services/ai_features.py` was created with `generate_daily_briefing()` using `claude-haiku-4-5-20251001` and ephemeral prompt caching on the system block. The briefing renders in a styled card above the schedule table after "Generate Schedule" is clicked, with graceful fallback when `ANTHROPIC_API_KEY` is unset.

---

## ✅ Phase 5: Week Calendar View (April 25, 2026)

- **Week calendar view** — replaced the card-list timeline with a full 7-day HTML/CSS/JS calendar grid rendered via `st.components.v1.html`; pet task events are absolutely positioned by minute as blue blocks (🐾) showing `start – end` time range, with auto-scroll to the current time and a red indicator line for now.
- **Schedule Preferences removed** — the max-tasks/available-minutes form was removed from the UI; sensible defaults remain in the data model and still drive `generate_schedule()` without user friction.

> ✅ **Completed April 25, 2026.**

---

## ✅ Phase 6: Remove Google OAuth · Add Sign-out Summary Email (April 25, 2026)

**Removed:**
- `pawpal/services/google_calendar.py` — deleted entirely; OAuth flow, event fetching, and conflict detection against Google Calendar are gone.
- `create_or_get_google_user()` removed from `database.py` — no longer needed without Google sign-in.
- `auth.py` — "Continue with Google" button and all Google imports removed; login modal is now email/password only with Sign In and Create Account tabs.
- `app.py` — Google Calendar connect/disconnect UI removed; week calendar now shows only pet task events (no green Google overlay); Google conflict check removed from the Add Task flow.
- `requirements.txt` — `google-api-python-client`, `google-auth-httplib2`, `google-auth-oauthlib` removed.

**Added — Sign-out summary email (`pawpal/services/email_service.py`):**
- `send_signout_email(to_email, owner_name, owner, delay_minutes=60)` — called from the Log Out button in `app.py` before session state is cleared.
- Collects all **incomplete** tasks across every pet; completed tasks are silently excluded.
- Picks **today** as the target date when signing out before 20:00, **tomorrow** after.
- Calls `resend.Emails.send()` with `scheduled_at` set to now + 60 minutes — delivery is handled server-side by Resend with no background threads or task queues needed.
- `_build_signout_html(owner_name, task_rows, for_date)` — separate HTML builder for this email (pet, task, priority, duration, time, frequency columns).
- Fails gracefully when `RESEND_API_KEY` is unset or no pending tasks exist.

**Tests (`tests/test_services.py`, `tests/test_e2e.py`):**
- All 9 Google Calendar tests removed.
- 8 new `send_signout_email` / `_build_signout_html` unit tests added — verify: HTML includes owner name, pet name, pending task description; HTML excludes completed tasks; fails with correct message when API key is absent; fails with "no pending tasks" message when all tasks are done.
- 2 new `send_signout_email` unit tests gated on `resend` being installed — verify: `scheduled_at` offset is within 2 minutes of 60 minutes; HTML body contains pending task and excludes completed task.
- 2 new e2e journeys (Journeys 5 & 6 replaced) covering sign-out email filtering and DB round-trip with mocked Resend.
- **Total: 45 tests passing, 3 skipped (require `resend` package).**

> ✅ **Completed April 25, 2026.**

---

## ✅ Phase 7: Nav Bar + Username Auth + Account Recovery (April 25, 2026)

**Removed:**
- Auto-appearing login modal on page load — the app no longer blocks with a dialog immediately; users see content first.
- Bare `st.title` / `st.caption` / `st.stop()` auth gate replaced entirely.
- Duplicate logged-in header block (title + welcome caption + logout button) removed from the dashboard — the nav bar now owns all of this.

**Added — Colored nav bar (`app.py`):**
- `_render_nav_bar()` — blue gradient bar (`#4a6cf7 → #3b5de7`) rendered on every page load via injected CSS + `st.markdown` + `st.columns`.
- Logged-out state: **Sign In** (primary/filled) and **Create Account** buttons on the right; clicking either sets `st.session_state.modal_open` + `modal_view` and reruns — modal only opens on demand.
- Logged-in state: welcome text with name + `@username`, Log Out button that schedules the sign-out summary email before clearing session.
- `_render_landing_page()` — hero heading, subheading, and 3-column feature card grid (Schedule Tasks / Email Reminders / AI Briefing) visible to logged-out users.

**Added — Username-based authentication (`auth.py`, `database.py`):**
- `username` column added to the `users` table via a non-destructive `init_db()` migration: detects missing column, adds it, backfills existing rows from email prefix, creates a unique index — runs exactly once.
- `create_user()` now takes `username` as the second argument; returns `False` on duplicate email **or** duplicate username.
- `get_user_by_username(username)` — case-insensitive lookup; sign-in now uses username + password instead of email + password.
- `get_user_by_email(email)` — for recovery flow; old `get_user()` kept as an alias.
- `update_password(email, new_hash)` — used by account recovery.
- Session state gains `user_username` alongside existing `user_email` and `user_name`.

**Added — Input validation helpers (`auth.py`):**
- `_validate_username(username)` — regex `^[a-zA-Z][a-zA-Z0-9_]{2,19}$`; 3–20 chars, starts with letter, letters/digits/underscores only.
- `_validate_password(password)` — 8–12 chars, ≥1 uppercase, ≥1 lowercase, ≥1 digit, ≥1 symbol; returns **all** failing rules at once so the user can fix everything in one shot.
- No new packages — validation uses Python's built-in `re` module.

**Added — 3-view login modal (`auth.py`):**
- **Sign In view** — username + password fields; links to Create Account and Forgot Password views.
- **Create Account view** — name, username, email, password, confirm password; all validators run before any DB write; shows all errors simultaneously.
- **Account Recovery view** — user enters email; system generates a guaranteed-valid temporary password, hashes it, updates the DB, and sends it via `send_recovery_email()`; falls back to showing the username on screen if `RESEND_API_KEY` is unset.

**Added — Recovery email (`email_service.py`):**
- `send_recovery_email(to_email, username, temp_password)` — immediate delivery (no `scheduled_at`); HTML table showing username reminder and temporary password with sign-in instructions.

**Tests (`tests/test_services.py`, `tests/test_e2e.py`):**
- 8 username validator tests, 9 password validator tests — cover valid inputs, every individual rule failure, and multi-error accumulation.
- 5 new DB unit tests: `create_user` with username, duplicate username rejection, `get_user_by_username`, `get_user_by_email`, `update_password`.
- 1 migration test: simulates a legacy DB without `username` column and verifies `init_db()` backfills it correctly.
- 1 recovery email failure test; 6 new e2e journeys covering username sign-in, DB round-trip, account recovery, and validation guards.
- **Total: 80 tests, all passing.**

## Current File Structure

```
app.py                          ← Streamlit entry point (streamlit run app.py)
pawpal/
  __init__.py
  models.py                     ← Task, Pet, Owner, Scheduler
  services/
    auth.py                     ← _validate_username, _validate_password, _hash, show_login_modal (3 views)
    database.py                 ← init_db (with migration), create_user, get_user_by_username/email, update_password, save_owner, load_owner
    email_service.py            ← send_schedule_email, send_signout_email, send_recovery_email
    ai_features.py              ← generate_daily_briefing (Claude Haiku + prompt caching)
scripts/
  demo.py                       ← feature demo (python scripts/demo.py)
tests/
  __init__.py
  test_pawpal.py                ← 13 model/scheduler tests
  test_services.py              ← 47 service-layer unit tests
  test_e2e.py                   ← 20 end-to-end journey tests
```
