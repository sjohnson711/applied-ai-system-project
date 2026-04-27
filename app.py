import os
import streamlit as st
import streamlit.components.v1 as components
from datetime import datetime, date, timedelta

from pawpal.models import Owner, Pet, Task, Scheduler
from pawpal.services.database import init_db, load_owner, save_owner, delete_task
from pawpal.services.auth import is_logged_in, show_login_modal, logout
from pawpal.services.email_service import send_signout_email, send_task_alert_email
from pawpal.services.ai_features import generate_weekly_briefing

# ─── Nav bar ─────────────────────────────────────────────────────────────────

_NAV_CSS = """
<style>
[data-testid="stToolbar"] { display: none; }

.pawpal-nav {
    background: linear-gradient(90deg, #4a6cf7 0%, #3b5de7 100%);
    padding: 0.75rem 1.5rem;
    border-radius: 0 0 12px 12px;
    margin-bottom: 0.5rem;
}
.pawpal-nav-brand {
    color: white;
    font-size: 1.3rem;
    font-weight: 700;
    letter-spacing: -0.01em;
    margin: 0;
}
div[data-testid="stHorizontalBlock"]:has(button[data-testid^="stBaseButton"]) {
    margin-top: -0.5rem;
}

/* Sign In button: soft green default, brand blue on hover */
[data-testid="stBaseButton-primary"] {
    background-color: #10b981 !important;
    border-color: #10b981 !important;
    color: white !important;
    transition: background-color 0.25s ease, border-color 0.25s ease !important;
}
[data-testid="stBaseButton-primary"]:hover {
    background-color: #4a6cf7 !important;
    border-color: #4a6cf7 !important;
    color: white !important;
}
</style>
<div class="pawpal-nav">
  <p class="pawpal-nav-brand">🐾 Pet2Go</p>
</div>
"""


def _render_nav_bar() -> None:
    st.markdown(_NAV_CSS, unsafe_allow_html=True)

    if is_logged_in():
        col_info, col_logout = st.columns([5, 1])
        with col_info:
            uname = st.session_state.get("user_username", "")
            name  = st.session_state.get("user_name", "")
            display = f"Welcome back, **{name}**" + (f" · @{uname}" if uname else "")
            st.caption(display)
        with col_logout:
            if st.button("Log out", key="logout_btn"):
                new_tasks = st.session_state.get("session_new_tasks", [])
                if new_tasks:
                    send_task_alert_email(
                        st.session_state.user_email,
                        st.session_state.get("user_name", ""),
                        new_tasks,
                    )
                send_signout_email(
                    st.session_state.user_email,
                    st.session_state.get("user_name", ""),
                    st.session_state.owner,
                )
                logout()
    else:
        _, c_signin, c_create = st.columns([5, 1, 1.4])
        with c_signin:
            if st.button("Sign In", key="nav_signin_btn", type="primary", use_container_width=True):
                st.session_state.modal_open = True
                st.session_state.modal_view = "signin"
                st.rerun()
        with c_create:
            if st.button("Create Account", key="nav_create_btn", use_container_width=True):
                st.session_state.modal_open = True
                st.session_state.modal_view = "create"
                st.rerun()


_SLIDESHOW_PHOTOS = [
    "photo-1601758228041-f3b2795255f1",  # woman hugging golden retriever
    "photo-1587300003388-59208cc962cb",  # labrador in sunlight
    "photo-1548199973-03cce0bbc87b",     # two dogs running on beach
    "photo-1552053831-71594a27632d",     # golden retriever puppy
    "photo-1537151608828-ea2b11777ee8",  # dog portrait outdoors
    "photo-1583511655857-d19b40a7a54e",  # smiling golden retriever
    "photo-1574144611937-0df059b5ef3e",  # fluffy cat portrait
    "photo-1514888286974-6c03e2ca1dba",  # orange tabby cat
    "photo-1561037404-61cd46aa615b",     # joyful dog outdoors
    "photo-1560807707-8cc77767d783",     # adorable puppies together
]


