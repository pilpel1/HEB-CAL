"""מסכים: טקסט HTML ומקלדת. בלי גישה לבסיס."""
from __future__ import annotations

from datetime import date, timedelta

from app.bot.query import PAGE_SIZE, PEOPLE_PAGE, clamp_page
from app.bot.textutil import clip, code, esc
from app.services.recurrence import hebrew_display
from app.services.shifts import (
    WEEKDAY_NAMES,
    hebrew_day_month,
    week_heading,
    week_parasha,
    weekday_index,
)

SHIFT_LABELS = {"m": "בוקר", "e": "ערב", "n": "לילה"}
PRESET_TIMES = ("09:00", "12:00", "18:00", "21:00")
MENU_TITLE = "📅 לוח השנה המשותף — מה להציג?"
BTN_MENU = "🏠 תפריט ראשי"
BTN_ADD = "➕ הוספת אירוע"
LIST_HINT = "לחצו על אירוע לפרטים, עריכה או מחיקה."
DAY_LETTERS = ("א׳", "ב׳", "ג׳", "ד׳", "ה׳", "ו׳", "ש׳")
SHIFTS_PER_ROW = 3


_BUTTON_STYLES = frozenset({"danger", "success", "primary"})
# רק כפתור השמירה עצמו. כניסה להוספה נשארת רגילה כדי שלא תצבע את התפריט.
_SUCCESS_ACTIONS = frozenset({"add:ok", "ed:ok", "sh:ok"})
_SHIFT_ORDER = {"בוקר": 0, "ערב": 1, "לילה": 2}


def button_style(callback_data: str) -> str | None:
    """סגנון Bot API 9.4, רק איפה שהוא משנה החלטה.

    danger על מחיקה (כולל האישור). success רק על «שמירה».
    primary על פתיחת עריכה בכרטיס. «לשמור בכל זאת» נשאר בלי צבע:
    ירוק היה מעודד דריסה. צבע של אדם לא נכנס לכאן.
    """
    data = str(callback_data or "")
    if data.startswith("rmy:") or data.startswith("rm:"):
        return "danger"
    if data in _SUCCESS_ACTIONS:
        return "success"
    if data.startswith("ed:") and data[3:].isdigit():
        return "primary"
    return None


def kb(rows: list[list[tuple[str, str]]]) -> dict:
    inline = []
    for row in rows:
        buttons = []
        for text, data in row:
            raw = str(data)
            if not raw or len(raw.encode("utf-8")) > 64:
                raise ValueError(f"callback_data too long: {raw!r}")
            button = {"text": clip(text, 40), "callback_data": raw}
            style = button_style(raw)
            if style:
                if style not in _BUTTON_STYLES:
                    raise ValueError(f"unknown button style: {style!r}")
                button["style"] = style
            buttons.append(button)
        if buttons:
            inline.append(buttons)
    if not inline:
        inline = [[{"text": BTN_MENU, "callback_data": "home"}]]
    return {"inline_keyboard": inline}


def _pairs(items: list[tuple[str, str]]) -> list[list[tuple[str, str]]]:
    rows = []
    row = []
    for item in items:
        row.append(item)
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    return rows


def menu_rows() -> list[list[tuple[str, str]]]:
    return [
        [("📆 אירועי היום", "today"), ("🗓 השבוע הקרוב", "week")],
        [("⏭ אירועים קרובים", "soon"), ("👷 משמרות", "shifts")],
        [("👤 לפי אדם", "who"), ("🔍 חיפוש אירוע", "find")],
        [(BTN_ADD, "add"), ("⚙️ הגדרות", "set")],
    ]


def _exit(*extra: tuple[str, str]) -> list[tuple[str, str]]:
    return [*extra, (BTN_MENU, "home")]


def _back_cancel(back: str) -> list[tuple[str, str]]:
    return [("חזרה", back), ("ביטול", "cancel")]


def greg(day: date) -> str:
    return f"{day.day:02d}.{day.month:02d}.{day.year}"


def ymd(day: date) -> str:
    return day.strftime("%Y%m%d")


def parse_ymd(value: str) -> date | None:
    if len(value) != 8 or not value.isdigit():
        return None
    try:
        return date(int(value[:4]), int(value[4:6]), int(value[6:]))
    except ValueError:
        return None


def weekday_name(day: date) -> str:
    return WEEKDAY_NAMES[weekday_index(day)]


def _day_label(prefix: str, day: date) -> str:
    return f"{prefix} · {hebrew_day_month(day)}"


def home_screen(chat_id, linked: list[dict], *, note: str = "") -> tuple[str, dict]:
    """צ'אט לא מחובר: רק המזהה. מחובר: רק התפריט."""
    lines = []
    if note:
        lines.append(esc(note).rstrip())
        lines.append("")
    if not linked:
        from app.reminders.telegram import chat_id_reply

        lines.append(chat_id_reply(chat_id))
        return "\n".join(lines), kb([[("חיבור כאן", "set:link")]])
    lines.append(MENU_TITLE)
    return "\n".join(lines), kb(menu_rows())


