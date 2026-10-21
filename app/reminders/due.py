"""מי בוחר תזכורות שהגיע זמנן — משותף ל-worker ול-API של הדפדפן.

Web Push עתידי צריך לקרוא ל-``browser_due`` (או לחלץ payload זהה) ולרשום
שליחה בטבלה נפרדת לפי ערוץ. ``sent_at`` נשאר חותמת הטלגרם בלבד.
"""
from __future__ import annotations

from datetime import datetime

from app.reminders.repository import list_people, load_reminder_rows, reminder_to_dict
from app.reminders.schedule import (
    browser_body,
    fire_at,
    is_due,
    in_browser_window,
    occurrence_start,
    reminder_default_time,
    reminder_message,
    reminder_timezone,
)


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


def _evaluated(now: datetime | None = None):
    tz = reminder_timezone()
    default_time = reminder_default_time()
    current = now or datetime.now(tz)
    people = _people_by_id()
    items = []
    for row in load_reminder_rows():
        event = {
            "title": row["title"],
            "gregorian_date": row["gregorian_date"],
            "hebrew_date": row["hebrew_date"],
            "time": row["time"],
            "description": row["description"],
            "end_date": row["end_date"],
        }
        try:
            start = occurrence_start(event, current, tz=tz, default_time=default_time)
            fire = fire_at(
                event,
                row["offset_minutes"],
                now=current,
                tz=tz,
                default_time=default_time,
            )
        except (ValueError, TypeError):
            continue
        reminder = reminder_to_dict(row)
        items.append({
            "row": row,
            "event": event,
            "reminder": reminder,
            "start": start,
            "fire": fire,
            "chat_ids": _chat_ids(reminder["recipient_ids"], people),
        })
    return current, items


def telegram_due(now: datetime | None = None) -> list[dict]:
    """תזכורות שלא נשלחו בטלגרם, שהמועד שלהן עבר, ויש להן לפחות צ'אט אחד."""
    current, items = _evaluated(now)
    due = []
    for item in items:
        row = item["row"]
        if not is_due(item["fire"], current, row["sent_at"]):
            continue
        if not item["chat_ids"]:
            continue
        due.append({
            "id": row["id"],
            "event_id": row["event_id"],
            "offset_minutes": row["offset_minutes"],
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
        visible.append({
            "id": row["id"],
            "event_id": row["event_id"],
            "offset_minutes": row["offset_minutes"],
            "recipient_ids": item["reminder"]["recipient_ids"],
            "title": item["event"]["title"],
            "body": browser_body(
                item["event"],
                row["offset_minutes"],
                item["start"],
                item["fire"],
                current,
            ),
            "tag": f"heb-cal-reminder-{row['id']}-{fire_iso}",
            "fire_at": fire_iso,
            "event_start": item["start"].isoformat(),
        })
    return visible
