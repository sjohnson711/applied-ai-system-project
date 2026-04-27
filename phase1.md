# PawPal+ Enhancement Plan

# Pre-Plan
  - We are going to create a modal signin for the app where the user will have to sign into the app. Once they are in the app. The app will load their personal dashboard where they are able to use the functionality currently to add their pet species, pet name, Even a place for breed that will be optional. For the owner preferences we want to have a form that they will complete that will schedule their time. If there are any conflicts the app will flag the time.

---

## Context

The user wants to evolve PawPal+ from a functional demo into a professional, robust daily planning tool. Key upgrades in scope:

1. **Sign-out summary email** — when the user logs out, schedule a task-summary email to arrive 60 minutes later via Resend's `scheduled_at` API; includes all pending (incomplete) tasks across all pets
2. **Claude API daily briefing** — after schedule generation, produce a natural-language summary of the owner's day
3. **SQLite persistence** — survive page refreshes; data should not vanish on Streamlit rerun

The app currently lives at `/Users/sethjohnson/applied-ai-system-project/`. It runs locally (`streamlit run app.py`).

---

## Architecture

### Service files

| File | Purpose |
|---|---|
| `pawpal/services/database.py` | SQLite CRUD: init schema, save/load owner → pets → tasks |
| `pawpal/services/email_service.py` | Resend email delivery: schedule email + sign-out summary email |
| `pawpal/services/ai_features.py` | Claude API call that produces the natural-language daily briefing |
| `pawpal/services/auth.py` | Email/password authentication with PBKDF2 hashing |

### Files to modify

| File | Changes |
|---|---|
| `app.py` | Auth gate, week calendar, task management, build schedule with Done buttons, sign-out email trigger, email tomorrow's schedule |
| `requirements.txt` | `streamlit`, `pytest`, `resend`, `anthropic` |

---

## Implementation Steps

### Step 1 — SQLite persistence (`database.py`)

**Schema (4 tables):**

```sql
users       (email PK, name, password_hash)
owner_prefs (email PK → users, max_tasks_per_day, available_minutes)
pets        (id PK, owner_email → users, name, species, breed, age)
tasks       (id PK, pet_id → pets, description, time TEXT, frequency, completed, duration, priority)
```

`time` stored as ISO-8601 string (`datetime.isoformat()`), or `NULL` if unset.

**Functions:**
- `init_db()` — create tables if they don't exist; called once at app startup
- `create_user(email, name, password_hash)` — insert new user; returns False on duplicate
- `get_user(email)` — return user dict or None
- `save_owner(owner, email)` — upsert owner row, upsert all pets, upsert all tasks
- `load_owner(email)` — reconstruct full Owner/Pet/Task graph from DB

---

### Step 2 — Authentication (`auth.py`)

- PBKDF2-HMAC-SHA256 password hashing with a fixed salt
- `show_login_modal()` — Streamlit dialog with Sign In / Create Account tabs
- `is_logged_in()` — checks `st.session_state.user_email`
- `logout()` — clears session state and reruns

---

### Step 3 — Sign-out summary email (`email_service.py`)

**Function:** `send_signout_email(to_email, owner_name, owner, delay_minutes=60)`

**Approach:**
- Collect all incomplete tasks across every pet
- Pick today as target date if before 20:00, tomorrow otherwise
- Call `resend.Emails.send()` with `scheduled_at` = now + 60 minutes (ISO 8601 with timezone)
- Returns `(bool, str)` — gracefully fails when API key is absent or no pending tasks exist

**Integration point in `app.py`:**
- Log Out button calls `send_signout_email(user_email, user_name, owner)` before `logout()`
- Requires `RESEND_API_KEY` env var (fails gracefully with message if not set)

---

### Step 4 — Claude API daily briefing (`ai_features.py`)

**Function:** `generate_daily_briefing(owner_name, schedule, target_date)`

**Approach:**
- Use `anthropic.Anthropic()` client with model `claude-haiku-4-5-20251001`
- System prompt cached with `cache_control: {"type": "ephemeral"}` to keep costs near zero
- Returns a 3-5 sentence conversational briefing

**Integration point in `app.py`:**
- After `generate_schedule()` succeeds, call `generate_daily_briefing()`
- Display in a styled card above the schedule table
- Requires `ANTHROPIC_API_KEY` env var (fails gracefully if not set)

---

### Step 5 — Week calendar view (`app.py`)

- 7-day HTML/CSS grid rendered via `st.components.v1.html`
- Blue blocks for pet tasks positioned by minute within a 6am–10pm window
- Auto-scrolls to current time on load; red line marks the current moment
- Previous/next week navigation via session state offset

---

## Requirements (`requirements.txt`)

```
streamlit>=1.36
pytest>=7.0
resend>=0.7.0
anthropic>=0.50
```

---

## Verification

1. **SQLite persistence** — add a pet and task, refresh the page → data should still be present
2. **Sign-out email** — log out → check inbox ~60 minutes later for task summary; verify only pending tasks appear
3. **No tasks case** — complete all tasks then log out → no email is sent; confirm graceful message
4. **Claude briefing** — click "Generate Schedule" with tasks present → AI briefing appears above the table
5. **Task completion** — click "✅ Done" on a daily task → task disappears, new occurrence appears in pet's task list
6. **Full test suite** — `python -m pytest` → 45 tests pass, 3 skipped (require `resend` package)

---

## User Setup Checklist (one-time)

- [ ] `pip install -r requirements.txt`
- [ ] Set `RESEND_API_KEY=<your_key>` in shell or `.env`
- [ ] Set `ANTHROPIC_API_KEY=<your_key>` in shell or `.env` (optional — enables AI briefing)
- [ ] Run `streamlit run app.py`
