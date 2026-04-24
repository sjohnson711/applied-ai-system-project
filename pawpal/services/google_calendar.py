import os
from datetime import datetime, date, timedelta
from typing import Optional

try:
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build
    GOOGLE_AVAILABLE = True
except ImportError:
    GOOGLE_AVAILABLE = False

SCOPES = ["https://www.googleapis.com/auth/calendar.readonly"]
_TOKEN_FILE = "token.json"
_CREDS_FILE = "credentials.json"


def get_credentials() -> Optional[object]:
    """Run OAuth flow if needed and return valid credentials, or None on failure."""
    if not GOOGLE_AVAILABLE:
        return None
    creds = None
    if os.path.exists(_TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(_TOKEN_FILE, SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        elif os.path.exists(_CREDS_FILE):
            flow = InstalledAppFlow.from_client_secrets_file(_CREDS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)
        else:
            return None
        with open(_TOKEN_FILE, "w") as f:
            f.write(creds.to_json())
    return creds


def get_events_for_date(target_date: date) -> list:
    """Return a list of {summary, start_dt, end_dt} dicts for the given date."""
    creds = get_credentials()
    if not creds:
        return []
    service = build("calendar", "v3", credentials=creds)
    day_start = datetime.combine(target_date, datetime.min.time()).isoformat() + "Z"
    day_end = datetime.combine(target_date + timedelta(days=1), datetime.min.time()).isoformat() + "Z"
    result = (
        service.events()
        .list(
            calendarId="primary",
            timeMin=day_start,
            timeMax=day_end,
            singleEvents=True,
            orderBy="startTime",
        )
        .execute()
    )
    events = []
    for item in result.get("items", []):
        start_raw = item["start"].get("dateTime", item["start"].get("date"))
        end_raw = item["end"].get("dateTime", item["end"].get("date"))
        start_dt = _parse_dt(start_raw)
        end_dt = _parse_dt(end_raw)
        events.append({"summary": item.get("summary", "Untitled"), "start_dt": start_dt, "end_dt": end_dt})
    return events


def check_task_conflict(task_time: datetime, duration_minutes: int, events: list) -> list[str]:
    """Return names of calendar events that overlap with [task_time, task_time + duration]."""
    if not task_time:
        return []
    task_end = task_time + timedelta(minutes=max(duration_minutes, 1))
    conflicts = []
    for event in events:
        if not event.get("start_dt"):
            continue
        evt_start = event["start_dt"].replace(tzinfo=None)
        evt_end = (
            event["end_dt"].replace(tzinfo=None)
            if event.get("end_dt")
            else evt_start + timedelta(hours=1)
        )
        if task_time < evt_end and task_end > evt_start:
            conflicts.append(event["summary"])
    return conflicts


def _parse_dt(raw: str) -> Optional[datetime]:
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
