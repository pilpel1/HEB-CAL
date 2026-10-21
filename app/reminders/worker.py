"""סבב שליחה: תזכורות שהגיע זמנן + מענה ל-/start.

הרצה מהשורש של הריפו:

    python scripts/reminder_worker.py
    python -m app.reminders.worker --once
"""
from __future__ import annotations

import argparse
import os
import sys
import time

from app.reminders.due import telegram_due
from app.reminders.repository import mark_reminder_sent
from app.reminders.telegram import TelegramError, consume_updates, send_message


def bot_token() -> str:
    return (os.getenv("TELEGRAM_BOT_TOKEN") or "").strip()


def poll_seconds() -> int:
    raw = (os.getenv("REMINDER_POLL_SECONDS") or "45").strip()
    try:
        value = int(raw)
    except ValueError:
        value = 45
    return max(30, min(value, 60))


def process_due_reminders(*, now=None, send=None, token: str | None = None) -> int:
    """שולח תזכורות due ומסמן sent_at רק אחרי הצלחה לכל הצ'אטים שלהן."""
    token = bot_token() if token is None else token.strip()
    sender = send or send_message
    delivered = 0
    for item in telegram_due(now=now):
        if not token:
            print(
                f"reminder {item['id']} is due but TELEGRAM_BOT_TOKEN is empty; not marked sent",
                file=sys.stderr,
            )
            continue
        ok = True
        for chat_id in item["chat_ids"]:
            try:
                sender(token, chat_id, item["text"])
            except Exception as exc:
                ok = False
                print(
                    f"reminder {item['id']} chat {chat_id} failed: {exc}",
                    file=sys.stderr,
                )
        if ok:
            mark_reminder_sent(item["id"], occurrence_date=item.get("occurrence_date"))
            delivered += 1
            print(f"sent reminder {item['id']} for event {item['event_id']}")
    return delivered


def run_once(*, long_poll: int = 0, offset: int | None = None) -> int | None:
    process_due_reminders()
    token = bot_token()
    if not token:
        print("TELEGRAM_BOT_TOKEN is empty; /start handler skipped", file=sys.stderr)
        return offset
    try:
        return consume_updates(token, offset, long_poll=long_poll)
    except TelegramError as exc:
        print(f"telegram updates failed: {exc}", file=sys.stderr)
        return offset


def run_loop(interval: int | None = None) -> None:
    interval = poll_seconds() if interval is None else max(30, min(int(interval), 60))
    offset = None
    print(f"reminder worker started, interval {interval}s")
    while True:
        started = time.monotonic()
        process_due_reminders()
        token = bot_token()
        if token:
            # ה-long-poll מחזיק את הסבב פתוח: /start נענה תוך כדי, ו-due נבדק שוב אחריו
            try:
                offset = consume_updates(token, offset, long_poll=min(50, interval))
            except TelegramError as exc:
                print(f"telegram updates failed: {exc}", file=sys.stderr)
        elapsed = time.monotonic() - started
        remaining = interval - elapsed
        if remaining > 0:
            time.sleep(remaining)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="שליחת תזכורות טלגרם ומענה ל-/start")
    parser.add_argument(
        "--once",
        action="store_true",
        help="סבב אחד (due + getUpdates בלי המתנה) ואז יציאה",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=None,
        help="שניות בין סבבים (30–60, ברירת מחדל REMINDER_POLL_SECONDS או 45)",
    )
    args = parser.parse_args(argv)

    # טוען .env ומאתחל סכמה. הייבוא כאן כדי ש--help לא יפתח DB.
    from app import app

    with app.app_context():
        if args.once:
            run_once(long_poll=0)
            return 0
        try:
            run_loop(args.interval)
        except KeyboardInterrupt:
            print("reminder worker stopped")
            return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
