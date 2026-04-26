# Model Card — Pet2Go (PawPal+)

**Project:** Pet2Go / PawPal+  
**Author:** Seth Johnson  
**Date:** April 25, 2026  
**Stack:** Python · Streamlit · SQLite · Google Gemini (gemini-2.0-flash) · Resend

---

## What This App Does

Pet2Go is a personal pet care scheduler with an AI layer on top. You sign in, and before you even see your dashboard, the app greets you with a warm, natural-language summary of the week ahead — written by Gemini, in a different personality every time. It knows your pets by name, lists their actual tasks, and highlights what's coming up tomorrow. Then it gets out of your way.

Beyond the AI layer, the app handles the full scheduling workflow: adding pets and tasks, detecting time conflicts, auto-rescheduling recurring care, and sending a summary email when you sign out. All of that data lives in a local SQLite database so nothing disappears on a page refresh.

---

## Where This Started

The project began as **PawPal+** — a clean but minimal Streamlit demo built around four Python classes: `Owner`, `Pet`, `Task`, and `Scheduler`. At that stage you could add pets and tasks, mark things complete, and see a sorted schedule. There was no login, no database, and no AI. It was a working proof of concept that showed the architecture was sound.

Phase 1 was about turning that demo into a real application. The plan was clear: add user authentication, persist data to SQLite, trigger a summary email on sign-out, and wire in an AI briefing after schedule generation. Each of those felt like a discrete feature. In practice, they were all tangled together — the email service needed the database, the AI briefing needed the database, and auth needed to gate both.

Phase 2 kept going from there. A navigation bar. Username-based sign-in with validation rules. Account recovery by email. A date picker on the task form. Sliding photo backgrounds on the landing page. Edit and delete buttons on every task card. Each feature was small in isolation, but the cumulative effect transformed what looked like a class project into something that felt like a product.

---

## The AI Feature: How It Actually Works

The AI briefing is the most visible part of the capstone extension, but the interesting engineering is not the prompt — it's everything before the prompt.

When a user signs in, the app retrieves their full Owner → Pet → Task graph from SQLite. It then structures that data day-by-day across the next seven days. Daily tasks get expanded across every day they're active; one-time tasks appear only on their scheduled date. Completed tasks are filtered out. Tasks without a time slot are collected separately as "anytime" items.

That structured schedule text is what gets sent to Gemini. Without that retrieval and expansion step, the model would only see a single pending instance of a daily task and have no way to know it repeats every morning. That structuring step — pulling data from the database, reshaping it into something the model can reason about — is the core of what makes this a RAG implementation rather than just an API call.

On top of that, every briefing picks a random personality from a list of ten vibes: a warm morning radio host, a cozy storyteller, a cheerful park ranger, a poetic writer. The vibe is injected into the system prompt and the temperature is set to 1.3. This combination keeps every login feeling different without requiring any additional infrastructure.

The original plan called for the Claude API. Midway through, the project switched to Google Gemini (`gemini-2.0-flash`). The architecture did not change — the retrieval layer, the prompt structure, and the logging were all the same. Only the client library and model name changed. That flexibility reflected good separation of concerns: the AI layer was thin enough that swapping providers was a one-file change.

---

## What Worked Well

**The class structure held up.** Keeping `Task` and `Pet` as simple data holders and pushing all intelligence into `Scheduler` paid off consistently. Every new feature could be tested in isolation, and the UI never needed to know how the data was structured internally.

**Logging made invisible problems visible.** The first version of the briefing feature appeared to work — no errors, no crashes — but Gemini was never being called because the API key was missing and the exception handler silently returned an empty string. Adding `_log.warning` for missing keys and `_log.error` with `exc_info=True` for API failures immediately surfaced what was actually happening. That habit of structured logging is now baked into every service file.

**Graceful degradation throughout.** The email service, the Gemini integration, and the conflict detection all fail safely. If Resend isn't configured, sign-out works fine and no email sends. If the Gemini key is absent, the briefing modal still opens with the structured task list. No missing API key breaks the core app.

