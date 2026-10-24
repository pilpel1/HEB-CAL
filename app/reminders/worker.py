"""סבב שליחה: תזכורות שהגיע זמנן + תפריט הבוט (כפתורים ופקודות).

הלולאה הארוכה מפעילה גם סנכרון יומן גוגל (``app.gcal.worker``), בערך כל 15 דקות.

תזכורות ולחיצות רצות בלולאות נפרדות. לחיצה לא מחכה לסבב התזכורות:
``getUpdates`` עם long poll של 25 שניות רץ ברצף, ו-``answerCallbackQuery``
יוצא לפני בניית המסך.

הרצה מהשורש של הריפו:

    python scripts/reminder_worker.py
    python -m app.reminders.worker --once
"""
from __future__ import annotations

import argparse
import os
import sys
import threading
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
                continue
            mark_reminder_sent(
                item["id"],
                occurrence_date=item.get("occurrence_date"),
                chat_id=str(chat_id),
            )
        if ok:
            if not item.get("occurrence_date"):
                mark_reminder_sent(item["id"])
            delivered += 1
            print(f"sent reminder {item['id']} for event {item['event_id']}")
    return delivered


# Telegram מחזיר getUpdates ברגע שיש עדכון, או אחרי timeout השניות האלה.
UPDATE_LONG_POLL_SECONDS = 25


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


def _reminder_loop(stop: threading.Event, interval: int, process) -> None:
    while not stop.is_set():
        started = time.monotonic()
        try:
            process()
        except Exception as exc:
            print(f"reminder check failed: {exc}", file=sys.stderr)
        remaining = interval - (time.monotonic() - started)
        if stop.wait(max(0.0, remaining)):
            return


def _update_loop(stop: threading.Event, *, consume, token_fn) -> None:
    """long poll רצוף. בלי שינה של סבב התזכורות בין לחיצה ללחיצה."""
    offset = None
    while not stop.is_set():
        token = token_fn()
        if not token:
            if stop.wait(2):
                return
            continue
        try:
            offset = consume(token, offset, long_poll=UPDATE_LONG_POLL_SECONDS)
        except TelegramError as exc:
            print(f"telegram updates failed: {exc}", file=sys.stderr)
            if stop.wait(1):
                return
        except Exception as exc:
            print(f"telegram updates failed: {exc}", file=sys.stderr)
            if stop.wait(1):
                return


def run_loop(
    interval: int | None = None,
    *,
    stop_event: threading.Event | None = None,
    consume=consume_updates,
    process=process_due_reminders,
    token_fn=bot_token,
) -> None:
    """תזכורות במחזור שלהן. לחיצות בשרשור נפרד, לא מחכות ל-process."""
    interval = poll_seconds() if interval is None else max(30, min(int(interval), 60))
    stop = stop_event or threading.Event()
    updater = threading.Thread(
        target=_update_loop,
        args=(stop,),
        kwargs={"consume": consume, "token_fn": token_fn},
        name="telegram-updates",
        daemon=True,
    )
    print(f"reminder worker started, reminders every {interval}s, updates long-poll {UPDATE_LONG_POLL_SECONDS}s")
    updater.start()
    try:
        _reminder_loop(stop, interval, process)
    finally:
        stop.set()
        # ה-long poll התקוע ננטש ביציאה. השרשור daemon לא מחזיק את התהליך.
        updater.join(timeout=1)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="שליחת תזכורות טלגרם ותפריט הבוט")
    parser.add_argument(
        "--once",
        action="store_true",
        help="סבב אחד (due + getUpdates בלי המתנה) ואז יציאה",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=None,
        help="שניות בין בדיקות תזכורות (30–60, ברירת מחדל REMINDER_POLL_SECONDS או 45). לחיצות נענות בנפרד",
    )
    args = parser.parse_args(argv)

    # טוען .env ומאתחל סכמה. הייבוא כאן כדי ש--help לא יפתח DB.
    from app import app

    with app.app_context():
        if args.once:
            run_once(long_poll=0)
            return 0
        from app.gcal.worker import run_loop as gcal_loop
        from app.gcal.worker import sync_interval_seconds

        stop = threading.Event()
        gcal = threading.Thread(
            target=gcal_loop,
            kwargs={"stop": stop, "interval": sync_interval_seconds()},
            name="gcal-sync",
            daemon=True,
        )
        gcal.start()
        try:
            run_loop(args.interval, stop_event=stop)
        except KeyboardInterrupt:
            print("reminder worker stopped")
            return 0
        finally:
            stop.set()
            gcal.join(timeout=1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