def _filter_row(mode: str) -> list[tuple[str, str]]:
    labels = (("all", "הכל", "flt:all"), ("ev", "אירועים", "flt:ev"), ("sh", "משמרות", "flt:sh"))
    return [
        (f"הצג: {label} ✓" if mode == key else f"הצג: {label}", data)
        for key, label, data in labels
    ]


def _count_line(count: int) -> str:
    if count == 0:
        return "אין אירועים."
    if count == 1:
        return "אירוע אחד."
    return f"{count} אירועים."


def _person_name(people: dict, person_id) -> str:
    person = people.get(person_id)
    if not person:
        return "אדם שנמחק"
    return person.get("name") or "בלי שם"


def visible_name(event: dict) -> str:
    """במשמרת מציגים את סוג המשמרת כשהוא שמור. הכותרת החופשית נשארת בבסיס."""
    if event.get("is_shift"):
        label = str(event.get("shift_label") or "").strip()
        if label:
            return label
    title = str(event.get("title") or "").strip()
    return title or "אירוע"


def _row_button(event: dict, people: dict, *, with_date: bool) -> str:
    title = visible_name(event)
    if event.get("is_shift"):
        name = _person_name(people, event.get("shift_person_id"))
        title = f"{title} · {name}"
    prefix = ""
    raw_day = (event.get("gregorian_date") or "")[:10]
    try:
        day = date.fromisoformat(raw_day)
    except ValueError:
        day = None
    if with_date and day is not None:
        prefix = f"{day.day:02d}.{day.month:02d} "
    elif event.get("time"):
        prefix = f"{event['time']} "
    return clip(f"{prefix}{title}")


def _unique_buttons(events: list[dict], people: dict, *, with_date: bool) -> list[tuple[str, str]]:
    used: set[str] = set()
    buttons = []
    for event in events:
        label = _row_button(event, people, with_date=with_date)
        if label in used:
            label = clip(f"{label} #{event.get('id')}")
        used.add(label)
        raw_day = (event.get("gregorian_date") or "")[:10]
        try:
            day = date.fromisoformat(raw_day)
            stamp = ymd(day)
        except ValueError:
            stamp = "00000000"
        buttons.append((label, f"ev:{event.get('id')}:{stamp}"))
    return buttons


def list_screen(
    *,
    kind: str,
    rows: list[dict],
    page: int,
    today: date,
    mode: str,
    people: dict,
    person_name: str | None = None,
    query: str | None = None,
    start: date | None = None,
    end: date | None = None,
    note: str = "",
) -> tuple[str, dict]:
    page, pages = clamp_page(len(rows), page)
    chunk = rows[page * PAGE_SIZE : (page + 1) * PAGE_SIZE]
    with_date = kind != "today"
    lines = []
    if note:
        lines.append(esc(note).rstrip())
        lines.append("")
    lines.extend(_list_heading(kind, today, start, end, person_name, query, mode))
    lines.append(_count_line(len(rows)))
    if pages > 1:
        lines.append(f"עמוד {page + 1}/{pages}")
    lines.append("")
    if not chunk:
        lines.append(_empty_hint(kind, mode))
    else:
        for event in chunk:
            lines.append(_event_line(event, people, with_date=with_date))
        lines.append("")
        lines.append(LIST_HINT)
    buttons = [[item] for item in _unique_buttons(chunk, people, with_date=with_date)]
    nav = []
    if page > 0:
        nav.append(("הקודם", f"pg:{page - 1}"))
    if page + 1 < pages:
        nav.append(("הבא", f"pg:{page + 1}"))
    if nav:
        buttons.append(nav)
    if kind != "shifts":
        buttons.append(_filter_row(mode))
    if kind == "shifts":
        buttons.append([("➕ משמרת חדשה", "sh:new"), (BTN_MENU, "home")])
    elif kind == "find":
        buttons.append([("🔍 חיפוש אחר", "find"), (BTN_ADD, "add")])
        buttons.append([(BTN_MENU, "home")])
    else:
        buttons.append([(BTN_ADD, "add"), (BTN_MENU, "home")])
    return "\n".join(lines).strip(), kb(buttons)


