import os
import smtplib
from datetime import date, datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText


def _send_gmail(to_email: str, subject: str, html: str) -> tuple[bool, str]:
    user = os.environ.get("GMAIL_USER", "")
    password = os.environ.get("GMAIL_APP_PASSWORD", "")
    if not user or not password:
        return False, "Gmail credentials are not configured."
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = f"PawPal+ <{user}>"
        msg["To"] = to_email
        msg.attach(MIMEText(html, "html"))
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(user, password)
            server.sendmail(user, to_email, msg.as_string())
        return True, f"Email sent to {to_email}."
    except Exception as exc:
        return False, str(exc)


def send_schedule_email(
    to_email: str,
    owner_name: str,
    schedule: list,
    for_date: date,
) -> tuple[bool, str]:
    """Send the generated schedule for for_date via Gmail. Returns (success, message)."""
    subject = f"PawPal+ — Schedule for {for_date.strftime('%A, %B %d')}"
    ok, msg = _send_gmail(to_email, subject, _build_html(owner_name, schedule, for_date))
    return ok, f"Schedule sent to {to_email}!" if ok else msg


def send_signout_email(
    to_email: str,
    owner_name: str,
    owner,
) -> tuple[bool, str]:
    """Send a task-summary email immediately on sign-out via Gmail."""
    task_rows = [
        (pet, task)
        for pet in owner.pets
        for task in pet.get_tasks()
        if not task.completed
    ]

    if not task_rows:
        return False, "No pending tasks to include in the summary."

    now = datetime.now()
    target_date = now.date() if now.hour < 20 else (now + timedelta(days=1)).date()
    subject = f"PawPal+ — Task Summary for {target_date.strftime('%A, %B %-d')}"
    return _send_gmail(to_email, subject, _build_signout_html(owner_name, task_rows, target_date))


def send_task_alert_email(
    to_email: str,
    owner_name: str,
    tasks: list,
) -> tuple[bool, str]:
    """Send a session-end summary of newly added tasks. tasks is [(pet_name, task), ...]."""
    if not tasks:
        return False, "No tasks to include in the alert."
    return _send_gmail(
        to_email,
        "PawPal+ — Tasks added this session",
        _build_task_alert_html(owner_name, tasks),
    )


def send_recovery_email(
    to_email: str,
    username: str,
    temp_password: str,
) -> tuple[bool, str]:
    """Send an account recovery email containing the username and a temporary password."""
    html = f"""<!DOCTYPE html>
<html>
<body style="font-family:sans-serif;max-width:520px;margin:auto;padding:24px;color:#222">
  <h2 style="color:#2c3e50">🐾 PawPal+ — Account Recovery</h2>
  <p>We received a recovery request for your account.</p>
  <table cellpadding="10" cellspacing="0" style="width:100%;border-collapse:collapse;">
    <tr>
      <td style="background:#f4f4f4;font-weight:bold;width:40%;">Username</td>
      <td style="border:1px solid #ddd;padding:10px;font-family:monospace;">{username}</td>
    </tr>
    <tr>
      <td style="background:#f4f4f4;font-weight:bold;">Temporary password</td>
      <td style="border:1px solid #ddd;padding:10px;font-family:monospace;">{temp_password}</td>
    </tr>
  </table>
  <p style="margin-top:20px;">Sign in with your username and this temporary password,
  then update your password from your account settings.</p>
  <p style="margin-top:28px;font-size:13px;color:#888">
    Sent by PawPal+ &mdash; your personal pet care planner.
  </p>
</body>
</html>"""
    return _send_gmail(to_email, "PawPal+ — Account Recovery", html)


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


def _build_task_alert_html(owner_name: str, tasks: list) -> str:
    """Build the HTML body for a session task-added summary email."""
    _priority_color = {"high": "#e74c3c", "medium": "#f39c12", "low": "#27ae60"}

    rows = ""
    for pet_name, task in tasks:
        time_str = task.time.strftime("%A, %B %-d at %-I:%M %p") if task.time else "No set time"
        pc = _priority_color.get(task.priority, "#888")
        rows += f"""
        <tr>
          <td style="border-bottom:1px solid #e2e8f0;padding:10px;">{pet_name}</td>
          <td style="border-bottom:1px solid #e2e8f0;padding:10px;">{task.description}</td>
          <td style="border-bottom:1px solid #e2e8f0;padding:10px;
              color:{pc};font-weight:bold;">{task.priority.capitalize()}</td>
          <td style="border-bottom:1px solid #e2e8f0;padding:10px;">{task.duration} min</td>
          <td style="border-bottom:1px solid #e2e8f0;padding:10px;">{time_str}</td>
          <td style="border-bottom:1px solid #e2e8f0;padding:10px;">{task.frequency.capitalize()}</td>
        </tr>"""

    return f"""<!DOCTYPE html>
<html>
<body style="font-family:sans-serif;max-width:680px;margin:auto;padding:24px;color:#222">
  <h2 style="color:#2c3e50">🐾 PawPal+ — Tasks Added This Session</h2>
  <p>Hi <strong>{owner_name}</strong>,</p>
  <p>Here are the tasks you added during your last session:</p>
  <table border="1" cellpadding="0" cellspacing="0"
         style="width:100%;border-collapse:collapse;border-color:#e2e8f0;">
    <thead style="background:#f8fafc;">
      <tr>
        <th style="padding:10px;text-align:left;">Pet</th>
        <th style="padding:10px;text-align:left;">Task</th>
        <th style="padding:10px;text-align:left;">Priority</th>
        <th style="padding:10px;text-align:left;">Duration</th>
        <th style="padding:10px;text-align:left;">Scheduled</th>
        <th style="padding:10px;text-align:left;">Frequency</th>
      </tr>
    </thead>
    <tbody>{rows}</tbody>
  </table>
  <p style="margin-top:28px;font-size:13px;color:#888">
    Sent by PawPal+ &mdash; your personal pet care planner.
  </p>
</body>
</html>"""


def _build_signout_html(owner_name: str, task_rows: list, for_date: date) -> str:
    date_str = for_date.strftime("%A, %B %d, %Y")

    rows = ""
    for pet, task in task_rows:
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
          <td>{task.frequency}</td>
        </tr>"""

    return f"""<!DOCTYPE html>
<html>
<body style="font-family:sans-serif;max-width:680px;margin:auto;padding:24px;color:#222">
  <h2 style="color:#2c3e50">🐾 PawPal+ — {date_str}</h2>
  <p>Hi <strong>{owner_name}</strong>,</p>
  <p>Here is a summary of your pending pet care tasks:</p>
  <table border="1" cellpadding="8" cellspacing="0"
         style="width:100%;border-collapse:collapse;border-color:#ddd">
    <thead style="background:#f4f4f4">
      <tr>
        <th>Pet</th><th>Task</th><th>Priority</th>
        <th>Duration</th><th>Time</th><th>Frequency</th>
      </tr>
    </thead>
    <tbody>{rows}</tbody>
  </table>
  <p style="margin-top:28px;font-size:13px;color:#888">
    Sent by PawPal+ &mdash; your personal pet care planner.
  </p>
</body>
</html>"""
