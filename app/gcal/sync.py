"""משיכה, פענוח, ועדכון אירועים. הכתובת לא נכתבת ללוג."""
from __future__ import annotations

import os
import sys
import urllib.error
import urllib.request
from datetime import date, timedelta

from app.database import get_db
from app.gcal.errors import GcalUserError
from app.gcal.parse import overlaps_window, parse_ical
from app.gcal.repository import (
    get_source_row,
    mark_sync_error,
    mark_sync_success,
    utc_now_stamp,
)
from app.gcal.urls import is_google_ical_url, redact
from app.services.hebrew_format import normalize_hebrew_date_text

PAST_DAYS_DEFAULT = 180
FUTURE_DAYS_DEFAULT = 400
TIMEOUT_SECONDS = 20
MAX_BYTES = 8 * 1024 * 1024

FETCH_TIMEOUT = "החיבור ליומן גוגל לקח יותר מדי זמן. נסו שוב."
FETCH_NETWORK = "לא הצלחנו להגיע ליומן גוגל. בדקו את החיבור ונסו שוב."
FETCH_NOT_FOUND = "היומן לא נמצא. הכתובת הסודית אולי בוטלה. העתיקו אותה מחדש מיומן גוגל."
FETCH_FORBIDDEN = "אין גישה ליומן. העתיקו מחדש את הכתובת הסודית."
FETCH_STATUS = "יומן גוגל החזיר שגיאה. נסו שוב מאוחר יותר."
FETCH_TOO_BIG = "היומן גדול מדי לסנכרון."
FETCH_REDIRECT = "היומן הפנה לכתובת לא מוכרת."
SYNC_FAILED = "הסנכרון נכשל. נסו שוב."


def sync_window(today: date | None = None) -> tuple[date, date]:
    if today is None:
        from datetime import datetime

        from app.reminders.schedule import reminder_timezone

        today = datetime.now(reminder_timezone()).date()
    past = _env_days("GCAL_SYNC_PAST_DAYS", PAST_DAYS_DEFAULT)
    future = _env_days("GCAL_SYNC_FUTURE_DAYS", FUTURE_DAYS_DEFAULT)
    return today - timedelta(days=past), today + timedelta(days=future)


def _env_days(name: str, default: int) -> int:
    raw = (os.getenv(name) or "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return max(1, min(value, 3650))


class _GoogleOnlyRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not is_google_ical_url(newurl):
            raise GcalUserError(FETCH_REDIRECT)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def fetch_ical(url: str, *, timeout: int = TIMEOUT_SECONDS) -> bytes:
    """מוריד את היומן. זורק GcalUserError בעברית, בלי הכתובת."""
    if not is_google_ical_url(url):
        from app.gcal.urls import INVALID_URL

        raise GcalUserError(INVALID_URL)
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "HEB-CAL/1.0 (household calendar sync)"},
        method="GET",
    )
    opener = urllib.request.build_opener(_GoogleOnlyRedirect)
    try:
        with opener.open(request, timeout=timeout) as response:
            status = getattr(response, "status", 200)
            if status != 200:
                raise GcalUserError(_status_message(status))
            return _read_limited(response)
    except GcalUserError:
        raise
    except urllib.error.HTTPError as exc:
        raise GcalUserError(_status_message(exc.code)) from exc
    except TimeoutError as exc:
        raise GcalUserError(FETCH_TIMEOUT) from exc
    except urllib.error.URLError as exc:
        reason = exc.reason
        if isinstance(reason, TimeoutError):
            raise GcalUserError(FETCH_TIMEOUT) from exc
        raise GcalUserError(FETCH_NETWORK) from exc
    except Exception as exc:
        raise GcalUserError(FETCH_NETWORK) from exc


def _status_message(status: int) -> str:
    if status == 404:
        return FETCH_NOT_FOUND
    if status in (401, 403):
        return FETCH_FORBIDDEN
    return FETCH_STATUS


def _read_limited(response) -> bytes:
    chunks = []
    size = 0
    while True:
        chunk = response.read(65536)
        if not chunk:
            break
        size += len(chunk)
        if size > MAX_BYTES:
            raise GcalUserError(FETCH_TOO_BIG)
        chunks.append(chunk)
    return b"".join(chunks)