def _list_heading(kind, today, start, end, person_name, query, mode) -> list[str]:
    filt = {"all": "הכל", "ev": "בלי משמרות", "sh": "רק משמרות"}.get(mode, "הכל")
    if kind == "today":
        day = start or today
        return [
            f"היום · יום {weekday_name(day)} · {filt}",
            code(greg(day)),
            esc(hebrew_display(day)),
        ]
    if kind == "week" and start and end:
        try:
            heading = week_heading(start)
            title = heading.get("week_title") or ""
        except Exception:
            title = ""
        lines = [f"השבוע · {filt}"]
        if title:
            lines.append(esc(title))
        lines.append(f"{code(greg(start))}–{code(greg(end))}")
        return lines
    if kind == "soon" and start and end:
        return [
            f"הקרובים · {SOON_LABEL} · {filt}",
            f"{code(greg(start))}–{code(greg(end))}",
        ]
    if kind == "shifts" and start and end:
        return [
            "משמרות",
            f"{code(greg(start))}–{code(greg(end))}",
        ]
    if kind == "person":
        who = esc(person_name or "האדם")
        return [
            f"של {who} · {filt}",
            "משמרות, ואירועים שהוא נמען לתזכורת שלהם.",
        ]
    if kind == "find":
        return [f"חיפוש · {esc(query or '')} · {filt}"]
    return ["יומן"]


SOON_LABEL = "30 יום"


def _empty_hint(kind: str, mode: str) -> str:
    if mode == "sh":
        return "אין משמרות בסינון הזה. אפשר להחליף ל«הכל»."
    if mode == "ev":
        return "אין אירועים בלי משמרות. אפשר להחליף סינון."
    if kind == "today":
        return "אין אירועים היום. אפשר להוסיף."
    if kind == "week":
        return "אין אירועים השבוע. אפשר להוסיף."
    if kind == "soon":
        return "אין אירועים ב-30 הימים הקרובים."
    if kind == "shifts":
        return "אין משמרות בשבוע הזה."
    if kind == "person":
        return "אין לאדם הזה משמרות או תזכורות בטווח."
    if kind == "find":
        return "אין תוצאות. נסו מילה אחרת."
    return "אין מה להציג."


def _event_line(event: dict, people: dict, *, with_date: bool) -> str:
    title = esc(visible_name(event))
    bits = []
    if with_date and event.get("gregorian_date"):
        bits.append(esc(_safe_greg(event["gregorian_date"])))
    if event.get("time"):
        bits.append(esc(event["time"]))
    else:
        bits.append("כל היום")
    if event.get("is_shift"):
        bits.append("משמרת · " + esc(_person_name(people, event.get("shift_person_id"))))
    elif event.get("recurring") or event.get("recurrence_freq"):
        bits.append("חוזר")
    extra = " · ".join(bits)
    return f"• <b>{title}</b>\n  {extra}"


def _day_letter(day: date) -> str:
    return DAY_LETTERS[weekday_index(day)]


def _shift_face(event: dict) -> str:
    """סוג המשמרת. כותרת חופשית שונה מהסוג מוצגת כמו שהיא."""
    label = str(event.get("shift_label") or "").strip()
    title = str(event.get("title") or "").strip()
    if title and title != label:
        return title
    return label or title or "משמרת"


def _shift_bit(event: dict, people: dict) -> str:
    return f"{_person_name(people, event.get('shift_person_id'))} {_shift_face(event)}"


def _shift_sort_key(event: dict, people: dict) -> tuple:
    face = _shift_face(event)
    return (
        _person_name(people, event.get("shift_person_id")),
        _SHIFT_ORDER.get(face, 9),
        face,
        event.get("id") or 0,
    )


def _day_bits(items: list[dict], people: dict) -> str:
    """אותו אדם עם כמה משמרות נכתב פעם אחת: «שירה בוקר, ערב, לילה»."""
    groups: list[tuple[str, list[str]]] = []
    for event in items:
        name = _person_name(people, event.get("shift_person_id"))
        face = _shift_face(event)
        if groups and groups[-1][0] == name:
            groups[-1][1].append(face)
        else:
            groups.append((name, [face]))
    parts = []
    for name, faces in groups:
        if len(faces) == 1:
            parts.append(f"{name} {faces[0]}")
        else:
            parts.append(f"{name} {', '.join(faces)}")
    return " · ".join(parts)


def _week_header(start: date) -> str:
    end = start + timedelta(days=6)
    span = code(f"{greg(start)}–{greg(end)}")
    try:
        parasha = week_parasha(end)
    except Exception:
        parasha = None
    if parasha:
        return f"{span} · פרשת {esc(parasha)}"
    return span


