"""פענוח טבלת לוז מ-Markdown (ייצוא Google Docs) לרשומות יום/אירוע/משמרת.

אין כאן כתיבה לבסיס. צבעי המשמרת (ציאן=אביחי, כתום=שירה) לא שורדים
בייצוא, ולכן מועמד למשמרת נשאר בלי אדם.
"""
from __future__ import annotations

import re
from datetime import date

from app.services.event_payload import clean_event_time
from app.services.hebrew_dates import _year_number
from app.services.recurrence import hebrew_display
from app.services.shifts import SHIFT_LABELS

_SHIFT_MODIFIERS = frozenset({"מאוחר", "קצר", "מוקדם"})
_BREAKS = re.compile(r"(?:\x0b|<br\s*/?>)+", re.I)
_STRIKE = re.compile(r"~~(.*?)~~", re.S)
_CLOCK = re.compile(r"(?<!\d)(\d{1,2}:\d{2})(?!\d)")
_HEB_YEAR = re.compile(r"ה?תש[א-ת]*[\"״]?[א-ת]*")
_SEPARATOR = re.compile(r"^:?-{3,}:?$")
_DATE = re.compile(
    r"^(?P<hday>[א-ת]{1,3}[\"״׳']?)"
    r"(?:\s+(?P<hmonth>מרחשוון|חשוון|חשון|כסלו|טבת|שבט|ניסן|אייר|"
    r"סיוון|סיון|תמוז|אלול|תשרי|באב|בשבט|אדר(?:\s*[אב״'׳]+)?|אב))?"
    r"(?:\s+(?P<hyear>ה?תש[א-ת]*[\"״]?[א-ת]*))?"
    r"\s+(?P<greg>\d{1,2}(?:\.\d{1,2}(?:\.\d{2,4})?)?)"
    r"(?=\s|$)"
)


class LuzParseError(ValueError):
    """לוז לא ניתן לפענוח."""


def parse_luz(text: str, *, default_year: int | None = None) -> dict:
    """מפענח את כל תאי התאריך במסמך. בלי כתיבה."""
    if not isinstance(text, str):
        raise LuzParseError("הקלט חייב להיות טקסט")
    year = default_year or _gregorian_year_from_heading(text)
    if year is None:
        raise LuzParseError("אין שנת ייחוס. כותרת עם תשפ\"ז או default_year.")

    frags: list[dict] = []
    for raw_cell in _iter_cells(text):
        cell = _clean_cell(raw_cell)
        if not cell:
            continue
        first, rest = _split_lines(cell)
        match = _DATE.match(first)
        if not match:
            continue
        greg = match.group("greg").rstrip(".")
        parts = [int(p) for p in greg.split(".") if p != ""]
        content = first[match.end() :].strip()
        lines = [content] if content else []
        lines.extend(rest)
        hyear = _parse_hebrew_year(match.group("hyear") or "")
        frag_year = None
        if len(parts) == 3:
            frag_year = parts[2] if parts[2] > 100 else 2000 + parts[2]
        elif hyear:
            frag_year = hyear - 3761
        frags.append(
            {
                "day": parts[0],
                "month": parts[1] if len(parts) > 1 else None,
                "year": frag_year,
                "source_label": first[: match.end()].strip(),
                "lines": lines,
            }
        )

    days = []
    for frag, gregorian in zip(frags, _resolve_dates(frags, year)):
        events, shifts = _lines_to_records(frag["lines"], gregorian)
        days.append(
            {
                "gregorian_date": gregorian.isoformat(),
                "hebrew_date": hebrew_display(gregorian),
                "source_label": frag["source_label"],
                "events": events,
                "shift_candidates": shifts,
            }
        )
    records = [row for day in days for row in (*day["shift_candidates"], *day["events"])]
    unassigned = sum(1 for row in records if row.get("is_shift") and row.get("shift_person_id") is None)
    return {
        "days": days,
        "records": records,
        "stats": {
            "days": len(days),
            "events": sum(len(day["events"]) for day in days),
            "shift_candidates": sum(len(day["shift_candidates"]) for day in days),
            "unassigned_shift_candidates": unassigned,
        },
    }


def filter_days(parsed: dict, start: date | None, end: date | None) -> dict:
    """חותך לפי טווח תאריכים כולל. לא כותב כלום."""
    days = []
    for day in parsed["days"]:
        current = date.fromisoformat(day["gregorian_date"])
        if start and current < start:
            continue
        if end and current > end:
            continue
        days.append(day)
    records = [row for day in days for row in (*day["shift_candidates"], *day["events"])]
    return {
        "days": days,
        "records": records,
        "stats": {
            "days": len(days),
            "events": sum(len(day["events"]) for day in days),
            "shift_candidates": sum(len(day["shift_candidates"]) for day in days),
            "unassigned_shift_candidates": sum(
                1 for row in records if row.get("is_shift") and row.get("shift_person_id") is None
            ),
        },
    }


def _gregorian_year_from_heading(text: str) -> int | None:
    for match in _HEB_YEAR.finditer(text):
        year = _parse_hebrew_year(match.group(0))
        if year:
            return year - 3761
    return None


def _parse_hebrew_year(token: str) -> int | None:
    letters = re.sub(r"[\"״'׳]", "", (token or "").strip())
    if not letters:
        return None
    return _year_number(letters)


