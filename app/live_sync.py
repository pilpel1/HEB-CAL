"""סנכרון חי בין מכשירים: מונה שינויים ב-SQLite וזרם SSE.

הבוט וסנכרון גוגל רצים בתהליך נפרד, לכן הפאב/סאב הוא שורה ב-``live_sync``
ולא זיכרון של Flask. כל חיבור SSE פותח חיבור SQLite קצר לכל בדיקה —
בלי snapshot ישן ובלי לחסום כתיבות על חיבור ארוך.
"""
from __future__ import annotations

import json
import os
import re
import sqlite3
import time
from datetime import datetime, timezone

from flask import Response, has_request_context, request

from app.database import SCHEMA_BUSY_TIMEOUT_MS, get_database_path, get_db

CLIENT_HEADER = "X-Heb-Cal-Client"
CLIENT_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
ALLOWED_ACTIONS = frozenset({"created", "updated", "deleted", "changed"})


def _utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def poll_interval() -> float:
    raw = (os.getenv("HEB_CAL_LIVE_SYNC_POLL") or "").strip()
    if not raw:
        return 0.8
    try:
        return max(0.05, min(5.0, float(raw)))
    except ValueError:
        return 0.8


def keepalive_interval() -> float:
    raw = (os.getenv("HEB_CAL_LIVE_SYNC_KEEPALIVE") or "").strip()
    if not raw:
        return 15.0
    try:
        return max(5.0, min(60.0, float(raw)))
    except ValueError:
        return 15.0


def ensure_live_sync_schema(db) -> None:
    """טבלה אחת. בלי העלאת user_version — ה-DDL אידמפוטנטי."""
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS live_sync (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            revision INTEGER NOT NULL DEFAULT 0,
            origin TEXT,
            event_ids TEXT NOT NULL DEFAULT '[]',
            action TEXT,
            updated_at TEXT
        )
        """
    )
    db.execute(
        "INSERT OR IGNORE INTO live_sync (id, revision, event_ids) VALUES (1, 0, '[]')"
    )
    db.commit()


def clean_client_id(value) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not CLIENT_ID_RE.fullmatch(text):
        return None
    return text


def current_client_id() -> str | None:
    if not has_request_context():
        return None
    header = request.headers.get(CLIENT_HEADER)
    if header:
        cleaned = clean_client_id(header)
        if cleaned:
            return cleaned
    return clean_client_id(request.args.get("client"))


def _ids_payload(event_ids) -> list[int]:
    if not event_ids:
        return []
    cleaned: list[int] = []
    seen: set[int] = set()
    for item in event_ids:
        try:
            number = int(item)
        except (TypeError, ValueError):
            continue
        if number <= 0 or number in seen:
            continue
        seen.add(number)
        cleaned.append(number)
        if len(cleaned) > 100:
            return []
    return cleaned


def bump_events_revision(*, origin=None, event_ids=None, action="changed", commit: bool = True) -> int:
    """מעלה את המונה אחרי מוטציה שהצליחה. origin=None נלקח מהבקשה אם יש."""
    db = get_db()
    if origin is None:
        origin = current_client_id()
    else:
        origin = clean_client_id(origin)
    if action not in ALLOWED_ACTIONS:
        action = "changed"
    ids = _ids_payload(event_ids)
    stamp = _utc_stamp()
    db.execute(
        """
        INSERT INTO live_sync (id, revision, origin, event_ids, action, updated_at)
        VALUES (1, 1, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            revision = live_sync.revision + 1,
            origin = excluded.origin,
            event_ids = excluded.event_ids,
            action = excluded.action,
            updated_at = excluded.updated_at
        """,
        (origin, json.dumps(ids), action, stamp),
    )
    if commit:
        db.commit()
    row = db.execute("SELECT revision FROM live_sync WHERE id = 1").fetchone()
    return int(row[0]) if row else 1


def _row_to_snapshot(row) -> dict:
    if row is None:
        return {"revision": 0, "origin": None, "ids": [], "action": None}
    try:
        ids = json.loads(row["event_ids"] or "[]")
    except (TypeError, json.JSONDecodeError):
        ids = []
    if not isinstance(ids, list):
        ids = []
    clean_ids = []
    for item in ids:
        try:
            clean_ids.append(int(item))
        except (TypeError, ValueError):
            continue
    action = row["action"] if row["action"] in ALLOWED_ACTIONS else None
    return {
        "revision": int(row["revision"] or 0),
        "origin": row["origin"],
        "ids": clean_ids,
        "action": action,
    }


def read_live_sync_snapshot() -> dict:
    """חיבור קצר — רואה קומיטים מתהליכים אחרים, בלי g.db של בקשת ה-SSE."""
    conn = sqlite3.connect(
        str(get_database_path()),
        timeout=SCHEMA_BUSY_TIMEOUT_MS / 1000,
    )
    try:
        conn.row_factory = sqlite3.Row
        conn.execute(f"PRAGMA busy_timeout = {SCHEMA_BUSY_TIMEOUT_MS}")
        row = conn.execute(
            "SELECT revision, origin, event_ids, action FROM live_sync WHERE id = 1"
        ).fetchone()
        return _row_to_snapshot(row)
    except sqlite3.Error:
        return {"revision": 0, "origin": None, "ids": [], "action": None}
    finally:
        conn.close()


def _sse_encode(event: str, data: dict, event_id=None) -> str:
    lines = [f"event: {event}", f"data: {json.dumps(data, ensure_ascii=False)}"]
    if event_id is not None:
        lines.insert(0, f"id: {event_id}")
    return "\n".join(lines) + "\n\n"


def generate_live_sync_sse(last_event_id: str | None = None):
    yield "retry: 2000\n\n"
    snap = read_live_sync_snapshot()
    last_revision = snap["revision"]
    yield _sse_encode(
        "hello",
        {"type": "hello", "revision": last_revision},
        event_id=last_revision,
    )
    if last_event_id and last_event_id.isdigit():
        try:
            seen = int(last_event_id)
        except ValueError:
            seen = last_revision
        if last_revision > seen:
            yield _sse_encode(
                "changed",
                {
                    "type": "changed",
                    "revision": last_revision,
                    "origin": snap["origin"],
                    "ids": snap["ids"],
                    "action": snap["action"] or "changed",
                },
                event_id=last_revision,
            )

    poll = poll_interval()
    keepalive = keepalive_interval()
    idle = 0.0
    try:
        while True:
            time.sleep(poll)
            snap = read_live_sync_snapshot()
            if snap["revision"] != last_revision:
                last_revision = snap["revision"]
                idle = 0.0
                yield _sse_encode(
                    "changed",
                    {
                        "type": "changed",
                        "revision": last_revision,
                        "origin": snap["origin"],
                        "ids": snap["ids"],
                        "action": snap["action"] or "changed",
                    },
                    event_id=last_revision,
                )
            else:
                idle += poll
                if idle >= keepalive:
                    idle = 0.0
                    yield ": keepalive\n\n"
    except GeneratorExit:
        return


def live_sync_response() -> Response:
    last_event_id = (request.headers.get("Last-Event-ID") or "").strip()
    response = Response(
        generate_live_sync_sse(last_event_id or None),
        mimetype="text/event-stream",
    )
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["X-Accel-Buffering"] = "no"
    response.headers["Connection"] = "keep-alive"
    response.timeout = None
    return response