def shifts_board(rows: list[dict], people: dict, today: date, anchor: date) -> tuple[str, dict]:
    """שבוע אחד (ראשון–שבת). רק ימים עם משמרות, וכפתור לכל משמרת."""
    by_day: dict[str, list[dict]] = {}
    for event in rows:
        raw = (event.get("gregorian_date") or "")[:10]
        by_day.setdefault(raw, []).append(event)
    lines = [_week_header(anchor)]
    buttons: list[list[tuple[str, str]]] = []
    used: set[str] = set()
    found = False
    for offset in range(7):
        day = anchor + timedelta(days=offset)
        items = by_day.get(day.isoformat()) or []
        if not items:
            continue
        found = True
        items.sort(key=lambda event: _shift_sort_key(event, people))
        lines.append(
            f"{_day_letter(day)} {day.day}.{day.month} · {esc(_day_bits(items, people))}"
        )
        day_buttons: list[tuple[str, str]] = []
        for event in items:
            # היום כבר בשורת הטקסט. תאריך רק כשיש שני כפתורים זהים.
            label = _shift_bit(event, people)
            if label in used:
                label = f"{day.day}.{day.month} {label}"
            if label in used:
                label = f"{label} #{event.get('id')}"
            used.add(label)
            day_buttons.append((label, f"ev:{event.get('id')}:{ymd(day)}"))
        for index in range(0, len(day_buttons), SHIFTS_PER_ROW):
            buttons.append(day_buttons[index : index + SHIFTS_PER_ROW])
    if not found:
        lines.append("אין משמרות בשבוע הזה")
    previous = anchor - timedelta(days=7)
    following = anchor + timedelta(days=7)
    this_sunday = today - timedelta(days=weekday_index(today))
    nav = [("שבוע קודם", f"sw:{ymd(previous)}")]
    if anchor != this_sunday:
        nav.append(("השבוע", f"sw:{ymd(this_sunday)}"))
    nav.append(("שבוע הבא", f"sw:{ymd(following)}"))
    buttons.append(nav)
    buttons.append([("➕ משמרת חדשה", "sh:new"), (BTN_MENU, "home")])
    return "\n".join(lines).strip(), kb(buttons)


def shifts_off_screen() -> tuple[str, dict]:
    text = "\n".join(
        [
            "משמרות כבויות בבית.",
            "אפשר להדליק אותן. זה חל על כל מי שמשתמש ביומן.",
        ]
    )
    return text, kb(
        [
            [("הדלקת משמרות", "set:sh:1")],
            [(BTN_MENU, "home")],
        ]
    )


def event_screen(event: dict, people: dict, focus: date | None = None) -> tuple[str, dict]:
    title = esc(visible_name(event))
    raw = (event.get("gregorian_date") or "")[:10]
    try:
        anchor = date.fromisoformat(raw)
    except ValueError:
        anchor = focus
    shown = focus or anchor
    lines = [f"<b>{title}</b>"]
    if event.get("is_shift"):
        lines.append(
            "משמרת · " + esc(_person_name(people, event.get("shift_person_id")))
        )
    if shown is not None:
        lines.append(f"יום {weekday_name(shown)} · {code(greg(shown))}")
        lines.append(esc(hebrew_display(shown)))
    if event.get("is_shift"):
        lines.append("כל היום")
    elif event.get("time"):
        lines.append(f"שעה {code(event['time'])}")
    else:
        lines.append("כל היום")
    end = event.get("end_date")
    if end and shown is not None and end[:10] != shown.isoformat():
        lines.append(f"עד {code(_safe_greg(end))}")
    description = (event.get("description") or "").strip()
    if description:
        short = description if len(description) <= 400 else description[:399] + "…"
        lines.append(esc(short))
    recurring = bool(event.get("recurrence_freq"))
    if recurring:
        lines.append("אירוע חוזר. עריכה ומחיקה כאן חלות על כל הסדרה.")
    lines.append("")
    lines.append("אפשר לערוך, למחוק, או לחזור לרשימה.")
    event_id = event.get("id")
    if event.get("is_shift"):
        actions = [[("📅 שינוי תאריך", f"ed:{event_id}"), ("🗑 מחיקה", f"rm:{event_id}")]]
    else:
        actions = [[("✏️ עריכה", f"ed:{event_id}"), ("🗑 מחיקה", f"rm:{event_id}")]]
    actions.append([("↩️ חזרה לרשימה", "back:list"), (BTN_MENU, "home")])
    return "\n".join(lines), kb(actions)


def _safe_greg(value: str) -> str:
    try:
        return greg(date.fromisoformat(value[:10]))
    except ValueError:
        return value[:10]


def missing_event_screen() -> tuple[str, dict]:
    text = "האירוע כבר לא ביומן.\nאפשר לחזור לרשימה."
    return text, kb([[("↩️ חזרה לרשימה", "back:list"), (BTN_MENU, "home")]])


def delete_screen(event: dict) -> tuple[str, dict]:
    title = esc(visible_name(event))
    lines = [f"למחוק את «{title}»?", "אי אפשר לבטל."]
    if event.get("recurrence_freq"):
        lines.append("זו סדרה. יימחק כל מה שחוזר, לא רק יום אחד.")
    lines.append(f"מזהה: {code(event.get('id'))}")
    event_id = event.get("id")
    return "\n".join(lines), kb(
        [
            [("כן, למחוק", f"rmy:{event_id}"), ("לא", f"ev:{event_id}")],
        ]
    )


def add_title_screen() -> tuple[str, dict]:
    text = "איך לקרוא לאירוע?\nכתבו שם. אחר כך בוחרים תאריך — ברירת המחדל היא היום, כל היום."
    return text, kb([_back_cancel("home")])