**The test suite stayed honest.** Eighty tests pass because the test targets are things that can actually be asserted: task counts, sort order, conflict detection logic, DB round-trips. The tests don't try to assert what Gemini said — they assert that the data pipeline feeding Gemini is correct. That distinction kept the test suite useful and fast.

---

## What Was Hard

**Getting the right data to the model in the right shape** was harder than writing the prompt. The gap between "what's in the database" and "what Gemini needs to generate a useful briefing" required a real structuring step. An early version passed a flat list of tasks to the model and got back generic responses that didn't mention specific days or times. Adding the day-by-day expansion and the daily task repetition logic was what made the output specific and trustworthy.

**Session state management in Streamlit** is genuinely tricky. Streamlit reruns the entire script on every interaction, which means any object created at the top level gets recreated unless it's explicitly stored in `st.session_state`. Early bugs came from the `Owner` object being reconstructed on every button click, wiping unsaved data. The fix — loading from SQLite into session state once and treating session state as the source of truth — held up, but it took time to reason through correctly.

**Auth added more complexity than expected.** PBKDF2 hashing, username validation with regex, account recovery via email, the three-view modal (`signin` / `create` / `recover`) — each piece was straightforward alone, but wiring them together with Streamlit's dialog system and maintaining clean state transitions required careful attention. The test suite for auth ended up being some of the most valuable tests in the project because the edge cases were easy to miss manually.

**Conflict detection had a subtle bug.** The original check only flagged tasks at the exact same datetime. Two tasks at 9:00 AM and 9:20 AM, each with 30-plus-minute durations, would silently overlap. The fix was duration-aware interval logic: `task_a.start < task_b.end AND task_b.start < task_a.end`. Simple in retrospect, but the original version looked correct until a specific scenario exposed it.

---

## Design Decisions Worth Noting

**Scheduler as the single brain.** All scheduling intelligence lives in `Scheduler`. The UI delegates every operation to a class method and only handles presentation. The tradeoff is a slightly more verbose call chain, but it means the logic is independently testable and the UI stays clean.

**Non-blocking conflict warnings.** A conflict warning appears alongside the success message, but the task is always saved. This was a deliberate choice: an owner scheduling two overlapping tasks may be doing it intentionally (supervised activities, for instance) and shouldn't be locked out. The warning informs; it doesn't gatekeep.

**Mandatory start times.** Early versions made start time optional. Making it required was the right call — conflict detection doesn't work without it, and every task appears in a meaningful chronological timeline. The friction of entering a time is worth the reliability it enables.

**SQLite over session state alone.** Streamlit's session state resets on refresh. For a tool you use every day, losing all your data on an accidental refresh is a dealbreaker. SQLite was the obvious fix — local, dependency-free, easy to inspect with `scripts/logTable.py`.

---

## Limitations

- The AI briefing depends on an external API key. If `GEMINI_API_KEY` is missing or the API is down, the briefing is silently skipped. The modal still opens with the raw task list, but the AI-generated summary is gone.
- There is no multi-user isolation in the database schema beyond filtering by `owner_email`. A production deployment would need proper row-level security.
- The test suite does not cover the Gemini API call or the Resend email delivery, since both require live credentials. Those paths are validated manually.
- `pawpal.db` is a local file. There is no sync across devices.

---

## What This Build Taught Me

Integrating AI into a real application is primarily a data architecture problem. The model is the easy part — getting the right data to it in the right shape, at the right time, is where most of the work lives.

Silent failures are more dangerous than loud ones. An error that crashes the app is immediately visible and fixable. An error that swallows an exception and returns an empty string looks like it's working. Structured logging is not optional.

Small prompt additions can have outsized effects. Ten personality vibes, a time-of-day variable, a maximum of four sentences — none of those are complex engineering, but together they make the difference between a response that feels like boilerplate and one that feels like it was written for you specifically.

And finally: the parts of the system that are hardest to test — the AI outputs, the external emails — are also the parts that benefit most from the surrounding code being rigorously tested. If the data pipeline is right, the AI output tends to be right. That framing made the whole project easier to reason about.

---

*Run with: `streamlit run app.py`*
