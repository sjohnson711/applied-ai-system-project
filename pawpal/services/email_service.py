import os
from datetime import date

try:
    import resend as _resend
    RESEND_AVAILABLE = True
except ImportError:
    RESEND_AVAILABLE = False


def send_schedule_email(
    to_email: str,
    owner_name: str,
    schedule: list,
    for_date: date,
) -> tuple[bool, str]:
    """Send the schedule for for_date via Resend. Returns (success, message)."""
    if not RESEND_AVAILABLE:
        return False, "resend package is not installed. Run: pip install resend"

    api_key = os.environ.get("RESEND_API_KEY", "")
    if not api_key:
        return False, "RESEND_API_KEY environment variable is not set."

    _resend.api_key = api_key
    subject = f"PawPal+ — Schedule for {for_date.strftime('%A, %B %d')}"

    params = {
        "from": "PawPal+ <onboarding@resend.dev>",
        "to": [to_email],
        "subject": subject,
        "html": _build_html(owner_name, schedule, for_date),
    }
    try:
        _resend.Emails.send(params)
        return True, f"Schedule sent to {to_email}!"
    except Exception as exc:
        return False, str(exc)


def _build_html(owner_name: str, schedule: list, for_date: date) -> str:
    date_str = for_date.strftime("%A, %B %d, %Y")

    rows = ""
    for pet, task, reason in schedule:
        time_str = task.time.strftime("%H:%M") if task.time else "Anytime"
        priority_color = {"high": "#e74c3c", "medium": "#f39c12", "low": "#27ae60"}.get(
            task.priority, "#888"
        )
        rows += f"""
        <tr>
          <td>{pet.name}</td>
          <td>{task.description}</td>
          <td style="color:{priority_color};font-weight:bold">{task.priority}</td>
          <td>{task.duration} min</td>
          <td>{time_str}</td>
          <td style="color:#555;font-size:12px">{reason}</td>
        </tr>"""

    return f"""
    <!DOCTYPE html>
    <html>
    <body style="font-family:sans-serif;max-width:680px;margin:auto;padding:24px;color:#222">
      <h2 style="color:#2c3e50">🐾 PawPal+ — {date_str}</h2>
      <p>Hi <strong>{owner_name}</strong>,</p>
      <p>Here's the pet care schedule lined up for tomorrow:</p>
      <table border="1" cellpadding="8" cellspacing="0"
             style="width:100%;border-collapse:collapse;border-color:#ddd">
        <thead style="background:#f4f4f4">
          <tr>
            <th>Pet</th><th>Task</th><th>Priority</th>
            <th>Duration</th><th>Time</th><th>Notes</th>
          </tr>
        </thead>
        <tbody>{rows}</tbody>
      </table>
      <p style="margin-top:28px;font-size:13px;color:#888">
        Sent by PawPal+ &mdash; your personal pet care planner.
      </p>
    </body>
    </html>
    """