def _render_landing_page() -> None:
    n       = len(_SLIDESHOW_PHOTOS)
    show_s  = 6.0   # seconds each image stays fully visible
    fade_s  = 0.8   # seconds for cross-fade between images
    total_s = n * show_s

    slot_pct = show_s / total_s * 100   # e.g. 10% per image for n=10
    fade_pct = fade_s / total_s * 100   # e.g. 2% for the fade window

    imgs_html   = ""
    style_rules = ""
    for i, photo_id in enumerate(_SLIDESHOW_PHOTOS):
        url = (
            f"https://images.unsplash.com/{photo_id}"
            f"?w=900&auto=format&q=80"
        )

        slot_start = round(i * slot_pct, 3)
        full_end   = round(slot_start + slot_pct - fade_pct, 3)
        slot_end   = round(slot_start + slot_pct, 3)

        imgs_html += (
            f'<img src="{url}" alt="Pet photo" '
            f'style="position:absolute;top:0;left:0;width:100%;height:100%;'
            f'object-fit:cover;object-position:center 30%;opacity:0;'
            f'animation:fade{i} {total_s}s infinite;" />'
        )

        if i == 0:
            # Image 0 starts visible; fades back in at end of cycle for seamless loop
            loop_in = round(100 - fade_pct, 3)
            style_rules += (
                f"@keyframes fade{i}{{"
                f"0%{{opacity:1}}"
                f"{full_end}%{{opacity:1}}"
                f"{slot_end}%{{opacity:0}}"
                f"{loop_in}%{{opacity:0}}"
                f"100%{{opacity:1}}"
                f"}}"
            )
        else:
            # Each image fades in during the previous image's fade-out (overlap = no gap)
            fade_in_start = round(slot_start - fade_pct, 3)
            style_rules += (
                f"@keyframes fade{i}{{"
                f"0%{{opacity:0}}"
                f"{fade_in_start}%{{opacity:0}}"
                f"{slot_start}%{{opacity:1}}"
                f"{full_end}%{{opacity:1}}"
                f"{slot_end}%{{opacity:0}}"
                f"100%{{opacity:0}}"
                f"}}"
            )

    slideshow_html = f"""
<!DOCTYPE html><html><head><meta charset="utf-8">
<style>
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  body {{ background:transparent; overflow:hidden; }}
  .hero {{ position:relative; width:100%; height:400px;
           border-radius:16px; overflow:hidden; }}
  .overlay {{
    position:absolute; bottom:0; left:0; right:0; height:50%;
    background:linear-gradient(to bottom,transparent,rgba(15,23,42,0.55));
    z-index:10;
  }}
  .tagline {{
    position:absolute; bottom:24px; left:0; right:0;
    text-align:center; z-index:11;
    color:white; font-family:system-ui,-apple-system,sans-serif;
    font-size:1.35rem; font-weight:700; letter-spacing:-0.01em;
    text-shadow:0 1px 4px rgba(0,0,0,0.4);
  }}
  {style_rules}
</style>
</head><body>
<div class="hero">
  {imgs_html}
  <div class="overlay"></div>
  <div class="tagline">🐾 Every pet deserves great care — and so do you.</div>
</div>
</body></html>"""

    components.html(slideshow_html, height=416, scrolling=False)

    st.markdown(
        "<h1 style='text-align:center;color:#4a6cf7;margin-top:1.5rem;'>🐾 Pet2Go</h1>",
        unsafe_allow_html=True,
    )
    st.markdown(
        "<p style='text-align:center;color:#64748b;font-size:1.1rem;'>"
        "Your personal pet care planner</p>",
        unsafe_allow_html=True,
    )
    st.write("")

    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown(
            "<div style='text-align:center;padding:1.5rem;background:#f0f4ff;"
            "border-radius:12px;'>"
            "<div style='font-size:2rem;'>🗓</div>"
            "<div style='font-weight:600;margin-top:0.5rem;'>Schedule Tasks</div>"
            "<div style='color:#64748b;font-size:0.85rem;margin-top:0.25rem;'>"
            "Organise daily and weekly pet care</div></div>",
            unsafe_allow_html=True,
        )
    with c2:
        st.markdown(
            "<div style='text-align:center;padding:1.5rem;background:#f0fdf4;"
            "border-radius:12px;'>"
            "<div style='font-size:2rem;'>📧</div>"
            "<div style='font-weight:600;margin-top:0.5rem;'>Email Reminders</div>"
            "<div style='color:#64748b;font-size:0.85rem;margin-top:0.25rem;'>"
            "Receive a task summary when you sign out</div></div>",
            unsafe_allow_html=True,
        )
    with c3:
        st.markdown(
            "<div style='text-align:center;padding:1.5rem;background:#fdf4ff;"
            "border-radius:12px;'>"
            "<div style='font-size:2rem;'>✨</div>"
            "<div style='font-weight:600;margin-top:0.5rem;'>AI Briefing</div>"
            "<div style='color:#64748b;font-size:0.85rem;margin-top:0.25rem;'>"
            "Natural-language weekly summary powered by Groq</div></div>",
            unsafe_allow_html=True,
        )

    st.write("")
    st.markdown(
        "<p style='text-align:center;color:#94a3b8;'>Sign in or create a free account to get started.</p>",
        unsafe_allow_html=True,
    )