def _draft_day(draft: dict, today: date) -> date:
    raw = (draft.get("gregorian_date") or "")[:10]
    try:
        return date.fromisoformat(raw)
    except ValueError:
        return today


def add_confirm_screen(draft: dict, today: date, *, error: str = "") -> tuple[str, dict]:
    day = _draft_day(draft, today)
    lines = []
    if error:
        lines.append(esc(error))
        lines.append("")
    lines.append("לשמור את האירוע?")
    lines.append("")
    lines.append(f"<b>{esc(draft.get('title') or '')}</b>")
    lines.append(f"יום {weekday_name(day)} · {code(greg(day))}")
    lines.append(esc(hebrew_display(day)))
    if draft.get("time"):
        lines.append(f"שעה {code(draft['time'])}")
    else:
        lines.append("כל היום")
    if draft.get("end_date"):
        lines.append(f"עד {code(_safe_greg(draft['end_date']))}")
    if (draft.get("description") or "").strip():
        lines.append(esc(draft["description"].strip()))
    lines.append("")
    lines.append("אפשר לשמור כמו שזה, או לשנות.")
    tomorrow = today + timedelta(days=1)
    today_label = _day_label("היום", today)
    tomorrow_label = _day_label("מחר", tomorrow)
    if day == today:
        today_label = "• " + today_label
    elif day == tomorrow:
        tomorrow_label = "• " + tomorrow_label
    return "\n".join(lines), kb(
        [
            [("שמירה", "add:ok")],
            [(today_label, "add:d:0"), (tomorrow_label, "add:d:1")],
            [("תאריך אחר", "add:d:x"), ("שעה", "add:time")],
            [("תיאור", "add:desc"), ("עד תאריך", "add:end")],
            [("ביטול", "cancel")],
        ]
    )


def add_date_screen(today: date) -> tuple[str, dict]:
    text = "\n".join(
        [
            "איזה תאריך?",
            f"כתבו, למשל {code(greg(today))}",
            "אפשר גם «היום» או «מחר».",
        ]
    )
    return text, kb(
        [
            [(_day_label("היום", today), "add:d:0"), (_day_label("מחר", today + timedelta(days=1)), "add:d:1")],
            _back_cancel("back:add"),
        ]
    )


def add_time_screen(draft: dict) -> tuple[str, dict]:
    current = draft.get("time")
    lines = ["באיזו שעה?", f"או כתבו, למשל {code('18:30')}"]
    rows = [[("• כל היום" if not current else "כל היום", "add:all")]]
    presets = []
    for stamp in PRESET_TIMES:
        label = f"• {stamp}" if current == stamp else stamp
        presets.append((label, "add:hm:" + stamp.replace(":", "")))
    rows.extend(_pairs(presets))
    rows.append([("שעה אחרת", "add:hm:x")])
    rows.append(_back_cancel("back:add"))
    return "\n".join(lines), kb(rows)


def add_time_text_screen() -> tuple[str, dict]:
    text = f"כתבו שעה, למשל {code('18:30')}\nאו «כל היום»."
    return text, kb([[("כל היום", "add:all")], _back_cancel("back:add")])


def edit_time_text_screen() -> tuple[str, dict]:
    text = f"כתבו שעה, למשל {code('18:30')}\nאו «כל היום»."
    return text, kb([[("כל היום", "ed:all")], _back_cancel("back:edit")])


def add_desc_screen() -> tuple[str, dict]:
    text = "כתבו תיאור.\n«בלי» מוחק תיאור קודם."
    return text, kb([[("בלי תיאור", "add:desc0")], _back_cancel("back:add")])


def add_end_screen(draft: dict, today: date) -> tuple[str, dict]:
    day = _draft_day(draft, today)
    nxt = day + timedelta(days=1)
    text = "\n".join(
        [
            "עד מתי האירוע נמשך?",
            "ליום אחד לא צריך תאריך סיום.",
            f"כתבו תאריך, למשל {code(greg(nxt))}",
        ]
    )
    return text, kb(
        [
            [("רק יום אחד", "add:end0")],
            [(f"עד {hebrew_day_month(nxt)}", "add:end1")],
            _back_cancel("back:add"),
        ]
    )


def edit_menu_screen(draft: dict, *, error: str = "") -> tuple[str, dict]:
    lines = []
    if error:
        lines.append(esc(error))
        lines.append("")
    lines.append(f"מה לשנות ב«{esc(draft.get('title') or '')}»?")
    if draft.get("recurring"):
        lines.append("זה אירוע חוזר. שינוי כאן מזיז את כל הסדרה.")
    try:
        day = date.fromisoformat(draft.get("gregorian_date") or "")
        lines.append(f"{code(greg(day))} · {esc(hebrew_display(day))}")
    except ValueError:
        pass
    if draft.get("time"):
        lines.append(f"שעה {code(draft['time'])}")
    else:
        lines.append("כל היום")
    lines.append("לחצו מה לשנות, ואז שמירה.")
    return "\n".join(lines), kb(
        [
            [("כותרת", "edf:title"), ("תאריך", "edf:date")],
            [("שעה", "edf:time"), ("תיאור", "edf:desc")],
            [("תאריך סיום", "edf:end")],
            [("שמירה", "ed:ok")],
            [("חזרה לאירוע", "back:ev"), ("ביטול", "cancel")],
        ]
    )


