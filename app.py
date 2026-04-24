import streamlit as st
from datetime import datetime, date, timedelta

from pawpal.models import Owner, Pet, Task, Scheduler
from pawpal.services.database import init_db, load_owner, save_owner
from pawpal.services.auth import is_logged_in, show_login_modal, logout
from pawpal.services.email_service import send_schedule_email

try:
    from pawpal.services.google_calendar import (
        get_credentials,
        get_events_for_date,
        check_task_conflict,
        GOOGLE_AVAILABLE,
    )
except ImportError:
    GOOGLE_AVAILABLE = False

st.set_page_config(page_title="PawPal+", page_icon="🐾", layout="centered")
init_db()

# ─── AUTH GATE ───────────────────────────────────────────────────────────────
if not is_logged_in():
    st.title("🐾 PawPal+")
    st.caption("Your personal pet care planner")
    show_login_modal()
    st.stop()

# ─── SESSION BOOTSTRAP ───────────────────────────────────────────────────────
user_email: str = st.session_state.user_email
user_name: str = st.session_state.get("user_name", "")

if "owner" not in st.session_state:
    loaded = load_owner(user_email)
    st.session_state.owner = loaded if loaded else Owner(name=user_name)

owner: Owner = st.session_state.owner

# ─── HEADER ──────────────────────────────────────────────────────────────────
col_title, col_logout = st.columns([5, 1])
with col_title:
    st.title("🐾 PawPal+")
with col_logout:
    st.write("")  # vertical align
    if st.button("Log out", key="logout_btn"):
        logout()

st.caption(f"Welcome back, **{user_name}** · {user_email}")
st.divider()

# ─── MY PETS ─────────────────────────────────────────────────────────────────
st.subheader("My Pets")

col1, col2, col3 = st.columns(3)
with col1:
    pet_name = st.text_input("Pet name", value="", key="pet_name")
with col2:
    species = st.selectbox("Species", ["dog", "cat", "rabbit", "bird", "other"], key="pet_species")
with col3:
    breed = st.text_input("Breed (optional)", value="", key="pet_breed")

if st.button("Add Pet", key="add_pet_btn"):
    if pet_name.strip():
        new_pet = Pet(name=pet_name.strip(), species=species, breed=breed.strip())
        owner.add_pet(new_pet)
        save_owner(owner, user_email)
        st.success(f"Added {pet_name.strip()} the {species}!")
        st.rerun()
    else:
        st.warning("Please enter a pet name.")

if owner.pets:
    st.write(
        "**Your pets:** "
        + "  ·  ".join(
            f"{p.name} ({p.species}{', ' + p.breed if p.breed else ''})"
            for p in owner.pets
        )
    )
else:
    st.info("No pets yet. Add one above to get started.")

st.divider()

# ─── SCHEDULE PREFERENCES ────────────────────────────────────────────────────
st.subheader("Schedule Preferences")
st.caption("These caps control how your daily plan is built.")

col1, col2 = st.columns(2)
with col1:
    max_tasks = st.number_input(
        "Max tasks per day",
        min_value=1,
        max_value=20,
        value=owner.preferences.get("max_tasks_per_day", 5),
        key="pref_max",
    )
with col2:
    available_minutes = st.number_input(
        "Available time (minutes)",
        min_value=10,
        max_value=480,
        value=owner.preferences.get("available_minutes", 90),
        key="pref_mins",
    )

if st.button("Save Preferences", key="save_prefs_btn"):
    owner.set_preferences(
        {"max_tasks_per_day": int(max_tasks), "available_minutes": int(available_minutes)}
    )
    save_owner(owner, user_email)
    st.success("Preferences saved.")

st.divider()

# ─── GOOGLE CALENDAR ─────────────────────────────────────────────────────────
st.subheader("Google Calendar")

if GOOGLE_AVAILABLE:
    gcal_connected = st.session_state.get("gcal_connected", False)
    if not gcal_connected:
        st.caption(
            "Connect your Google Calendar so PawPal+ can flag task times "
            "that conflict with existing events."
        )
        if st.button("🔗 Connect Google Calendar", key="gcal_connect_btn"):
            with st.spinner("Opening browser for Google auth…"):
                creds = get_credentials()
            if creds:
                st.session_state.gcal_connected = True
                st.success("Google Calendar connected!")
                st.rerun()
            else:
                st.error(
                    "Could not connect. Make sure **credentials.json** is in the project folder."
                )
    else:
        st.success("✅ Google Calendar connected — conflicts will be flagged when you add tasks.")
        if st.button("Disconnect", key="gcal_disconnect_btn"):
            st.session_state.gcal_connected = False
            st.rerun()
else:
    st.caption(
        "Google Calendar sync is optional. To enable it, install the extra dependencies:"
    )
    st.code(
        "pip install google-api-python-client google-auth-httplib2 google-auth-oauthlib",
        language="bash",
    )

st.divider()

# ─── TASKS ───────────────────────────────────────────────────────────────────
st.subheader("Tasks")
st.caption("Select a pet and add care tasks to their schedule.")