# ─── Week calendar renderer ───────────────────────────────────────────────────

def _render_week_cal(week_start: date, pet_events: list) -> str:
    CAL_START_H = 6
    CAL_END_H = 22
    HOUR_PX = 60
    TOTAL_H = (CAL_END_H - CAL_START_H) * HOUR_PX

    today = date.today()
    days = [week_start + timedelta(days=i) for i in range(7)]
    day_labels = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

    header = '<div style="width:52px;flex-shrink:0;"></div>'
    for i, d in enumerate(days):
        is_today = d == today
        num_bg    = "#4a6cf7" if is_today else "transparent"
        num_color = "#fff"    if is_today else "#1e293b"
        lbl_color = "#4a6cf7" if is_today else "#94a3b8"
        header += (
            f'<div style="flex:1;text-align:center;padding:6px 2px;">'
            f'<div style="font-size:0.65rem;font-weight:600;color:{lbl_color};'
            f'text-transform:uppercase;letter-spacing:0.05em;">{day_labels[i]}</div>'
            f'<div style="display:inline-flex;align-items:center;justify-content:center;'
            f'width:28px;height:28px;border-radius:50%;background:{num_bg};color:{num_color};'
            f'font-size:0.85rem;font-weight:700;margin-top:2px;">{d.day}</div>'
            f'</div>'
        )

    time_col = ""
    for h in range(CAL_START_H, CAL_END_H + 1):
        top = (h - CAL_START_H) * HOUR_PX
        label = f"{h % 12 or 12}{'am' if h < 12 else 'pm'}"
        time_col += (
            f'<div style="position:absolute;top:{top - 7}px;right:6px;'
            f'font-size:0.6rem;font-weight:500;color:#94a3b8;white-space:nowrap;">{label}</div>'
        )

    pet_by_day: dict = {}
    for ev in pet_events:
        pet_by_day.setdefault(ev["day"], []).append(ev)

    cal_start_min = CAL_START_H * 60
    day_cols = ""
    for d in days:
        is_today   = d == today
        col_bg     = "rgba(74,108,247,0.03)" if is_today else "#fff"
        line_color = "#e8effe" if is_today else "#f1f5f9"

        gridlines = ""
        for h in range(CAL_START_H, CAL_END_H):
            top = (h - CAL_START_H) * HOUR_PX
            gridlines += (
                f'<div style="position:absolute;width:100%;height:1px;background:{line_color};top:{top}px;left:0;"></div>'
                f'<div style="position:absolute;width:100%;height:1px;background:#fafafa;top:{top + 30}px;left:0;"></div>'
            )

        evs_html = ""
        for ev in pet_by_day.get(d, []):
            s_min  = ev["start"].hour * 60 + ev["start"].minute
            e_min  = ev["end"].hour * 60 + ev["end"].minute
            top_px = max(0, s_min - cal_start_min)
            h_px   = max(22, e_min - s_min)
            s_str  = ev["start"].strftime("%-I:%M %p")
            e_str  = ev["end"].strftime("%-I:%M %p")
            evs_html += (
                f'<div style="position:absolute;top:{top_px}px;left:2px;right:2px;height:{h_px}px;'
                f'background:#4a6cf7;border-radius:4px;padding:2px 4px;font-size:0.62rem;'
                f'color:white;overflow:hidden;box-shadow:0 1px 2px rgba(74,108,247,0.3);">'
                f'<div style="font-weight:700;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">🐾 {ev["label"]}</div>'
                f'<div style="opacity:0.85;white-space:nowrap;">{s_str} – {e_str}</div>'
                f'</div>'
            )

        day_cols += (
            f'<div style="flex:1;position:relative;min-height:{TOTAL_H}px;'
            f'border-left:1px solid #e2e8f0;background:{col_bg};">'
            f'{gridlines}{evs_html}'
            f'</div>'
        )

    now         = datetime.now()
    now_min     = now.hour * 60 + now.minute
    now_top     = max(0, now_min - cal_start_min)
    now_day_idx = today.weekday()
    now_line    = ""
    if week_start <= today < week_start + timedelta(days=7):
        now_line = (
            f'<script>'
            f'(function(){{var cols=document.querySelectorAll(".day-col");'
            f'if(cols[{now_day_idx}]){{var l=document.createElement("div");'
            f'l.style.cssText="position:absolute;width:100%;height:2px;background:#ef4444;'
            f'top:{now_top}px;left:0;z-index:5;";'
            f'cols[{now_day_idx}].appendChild(l);}}}})();'
            f'</script>'
        )

    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8">