def edit_title_screen() -> tuple[str, dict]:
    return "כתבו כותרת חדשה.", kb([_back_cancel("back:edit")])


def edit_date_screen(draft: dict, today: date, *, shift: bool = False) -> tuple[str, dict]:
    try:
        current = date.fromisoformat(draft.get("gregorian_date") or "")
    except ValueError:
        current = today
    lines = ["איזה תאריך?"]
    if draft.get("recurring") and not shift:
        lines.append("התאריך החדש יהיה ההתחלה של כל הסדרה.")
    if shift:
        lines.append("המשמרת תעבור ליום שתבחרו.")
    lines.append(f"עכשיו: {code(greg(current))} · {esc(hebrew_display(current))}")
    lines.append(f"אפשר לכתוב, למשל {code(greg(today))}")
    tomorrow = today + timedelta(days=1)
    rows = [
        [(_day_label("היום", today), "ed:d:0"), (_day_label("מחר", tomorrow), "ed:d:1")],
        [("תאריך אחר", "ed:d:x")],
    ]
    if shift:
        rows.append([("שמירה", "ed:ok")])
        rows.append([("חזרה לאירוע", "back:ev"), ("ביטול", "cancel")])
    else:
        rows.append(_back_cancel("back:edit"))
    return "\n".join(lines), kb(rows)


def edit_date_text_screen() -> tuple[str, dict]:
    text = f"כתבו תאריך, למשל {code('22.10.2026')}"
    return text, kb([_back_cancel("back:edit")])


def edit_time_screen(draft: dict) -> tuple[str, dict]:
    text, markup = add_time_screen(draft)
    # אותם כפתורי שעה, אבל חוזרים לעריכה. מחליפים את ה-callback.
    rebuilt = []
    for row in markup["inline_keyboard"]:
        new_row = []
        for button in row:
            data = button["callback_data"]
            data = (
                data.replace("add:all", "ed:all")
                .replace("add:hm:", "ed:hm:")
                .replace("back:add", "back:edit")
            )
            new_row.append((button["text"], data))
        rebuilt.append(new_row)
    return "באיזו שעה חדשה?\n" + text.split("\n", 1)[-1], kb(rebuilt)


def edit_desc_screen() -> tuple[str, dict]:
    text = "כתבו תיאור חדש.\n«בלי» מוחק את התיאור."
    return text, kb([[("בלי תיאור", "ed:desc0")], _back_cancel("back:edit")])


def edit_end_screen(draft: dict) -> tuple[str, dict]:
    try:
        day = date.fromisoformat(draft.get("gregorian_date") or "")
    except ValueError:
        day = date.today()
    nxt = day + timedelta(days=1)
    text = "\n".join(
        [
            "עד מתי?",
            "«רק יום אחד» מוריד את הסיום.",
            f"למשל {code(greg(nxt))}",
        ]
    )
    return text, kb(
        [
            [("רק יום אחד", "ed:end0"), ("יום אחרי", "ed:end1")],
            _back_cancel("back:edit"),
        ]
    )


def conflict_screen(current: dict, draft: dict) -> tuple[str, dict]:
    lines = [
        "האירוע השתנה מאז שפתחתם אותו.",
        "",
        "עכשיו ביומן:",
        _plain_event(current),
        "",
        "אצלכם:",
        _plain_draft(draft),
        "",
        "לשמור בכל זאת דורס את מה שבסיס. להציג מחדש זורק את השינוי שלכם.",
    ]
    return "\n".join(lines), kb(
        [
            [("לשמור בכל זאת", "ed:force")],
            [("להציג מחדש", "back:ev"), ("ביטול", "cancel")],
        ]
    )


def _plain_event(event: dict) -> str:
    bits = [esc(visible_name(event))]
    if event.get("gregorian_date"):
        bits.append(code(_safe_greg(event["gregorian_date"])))
    bits.append(code(event["time"]) if event.get("time") else "כל היום")
    return " · ".join(bits)


def _plain_draft(draft: dict) -> str:
    return _plain_event(draft)


