"""מפתחות אישיים לשרת ה-MCP.

הטוקן המלא מוצג פעם אחת ביצירה. בטבלה נשמרים רק ``key_prefix`` (לזיהוי
ולתצוגה) ו-SHA-256 של הטוקן כולו. 32 בתים אקראיים לא צריכים hash איטי.
"""
from __future__ import annotations

import hashlib
import hmac
import re
import secrets
from datetime import date, datetime, time, timedelta, timezone

from app.database import get_db

TOKEN_PREFIX = "hcal"
SLIDING_DAYS = 30
# כתיבת "שימוש אחרון" לכל היותר פעם בדקה לכל מפתח. התפוגה יכולה להקדים
# בדקה לכל היותר, ולעולם לא לאחר.
TOUCH_INTERVAL = timedelta(seconds=60)
ACTIVE_LIMIT = 10
LABEL_MAX = 60
PERMISSIONS = ("read", "write")

_TOKEN_RE = re.compile(r"^hcal_([0-9a-f]{8})_([A-Za-z0-9_-]{43})$")
_STAMP = "%Y-%m-%dT%H:%M:%SZ"


class McpKeyError(ValueError):
    """קלט לא תקין ביצירת מפתח. ההודעה מוצגת למשתמש."""


def utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def _stamp(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime(_STAMP)


def _parse_stamp(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.strptime(value, _STAMP).replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def ensure_mcp_keys_schema(db) -> None:
    """טבלה אחת. בלי העלאת user_version — ה-DDL אידמפוטנטי."""
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS mcp_keys (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            label TEXT NOT NULL,
            key_prefix TEXT NOT NULL UNIQUE,
            secret_hash TEXT NOT NULL,
            permission TEXT NOT NULL CHECK (permission IN ('read', 'write')),
            created_at TEXT NOT NULL,
            last_used_at TEXT,
            expires_at TEXT NOT NULL,
            absolute_expires_at TEXT,
            revoked_at TEXT
        )
        """
    )
    db.execute("CREATE INDEX IF NOT EXISTS idx_mcp_keys_user ON mcp_keys(user_id)")
    db.commit()


def _status(row, now: datetime) -> str:
    if row["revoked_at"]:
        return "revoked"
    expires = _parse_stamp(row["expires_at"])
    if expires is None or now >= expires:
        return "expired"
    absolute = _parse_stamp(row["absolute_expires_at"])
    if absolute is not None and now >= absolute:
        return "expired"
    return "active"


def _effective_expiry(row) -> str | None:
    """המועד שבו המפתח באמת מפסיק: המוקדם מבין חלון 30 הימים ותאריך הסיום."""
    sliding = _parse_stamp(row["expires_at"])
    absolute = _parse_stamp(row["absolute_expires_at"])
    if sliding is None:
        return row["absolute_expires_at"]
    if absolute is None or absolute >= sliding:
        return row["expires_at"]
    return row["absolute_expires_at"]


def _public(row, now: datetime) -> dict:
    return {
        "id": row["id"],
        "user_id": row["user_id"],
        "user_name": row["user_name"],
        "label": row["label"],
        "prefix": f"{TOKEN_PREFIX}_{row['key_prefix']}",
        "permission": row["permission"],
        "created_at": row["created_at"],
        "last_used_at": row["last_used_at"],
        "expires_at": row["expires_at"],
        "absolute_expires_at": row["absolute_expires_at"],
        "effective_expires_at": _effective_expiry(row),
        "revoked_at": row["revoked_at"],
        "status": _status(row, now),
    }


def _people_table(db) -> str:
    from app.users.table import quote_people_table, resolve_people_table

    return quote_people_table(resolve_people_table(db))


def _select_sql(db) -> str:
    people = _people_table(db)
    return f"""
        SELECT k.id, k.user_id, k.label, k.key_prefix, k.permission, k.created_at,
               k.last_used_at, k.expires_at, k.absolute_expires_at, k.revoked_at,
               p.name AS user_name
        FROM mcp_keys k
        LEFT JOIN {people} p ON p.id = k.user_id
    """


def list_keys() -> list[dict]:
    db = get_db()
    now = utc_now()
    rows = db.execute(_select_sql(db) + " ORDER BY k.id DESC").fetchall()
    return [_public(row, now) for row in rows]


def get_key(key_id: int) -> dict | None:
    db = get_db()
    row = db.execute(_select_sql(db) + " WHERE k.id = ?", (key_id,)).fetchone()
    return _public(row, utc_now()) if row else None


def _clean_label(value) -> str:
    text = " ".join(str(value or "").split())
    if not text:
        raise McpKeyError("צריך שם למכשיר או לתוכנה")
    if len(text) > LABEL_MAX:
        raise McpKeyError("השם ארוך מדי")
    return text


def _clean_permission(value) -> str:
    if value in (None, ""):
        return "read"
    if value not in PERMISSIONS:
        raise McpKeyError("הרשאה לא תקינה")
    return value


def _clean_absolute(value, now: datetime) -> str | None:
    """תאריך YYYY-MM-DD. המפתח תקף עד סוף היום הזה בשעון ישראל."""
    if value in (None, ""):
        return None
    try:
        day = date.fromisoformat(str(value).strip())
    except ValueError as exc:
        raise McpKeyError("תאריך התפוגה לא תקין") from exc
    from app.reminders.schedule import reminder_timezone

    local_end = datetime.combine(day + timedelta(days=1), time(0, 0), tzinfo=reminder_timezone())
    if local_end <= now:
        raise McpKeyError("תאריך התפוגה כבר עבר")
    return _stamp(local_end)


def _active_count(db, user_id: int, now: datetime) -> int:
    rows = db.execute(
        "SELECT revoked_at, expires_at, absolute_expires_at FROM mcp_keys WHERE user_id = ? AND revoked_at IS NULL",
        (user_id,),
    ).fetchall()
    return sum(1 for row in rows if _status(row, now) == "active")


def create_key(user_id, label, permission=None, absolute_expires_on=None) -> tuple[str, dict]:
    """(טוקן מלא, שורה ציבורית). הטוקן לא נשמר ולא יוחזר שוב."""
    from app.reminders.repository import get_person

    try:
        user_id = int(user_id)
    except (TypeError, ValueError) as exc:
        raise McpKeyError("בחרו משתמש") from exc
    if get_person(user_id) is None:
        raise McpKeyError("המשתמש לא נמצא")
    label = _clean_label(label)
    permission = _clean_permission(permission)
    now = utc_now()
    absolute = _clean_absolute(absolute_expires_on, now)

    db = get_db()
    if _active_count(db, user_id, now) >= ACTIVE_LIMIT:
        raise McpKeyError(f"למשתמש הזה כבר יש {ACTIVE_LIMIT} מפתחות פעילים. בטלו אחד קודם")

    for _attempt in range(5):
        prefix = secrets.token_hex(4)
        token = f"{TOKEN_PREFIX}_{prefix}_{secrets.token_urlsafe(32)}"
        if not _TOKEN_RE.fullmatch(token):
            continue
        try:
            cursor = db.execute(
                """
                INSERT INTO mcp_keys (
                    user_id, label, key_prefix, secret_hash, permission,
                    created_at, expires_at, absolute_expires_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    user_id,
                    label,
                    prefix,
                    hash_token(token),
                    permission,
                    _stamp(now),
                    _stamp(now + timedelta(days=SLIDING_DAYS)),
                    absolute,
                ),
            )
        except Exception as exc:  # sqlite3.IntegrityError על prefix כפול
            if "UNIQUE" not in str(exc):
                raise
            continue
        db.commit()
        return token, get_key(cursor.lastrowid)
    raise McpKeyError("לא הצלחנו ליצור מפתח. נסו שוב")


def revoke_key(key_id: int) -> bool:
    db = get_db()
    cursor = db.execute(
        "UPDATE mcp_keys SET revoked_at = ? WHERE id = ? AND revoked_at IS NULL",
        (_stamp(utc_now()), key_id),
    )
    db.commit()
    if cursor.rowcount:
        return True
    return db.execute("SELECT 1 FROM mcp_keys WHERE id = ?", (key_id,)).fetchone() is not None


def revoke_keys_for_user(db, user_id: int) -> None:
    """נקרא מתוך מחיקת משתמש, באותה טרנזקציה. בלי commit."""
    if not db.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'mcp_keys'"
    ).fetchone():
        return
    db.execute(
        "UPDATE mcp_keys SET revoked_at = ? WHERE user_id = ? AND revoked_at IS NULL",
        (_stamp(utc_now()), user_id),
    )