<style>body{{margin:0;font-family:system-ui,-apple-system,sans-serif;}}
.day-col{{flex:1;position:relative;min-height:{TOTAL_H}px;border-left:1px solid #e2e8f0;}}</style>
</head><body>
<div style="border:1px solid #e2e8f0;border-radius:12px;overflow:hidden;background:#fff;">
  <div style="display:flex;background:#f8fafc;border-bottom:2px solid #e2e8f0;padding:4px 4px 0 4px;">{header}</div>
  <div id="cal-scroll" style="overflow-y:auto;max-height:480px;">
    <div style="display:flex;min-height:{TOTAL_H}px;">
      <div style="width:52px;flex-shrink:0;position:relative;min-height:{TOTAL_H}px;
                  border-right:1px solid #e2e8f0;background:#f8fafc;">{time_col}</div>
      {day_cols}
    </div>
  </div>
</div>
<script>
var s=document.getElementById('cal-scroll');
if(s){{s.scrollTop=Math.max(0,{now_top}-120);}}
</script>
{now_line}
</body></html>"""


# ─── Claude briefing modal ───────────────────────────────────────────────────

@st.dialog("📋 Your Week Ahead")
def _briefing_modal(owner: Owner, owner_name: str) -> None:
    today    = date.today()
    tomorrow = today + timedelta(days=1)
    week_end = today + timedelta(days=6)

    # ── Build upcoming task list directly from owner ──────────────────────────
    days = [today + timedelta(days=i) for i in range(7)]
    by_day: dict = {d: [] for d in days}

    for pet in owner.pets:
        for task in pet.get_tasks():
            if task.completed or not task.time:
                continue
            start_date = task.time.date()
            if task.frequency == "daily":
                for d in days:
                    if d >= start_date:
                        by_day[d].append((pet, task))
            elif today <= start_date <= week_end:
                by_day[start_date].append((pet, task))

    has_tasks = any(by_day[d] for d in days)

    # ── Claude summary ────────────────────────────────────────────────────────
    if "briefing_text" not in st.session_state:
        with st.spinner("Getting your summary from Groq…"):
            st.session_state.briefing_text = generate_weekly_briefing(
                owner_name=owner_name,
                owner=owner,
                week_start=today,
                week_end=week_end,
            )

    briefing = st.session_state.get("briefing_text", "")
    if briefing:
        st.markdown(
            f"""<div style="background:linear-gradient(135deg,#f0f4ff 0%,#e8f0fe 100%);
            border-left:4px solid #4a6cf7;border-radius:8px;
            padding:1rem 1.25rem;margin-bottom:1rem;">
            <p style="margin:0 0 0.4rem 0;font-size:0.75rem;font-weight:600;
            color:#4a6cf7;letter-spacing:0.05em;text-transform:uppercase;">
            ✨ Groq's Summary</p>
            <p style="margin:0;font-size:0.95rem;color:#1e293b;line-height:1.6;">
            {briefing}</p></div>""",
            unsafe_allow_html=True,
        )

    # ── Task list (always shown so user can verify) ───────────────────────────
    if has_tasks:
        st.markdown("**Upcoming this week:**")
        _priority_color = {"high": "#e74c3c", "medium": "#f39c12", "low": "#27ae60"}
        for d in days:
            if not by_day[d]:
                continue
            label = d.strftime("%A, %B %-d")
            if d == today:
                label += " · Today"
            elif d == tomorrow:
                label += " · Tomorrow"
            st.caption(label)
            for pet, task in sorted(by_day[d], key=lambda pt: pt[1].time):
                color = _priority_color.get(task.priority, "#888")
                time_str = task.time.strftime("%-I:%M %p")
                st.markdown(
                    f"<div style='padding:0.35rem 0.75rem;margin-bottom:0.25rem;"
                    f"border-left:3px solid {color};border-radius:4px;background:#f8fafc;'>"
                    f"🐾 <b>{task.description}</b> · {pet.name} · {time_str} "
                    f"<span style='color:{color};font-size:0.8rem;'>({task.frequency})</span>"
                    f"</div>",
                    unsafe_allow_html=True,
                )
    else:
        st.info("No upcoming tasks this week. Add tasks to get a personalised summary!")

    st.write("")
    if st.button("Got it! 🐾", use_container_width=True, type="primary"):
        st.session_state.show_briefing = False
        st.session_state.pop("briefing_text", None)
        st.rerun()


# ─── Edit task modal ─────────────────────────────────────────────────────────

@st.dialog("✏️ Edit Task")
def _edit_task_modal(pet: "Pet", task: "Task", owner: "Owner", email: str) -> None:
    st.caption(f"Editing task for **{pet.name}**")

    new_desc = st.text_input("Task description", value=task.description, key="edit_desc")

    freq_opts = ["daily", "weekly", "monthly", "once"]
    freq_idx  = freq_opts.index(task.frequency) if task.frequency in freq_opts else 0
    new_freq  = st.selectbox("Frequency", freq_opts, index=freq_idx, key="edit_freq")

    ec1, ec2 = st.columns(2)
    with ec1:
        new_dur = st.number_input(
            "Duration (minutes)", min_value=0, max_value=300,
            value=task.duration or 30, key="edit_dur"
        )
    with ec2:
        pri_opts = ["high", "medium", "low"]
        pri_idx  = pri_opts.index(task.priority) if task.priority in pri_opts else 1
        new_pri  = st.selectbox("Priority", pri_opts, index=pri_idx, key="edit_pri")

    cur_date = task.time.date() if task.time else date.today()
    cur_time = task.time.time() if task.time else datetime.strptime("09:00", "%H:%M").time()

    ed1, ed2 = st.columns(2)
    with ed1:
        new_date = st.date_input("Date", value=cur_date, key="edit_date")
    with ed2:
        new_time = st.time_input("Start time", value=cur_time, key="edit_time")

    if st.button("Save changes", key="edit_save_btn", use_container_width=True, type="primary"):
        if not new_desc.strip():
            st.warning("Task description cannot be empty.")
            return
        task.description = new_desc.strip()
        task.frequency   = new_freq
        task.duration    = int(new_dur)
        task.priority    = new_pri
        task.time        = datetime.combine(new_date, new_time)
        save_owner(owner, email)
        st.session_state.pop("editing_task", None)
        st.rerun()

    if st.button("Cancel", key="edit_cancel_btn", use_container_width=True):
        st.session_state.pop("editing_task", None)
        st.rerun()


# ─── App bootstrap ────────────────────────────────────────────────────────────

st.set_page_config(page_title="Pet2Go", page_icon="🐾", layout="wide")

# Load API keys from st.secrets into os.environ so service modules pick them up
for _secret_key in ("RESEND_API_KEY", "GROQ_API_KEY"):
    if _secret_key not in os.environ:
        try:
            os.environ[_secret_key] = st.secrets[_secret_key]
        except (KeyError, FileNotFoundError):
            pass


try:
    init_db()
except Exception as _db_err:
    st.error(f"Database initialisation failed: {_db_err}. Please check your file permissions.")
    st.stop()

_render_nav_bar()

# ─── AUTH GATE ───────────────────────────────────────────────────────────────
if not is_logged_in():
    _render_landing_page()
    if st.session_state.get("modal_open"):
        show_login_modal()
    st.stop()

# ─── SESSION BOOTSTRAP ───────────────────────────────────────────────────────
user_email:    str = st.session_state.user_email
user_name:     str = st.session_state.get("user_name", "")
user_username: str = st.session_state.get("user_username", "")

if "owner" not in st.session_state:
    try:
        loaded = load_owner(user_email)
    except Exception:
        loaded = None
    st.session_state.owner          = loaded if loaded else Owner(name=user_name)
    st.session_state.session_new_tasks = []

owner: Owner = st.session_state.owner

# ─── WELCOME VIEW (shown inside sign-in modal after credentials pass) ─────────
if st.session_state.get("modal_view") == "welcome":
    show_login_modal()

# ─── CLAUDE BRIEFING (fires after "Let's go!" on sign-in) ────────────────────
if st.session_state.get("show_briefing"):
    _briefing_modal(owner, user_name or user_username)

st.divider()

# ─── WEEK CALENDAR (full width) ───────────────────────────────────────────────
st.subheader("Calendar")

if "cal_week_offset" not in st.session_state:
    st.session_state.cal_week_offset = 0

_today  = date.today()
_monday = _today - timedelta(days=_today.weekday())
week_start = _monday + timedelta(weeks=st.session_state.cal_week_offset)
week_end   = week_start + timedelta(days=6)

nav1, nav2, nav3 = st.columns([1, 6, 1])
with nav1:
    if st.button("‹", key="cal_prev", help="Previous week"):
        st.session_state.cal_week_offset -= 1
        st.rerun()
with nav2:
    this_week_badge = (
        "  <span style='color:#4a6cf7;font-size:0.75rem;font-weight:600;'>This week</span>"
        if st.session_state.cal_week_offset == 0 else ""
    )
    st.markdown(
        f"<div style='text-align:center;font-weight:600;color:#374151;padding-top:6px;'>"
        f"{week_start.strftime('%b %-d')} – {week_end.strftime('%b %-d, %Y')}"
        f"{this_week_badge}</div>",
        unsafe_allow_html=True,
    )
with nav3:
    if st.button("›", key="cal_next", help="Next week"):
        st.session_state.cal_week_offset += 1
        st.rerun()

pet_events = []
for pet in owner.pets:
    for task in pet.get_tasks():
        if task.time and not task.completed:
            end_time = task.time + timedelta(minutes=task.duration if task.duration else 30)
            pet_events.append({
                "day":   task.time.date(),
                "label": task.description,
                "start": task.time,
                "end":   end_time,
            })

components.html(
    _render_week_cal(week_start, pet_events),
    height=580,
    scrolling=False,
)

st.divider()

# ─── MAIN DASHBOARD: left = manage, right = schedule ─────────────────────────
col_left, col_right = st.columns([3, 2])

with col_left:
    # ── My Pets ──────────────────────────────────────────────────────────────
    st.subheader("My Pets")

    pc1, pc2, pc3 = st.columns(3)
    with pc1:
        pet_name = st.text_input("Pet name", value="", key="pet_name")
    with pc2:
        species = st.selectbox("Species", ["dog", "cat", "rabbit", "bird", "other"], key="pet_species")
    with pc3:
        breed = st.text_input("Breed (optional)", value="", key="pet_breed")

    if st.button("Add Pet", key="add_pet_btn"):
        if pet_name.strip():
            new_pet = Pet(name=pet_name.strip(), species=species, breed=breed.strip())
            owner.add_pet(new_pet)
            try:
                save_owner(owner, user_email)
            except RuntimeError as e:
                st.error(str(e))
            else:
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

    # ── Add Task ─────────────────────────────────────────────────────────────
    st.subheader("Tasks")
    st.caption("Select a pet and add care tasks to their schedule.")

    if owner.pets:
        pet_names         = [p.name for p in owner.pets]
        selected_pet_name = st.selectbox("Assign task to", pet_names, key="task_pet")
        selected_pet      = next(p for p in owner.pets if p.name == selected_pet_name)

        tc1, tc2 = st.columns(2)
        with tc1:
            task_description = st.text_input("Task description", value="", key="task_desc")
        with tc2:
            task_frequency = st.selectbox(
                "Frequency", ["daily", "weekly", "monthly", "once"], key="task_freq"
            )

        tc3, tc4 = st.columns(2)
        with tc3:
            task_duration = st.number_input(
                "Duration (minutes)", min_value=0, max_value=300, value=30, key="task_dur"
            )
        with tc4:
            task_priority = st.selectbox(
                "Priority", ["high", "medium", "low"], index=1, key="task_pri"
            )

        tc5, tc6 = st.columns(2)
        with tc5:
            task_date_input = st.date_input(
                "Date",
                value=date.today(),
                min_value=date.today(),
                key="task_date",
                help="For daily tasks this is the start date — the task repeats each day from here.",
            )
        with tc6:
            task_time_input = st.time_input(
                "Start time (required)",
                value=datetime.strptime("09:00", "%H:%M").time(),
                key="task_time",
            )

        if st.button("Add Task", key="add_task_btn"):
            if task_description.strip():
                task_time = datetime.combine(task_date_input, task_time_input)

                new_task = Task(
                    description=task_description.strip(),
                    frequency=task_frequency,
                    duration=int(task_duration),
                    priority=task_priority,
                    time=task_time,
                )
                selected_pet.add_task(new_task)

                conflict_warnings = Scheduler(owner).detect_conflicts_for_task(new_task, selected_pet)
                for w in conflict_warnings:
                    st.warning(w)

                try:
                    save_owner(owner, user_email)
                except RuntimeError as e:
                    st.error(str(e))
                else:
                    st.session_state.session_new_tasks.append((selected_pet.name, new_task))
                    st.success(f"Added '{task_description.strip()}' to {selected_pet.name}!")
                    st.rerun()
            else:
                st.warning("Please enter a task description.")
    else:
        st.info("Add a pet first to start adding tasks.")

with col_right:
    # ── Auto-rendered Schedule ────────────────────────────────────────────────
    st.subheader("📋 Schedule")

    all_pending = []
    for pet in owner.pets:
        for task in pet.get_tasks():
            if not task.completed:
                all_pending.append((pet, task))

    all_pending.sort(key=lambda pt: pt[1].time if pt[1].time else datetime.max)

    # Trigger edit modal when a task is queued for editing
    if "editing_task" in st.session_state:
        _edit_task_modal(*st.session_state.editing_task, owner, user_email)

    if all_pending:
        _priority_color = {"high": "#e74c3c", "medium": "#f39c12", "low": "#27ae60"}
        _priority_bg    = {"high": "#fef2f2", "medium": "#fffbeb", "low": "#f0fdf4"}

        for i, (pet, task) in enumerate(all_pending):
            pc      = _priority_color.get(task.priority, "#888")
            pbg     = _priority_bg.get(task.priority, "#f8fafc")
            t_str   = task.time.strftime("%a, %b %-d · %-I:%M %p") if task.time else "No set time"
            dur_str = f"{task.duration} min" if task.duration else "—"
            task_key = getattr(task, "_db_id", i)

            st.markdown(
                f"""<div style="background:{pbg};border-left:4px solid {pc};
                border-radius:6px;padding:0.7rem 1rem;margin-bottom:0.25rem;
                border:1px solid {pc}22;">
                  <div style="font-weight:600;color:#1e293b;font-size:0.95rem;">
                    {task.description}</div>
                  <div style="font-size:0.78rem;color:#64748b;margin-top:0.25rem;
                  display:flex;gap:0.75rem;flex-wrap:wrap;">
                    <span>🐾 {pet.name}</span>
                    <span>⏰ {t_str}</span>
                    <span>⏱ {dur_str}</span>
                    <span style="color:{pc};font-weight:600;">● {task.priority}</span>
                    <span>🔁 {task.frequency}</span>
                  </div>
                </div>""",
                unsafe_allow_html=True,
            )
            btn_edit, btn_del, _ = st.columns([1, 1, 4])
            with btn_edit:
                if st.button("✏️ Edit", key=f"edit_{task_key}", use_container_width=True):
                    st.session_state.editing_task = (pet, task)
                    st.rerun()
            with btn_del:
                if st.button("🗑 Delete", key=f"del_{task_key}", use_container_width=True):
                    pet.tasks = [t for t in pet.get_tasks() if t is not task]
                    if getattr(task, "_db_id", None):
                        delete_task(task._db_id)
                    st.rerun()
    else:
        st.info("No pending tasks yet. Add tasks using the form on the left.")