def _iter_cells(text: str):
    # לא splitlines: Google Docs שם VT (\\x0b) כשבירת-רכות בתוך תא, ו-splitlines חותך שם.
    for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        stripped = line.strip(" \t")
        if not stripped.startswith("|"):
            continue
        cells = [part.strip() for part in stripped.strip("|").split("|")]
        if cells and all(_SEPARATOR.fullmatch(part.replace(" ", "") or "") for part in cells):
            continue
        yield from cells


def _clean_cell(raw: str) -> str:
    text = _STRIKE.sub(r"\1", raw or "")
    text = text.replace(r"\)", ")").replace(r"\-", "-").replace(r"\*", "*")
    return text.replace("\u00a0", " ").strip()


def _split_lines(cell: str) -> tuple[str, list[str]]:
    parts = [part.strip() for part in _BREAKS.split(cell.replace("\r\n", "\n"))]
    lines: list[str] = []
    for part in parts:
        lines.extend(line.strip() for line in part.split("\n") if line.strip())
    if not lines:
        return "", []
    return lines[0], lines[1:]


def _resolve_dates(frags: list[dict], default_year: int) -> list[date]:
    n = len(frags)
    days = [frag["day"] for frag in frags]
    months = [frag["month"] for frag in frags]
    years = [frag["year"] or default_year for frag in frags]
    filled = [None] * n
    month = None
    prev = None
    for i in range(n):
        if months[i] is not None:
            month = months[i]
        elif month is not None and prev is not None and days[i] < prev:
            month += 1
            if month > 12:
                month = 1
                years[i] += 1
        filled[i] = month
        prev = days[i]
    month = None
    prev = None
    for i in range(n - 1, -1, -1):
        if filled[i] is not None:
            month = filled[i]
            prev = days[i]
            continue
        if month is None:
            continue
        if prev is not None and days[i] > prev:
            month -= 1
            if month < 1:
                month = 12
                years[i] -= 1
        filled[i] = month
        prev = days[i]
    out = []
    for i, frag in enumerate(frags):
        if filled[i] is None:
            raise LuzParseError(f"אין חודש לתאריך {frag['source_label']}")
        out.append(date(years[i], filled[i], days[i]))
    return out


def _lines_to_records(lines: list[str], gregorian: date) -> tuple[list[dict], list[dict]]:
    events: list[dict] = []
    shifts: list[dict] = []
    hebrew = hebrew_display(gregorian)
    iso = gregorian.isoformat()
    for line in lines:
        text = line.strip()
        if not text:
            continue
        labels, leftover = _shift_tokens(text)
        if labels and not leftover:
            for label in labels:
                shifts.append(_record(label, iso, hebrew, is_shift=True, shift_label=label))
            continue
        events.append(
            _record(
                text,
                iso,
                hebrew,
                is_shift=False,
                time=_first_clock(text),
                shift_hints=labels or None,
            )
        )
    return events, shifts


def _shift_tokens(line: str) -> tuple[list[str], bool]:
    core = re.sub(r"\([^)]*\)", " ", line)
    tokens = [tok.strip(".,;:!?") for tok in core.split() if tok.strip(".,;:!?")]
    labels: list[str] = []
    leftover = False
    i = 0
    while i < len(tokens):
        token = tokens[i]
        if token in SHIFT_LABELS:
            labels.append(token)
            i += 1
            if i < len(tokens) and tokens[i] in _SHIFT_MODIFIERS:
                i += 1
            continue
        if token.lower() == "it":
            labels.append("IT")
            i += 1
            continue
        if token == "משמרת" and i + 1 < len(tokens) and tokens[i + 1].lower() == "it":
            labels.append("IT")
            i += 2
            continue
        leftover = True
        i += 1
    return labels, leftover


def _first_clock(text: str) -> str | None:
    match = _CLOCK.search(text)
    if not match:
        return None
    try:
        return clean_event_time(match.group(1))
    except ValueError:
        return None


def _record(title, gregorian_date, hebrew_date, *, is_shift, shift_label=None, time=None, shift_hints=None):
    row = {
        "title": title,
        "gregorian_date": gregorian_date,
        "hebrew_date": hebrew_date,
        "time": None if is_shift else time,
        "description": "",
        "end_date": None,
        "color": None,
        "is_shift": 1 if is_shift else 0,
        "shift_person_id": None,
        "shift_person_name": None,
        "shift_label": shift_label if is_shift else None,
    }
    if not is_shift and shift_hints:
        row["shift_hints"] = shift_hints
    return row


def format_text_preview(parsed: dict) -> str:
    """תקציר קריא לתיאור PR — לא JSON."""
    lines = [
        f"ימים: {parsed['stats']['days']} · "
        f"אירועים: {parsed['stats']['events']} · "
        f"מועמדי משמרת (בלי אדם): {parsed['stats']['shift_candidates']}"
    ]
    for day in parsed["days"]:
        lines.append(f"\n{day['gregorian_date']} · {day['hebrew_date']} · {day['source_label']}")
        for shift in day["shift_candidates"]:
            lines.append(f"  משמרת? {shift['shift_label']} (בלי שיוך)")
        for event in day["events"]:
            clock = f"{event['time']} " if event.get("time") else ""
            hints = event.get("shift_hints") or []
            hint = f"  [רמזי משמרת: {', '.join(hints)}]" if hints else ""
            lines.append(f"  אירוע: {clock}{event['title']}{hint}")
        if not day["shift_candidates"] and not day["events"]:
            lines.append("  (ריק)")
    return "\n".join(lines) + "\n"
