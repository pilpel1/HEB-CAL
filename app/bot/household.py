"""בית אחד בפועל (``household_settings``). אם יש יותר משורה — לא מנחשים."""
from __future__ import annotations

from app.database import get_db
from app.services.shifts import set_shifts_enabled


def list_households() -> list[dict]:
    rows = get_db().execute(
        "SELECT id, shifts_enabled FROM household_settings ORDER BY id"
    ).fetchall()
    found = [
        {
            "id": int(row["id"]),
            "shifts_enabled": bool(row["shifts_enabled"]),
            "name": "הבית",
        }
        for row in rows
    ]
    if not found:
        return [{"id": 1, "shifts_enabled": False, "name": "הבית"}]
    if len(found) > 1:
        for item in found:
            item["name"] = f"בית {item['id']}"
    return found


def set_household_shifts(household_id: int, enabled: bool) -> bool:
    """בית 1 עובר ב-``set_shifts_enabled`` כמו האתר. בית אחר רק אם השורה קיימת."""
    household_id = int(household_id)
    if household_id == 1:
        return set_shifts_enabled(enabled)
    db = get_db()
    cursor = db.execute(
        "UPDATE household_settings SET shifts_enabled = ? WHERE id = ?",
        (1 if enabled else 0, household_id),
    )
    db.commit()
    if cursor.rowcount == 0:
        raise LookupError("הבית לא נמצא")
    return bool(enabled)
