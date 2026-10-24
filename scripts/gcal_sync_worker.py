#!/usr/bin/env python3
"""סנכרון חד-כיווני מיומן גוגל אל HEB-CAL, בערך כל 15 דקות.

מהשורש של הריפו:

    python scripts/gcal_sync_worker.py
    python scripts/gcal_sync_worker.py --once

הכתובת הסודית נשמרת רק בבסיס. לא מעבירים אותה בדגלים ולא כותבים אותה ללוג.
Worker התזכורות (scripts/reminder_worker.py) מפעיל את אותו סבב, אז בית
שמריץ רק אותו מקבל גם את היומן. מי שלא מריץ טלגרם מריץ את הסקריפט הזה.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.gcal.worker import main

if __name__ == "__main__":
    sys.exit(main())
