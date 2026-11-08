"""דגלי UI מהסביבה. אין מתג במסך למשתמש הקצה."""
from __future__ import annotations

import os

AI_SETTINGS_UI_ENV = "HEB_CAL_AI_SETTINGS_UI"


def ai_settings_ui_enabled() -> bool:
    """כרטיסי עוזר AI בהגדרות. כבוי כברירת מחדל; 1/true/yes/on מחזיר את המסך."""
    raw = os.getenv(AI_SETTINGS_UI_ENV)
    if raw is None or raw.strip() == "":
        return False
    return raw.strip().lower() in {"1", "true", "yes", "on"}