if owner.pets:
    pet_names = [p.name for p in owner.pets]
    selected_pet_name = st.selectbox("Assign task to", pet_names, key="task_pet")
    selected_pet = next(p for p in owner.pets if p.name == selected_pet_name)

    col1, col2 = st.columns(2)
    with col1:
        task_description = st.text_input("Task description", value="", key="task_desc")
    with col2:
        task_frequency = st.selectbox(
            "Frequency", ["daily", "weekly", "monthly", "once"], key="task_freq"
        )

    col3, col4 = st.columns(2)
    with col3:
        task_duration = st.number_input(
            "Duration (minutes)", min_value=0, max_value=300, value=30, key="task_dur"
        )
    with col4:
        task_priority = st.selectbox(
            "Priority", ["high", "medium", "low"], index=1, key="task_pri"
        )

    col5, col6 = st.columns(2)
    with col5:
        use_time = st.checkbox("Set a start time?", value=False, key="task_use_time")
    with col6:
        task_time_input = (
            st.time_input(
                "Start time",
                value=datetime.strptime("09:00", "%H:%M").time(),
                key="task_time",
            )
            if use_time
            else None
        )

    if st.button("Add Task", key="add_task_btn"):
        if task_description.strip():
            task_time = None
            if use_time and task_time_input:
                task_time = datetime.combine(datetime.today().date(), task_time_input)

            new_task = Task(
                description=task_description.strip(),
                frequency=task_frequency,
                duration=int(task_duration),
                priority=task_priority,
                time=task_time,
            )
            selected_pet.add_task(new_task)

            # Google Calendar conflict check
            if task_time and st.session_state.get("gcal_connected"):
                events = get_events_for_date(task_time.date())
                conflicts = check_task_conflict(task_time, int(task_duration), events)
                if conflicts:
                    st.warning(
                        f"⚠️ Calendar conflict: **{new_task.description}** overlaps with: "
                        + ", ".join(f"**{c}**" for c in conflicts)
                    )

            save_owner(owner, user_email)
            st.success(f"Added '{task_description.strip()}' to {selected_pet.name}!")
            st.rerun()
        else:
            st.warning("Please enter a task description.")

    # Task tables per pet
    for pet in owner.pets:
        tasks = pet.get_tasks()
        if tasks:
            st.write(f"**{pet.name}'s tasks:**")
            st.table(
                [
                    {
                        "Description": t.description,
                        "Priority": t.priority,
                        "Duration": f"{t.duration} min" if t.duration else "—",
                        "Frequency": t.frequency,
                        "Status": "✅ Done" if t.completed else "⏳ Pending",
                    }
                    for t in tasks
                ]
            )
else:
    st.info("Add a pet first to start adding tasks.")

st.divider()

# ─── BUILD SCHEDULE ──────────────────────────────────────────────────────────
st.subheader("Build Schedule")
st.caption("Generates today's plan ordered by priority, capped by your preferences.")

alert_email = st.text_input(
    "Email for schedule alert", value=user_email, key="alert_email"
)

if st.button("Generate Schedule", key="gen_schedule_btn"):
    scheduler = Scheduler(owner)

    conflicts = scheduler.detect_conflicts()
    if conflicts:
        st.error(
            f"⚠️ {len(conflicts)} scheduling conflict{'s' if len(conflicts) > 1 else ''} detected!"
        )
        with st.expander("View conflicts", expanded=True):
            for c in conflicts:
                st.warning(c)
    else:
        st.success("✅ No scheduling conflicts found.")

    schedule = scheduler.generate_schedule()
    st.session_state.last_schedule = schedule

    if schedule:
        total_duration = sum(task.duration for _, task, _ in schedule)
        prefs = owner.preferences

        st.success("Today's Schedule")
        m1, m2, m3 = st.columns(3)
        m1.metric("Tasks Selected", len(schedule))
        m2.metric("Total Time", f"{total_duration} min")
        m3.metric("Time Budget", f"{prefs.get('available_minutes', 90)} min")

        st.write("")
        hdr = st.columns([1.5, 2, 1, 1, 1, 1.5])
        for label, col in zip(["Pet", "Task", "Priority", "Duration", "Time", ""], hdr):
            col.markdown(f"**{label}**")

        for pet, task, reason in schedule:
            c1, c2, c3, c4, c5, c6 = st.columns([1.5, 2, 1, 1, 1, 1.5])
            c1.write(pet.name)
            c2.write(task.description)
            c3.write(task.priority)
            c4.write(f"{task.duration} min" if task.duration else "—")
            c5.write(task.time.strftime("%H:%M") if task.time else "—")
            if c6.button("✅ Done", key=f"done_{task.task_id}"):
                scheduler.complete_task(pet, task)
                save_owner(owner, user_email)
                st.rerun()

        with st.expander("📋 Plan explanation", expanded=False):
            st.text(scheduler.explain_plan())

        st.divider()
        tomorrow = date.today() + timedelta(days=1)
        if st.button(
            f"📧 Email tomorrow's schedule to {alert_email}",
            key="email_schedule_btn",
        ):
            with st.spinner("Sending…"):
                ok, msg = send_schedule_email(alert_email, owner.name, schedule, tomorrow)
            st.success(msg) if ok else st.error(msg)
    else:
        st.warning("No tasks selected. Add tasks to your pets or adjust your preferences.")
