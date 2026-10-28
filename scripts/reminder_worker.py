#!/usr/bin/env python3
"""נקודת כניסה ל-worker: תזכורות טלגרם, סיכום בוקר, ותפריט הבוט (בלי מודל שפה).

אותו תהליך מסנכרן גם יומן גוגל (כתובת iCal) בערך כל 15 דקות.
בלי טלגרם אפשר להריץ רק את ``scripts/gcal_sync_worker.py``.

תזכורות ולחיצות רצות במקביל. לחיצה נענית ב-long poll, לא במחזור התזכורות.

מהשורש של הריפו:

    python scripts/reminder_worker.py
    python scripts/reminder_worker.py --once

הטוקן נקרא רק מ-TELEGRAM_BOT_TOKEN (קובץ .env או הסביבה). לא לשמור טוקן אמיתי בגיט.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.reminders.worker import main

if __name__ == "__main__":
    sys.exit(main())
