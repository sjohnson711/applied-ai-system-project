## Claude instructions and job duties ##
- Do not make any changes without consulting me
- Do not download any packages if they are not needed. If you want to download a new package, provide a detailed reason and the tradeoffs.



# Phase 2 Planning Log

## ✅ Phase 7: Nav Bar + Username Auth + Account Recovery
> Planned and implemented April 25, 2026.

### What was built

**No new packages** — all validation uses Python's built-in `re` module.

**`database.py`**
- Non-destructive `init_db()` migration: adds `username TEXT` column if missing, backfills from email prefix, creates unique index — runs exactly once on startup.
- `create_user(email, username, name, password_hash)` — second parameter added; rejects duplicate email or duplicate username.
- `get_user_by_username(username)` — case-insensitive; used for sign-in flow.
- `get_user_by_email(email)` — used for account recovery; old `get_user()` kept as alias.
- `update_password(email, new_hash)` — used by recovery flow.

**`auth.py`**
- `_validate_username(username)` — regex `^[a-zA-Z][a-zA-Z0-9_]{2,19}$`; 3–20 chars, starts with letter.
- `_validate_password(password)` — 8–12 chars, ≥1 uppercase, ≥1 lowercase, ≥1 digit, ≥1 symbol; all errors returned at once.
- `show_login_modal()` rewritten as 3 views (driven by `st.session_state.modal_view`):
  - **`"signin"`** — username + password; links to create account and recovery.
  - **`"create"`** — name, username, email, password, confirm; validators fire before DB write.
  - **`"recover"`** — email → temp password generated + stored + emailed; falls back to showing username on screen if Resend not configured.

**`email_service.py`**
- `send_recovery_email(to_email, username, temp_password)` — immediate delivery, HTML table with username + temp password.

**`app.py`**
- `_render_nav_bar()` — blue gradient bar always visible; logged-out shows Sign In / Create Account buttons; logged-in shows `@username` + Log Out.
- `_render_landing_page()` — hero + 3-column feature card grid shown to logged-out users.
- Modal no longer auto-opens; only fires when `st.session_state.modal_open` is True (set by nav buttons).

**Tests: 80 passing**
- 8 username + 9 password validator unit tests
- DB: create with username, duplicate username rejection, get_by_username, get_by_email, update_password, migration backfill
- Recovery email failure test
- E2E: username sign-in flow, DB round-trip, account recovery, validation guards

---

** Start Here ** 

#Your instructions will start with some ** mandatory ** rules
- Make sure not to make any changes that are not industry focused. 
- Before any changes happen you will need to ask for permission even if things are not clear
- If you need to understand what I am asking, ask for clarity before implementation. 



Implementation: (Once we are done with implementation of each task below place a check mark on the side.)
    1. I want to automatically use Claude to write a summary of what the user has already planned for upcoming task with a welcoming message in a modal once the user has logged in. ✅

    2. We need to remove the Generate schedule on the button and automatically have the task make a nice structured list on the right side of the screen(The user should not have to hit a button to generate the task schedule.) We want to add the task layout to the email that we send the user. We do not need the Build schedule section at all and the email that we are sending for the schedule alert will be known from the database when the user signs in. We want to not display it in the app due to security reasons. ✅

 

    3. I want to add pictures that fade in and fade out of different families with their pets like pictures that enhance the UI. We can have at least 10 pictures that continue to fade in and out. I love the setup of the page now. Make the sign in button maybe a more welcoming color and you can make it the color that it is now during the hover. ✅

    4. Added a date picker to the task scheduling form so users can choose a specific date for any task frequency (not just daily). Daily tasks use the picked date as their start date and expand forward. The date input uses `date.today()` as the default and prevents scheduling in the past. Implemented in `app.py` — `task_date_input = st.date_input(...)` combined with `task_time_input` via `datetime.combine()`. ✅

    5. Added Claude AI weekly briefing modal triggered on sign-in. After the user hits "Let's go!" on the welcome screen, a second modal ("📋 Your Week Ahead") fires. It:
       - Calls `generate_weekly_briefing()` in `pawpal/services/ai_features.py` which retrieves all pending tasks from the `owner` object, structures them day-by-day, expands daily tasks across all 7 days, and sends the schedule as context to Claude Haiku.
       - Always shows a structured task list in the modal regardless of whether Claude responds (reliability guardrail).
       - API key loaded from `.streamlit/secrets.toml` → `os.environ["ANTHROPIC_API_KEY"]`.
       - Logging added to `ai_features.py`: `_log.warning` (missing key), `_log.debug` (schedule text), `_log.info` (success), `_log.error` with `exc_info=True` (exceptions).
       - Modal flow: `auth.py` welcome view sets `show_briefing = True` → `app.py` fires `_briefing_modal(owner, owner_name)` in authenticated section. ✅

    6. Added Edit and Delete buttons to every task card in the Schedule panel (right column). Each task card now has two action buttons below it:
       - **🗑 Delete** — removes the task from `pet.tasks` in memory and calls `delete_task(task._db_id)` to hard-delete the row from SQLite immediately. No confirmation prompt — instant removal.
       - **✏️ Edit** — opens a `@st.dialog("✏️ Edit Task")` modal pre-filled with the task's current description, frequency, duration, priority, date, and time. Saving writes changes back via `save_owner()`.
       - `delete_task(task_db_id: int)` added to `pawpal/services/database.py` and imported in `app.py`.
       - Unique widget keys use `task._db_id` (or loop index as fallback) to avoid key collisions across multiple cards. ✅