def authenticate(token: str | None) -> dict | None:
    """המפתח אם הוא תקף, אחרת None. לא כותב כלום — ``touch`` מאריך."""
    if not token or not isinstance(token, str):
        return None
    match = _TOKEN_RE.fullmatch(token)
    if not match:
        return None
    db = get_db()
    people = _people_table(db)
    row = db.execute(
        f"""
        SELECT k.id, k.user_id, k.permission, k.secret_hash, k.last_used_at,
               k.expires_at, k.absolute_expires_at, k.revoked_at, p.id AS person_id
        FROM mcp_keys k
        LEFT JOIN {people} p ON p.id = k.user_id
        WHERE k.key_prefix = ?
        """,
        (match.group(1),),
    ).fetchone()
    expected = row["secret_hash"] if row else hash_token("hcal_00000000_" + "0" * 43)
    if not hmac.compare_digest(expected, hash_token(token)) or row is None:
        return None
    if row["person_id"] is None:
        return None
    if _status(row, utc_now()) != "active":
        return None
    return {
        "id": row["id"],
        "user_id": row["user_id"],
        "permission": row["permission"],
        "last_used_at": row["last_used_at"],
    }


def touch(key: dict) -> None:
    """שימוש מוצלח: שימוש אחרון = עכשיו, תפוגה = עכשיו + 30 יום. מוגבל לפעם בדקה."""
    now = utc_now()
    last = _parse_stamp(key.get("last_used_at"))
    if last is not None and now - last < TOUCH_INTERVAL:
        return
    db = get_db()
    db.execute(
        """
        UPDATE mcp_keys SET last_used_at = ?, expires_at = ?
        WHERE id = ? AND revoked_at IS NULL
        """,
        (_stamp(now), _stamp(now + timedelta(days=SLIDING_DAYS)), key["id"]),
    )
    db.commit()
