import logging
import os
import random
from datetime import date, datetime, timedelta
from typing import Optional

_log = logging.getLogger(__name__)

# One vibe is picked at random each login — keeps every briefing feeling fresh.
_VIBES = [
    "You write like a warm morning radio host who adores animals.",
    "You're a cheerful park ranger who loves pets and sneaks in one gentle nature metaphor.",
    "You write like a best friend texting from a cozy café — casual, caring, one fun emoji.",
    "You're an enthusiastic pet trainer full of encouragement and one playful pet pun.",
    "You write like a wise, calm vet who has seen it all and genuinely loves every animal.",
    "You're a cozy storyteller — write as if the pets themselves sent this message through you.",
    "You write like a motivational coach who happens to be obsessed with animals.",
    "You're a friendly neighborhood pet shop owner — warm, practical, and a little quirky.",
    "You write in a poetic style: short, vivid, and full of heart.",
    "You're like a cheerful zookeeper narrating the day's adventures.",
]


def _groq_client():
    try:
        from groq import Groq
    except ImportError:
        _log.error("groq package not installed")
        return None
    api_key = os.environ.get("GROQ_API_KEY")
    _log.debug("GROQ_API_KEY from os.environ: %s", "found" if api_key else "missing")
    if not api_key:
        try:
            import streamlit as st
            api_key = st.secrets["GROQ_API_KEY"]
            _log.debug("GROQ_API_KEY from st.secrets: found")
        except KeyError:
            _log.error("GROQ_API_KEY missing from st.secrets")
        except Exception as exc:
            _log.error("st.secrets access failed: %s", exc)
    if not api_key:
        return None
    return Groq(api_key=api_key)


def generate_weekly_briefing(
    owner_name: str,
    owner,
    week_start: date,
    week_end: date,
) -> str:
    """Return a creative, warm welcome + task summary for the coming week."""
    client = _groq_client()
    if client is None:
        _log.warning("GROQ_API_KEY not set — weekly briefing skipped")
        return ""

    today    = date.today()
    tomorrow = today + timedelta(days=1)

    days = []
    cur = week_start
    while cur <= week_end:
        days.append(cur)
        cur += timedelta(days=1)

    by_day: dict = {d: [] for d in days}
    untimed_rows: list = []

    for pet in owner.pets:
        for task in pet.get_tasks():
            if task.completed:
                continue
            if not task.time:
                untimed_rows.append(f"- {pet.name}: {task.description} ({task.frequency})")
                continue
            start_date = task.time.date()
            if task.frequency == "daily":
                for d in days:
                    if d >= start_date:
                        by_day[d].append((pet.name, task))
            elif week_start <= start_date <= week_end:
                by_day[start_date].append((pet.name, task))

    lines = []
    for d in days:
        if not by_day[d]:
            continue
        label = d.strftime("%A %-d")
        if d == today:
            label += " (TODAY)"
        elif d == tomorrow:
            label += " (TOMORROW)"
        lines.append(f"{label}:")
        for pet_name, task in sorted(by_day[d], key=lambda pt: pt[1].time):
            time_str = task.time.strftime("%-I:%M %p")
            lines.append(f"  {pet_name} — {task.description} at {time_str} ({task.priority})")

    if untimed_rows:
        lines.append("Anytime:")
        lines.extend(untimed_rows)

    schedule_text = "\n".join(lines) if lines else "No tasks scheduled this week."

    vibe = random.choice(_VIBES)
    now_hour = datetime.now().hour
    time_of_day = "morning" if now_hour < 12 else "afternoon" if now_hour < 17 else "evening"

    system_prompt = (
        f"{vibe} "
        "You are Pet2Go, a pet care assistant. "
        f"It's {time_of_day}. "
        "Greet the owner by first name, then give a warm and specific summary of their upcoming "
        "pet care. Always name the pets and their actual tasks — don't be vague. "
        "Highlight tomorrow if tasks exist. Keep it to 4 sentences max. "
        "End with one short, heartfelt encouragement about their pets."
    )

    user_message = (
        f"Owner: {owner_name}. Today: {today.strftime('%A %B %-d')}.\n\n"
        f"Schedule:\n{schedule_text}"
    )

    try:
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": user_message},
            ],
            max_tokens=180,
            temperature=1.0,
        )
        briefing = response.choices[0].message.content.strip()
        _log.info("Weekly briefing generated for %s (%d chars)", owner_name, len(briefing))
        return briefing
    except Exception as exc:
        _log.error("Groq API call failed for %s: %s", owner_name, exc, exc_info=True)
        return ""


def generate_daily_briefing(
    owner_name: str,
    schedule: list,
    target_date: Optional[date] = None,
) -> str:
    """Return a 3-4 sentence creative daily briefing for the owner."""
    client = _groq_client()
    if client is None:
        return ""

    if target_date is None:
        target_date = date.today()

    rows = []
    for pet, task, _reason in schedule:
        time_str = task.time.strftime("%-I:%M %p") if task.time else "anytime"
        rows.append(f"- {pet.name}: {task.description} at {time_str} ({task.priority})")

    schedule_text = "\n".join(rows) if rows else "No tasks scheduled."

    vibe = random.choice(_VIBES)

    system_prompt = (
        f"{vibe} "
        "You are PawPal+, a pet care assistant. "
        "Give a warm, specific daily briefing in 3-4 sentences max. "
        "Name the pets and tasks — never be vague. "
        "Flag any high-priority items. End with a one-line encouragement."
    )

    user_message = (
        f"Owner: {owner_name}. Date: {target_date.strftime('%A %B %-d')}.\n\n"
        f"Schedule:\n{schedule_text}"
    )

    try:
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": user_message},
            ],
            max_tokens=150,
            temperature=1.0,
        )
        return response.choices[0].message.content.strip()
    except Exception as exc:
        _log.error("Groq API call failed for %s: %s", owner_name, exc, exc_info=True)
        return ""