def settings_screen(
    chat_id,
    linked: list[dict],
    household: dict | None,
    households: list[dict],
    *,
    note: str = "",
) -> tuple[str, dict]:
    lines = ["הגדרות", ""]
    if note:
        lines.insert(1, esc(note))
    lines.append(f"מזהה הצ'אט: {code(chat_id)}")
    if not linked:
        lines.append("הצ'אט לא מחובר לאדם.")
    else:
        names = ", ".join(esc(person["name"]) for person in linked)
        lines.append(f"מחובר אל: {names}")
    if household is None:
        lines.append("בחרו בית. המתג של משמרות חל רק עליו.")
        lines.append("האירועים עצמם משותפים.")
    else:
        state = "דלוקות" if household.get("shifts_enabled") else "כבויות"
        if len(households) > 1:
            lines.append(f"בית נבחר: {esc(household.get('name') or '')}")
            lines.append("כמה בתים בבסיס. המתג חל רק על הבית שנבחר. האירועים משותפים.")
        else:
            lines.append("בית אחד. המתג של משמרות חל על כולם.")
        lines.append(f"משמרות: {state}")
    rows: list[list[tuple[str, str]]] = []
    if len(households) > 1 or household is None:
        rows.extend(
            _pairs(
                [
                    (
                        f"• {item['name']}" if household and item["id"] == household["id"] else item["name"],
                        f"set:hh:{item['id']}",
                    )
                    for item in households
                ]
            )
        )
    rows.append([("חיבור לאדם", "set:link")])
    for person in linked:
        rows.append([(f"ניתוק {person['name']}", f"set:ul:{person['id']}")])
    if household is not None:
        if household.get("shifts_enabled"):
            rows.append([("כיבוי משמרות", "set:sh:0")])
            rows.append([("מי עובד במשמרות", "set:workers")])
        else:
            rows.append([("הדלקת משמרות", "set:sh:1")])
    rows.append([(BTN_MENU, "home")])
    return "\n".join(lines), kb(rows)


def shift_toggle_screen(enabled: bool, household_name: str) -> tuple[str, dict]:
    verb = "להדליק" if enabled else "לכבות"
    text = "\n".join(
        [
            f"{verb} משמרות ל{esc(household_name)}?",
            "זה חל על כל המשתמשים בבית הזה.",
        ]
    )
    answer = "set:shy:1" if enabled else "set:shy:0"
    return text, kb([[("כן", answer), ("לא", "set")]])


def link_picker(people: list[dict], page: int) -> tuple[str, dict]:
    page, pages = clamp_page(len(people), page, PEOPLE_PAGE)
    chunk = people[page * PEOPLE_PAGE : (page + 1) * PEOPLE_PAGE]
    lines = ["לחבר את הצ'אט למי?", "בחרו אדם, או צרו חדש."]
    if pages > 1:
        lines.append(f"עמוד {page + 1}/{pages}")
    if not people:
        lines.append("אין עדיין אנשים. אפשר ליצור עכשיו.")
    rows = [[(person["name"], f"set:pick:{person['id']}")] for person in chunk]
    nav = []
    if page > 0:
        nav.append(("הקודם", f"set:lp:{page - 1}"))
    if page + 1 < pages:
        nav.append(("הבא", f"set:lp:{page + 1}"))
    if nav:
        rows.append(nav)
    rows.append([("אדם חדש", "set:new")])
    rows.append([("חזרה", "set"), ("ביטול", "cancel")])
    return "\n".join(lines), kb(rows)


def link_conflict_screen(status: dict, chat_id) -> tuple[str, dict]:
    person = status["person"]
    name = esc(person["name"])
    lines = [f"חיבור הצ'אט אל {name}."]
    rows = []
    if status["others"]:
        others = ", ".join(esc(other["name"]) for other in status["others"])
        lines.append(f"המזהה {code(chat_id)} כבר אצל {others}.")
    if status["replaces"]:
        lines.append(f"ל{name} רשום צ'אט אחר: {code(status['old_chat'])}.")
    if status["others"]:
        lines.append("העברה מנתקת את האחרים מהמזהה הזה. חיבור משאיר אותם.")
    else:
        lines.append("להחליף למזהה של הצ'אט הזה?")
    person_id = person["id"]
    if status["others"]:
        rows.append([(f"העברה אל {person['name']}", f"set:move:{person_id}")])
        rows.append([("חיבור בלי לנתק", f"set:share:{person_id}")])
    else:
        rows.append([("כן, להחליף", f"set:share:{person_id}")])
    rows.append([("חזרה", "set:link"), ("ביטול", "cancel")])
    return "\n".join(lines), kb(rows)


def link_name_screen(*, error: str = "") -> tuple[str, dict]:
    lines = []
    if error:
        lines.append(esc(error))
    lines.append("איך קוראים לאדם החדש?")
    lines.append("כתבו שם. הצ'אט יחובר אליו.")
    return "\n".join(lines), kb([_back_cancel("set:link")])


