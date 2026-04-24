# PawPal+ Enhancement Plan

# Pre-Plan
  - We are going to create a modal signin for the app where the user will have to sign into the app. Once they are in the app. The app will load their personal dashboard where they are able to use the functionality currently to add their pet species, pet name, Even a place for breed that will be optional. For the owner preferences we want to have a form that they will complete that will schedule their time and if they sync their google account. If there are any conflicts the app will flag the time. 



## Context

The user wants to evolve PawPal+ from a functional demo into a professional, robust daily planning tool. Three key upgrades are in scope:

1. **Google Calendar integration** — warn the owner if a scheduled pet task conflicts with an existing Google Calendar event
2. **Claude API daily briefing** — after schedule generation, produce a natural-language summary of the owner's day
3. **SQLite persistence** — survive page refreshes; data should not vanish on Streamlit rerun

The app currently lives at `/Users/sethjohnson/applied-ai-system-project/`. It runs locally (`streamlit run app.py`).

---

## Architecture

### New files to create

| File | Purpose |
|---|---|
| `database.py` | SQLite CRUD: init schema, save/load owner → pets → tasks |
| `google_calendar.py` | Google OAuth, fetch events for a date, detect overlap with a task |
| `ai_features.py` | Claude API call that produces the natural-language daily briefing |

### Files to modify

| File | Changes |
|---|---|
| `app.py` | Add Google Calendar section, wire completion buttons, SQLite load/save, Claude briefing display |
| `requirements.txt` | Add `anthropic`, `google-api-python-client`, `google-auth-httplib2`, `google-auth-oauthlib` |

### Files left untouched

- `pawpal_system.py` — core logic is already complete; no changes needed
- `tests/test_pawpal.py` — tests cover the logic layer; no regression risk

---

## Implementation Steps

### Step 1 — SQLite persistence (`database.py`)

**Schema (3 tables):**

```sql
owners  (id, name, max_tasks_per_day, available_minutes)
pets    (id, owner_id, name, species, breed, age)
tasks   (id, pet_id, description, time TEXT, frequency, completed, duration, priority)
```

`time` stored as ISO-8601 string (`datetime.isoformat()`), or `NULL` if unset.

**Functions to implement:**
- `init_db()` — create tables if they don't exist; called once at app startup
- `save_owner(owner: Owner)` — upsert owner row, upsert all pets, upsert all tasks
- `load_owner(name: str) -> Optional[Owner]` — reconstruct full Owner/Pet/Task graph from DB; set `Task._id_counter` and `Pet._id_counter` to `max(id)+1` to prevent collisions

**Integration point in `app.py`:**
- Call `init_db()` at top of script (runs once per session due to caching)
- After owner name is entered, call `load_owner(name)` to restore state into `st.session_state`
- After any mutation (add pet, add task, complete task), call `save_owner(st.session_state.owner)`

---

### Step 2 — Google Calendar integration (`google_calendar.py`)

**Prerequisites (user must do once):**
1. Create a Google Cloud project → enable Google Calendar API
2. Create OAuth 2.0 credentials (`Desktop app` type) → download as `credentials.json` → place in project root
3. First app run: click "Connect Google Calendar" button → browser auth → `token.json` auto-created

**Functions to implement:**
- `get_credentials() -> Credentials` — check `token.json`; if missing/expired, run `InstalledAppFlow.run_local_server(port=0)` and save new token
- `get_events_for_date(target_date: date) -> list[dict]` — call Calendar API `events().list()` for the given day; return list of `{summary, start_dt, end_dt}` dicts
- `check_task_conflict(task_time: datetime, duration_minutes: int, events: list[dict]) -> list[dict]` — return any events whose time window overlaps `[task_time, task_time + duration]`

**Integration point in `app.py`:**
- New sidebar or section: "Google Calendar" with `Connect` / `Disconnect` button + status chip
- When user clicks "Add Task" and a start time is set, call `get_events_for_date` then `check_task_conflict`; surface any conflicts as `st.warning()` below the button (non-blocking — task is still added, owner just sees the alert)

---

### Step 3 — Claude API daily briefing (`ai_features.py`)

**Function to implement:**
- `generate_daily_briefing(owner_name: str, schedule: list[tuple], date: date) -> str`

**Approach:**
- Use `anthropic.Anthropic()` client with model `claude-sonnet-4-6`
- System prompt (cache with `cache_control` `ephemeral`): role description + app context
- User prompt: serialized schedule rows (pet name, task, time, priority, duration)
- Returns a 3-5 sentence conversational briefing, e.g.:
  *"Good morning Jordan! Today looks like a full one for Mochi — starting with a 7am walk (30 min), then a midday vet check-in (60 min). You have one high-priority task and two medium-priority ones totalling 90 minutes, which fits exactly in your budget. Make sure the vet visit is confirmed — it overlaps with your 11am Google Calendar meeting."*

**Integration point in `app.py`:**
- After `generate_schedule()` succeeds, automatically call `generate_daily_briefing()`
- Display in a new `st.info()` box above the schedule table, titled "AI Daily Briefing"
- Wrap in `with st.spinner("Generating briefing...")` to show loading state
- Requires `ANTHROPIC_API_KEY` env var (fail gracefully with a warning if not set)

---

### Step 4 — Task completion in the schedule view (`app.py`)

Currently the schedule table is a static `st.dataframe`. Replace with a `for` loop rendering each row as columns:

```
[Pet]  [Task]  [Time]  [Priority]  [Duration]  [Mark Complete button]
```

- Clicking "Mark Complete" calls `scheduler.complete_task(pet, task)` then `save_owner(...)`
- Completed tasks immediately disappear from the pending view
- Daily/weekly tasks auto-create the next occurrence (already implemented in `complete_task()`)

---

## Requirements (`requirements.txt` additions)

```
anthropic>=0.50
google-api-python-client>=2.0
google-auth-httplib2>=0.2
google-auth-oauthlib>=1.0
```

---

## Verification

1. **SQLite persistence** — add a pet and task, refresh the page → data should still be present
2. **Google Calendar conflict** — create a test event in Google Calendar at a specific time, add a task at the same time in PawPal+ → `st.warning` should appear with the event name
3. **Claude briefing** — click "Generate Schedule" with tasks present → AI briefing should appear above the table within a few seconds
4. **Task completion** — click "Mark Complete" on a daily task → task disappears, new occurrence appears in pet's task list; refresh → SQLite preserves the new task
5. **Full flow** — `python -m pytest tests/test_pawpal.py` should still pass (no changes to logic layer)

---

## User Setup Checklist (one-time)

- [ ] `pip install -r requirements.txt`
- [ ] Set `ANTHROPIC_API_KEY=<your_key>` in shell or `.env`
- [ ] Google Cloud Console: create project → enable Calendar API → download `credentials.json` to project root
- [ ] Run `streamlit run app.py` → click "Connect Google Calendar" → complete browser auth
