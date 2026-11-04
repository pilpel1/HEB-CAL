"""דגלי תפקיד על משתמש. הוספת דגל עתידי: שורה כאן + עמודה ב-_PEOPLE_COLUMNS."""
from __future__ import annotations

# (api_key, default_when_missing, תווית עברית לממשק)
USER_FLAGS = (
    ("receives_reminders", False, "תזכורות"),
    ("works_shifts", False, "משמרות"),
    ("daily_digest_enabled", False, "סיכום בוקר"),
)

USER_FLAG_KEYS = tuple(item[0] for item in USER_FLAGS)