def sync_source(source_id: int, *, fetch=None, today: date | None = None) -> dict:
    """מסנכרן מקור אחד גם אם הוא כבוי (הכפתור «סנכרן עכשיו»)."""
    row = get_source_row(source_id)
    if row is None:
        raise GcalUserError("החיבור לא נמצא")
    fetcher = fetch or fetch_ical
    window_start, window_end = sync_window(today)
    secret = row["ical_url"]
    try:
        payload = fetcher(secret)
        occurrences = parse_ical(payload, window_start, window_end)
        stats = _apply(source_id, occurrences, window_start, window_end, row["color"])
        stamp = utc_now_stamp()
        mark_sync_success(source_id, stamp)
    except GcalUserError as exc:
        message = redact(str(exc), secret)
        mark_sync_error(source_id, message)
        _log_failure(source_id)
        stats = None
    except Exception:
        mark_sync_error(source_id, SYNC_FAILED)
        _log_failure(source_id)
        stats = None
    from app.gcal.repository import get_source_public

    public = get_source_public(source_id) or {}
    public["sync"] = stats
    return public


def sync_enabled(*, fetch=None, today: date | None = None) -> list[dict]:
    """רק מקורות פעילים. כיבוי עוצר את הסבב, לא מוחק אירועים."""
    db = get_db()
    ids = [
        row["id"]
        for row in db.execute(
            "SELECT id FROM gcal_sources WHERE enabled = 1 ORDER BY id"
        ).fetchall()
    ]
    return [sync_source(source_id, fetch=fetch, today=today) for source_id in ids]


def _log_failure(source_id: int) -> None:
    print(f"gcal sync failed source_id={source_id}", file=sys.stderr)


def _apply(source_id: int, occurrences: list[dict], window_start: date, window_end: date, color) -> dict:
    db = get_db()
    existing = db.execute(
        """
        SELECT id, gcal_uid, gcal_recurrence_id, gregorian_date, end_date
        FROM events
        WHERE gcal_source_id = ?
        """,
        (source_id,),
    ).fetchall()
    by_key = {
        (row["gcal_uid"], row["gcal_recurrence_id"] or ""): row
        for row in existing
    }
    seen: set[tuple[str, str]] = set()
    inserted = 0
    updated = 0
    try:
        db.execute("BEGIN")
        for item in occurrences:
            key = (item["gcal_uid"], item["gcal_recurrence_id"])
            seen.add(key)
            current = by_key.get(key)
            hebrew = normalize_hebrew_date_text(item["hebrew_date"])
            if current is None:
                cursor = db.execute(
                    """
                    INSERT INTO events (
                        title, gregorian_date, hebrew_date, time, description, end_date, color,
                        recurrence_freq, recurrence_calendar, recurrence_until, recurrence_count,
                        is_shift, shift_person_id, shift_label,
                        gcal_source_id, gcal_uid, gcal_recurrence_id
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, NULL, NULL, NULL, NULL, 0, NULL, NULL, ?, ?, ?)
                    """,
                    (
                        item["title"],
                        item["gregorian_date"],
                        hebrew,
                        item["time"],
                        item["description"],
                        item["end_date"],
                        color,
                        source_id,
                        item["gcal_uid"],
                        item["gcal_recurrence_id"],
                    ),
                )
                by_key[key] = {"id": cursor.lastrowid}
                inserted += 1
                continue
            db.execute(
                """
                UPDATE events
                SET title = ?, gregorian_date = ?, hebrew_date = ?, time = ?,
                    description = ?, end_date = ?, color = ?
                WHERE id = ? AND gcal_source_id = ?
                """,
                (
                    item["title"],
                    item["gregorian_date"],
                    hebrew,
                    item["time"],
                    item["description"],
                    item["end_date"],
                    color,
                    current["id"],
                    source_id,
                ),
            )
            updated += 1

        stale = []
        for row in existing:
            key = (row["gcal_uid"], row["gcal_recurrence_id"] or "")
            if key in seen:
                continue
            if overlaps_window(row["gregorian_date"], row["end_date"], window_start, window_end):
                stale.append(row["id"])
        from app.gcal.repository import _delete_event_ids

        _delete_event_ids(db, stale)
        db.commit()
    except Exception:
        db.rollback()
        raise
    return {"inserted": inserted, "updated": updated, "deleted": len(stale)}
