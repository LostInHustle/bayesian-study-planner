import os
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from .schedule import TimeBlock

SCOPES = ["https://www.googleapis.com/auth/calendar.events"]
PLAN_PROPERTY = "bayesianStudyPlanner"


@dataclass
class CalendarSchedule:
    busy: list[TimeBlock]
    planned_events: dict[date, list[str]]
    started_days: set[date]


def connect(credentials_path=Path("credentials.json"), token_path=Path("token.json")):
    """Use the saved token or open the Google sign-in page on the first run."""
    credentials = None
    if token_path.exists():
        credentials = Credentials.from_authorized_user_file(str(token_path), SCOPES)

    if not credentials or not credentials.valid:
        if credentials and credentials.expired and credentials.refresh_token:
            credentials.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                str(credentials_path), SCOPES
            )
            credentials = flow.run_local_server(port=0)

        with token_path.open("w", encoding="utf-8") as token_file:
            os.fchmod(token_file.fileno(), 0o600)
            token_file.write(credentials.to_json())

    return build("calendar", "v3", credentials=credentials)


def get_exam(events, calendar_id, event_id, zone):
    event = events.get(calendarId=calendar_id, eventId=event_id).execute()
    if event.get("status") == "cancelled":
        raise ValueError("The exam event was cancelled.")
    start = event["start"]
    if "date" in start:
        exam_date = date.fromisoformat(start["date"])
    else:
        exam_date = get_event_time(start, zone).astimezone(zone).date()
    return event.get("summary") or "Exam", exam_date


def get_event_time(boundary, calendar_zone):
    if "dateTime" in boundary:
        value = datetime.fromisoformat(boundary["dateTime"])
        if value.tzinfo is None:
            zone = (
                ZoneInfo(boundary["timeZone"])
                if "timeZone" in boundary
                else calendar_zone
            )
            return value.replace(tzinfo=zone)
        return value
    return datetime.combine(
        date.fromisoformat(boundary["date"]), time.min, calendar_zone
    )


def read_schedule(events, calendar_id, dates, now, plan_key):
    """Read the busy times and find the study sessions for this exam."""
    zone = now.tzinfo
    schedule = CalendarSchedule(busy=[], planned_events={}, started_days=set())
    study_dates = set(dates)
    request = events.list(
        calendarId=calendar_id,
        timeMin=datetime.combine(dates[0], time.min, zone).isoformat(),
        timeMax=datetime.combine(
            dates[-1] + timedelta(days=1), time.min, zone
        ).isoformat(),
        singleEvents=True,
    )

    while request is not None:
        page = request.execute()
        calendar_zone = ZoneInfo(page["timeZone"])
        for event in page.get("items", []):
            if event.get("status") == "cancelled":
                continue

            start = get_event_time(event["start"], calendar_zone).astimezone(zone)
            end = get_event_time(event["end"], calendar_zone).astimezone(zone)
            private = event.get("extendedProperties", {}).get("private", {})
            if private.get(PLAN_PROPERTY) == plan_key and start.date() in study_dates:
                # Keep the event ID so a later run can move this session.
                if start.astimezone(UTC) > now.astimezone(UTC):
                    schedule.planned_events.setdefault(start.date(), []).append(
                        event["id"]
                    )
                    continue
                schedule.started_days.add(start.date())

            declined = any(
                attendee.get("self") and attendee.get("responseStatus") == "declined"
                for attendee in event.get("attendees", [])
            )
            if event.get("transparency") != "transparent" and not declined:
                schedule.busy.append(TimeBlock(start, end))

        request = events.list_next(request, page)
    return schedule


def write_plan(events, calendar_id, exam, plan, planned_events, plan_key):
    """Save one study session per day. Remove the old session if the choice is rest."""
    for day in plan:
        previous = planned_events.get(day.date, [])
        if day.session is not None:
            block = day.session
            body = {
                "summary": f"{day.action.capitalize()} study: {exam.title}",
                "start": {
                    "dateTime": block.start.isoformat(),
                    "timeZone": block.start.tzinfo.key,
                },
                "end": {
                    "dateTime": block.end.isoformat(),
                    "timeZone": block.end.tzinfo.key,
                },
                "transparency": "opaque",
                "extendedProperties": {"private": {PLAN_PROPERTY: plan_key}},
            }
            if previous:
                event = events.patch(
                    calendarId=calendar_id, eventId=previous[0], body=body
                ).execute()
                previous = previous[1:]
            else:
                event = events.insert(calendarId=calendar_id, body=body).execute()
            print(
                f"  {day.date}: Saved {day.action} study. "
                f"{event.get('htmlLink', event['id'])}"
            )

        for event_id in previous:
            events.delete(calendarId=calendar_id, eventId=event_id).execute()
            print(f"  {day.date}  Removed an earlier study session.")
