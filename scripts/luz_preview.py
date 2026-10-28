#!/usr/bin/env python3
"""תצוגת JSON יבשה של ייצוא לוז מ-Markdown. בלי כתיבה לבסיס.

מהשורש של הריפו:

    python scripts/luz_preview.py tests/fixtures/luz_sample_week.md
    python scripts/luz_preview.py path.md --from 2026-10-28 --to 2026-11-03
    python scripts/luz_preview.py path.md --text
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.luz.parse import LuzParseError, filter_days, format_text_preview, parse_luz


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="תצוגה יבשה של לוז מ-Markdown")
    parser.add_argument("path", type=Path, help="קובץ Markdown מייצוא Google Docs")
    parser.add_argument("--year", type=int, default=None, help="שנת ייחוס לועזית אם אין תשפ\"ז בכותרת")
    parser.add_argument("--from", dest="start", default=None, help="YYYY-MM-DD כולל")
    parser.add_argument("--to", dest="end", default=None, help="YYYY-MM-DD כולל")
    parser.add_argument("--text", action="store_true", help="תקציר קריא במקום JSON")
    args = parser.parse_args(argv)

    try:
        text = args.path.read_text(encoding="utf-8")
        parsed = parse_luz(text, default_year=args.year)
        start = date.fromisoformat(args.start) if args.start else None
        end = date.fromisoformat(args.end) if args.end else None
        if start or end:
            parsed = filter_days(parsed, start, end)
    except (OSError, LuzParseError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 1

    if args.text:
        sys.stdout.write(format_text_preview(parsed))
        return 0
    json.dump(parsed, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
