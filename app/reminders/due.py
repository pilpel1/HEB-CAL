"""מי בוחר תזכורות שהגיע זמנן — משותף ל-worker ול-API של הדפדפן.

Web Push עתידי צריך לקרוא ל-``browser_due`` (או לחלץ payload זהה) ולרשום
שליחה בטבלה נפרדת לפי ערוץ. ``sent_at`` נשאר חותמת הטלגרם בלבד.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.reminders.repository import (
    list_people,
    load_reminder_rows,
    reminder_to_dict,
    sent_chat_keys,
)
from app.reminders.schedule import (
    apply_offset,
    browser_body,
    event_start,
    is_due,
    in_browser_window,
    reminder_default_time,
    reminder_message,
    reminder_timezone,
)
from app.services.recurrence import expand_event, is_recurring

# תזכורת של מופע ישן (יותר מיום וחצי) לא נשלחת שוב כשמוסיפים חזרה.
RECURRENCE_LOOKBACK = timedelta(hours=36)


def _people_by_id() -> dict[int, dict]:
    return {person["id"]: person for person in list_people()}


def _chat_ids(recipient_ids, people_by_id) -> list[str]:
    found = []
    for person_id in recipient_ids:
        person = people_by_id.get(int(person_id))
        if not person:
            continue
        chat_id = (person.get("telegram_chat_id") or "").strip()
        if chat_id and chat_id not in found:
            found.append(chat_id)
    return found


def _event_from_row(row) -> dict:
    return {
        "id": row["event_id"],
        "title": row["title"],
        "gregorian_date": row["gregorian_date"],
        "hebrew_date": row["hebrew_date"],
        "time": row["time"],
        "description": row["description"],
        "end_date": row["end_date"],
        "recurrence_freq": row.get("recurrence_freq"),
        "recurrence_calendar": row.get("recurrence_calendar"),
        "recurrence_until": row.get("recurrence_until"),
        "recurrence_count": row.get("recurrence_count"),
        "exceptions": row.get("exceptions") or [],
    }


def _occurrences_for_reminder(event: dict, current: datetime, offset_minutes: int) -> list[dict]:
    if not is_recurring(event):
        return [{
            **event,
            "occurrence_date": event.get("gregorian_date"),
            "recurring": False,
        }]
    offset = max(0, int(offset_minutes))
    utc = current.astimezone(timezone.utc)
    local = current.tzinfo
    start_from = (utc - RECURRENCE_LOOKBACK).astimezone(local).date()
    start_to = (utc + timedelta(minutes=offset) + timedelta(days=2)).astimezone(local).date()
    return expand_event(event, event.get("exceptions") or [], start_from, start_to)


def _evaluated(now: datetime | None = None):
    tz = reminder_timezone()
    default_time = reminder_default_time()
    current = now or datetime.now(tz)
    if current.tzinfo is None:
        current = current.replace(tzinfo=tz)
    else:
        current = current.astimezone(tz)
    people = _people_by_id()
    sent_keys = sent_chat_keys()
    rows = load_reminder_rows()
    from app.database import exceptions_for_events

    exception_map = exceptions_for_events([row["event_id"] for row in rows])
    items = []
    for row in rows:
        event = _event_from_row(row)
        event["exceptions"] = exception_map.get(row["event_id"], [])
        reminder = reminder_to_dict(row)
        chat_ids = _chat_ids(reminder["recipient_ids"], people)
        recurring = is_recurring(event)
        for occ in _occurrences_for_reminder(event, current, row["offset_minutes"]):
            display = {
                "title": occ.get("title") or event.get("title"),
                "gregorian_date": occ.get("gregorian_date"),
                "hebrew_date": occ.get("hebrew_date") or event.get("hebrew_date"),
                "time": occ.get("time") if occ.get("time") is not None else event.get("time"),
                "description": occ.get("description") if occ.get("description") is not None else event.get("description"),
                "end_date": occ.get("end_date"),
            }
            try:
                start = event_start(display, tz=tz, default_time=default_time)
            except (ValueError, TypeError):
                continue
            fire = apply_offset(start, int(row["offset_minutes"]))
            if fire.astimezone(timezone.utc) < current.astimezone(timezone.utc) - RECURRENCE_LOOKBACK:
                continue
            occurrence_date = occ.get("occurrence_date") or event.get("gregorian_date")
            if not recurring and row["sent_at"]:
                pending_chats = []
            else:
                pending_chats = [
                    chat_id
                    for chat_id in chat_ids
                    if (row["id"], occurrence_date, chat_id) not in sent_keys
                    and (row["id"], occurrence_date, "") not in sent_keys
                ]
            items.append({
                "row": row,
                "event": display,
                "reminder": reminder,
                "start": start,
                "fire": fire,
                "chat_ids": pending_chats,
                "occurrence_date": occurrence_date,
                "already_sent": not pending_chats,
            })
    return current, items


def telegram_due(now: datetime | None = None) -> list[dict]:
    """תזכורות שלא נשלחו בטלגרם, שהמועד שלהן עבר, ויש להן לפחות צ'אט אחד."""
    current, items = _evaluated(now)
    due = []
    for item in items:
        row = item["row"]
        if item["already_sent"] or not is_due(item["fire"], current, None):
            continue
        if not item["chat_ids"]:
            continue
        due.append({
            "id": row["id"],
            "event_id": row["event_id"],
            "offset_minutes": row["offset_minutes"],
            "occurrence_date": item["occurrence_date"],
            "chat_ids": item["chat_ids"],
            "text": reminder_message(item["event"], row["offset_minutes"], item["start"]),
            "fire_at": item["fire"].isoformat(),
        })
    return due


def browser_due(
    now: datetime | None = None,
    *,
    within_seconds: int = 90,
    grace_seconds: int = 900,
) -> list[dict]:
    """תזכורות שהדפדפן צריך להציג כשהאפליקציה פתוחה.

    כולל תזכורות שכבר נשלחו בטלגרם, בתוך חלון החסד, כדי שטאב פתוח לא יפספס
    אותן. הלקוח מסנן כפילויות לפי ``tag``.
    """
    within_seconds = max(0, min(int(within_seconds), 3600))
    grace_seconds = max(0, min(int(grace_seconds), 24 * 3600))
    current, items = _evaluated(now)
    visible = []
    for item in items:
        if not in_browser_window(
            item["fire"],
            current,
            within_seconds=within_seconds,
            grace_seconds=grace_seconds,
        ):
            continue
        row = item["row"]
        fire_iso = item["fire"].isoformat()
        occurrence_date = item["occurrence_date"] or ""
        visible.append({
            "id": row["id"],
            "event_id": row["event_id"],
            "offset_minutes": row["offset_minutes"],
            "occurrence_date": item["occurrence_date"],
            "recipient_ids": item["reminder"]["recipient_ids"],
            "title": item["event"]["title"],
            "body": browser_body(
                item["event"],
                row["offset_minutes"],
                item["start"],
                item["fire"],
                current,
            ),
            "tag": f"heb-cal-reminder-{row['id']}-{occurrence_date}-{fire_iso}",
            "fire_at": fire_iso,
            "event_start": item["start"].isoformat(),
        })
    return visible