def workers_screen(people: list[dict], page: int = 0) -> tuple[str, dict]:
    page, pages = clamp_page(len(people), page, PEOPLE_PAGE)
    chunk = people[page * PEOPLE_PAGE : (page + 1) * PEOPLE_PAGE]
    lines = ["מי עובד במשמרות?", "לחיצה מחליפה דלוק/כבוי."]
    if pages > 1:
        lines.append(f"עמוד {page + 1}/{pages}")
    if not people:
        lines.append("אין אנשים. אפשר ליצור בהגדרות.")
    rows = []
    for person in chunk:
        mark = "כן" if person.get("works_shifts") else "לא"
        rows.append([(f"{person['name']} · {mark}", f"set:ws:{person['id']}")])
    nav = []
    if page > 0:
        nav.append(("הקודם", f"set:wp:{page - 1}"))
    if page + 1 < pages:
        nav.append(("הבא", f"set:wp:{page + 1}"))
    if nav:
        rows.append(nav)
    rows.append([("חזרה", "set"), (BTN_MENU, "home")])
    return "\n".join(lines), kb(rows)


def person_picker(people: list[dict], page: int) -> tuple[str, dict]:
    page, pages = clamp_page(len(people), page, PEOPLE_PAGE)
    chunk = people[page * PEOPLE_PAGE : (page + 1) * PEOPLE_PAGE]
    lines = ["של מי להציג?", "משמרות שלו, ואירועים שהוא מקבל עליהם תזכורת."]
    if not people:
        lines.append("אין אנשים ביומן. אפשר להוסיף בהגדרות.")
    if pages > 1:
        lines.append(f"עמוד {page + 1}/{pages}")
    rows = [[(person["name"], f"who:{person['id']}")] for person in chunk]
    nav = []
    if page > 0:
        nav.append(("הקודם", f"whop:{page - 1}"))
    if page + 1 < pages:
        nav.append(("הבא", f"whop:{page + 1}"))
    if nav:
        rows.append(nav)
    if not people:
        rows.append([("הגדרות", "set")])
    rows.append([(BTN_MENU, "home")])
    return "\n".join(lines), kb(rows)


def find_screen(*, error: str = "") -> tuple[str, dict]:
    lines = []
    if error:
        lines.append(esc(error))
    lines.append("מה לחפש?")
    lines.append("כתבו מילה מהכותרת או מהתיאור.")
    lines.append("אפשר גם /find ואז המילה.")
    return "\n".join(lines), kb([[("ביטול", "cancel")]])


def shift_people_screen(people: list[dict]) -> tuple[str, dict]:
    lines = ["למי המשמרת?"]
    if not people:
        lines.append("אף אחד לא מסומן למשמרות.")
        lines.append("אפשר לסמן אנשים, ואז לחזור לכאן.")
        return "\n".join(lines), kb(
            [
                [("מי עובד במשמרות", "set:workers")],
                [("חזרה", "shifts"), ("ביטול", "cancel")],
            ]
        )
    rows = [[(person["name"], f"sh:p:{person['id']}")] for person in people]
    rows.append([("חזרה", "shifts"), ("ביטול", "cancel")])
    return "\n".join(lines), kb(rows)


def shift_label_screen(person_name: str) -> tuple[str, dict]:
    text = f"איזו משמרת ל{esc(person_name)}?"
    return text, kb(
        [
            [("בוקר", "sh:l:m"), ("ערב", "sh:l:e")],
            [("לילה", "sh:l:n")],
            [("חזרה", "sh:new"), ("ביטול", "cancel")],
        ]
    )


def shift_confirm_screen(draft: dict, today: date, person_name: str, *, error: str = "") -> tuple[str, dict]:
    try:
        day = date.fromisoformat(draft.get("gregorian_date") or "")
    except ValueError:
        day = today
    label = SHIFT_LABELS.get(draft.get("label_key") or "", draft.get("label") or "")
    lines = []
    if error:
        lines.append(esc(error))
        lines.append("")
    lines.extend(
        [
            "לשמור משמרת?",
            "",
            f"<b>{esc(label)}</b> · {esc(person_name)}",
            f"יום {weekday_name(day)} · {code(greg(day))}",
            esc(hebrew_display(day)),
            "כל היום",
        ]
    )
    tomorrow = today + timedelta(days=1)
    return "\n".join(lines), kb(
        [
            [("שמירה", "sh:ok")],
            [(_day_label("היום", today), "sh:d:0"), (_day_label("מחר", tomorrow), "sh:d:1")],
            [("תאריך אחר", "sh:d:x")],
            [("חזרה", "sh:back"), ("ביטול", "cancel")],
        ]
    )


def shift_date_text_screen(today: date) -> tuple[str, dict]:
    text = f"כתבו תאריך למשמרת, למשל {code(greg(today))}"
    return text, kb(
        [
            [(_day_label("היום", today), "sh:d:0"), (_day_label("מחר", today + timedelta(days=1)), "sh:d:1")],
            [("חזרה", "sh:back"), ("ביטול", "cancel")],
        ]
    )


def deleted_note_screen(title: str) -> tuple[str, dict]:
    text = f"«{esc(title)}» נמחק."
    return text, kb([[("↩️ חזרה לרשימה", "back:list"), (BTN_MENU, "home")]])
