"""סיכום בוקר בטלגרם: לוח זמנים, תוכן, ושליחה אידמפוטנטית.

ברירת מחדל: כל יום א׳–ו׳ ב-06:00 לפי ``REMINDER_TIMEZONE`` (Asia/Jerusalem).
לא נשלח בשבת. בשישי ההודעה כוללת גם את שבת.
רק אדם עם ``telegram_chat_id`` ו-``daily_digest_enabled`` מקבל.
"""
from __future__ import annotations

import os
import sys
from datetime import date, datetime, timedelta

from app.bot.query import collect_list
from app.reminders.repository import list_people
from app.reminders.schedule import reminder_timezone
from app.services.shifts import weekday_index

DEFAULT_HOUR = 6
DEFAULT_MINUTE = 0
SATURDAY = 6
FRIDAY = 5
EMPTY_DAY = "אין אירועים היום"


def _env_int(name: str, default: int, lo: int, hi: int) -> int:
    raw = (os.getenv(name) or "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    if value < lo or value > hi:
        return default
    return value


def digest_clock() -> tuple[int, int]:
    """שעת הסיכום המקומית. ברירת מחדל 06:00. ערך שבור חוזר לברירת המחדל."""
    return (
        _env_int("DIGEST_HOUR", DEFAULT_HOUR, 0, 23),
        _env_int("DIGEST_MINUTE", DEFAULT_MINUTE, 0, 59),
    )


def local_now(now: datetime | None = None) -> datetime:
    tz = reminder_timezone()
    current = now or datetime.now(tz)
    if current.tzinfo is None:
        current = current.replace(tzinfo=tz)
    return current.astimezone(tz)


def digest_weekdays(day: date) -> bool:
    """True אם ביום הזה נשלח סיכום (א׳–ו׳, לא שבת)."""
    return weekday_index(day) != SATURDAY


def digest_coverage(day: date) -> list[date]:
    """הימים שנכנסים להודעה של אותו בוקר. שישי כולל גם שבת."""
    if weekday_index(day) == FRIDAY:
        return [day, day + timedelta(days=1)]
    return [day]


def digest_ready(now: datetime | None = None) -> bool:
    """הגיע הזמן לשלוח היום (אחרי השעה, ולא שבת)."""
    current = local_now(now)
    if not digest_weekdays(current.date()):
        return False
    hour, minute = digest_clock()
    return (current.hour, current.minute) >= (hour, minute)


def format_digest(days: list[date], people: dict) -> str:
    """טקסט HTML כמו ``/today``, בלי מזהי אירוע ובלי כפתורים."""
    from app.bot import ui
    from app.bot.textutil import esc
    from app.services.recurrence import hebrew_display

    lines = ["☀️ סיכום בוקר"]
    for index, day in enumerate(days):
        if index:
            lines.append("")
        lines.append(f"יום {ui.weekday_name(day)} · {ui.code(ui.greg(day))}")
        lines.append(esc(hebrew_display(day)))
        rows = collect_list("today", day)
        if not rows:
            lines.append(EMPTY_DAY)
            continue
        for event in rows:
            lines.append(ui._event_line(event, people, with_date=False))
    return "\n".join(lines).strip()


def digest_last_sent(person_id: int) -> date | None:
    from app.database import get_db

    row = get_db().execute(
        "SELECT daily_digest_last_sent FROM reminder_people WHERE id = ?",
        (person_id,),
    ).fetchone()
    if row is None or not row["daily_digest_last_sent"]:
        return None
    try:
        return date.fromisoformat(str(row["daily_digest_last_sent"])[:10])
    except ValueError:
        return None


def mark_digest_sent(person_id: int, day: date) -> None:
    from app.database import get_db

    db = get_db()
    db.execute(
        "UPDATE reminder_people SET daily_digest_last_sent = ? WHERE id = ?",
        (day.isoformat(), person_id),
    )
    db.commit()


def opted_in_people() -> list[dict]:
    """רק מי שמחובר לצ'אט והדליק סיכום. בלי צ'אט — לא נשלח."""
    found = []
    for person in list_people():
        chat = (person.get("telegram_chat_id") or "").strip()
        if not chat:
            continue
        if not person.get("daily_digest_enabled"):
            continue
        found.append(person)
    return found


def process_daily_digests(*, now=None, send=None, token: str | None = None) -> int:
    """שולח סיכום לכל נמען שהגיע זמנו, פעם אחת ליום מקומי.

    כמה אנשים על אותו צ'אט מקבלים הודעה אחת. חותמת נרשמת רק אחרי שליחה
    שהצליחה, כדי שקריסה לא תבלע יום.
    """
    from app.reminders.telegram import send_message

    current = local_now(now)
    today = current.date()
    if not digest_ready(current):
        return 0
    token = (os.getenv("TELEGRAM_BOT_TOKEN") or "").strip() if token is None else str(token).strip()
    sender = send or send_message
    people = list_people()
    by_id = {person["id"]: person for person in people}
    recipients = opted_in_people()
    groups: dict[str, list[dict]] = {}
    for person in recipients:
        chat = str(person["telegram_chat_id"]).strip()
        groups.setdefault(chat, []).append(person)

    delivered = 0
    text = format_digest(digest_coverage(today), by_id)
    for chat, members in groups.items():
        pending = [person for person in members if digest_last_sent(person["id"]) != today]
        if not pending:
            continue
        already = [person for person in members if digest_last_sent(person["id"]) == today]
        if already:
            for person in pending:
                mark_digest_sent(person["id"], today)
            continue
        if not token:
            print(
                f"daily digest for chat {chat} is due but TELEGRAM_BOT_TOKEN is empty; not marked sent",
                file=sys.stderr,
            )
            continue
        try:
            sender(token, chat, text)
        except Exception as exc:
            print(f"daily digest chat {chat} failed: {exc}", file=sys.stderr)
            continue
        for person in pending:
            mark_digest_sent(person["id"], today)
        delivered += 1
        print(f"sent daily digest to chat {chat}")
    return delivered
