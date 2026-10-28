"""בוט טלגרם: תפריט, רשימות, CRUD, הגדרות. בלי רשת."""
from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from app.bot.dispatch import handle_update
from app.bot.parse import InputError, parse_user_date, parse_user_time
from app.reminders.telegram import consume_updates
from app.services.recurrence import hebrew_display
from app.services.shifts import weekday_index

TZ = ZoneInfo("Asia/Jerusalem")
NOW = datetime(2026, 10, 22, 15, 0, tzinfo=TZ)
TODAY = NOW.date()


def _msg(text, chat=42, message_id=1):
    return {
        "update_id": 1,
        "message": {"message_id": message_id, "text": text, "chat": {"id": chat}},
    }


def _cb(data, chat=42, message_id=5, cb_id="cb1"):
    return {
        "update_id": 2,
        "callback_query": {
            "id": cb_id,
            "data": data,
            "message": {"message_id": message_id, "chat": {"id": chat}, "text": "x"},
        },
    }


def _go(app, update, now=NOW):
    with app.app_context():
        return handle_update(update, now=now)


def _buttons(reply):
    found = []
    for row in reply["markup"]["inline_keyboard"]:
        for button in row:
            assert button["text"]
            assert 1 <= len(button["callback_data"].encode("utf-8")) <= 64
            assert button.get("style") in (None, "danger", "success", "primary")
            found.append(button)
    return found


def _has_exit(reply):
    datas = [button["callback_data"] for button in _buttons(reply)]
    assert any(
        data in {"home", "cancel"} or data.startswith("back") or data == "set"
        for data in datas
    ), datas


def _press(app, reply, label, *, chat=42, now=NOW):
    buttons = _buttons(reply)
    exact = [button for button in buttons if button["text"] == label]
    marked = [
        button
        for button in buttons
        if button["text"].startswith(label) or button["text"].startswith("• " + label)
    ]
    contains = [button for button in buttons if label in button["text"]]
    chosen = exact or marked or contains
    assert len(chosen) == 1, (label, [button["text"] for button in buttons])
    return _go(app, _cb(chosen[0]["callback_data"], chat=chat), now=now)


def _event(app, title, day, **kwargs):
    with app.app_context():
        from app.database import create_event

        return create_event(
            title,
            day.isoformat(),
            hebrew_display(day),
            time=kwargs.get("time"),
            description=kwargs.get("description") or "",
            end_date=kwargs.get("end_date"),
            recurrence=kwargs.get("recurrence"),
            shift=kwargs.get("shift"),
        )


def _person(app, name="דני", chat=None, **flags):
    with app.app_context():
        from app.reminders.repository import create_person

        return create_person(name, None if chat is None else str(chat), **flags)


def _titles(app):
    with app.app_context():
        from app.database import get_all_events

        return [event["title"] for event in get_all_events()]


def test_button_style_is_semantic_and_ignores_colors():
    from app.bot.ui import button_style, kb

    assert button_style("rm:4") == "danger"
    assert button_style("rmy:4") == "danger"
    assert button_style("add") is None
    assert button_style("sh:new") is None
    assert button_style("set:new") is None
    assert button_style("add:ok") == "success"
    assert button_style("ed:ok") == "success"
    assert button_style("sh:ok") == "success"
    assert button_style("ed:force") is None
    assert button_style("ed:12") == "primary"
    assert button_style("today") is None
    assert button_style("ev:3:20261022") is None
    assert button_style("home") is None
    assert button_style("set:hh:1") is None
    for color in ("cyan", "yellow", "orange", "green", "red", "blue", "pink"):
        assert button_style(color) is None
    marked = kb([[("שמירה", "add:ok"), ("היום", "today")]])
    save, other = marked["inline_keyboard"][0]
    assert save["style"] == "success"
    assert "style" not in other


def test_screen_styles_match_the_action(app):
    from app.services.shifts import set_shifts_enabled

    _person(app, "דני", chat=42)
    menu = _go(app, _msg("/start"))
    styles = {button["text"]: button.get("style") for button in _buttons(menu)}
    assert styles["➕ הוספת אירוע"] is None
    assert styles["📆 אירועי היום"] is None
    assert styles["⚙️ הגדרות"] is None

    _event(app, "פגישה", TODAY, time="10:00")
    card = _press(app, _go(app, _msg("/today")), "פגישה")
    card_styles = {button["text"]: button.get("style") for button in _buttons(card)}
    assert card_styles["✏️ עריכה"] == "primary"
    assert card_styles["🗑 מחיקה"] == "danger"
    assert card_styles["↩️ חזרה לרשימה"] is None
    ask = _press(app, card, "מחיקה")
    ask_styles = {button["text"]: button.get("style") for button in _buttons(ask)}
    assert ask_styles["כן, למחוק"] == "danger"
    assert ask_styles["לא"] is None

    with app.app_context():
        set_shifts_enabled(True)
    _person(app, "אביחי", works_shifts=1)
    board = _go(app, _cb("shifts"))
    board_styles = {button["text"]: button.get("style") for button in _buttons(board)}
    assert board_styles["➕ משמרת חדשה"] is None
    assert board_styles["🏠 תפריט ראשי"] is None
    assert all(
        button.get("style") is None
        for button in _buttons(board)
        if button["callback_data"].startswith("ev:")
    )


def test_parse_rejects_impossible_dates_and_times():
    with_error = False
    try:
        parse_user_date("2026-02-31", TODAY)
    except InputError as exc:
        with_error = "לא קיים" in str(exc)
    assert with_error
    try:
        parse_user_date("31.02.2026", TODAY)
        raise AssertionError("should fail")
    except InputError:
        pass
    try:
        parse_user_date("29.02.2026", TODAY)
        raise AssertionError("2026 is not a leap year")
    except InputError:
        pass
    assert parse_user_date("29.02.2024", TODAY).isoformat() == "2024-02-29"
    assert parse_user_date("היום", TODAY) == TODAY
    assert parse_user_date("מחר", TODAY) == TODAY + timedelta(days=1)
    try:
        parse_user_time("25:99")
        raise AssertionError("bad time")
    except InputError as exc:
        assert "18:30" in str(exc)
    assert parse_user_time("9:30") == "09:30"
    assert parse_user_time("1830") == "18:30"
    assert parse_user_time("כל היום") is None
    assert parse_user_date("251026", TODAY).isoformat() == "2026-10-25"
    assert parse_user_date('י"ג חשון', TODAY).isoformat() == "2026-10-24"
    assert parse_user_date("יג חשוון", TODAY).isoformat() == "2026-10-24"
    assert parse_user_date("י״ג במרחשוון", TODAY).isoformat() == "2026-10-24"
    assert parse_user_date("יג בחשוון", TODAY).isoformat() == "2026-10-24"
    assert parse_user_date("ל חשון", TODAY).isoformat() == "2026-11-10"
    later = TODAY.replace(month=11, day=11)
    assert parse_user_date("ל חשון", later).isoformat() == "2027-11-30"
    assert parse_user_date("א׳ אדר א׳", TODAY).isoformat() == "2027-02-08"
    assert parse_user_date("א אדר", TODAY).isoformat() == "2027-03-10"
    assert parse_user_date("א אדר", date(2027, 3, 15)).isoformat() == "2028-02-28"
    assert parse_user_date('י"ג חשון תשפ״ו', TODAY).isoformat() == "2025-11-04"
    assert parse_user_date("יג חשון ה'תשפז", TODAY).isoformat() == "2026-10-24"
    assert parse_user_date("א תשרי", TODAY).isoformat() == "2027-10-02"
    try:
        parse_user_date("321399", TODAY)
        raise AssertionError("bad compact date")
    except InputError:
        pass
    try:
        parse_user_date("יג חודשלא", TODAY)
        raise AssertionError("bad hebrew month")
    except InputError as exc:
        assert "חודש" in str(exc)


def test_plain_adar_follows_the_hebrew_year():
    """«אדר» בלי א׳/ב׳: בשנה מעוברת אדר ב׳, בשנה פשוטה אדר."""
    from pyluach.dates import HebrewDate

    def greg(year, month, day):
        converted = HebrewDate(year, month, day).to_greg()
        return date(converted.year, converted.month, converted.day)

    assert parse_user_date("יד אדר תשפז", TODAY) == greg(5787, 13, 14)
    assert parse_user_date("יד אדר תשפח", TODAY) == greg(5788, 12, 14)
    assert parse_user_date("יד אדר א תשפז", TODAY) == greg(5787, 12, 14)
    assert parse_user_date("יד אדר ב תשפח", TODAY) == greg(5788, 12, 14)
    assert parse_user_date("א׳ אדר א׳ תשפ״ז", TODAY) == greg(5787, 12, 1)
    try:
        parse_user_date("ל אדר א תשפח", TODAY)
        raise AssertionError("30 Adar does not exist in a plain year")
    except InputError as exc:
        assert "לא קיים" in str(exc)


def test_start_unlinked_is_only_the_chat_id(app):
    reply = _go(app, _msg("/start"))
    assert reply["text"] == (
        "מזהה הצ'אט שלך: <code>42</code>\n"
        "מעתיקים את המספר להגדרות, תחת תזכורות."
    )
    labels = [button["text"] for button in _buttons(reply)]
    assert labels == ["חיבור כאן"]
    for label in ("היום", "השבוע", "אירועי החודש", "משמרות", "לפי אדם", "חיפוש", "אירוע חדש", "הגדרות"):
        assert label not in labels
    assert "מה עושים?" not in reply["text"]
    link = _press(app, reply, "חיבור כאן")
    assert "לחבר את הצ'אט" in link["text"]
    _has_exit(link)


def test_start_linked_is_only_the_menu(app):
    _person(app, "דני", chat=42)
    _person(app, "נועה", chat=42)
    reply = _go(app, _msg("/start@HebCalBot"))
    assert reply["text"] == "📅 לוח השנה המשותף — מה להציג?"
    assert "<code>" not in reply["text"]
    assert "דני" not in reply["text"]
    labels = [button["text"] for button in _buttons(reply)]
    assert labels == [
        "🗓 אירועי השבוע",
        "📆 אירועי היום",
        "👷 משמרות",
        "⏮ אירועי החודש",
        "👤 לפי אדם",
        "🔍 חיפוש אירוע",
        "➕ הוספת אירוע",
        "⚙️ הגדרות",
    ]
    rows = reply["markup"]["inline_keyboard"]
    assert [button["text"] for button in rows[0]] == ["🗓 אירועי השבוע", "📆 אירועי היום"]
    assert [button["text"] for button in rows[1]] == ["👷 משמרות", "⏮ אירועי החודש"]
    assert [button["text"] for button in rows[2]] == ["👤 לפי אדם", "🔍 חיפוש אירוע"]
    assert [button["text"] for button in rows[3]] == ["➕ הוספת אירוע", "⚙️ הגדרות"]
    _has_exit(reply)
    for button in _buttons(reply):
        screen = _go(app, _cb(button["callback_data"]))
        _has_exit(screen)
        assert screen["text"]
        assert "<" not in screen["text"] or "<code>" in screen["text"] or "<b>" in screen["text"]
    settings = _press(app, reply, "הגדרות")
    assert "<code>42</code>" in settings["text"]
    assert "דני" in settings["text"]
    assert "נועה" in settings["text"]
    group = _go(app, _msg("/start", chat=-100))
    assert "<code>-100</code>" in group["text"]
    assert [button["text"] for button in _buttons(group)] == ["חיבור כאן"]


def test_unknown_command_sticker_and_bad_callback(app):
    unlinked = _go(app, _msg("/nope"))
    assert "אין פקודה" in unlinked["text"]
    assert "<code>42</code>" in unlinked["text"]
    assert "היום" not in [button["text"] for button in _buttons(unlinked)]
    _person(app, "דני", chat=42)
    reply = _go(app, _msg("/nope"))
    assert "אין פקודה" in reply["text"]
    assert "📆 אירועי היום" in [button["text"] for button in _buttons(reply)]
    assert "<code>" not in reply["text"]
    sticker = _go(app, {"update_id": 3, "message": {"chat": {"id": 42}}})
    assert "כפתור" in sticker["text"]
    bad = _go(app, _cb("../x"))
    assert bad["toast"] == "הפתור לא מוכר" or "לא מוכר" in bad["toast"]
    assert "📅 לוח השנה המשותף — מה להציג?" in bad["text"]
    assert handle_update({"update_id": 9})["skip"] is True


def test_today_week_soon_and_pagination(app):
    sunday = TODAY - timedelta(days=weekday_index(TODAY))
    saturday = sunday + timedelta(days=6)
    _event(app, "היום-אירוע", TODAY, time="18:30")
    _event(app, "מחר-אירוע", TODAY + timedelta(days=1))
    _event(app, "ראשון", sunday)
    _event(app, "שבת", saturday)
    _event(app, "לפני", sunday - timedelta(days=1))
    _event(app, "אחרי-השבוע", saturday + timedelta(days=1))
    _event(app, "עוד-30", TODAY + timedelta(days=30))
    _event(app, "עוד-31", TODAY + timedelta(days=31))
    for index in range(6):
        _event(app, f"רצף-{index}", TODAY)

    today = _go(app, _msg("/today"))
    assert hebrew_display(TODAY) in today["text"]
    assert "<code>22.10.2026</code>" in today["text"]
    assert "מחר-אירוע" not in today["text"]
    assert "לחצו על אירוע לפרטים, עריכה או מחיקה." in today["text"]
    assert "רצף-0" in today["text"]
    assert "הבא ←" in [button["text"] for button in _buttons(today)]
    page2 = _press(app, today, "הבא")
    assert "→ הקודם" in [button["text"] for button in _buttons(page2)]
    assert "היום-אירוע" in page2["text"]
    assert "18:30" in page2["text"]
    assert "רצף-0" not in page2["text"]
    clamped = _go(app, _cb("pg:99"))
    assert not any(button["text"].startswith("הבא") for button in _buttons(clamped))

    week = _go(app, _msg("/week"))
    week2 = _press(app, week, "הבא")
    combined = week["text"] + week2["text"]
    assert "<code>18.10.2026</code>" in week["text"]
    assert "<code>24.10.2026</code>" in week["text"]
    assert "ראשון" in combined
    assert "שבת" in combined
    assert "היום-אירוע" in combined
    assert "לפני" not in combined
    assert "אחרי-השבוע" not in combined
    _has_exit(week)

    soon = _go(app, _cb("soon"))
    assert "אירועי החודש" in soon["text"]
    assert "30 יום" in soon["text"]
    assert "<code>21.11.2026</code>" in soon["text"]
    blob = soon["text"]
    screen = soon
    screen = _press(app, screen, "הבא")
    nav = next(
        row
        for row in screen["markup"]["inline_keyboard"]
        if any("הבא" in button["text"] or "הקודם" in button["text"] for button in row)
    )
    assert [button["text"] for button in nav] == ["הבא ←", "→ הקודם"]
    blob += screen["text"]
    while any(button["text"].startswith("הבא") for button in _buttons(screen)):
        screen = _press(app, screen, "הבא")
        blob += screen["text"]
    assert "עוד-30" in blob
    assert "עוד-31" not in blob


def test_filters_person_and_find(app):
    danny = _person(app, "דני", chat=42, works_shifts=1)
    noa = _person(app, "נועה", chat="", works_shifts=1)
    _event(app, "פגישה", TODAY, description="זום")
    meeting = _event(app, "תזכורת לנועה", TODAY)
    _event(app, "בוקר", TODAY, shift=(1, danny["id"], "בוקר"))
    _event(app, "ערב", TODAY, shift=(1, noa["id"], "ערב"))
    _event(app, "ארכיון", TODAY.replace(year=2020))
    with app.app_context():
        from app.reminders.repository import replace_event_reminders

        replace_event_reminders(meeting, [{"offset_minutes": 0, "recipient_ids": [noa["id"]]}])
        from app.services.shifts import set_shifts_enabled

        set_shifts_enabled(True)

    listed = _go(app, _msg("/today"))
    assert "פגישה" in listed["text"]
    assert "בוקר" in listed["text"]
    only_shifts = _press(app, listed, "משמרות")
    assert "בוקר" in only_shifts["text"]
    assert "פגישה" not in only_shifts["text"]
    assert "רק משמרות" in only_shifts["text"]
    only_events = _press(app, only_shifts, "אירועים")
    assert "פגישה" in only_events["text"]
    assert "בוקר" not in only_events["text"]

    week = _go(app, _msg("/week"))
    assert "בלי משמרות" in week["text"]
    assert "בוקר" not in week["text"]
    _go(app, _cb("flt:all"))

    people = _go(app, _cb("who"))
    assert "משמרות" in people["text"] and "תזכורת" in people["text"]
    danny_list = _press(app, people, "דני")
    assert "בוקר" in danny_list["text"]
    assert "ערב" not in danny_list["text"]
    assert "תזכורת לנועה" not in danny_list["text"]
    noa_list = _go(app, _cb(f"who:{noa['id']}"))
    assert "תזכורת לנועה" in noa_list["text"]
    assert "ערב" in noa_list["text"]
    assert "בוקר" not in noa_list["text"]

    found = _go(app, _msg("/find זום"))
    assert "פגישה" in found["text"]
    assert "ארכיון" not in found["text"]
    old = _go(app, _msg("/find ארכיון"))
    assert "ארכיון" in old["text"]
    empty = _go(app, _msg("/find אין-כזה-דבר"))
    assert "אין תוצאות" in empty["text"]
    _has_exit(empty)
    prompt = _go(app, _msg("/find"))
    assert "מה לחפש" in prompt["text"]
    too_long = _go(app, _msg("/find " + "א" * 81))
    assert "ארוך" in too_long["text"]


def test_add_defaults_invalid_input_and_cancel(app):
    asked = _go(app, _msg("/add"))
    assert "שם" in asked["text"]
    _has_exit(asked)
    confirm = _go(app, _msg("פגישה"))
    assert "פגישה" in confirm["text"]
    assert "כל היום" in confirm["text"]
    assert hebrew_display(TODAY) in confirm["text"]
    assert "<code>22.10.2026</code>" in confirm["text"]
    assert _titles(app) == []

    cancelled = _press(app, confirm, "ביטול")
    assert "בוטל" in cancelled["text"]
    assert _titles(app) == []

    _go(app, _msg("/add"))
    confirm = _go(app, _msg("פגישה"))
    tomorrow = _press(app, confirm, "מחר")
    assert hebrew_display(TODAY + timedelta(days=1)) in tomorrow["text"]
    typed = _press(app, tomorrow, "תאריך אחר")
    bad = _go(app, _msg("32.13.2026"))
    assert "לא" in bad["text"]
    _has_exit(bad)
    bad_iso = _go(app, _msg("2026-02-31"))
    assert "לא קיים" in bad_iso["text"] or "לא" in bad_iso["text"]
    leap = _go(app, _msg("29.02.2024"))
    assert "29.02.2024" in leap["text"]

    times = _press(app, leap, "שעה")
    custom = _press(app, times, "שעה אחרת")
    invalid_time = _go(app, _msg("25:00"))
    assert "18:30" in invalid_time["text"]
    timed = _go(app, _msg("9:30"))
    assert "<code>09:30</code>" in timed["text"]
    described = _press(app, timed, "תיאור")
    with_desc = _go(app, _msg("להביא עוגה"))
    assert "עוגה" in with_desc["text"]
    _press(app, with_desc, "עד תאריך")
    too_early = _go(app, _msg("01.01.2020"))
    assert "לפני" in too_early["text"]
    saved = _press(app, too_early, "רק יום אחד")
    final = _press(app, saved, "שמירה")
    assert "נשמר" in final["text"]
    assert "<code>" in final["text"]
    with app.app_context():
        from app.database import get_all_events

        rows = get_all_events()
    assert len(rows) == 1
    assert rows[0]["title"] == "פגישה"
    assert rows[0]["gregorian_date"] == "2024-02-29"
    assert rows[0]["time"] == "09:30"
    assert rows[0]["hebrew_date"] == hebrew_display(__import__("datetime").date.fromisoformat("2024-02-29"))
    assert "עוגה" in (rows[0]["description"] or "")
    assert not rows[0]["end_date"]


def test_edit_delete_conflict_and_missing(app):
    event_id = _event(app, "ישן", TODAY, time="10:00")
    listed = _go(app, _msg("/today"))
    card = _press(app, listed, "ישן")
    assert "מזהה:" not in card["text"]
    assert f"<code>{event_id}</code>" not in card["text"]
    assert "10:00" in card["text"]
    editor = _press(app, card, "עריכה")
    _press(app, editor, "כותרת")
    renamed = _go(app, _msg("חדש"))
    assert "חדש" in renamed["text"]

    with app.app_context():
        from app.database import get_event, update_event

        current = get_event(event_id)
        update_event(
            event_id,
            "אחר",
            current["gregorian_date"],
            current["hebrew_date"],
            time=current["time"],
            description=current["description"] or "",
            end_date=current["end_date"],
            color=current["color"],
        )
    conflict = _press(app, renamed, "שמירה")
    assert "השתנה" in conflict["text"]
    assert "אחר" in conflict["text"]
    assert "חדש" in conflict["text"]
    shown = _press(app, conflict, "להציג מחדש")
    assert "אחר" in shown["text"]
    assert _titles(app) == ["אחר"]

    editor = _press(app, shown, "עריכה")
    _press(app, editor, "כותרת")
    renamed = _go(app, _msg("סופי"))
    forced_setup = renamed
    with app.app_context():
        from app.database import get_event, update_event

        current = get_event(event_id)
        update_event(
            event_id,
            "ביניים",
            current["gregorian_date"],
            current["hebrew_date"],
            time=current["time"],
            description="",
            end_date=None,
            color=current["color"],
        )
    conflict = _press(app, forced_setup, "שמירה")
    saved = _press(app, conflict, "לשמור בכל זאת")
    assert "נשמר" in saved["text"]
    assert _titles(app) == ["סופי"]

    card = _go(app, _cb(f"ev:{event_id}"))
    ask_delete = _press(app, card, "מחיקה")
    assert "אי אפשר לבטל" in ask_delete["text"]
    assert _titles(app) == ["סופי"]
    kept = _press(app, ask_delete, "לא")
    assert "סופי" in kept["text"]
    ask_delete = _press(app, kept, "מחיקה")
    gone = _press(app, ask_delete, "כן, למחוק")
    assert "נמחק" in gone["text"]
    assert _titles(app) == []
    missing = _go(app, _cb(f"ev:{event_id}"))
    assert "כבר לא" in missing["text"]
    _has_exit(missing)

    event_id = _event(app, "יימחק", TODAY)
    listed = _go(app, _msg("/today"))
    card = _press(app, listed, "יימחק")
    editor = _press(app, card, "עריכה")
    with app.app_context():
        from app.database import delete_event

        delete_event(event_id)
    missing = _press(app, editor, "שמירה")
    assert "כבר לא" in missing["text"]


def test_html_escape_and_recurring_delete_warning(app):
    event_id = _event(
        app,
        "<b>xss</b>",
        TODAY,
        recurrence={
            "recurrence_freq": "yearly",
            "recurrence_calendar": "gregorian",
            "recurrence_until": None,
            "recurrence_count": 3,
        },
    )
    listed = _go(app, _msg("/today"))
    assert "<b>xss</b>" not in listed["text"]
    assert "&lt;b&gt;xss&lt;/b&gt;" in listed["text"]
    card = _press(app, listed, "xss")
    assert "מזהה:" not in card["text"]
    assert "כל הסדרה" in card["text"]
    ask = _press(app, card, "מחיקה")
    assert "סדרה" in ask["text"]
    assert f"<code>{event_id}</code>" in ask["text"]


def test_shifts_toggle_create_and_date_edit(app):
    off = _go(app, _cb("shifts"))
    assert "כבויות" in off["text"]
    _has_exit(off)
    settings = _press(app, off, "הצגת משמרות ביומן")
    assert "להציג" in settings["text"]
    settings = _press(app, settings, "כן")
    assert "דלוקות" in settings["text"]

    _person(app, "דני", chat=42, works_shifts=0)
    empty = _go(app, _cb("shifts"))
    assert "אין משמרות" in empty["text"]
    start = _press(app, empty, "משמרת חדשה")
    assert "אף אחד" in start["text"]
    workers = _press(app, start, "מי עובד במשמרות")
    flipped = _press(app, workers, "דני")
    assert "דני · כן" in [button["text"] for button in _buttons(flipped)]

    start = _go(app, _cb("sh:new"))
    assert "איזו משמרת" in start["text"]
    confirm = _press(app, start, "בוקר")
    assert "לשמור משמרת" in confirm["text"]
    assert hebrew_display(TODAY) in confirm["text"]
    saved = _press(app, confirm, "שמירה")
    assert "נשמר" in saved["text"]
    with app.app_context():
        from app.database import get_all_events

        shift = get_all_events()[0]
    assert shift["is_shift"] == 1
    assert shift["shift_label"] == "בוקר"
    assert shift["time"] is None

    listed = _go(app, _cb("shifts"))
    card = _press(app, listed, "בוקר")
    assert "אפשר לערוך" in card["text"]
    editor = _press(app, card, "עריכה")
    assert "מה לשנות" in editor["text"]
    assert "סוג משמרת" in [button["text"] for button in _buttons(editor)]
    date_screen = _press(app, editor, "תאריך")
    assert "המשמרת תעבור" in date_screen["text"]
    moved = _press(app, date_screen, "מחר")
    assert "התאריך עודכן" in moved["text"]
    saved = _press(app, moved, "שמירה")
    assert "נשמר" in saved["text"]
    with app.app_context():
        from app.database import get_all_events

        shift = get_all_events()[0]
    assert shift["gregorian_date"] == (TODAY + timedelta(days=1)).isoformat()
    assert shift["is_shift"] == 1
    assert shift["title"] == "בוקר"
    assert shift["shift_label"] == "בוקר"


def test_shift_detail_edit_reaches_title_note_person_and_label(app):
    danny = _person(app, "דני", works_shifts=1)
    noa = _person(app, "נועה", works_shifts=1)
    _person(app, "אורח", works_shifts=0)
    _event(app, "בוקר", TODAY, shift=(1, danny["id"], "בוקר"))

    card = _press(app, _go(app, _msg("/today")), "בוקר")
    labels = [button["text"] for button in _buttons(card)]
    assert "אפשר לערוך, למחוק, או לחזור לרשימה." in card["text"]
    assert any("עריכה" in label for label in labels)
    assert any("מחיקה" in label for label in labels)
    assert any("חזרה לרשימה" in label for label in labels)
    assert any("תפריט" in label for label in labels)
    assert not any("שינוי תאריך" in label for label in labels)
    styles = {button["text"]: button.get("style") for button in _buttons(card)}
    assert styles["✏️ עריכה"] == "primary"
    assert styles["🗑 מחיקה"] == "danger"

    editor = _press(app, card, "עריכה")
    datas = [button["callback_data"] for button in _buttons(editor)]
    assert {"edf:title", "edf:desc", "edf:date", "edf:person", "edf:label", "ed:ok"} <= set(datas)
    assert "edf:time" not in datas
    assert "edf:end" not in datas
    assert "משמרת · דני · בוקר" in editor["text"]

    _press(app, editor, "כותרת")
    titled = _go(app, _msg("משמרת כפולה"))
    assert "מה לשנות ב«משמרת כפולה»" in titled["text"]
    assert "הכותרת עודכנה" in titled["text"]

    note = _press(app, titled, "תיאור")
    assert "בלי תיאור" in [button["text"] for button in _buttons(note)]
    cleared = _press(app, note, "בלי תיאור")
    assert "התיאור עודכן" in cleared["text"]
    note = _press(app, cleared, "תיאור")
    noted = _go(app, _msg("להביא מפתחות"))
    assert "להביא מפתחות" in noted["text"]

    people = _press(app, noted, "אדם")
    assert "למי המשמרת" in people["text"]
    people_labels = [button["text"] for button in _buttons(people)]
    assert any(label.endswith("דני") for label in people_labels)
    assert "נועה" in people_labels
    assert "אורח" not in people_labels
    assert all(
        button["callback_data"].startswith("ed:p:")
        for button in _buttons(people)
        if button["callback_data"] not in {"back:edit", "cancel"}
    )
    stayed = _go(app, _msg("לא כפתור"))
    assert "למי המשמרת" in stayed["text"]
    moved_person = _press(app, stayed, "נועה")
    assert "האדם עודכן" in moved_person["text"]
    assert "משמרת · נועה · בוקר" in moved_person["text"]

    kinds = _press(app, moved_person, "סוג משמרת")
    kind_data = [button["callback_data"] for button in _buttons(kinds)]
    assert {"ed:l:m", "ed:l:e", "ed:l:n"} <= set(kind_data)
    back = _press(app, kinds, "חזרה")
    assert "מה לשנות ב«משמרת כפולה»" in back["text"]
    kinds = _press(app, back, "סוג משמרת")
    labeled = _press(app, kinds, "לילה")
    assert "סוג המשמרת עודכן" in labeled["text"]
    assert "משמרת · נועה · לילה" in labeled["text"]
    assert "מה לשנות ב«משמרת כפולה»" in labeled["text"]

    dated = _press(app, _press(app, labeled, "תאריך"), "מחר")
    assert "התאריך עודכן" in dated["text"]
    saved = _press(app, dated, "שמירה")
    assert "נשמר" in saved["text"]
    assert "<b>לילה</b>" in saved["text"]
    assert "נועה" in saved["text"]
    assert "להביא מפתחות" in saved["text"]
    assert "משמרת כפולה" not in saved["text"]
    assert any("מחיקה" in button["text"] for button in _buttons(saved))
    again = _press(app, saved, "עריכה")
    assert "מה לשנות ב«משמרת כפולה»" in again["text"]

    with app.app_context():
        from app.database import get_all_events

        shift = get_all_events()[0]
    assert shift["is_shift"] == 1
    assert shift["title"] == "משמרת כפולה"
    assert shift["description"] == "להביא מפתחות"
    assert shift["shift_label"] == "לילה"
    assert shift["shift_person_id"] == noa["id"]
    assert shift["gregorian_date"] == (TODAY + timedelta(days=1)).isoformat()
    assert shift["time"] is None
    assert not shift["end_date"]

    plain = _event(app, "בוקר", TODAY, shift=(1, danny["id"], "בוקר"))
    listed = _go(app, _msg("/today"))
    card = _press(app, listed, "בוקר")
    editor = _press(app, card, "עריכה")
    saved = _press(app, _press(app, _press(app, editor, "סוג משמרת"), "ערב"), "שמירה")
    assert "נשמר" in saved["text"]
    with app.app_context():
        from app.database import get_event

        synced = get_event(plain)
    assert synced["shift_label"] == "ערב"
    assert synced["title"] == "ערב"
    assert synced["shift_person_id"] == danny["id"]


def test_shift_display_uses_label_when_title_differs(app):
    person = _person(app, "דני", works_shifts=1)
    _event(app, "בוקר מוקדם", TODAY, shift=(1, person["id"], "בוקר"))
    listed = _go(app, _msg("/today"))
    assert "<b>בוקר</b>" in listed["text"]
    assert "בוקר מוקדם" not in listed["text"]
    card = _press(app, listed, "בוקר")
    assert "<b>בוקר</b>" in card["text"]
    assert "בוקר מוקדם" not in card["text"]
    ask = _press(app, card, "מחיקה")
    assert "«בוקר»" in ask["text"]
    assert "בוקר מוקדם" not in ask["text"]
    found = _go(app, _msg("/find בוקר"))
    assert "<b>בוקר</b>" in found["text"]
    by_title = _go(app, _msg("/find בוקר מוקדם"))
    assert "<b>בוקר</b>" in by_title["text"]


def test_settings_link_unlink_and_households(app, monkeypatch):
    danny = _person(app, "דני", chat=99)
    noa = _person(app, "נועה", chat=42)
    settings = _go(app, _msg("/settings"))
    assert "<code>42</code>" in settings["text"]
    assert "נועה" in settings["text"]
    picker = _press(app, settings, "חיבור לאדם")
    conflict = _press(app, picker, "דני")
    assert "99" in conflict["text"]
    assert "<code>99</code>" in conflict["text"]
    done = _press(app, conflict, "חיבור בלי לנתק")
    assert "דני" in done["text"]
    with app.app_context():
        from app.reminders.repository import get_person

        assert get_person(danny["id"])["telegram_chat_id"] == "42"
        assert get_person(noa["id"])["telegram_chat_id"] == "42"

    picker = _press(app, done, "חיבור לאדם")
    conflict = _press(app, picker, "דני")
    moved = _press(app, conflict, "העברה")
    with app.app_context():
        from app.reminders.repository import get_person

        assert get_person(danny["id"])["telegram_chat_id"] == "42"
        assert get_person(noa["id"])["telegram_chat_id"] in (None, "")

    picker = _press(app, moved, "חיבור לאדם")
    fresh = _press(app, picker, "אני לא ברשימה")
    missing = _go(app, _msg("  "))
    assert "שם" in missing["text"] or "חסר" in missing["text"]
    too_long = _go(app, _msg("א" * 81))
    assert "ארוך" in too_long["text"]
    created = _go(app, _msg("רינה"))
    assert "רינה" in created["text"]

    unlinked = _press(app, created, "ניתוק רינה")
    assert "נותק" in unlinked["text"] or "רינה" in unlinked["text"]

    labels = [b["text"] for b in _buttons(unlinked)]
    off = _press(app, unlinked, "הסתרת משמרות ביומן") if "הסתרת משמרות ביומן" in labels else _press(
        app, unlinked, "הצגת משמרות ביומן"
    )
    # המשמרות כבויות בהתחלה, אז זה מסך ההדלקה
    assert "משמרות" in off["text"]
    _press(app, off, "לא")

    homes = [
        {"id": 1, "shifts_enabled": False, "name": "בית 1"},
        {"id": 2, "shifts_enabled": True, "name": "בית 2"},
    ]
    monkeypatch.setattr("app.bot.household.list_households", lambda: homes)
    calls = []

    def _set(household_id, enabled):
        calls.append((household_id, enabled))
        for home in homes:
            if home["id"] == household_id:
                home["shifts_enabled"] = enabled
        return enabled

    monkeypatch.setattr("app.bot.household.set_household_shifts", _set)
    with app.app_context():
        from app.bot.session import save_session

        save_session("42", {"household_id": 99})
    picked = _go(app, _msg("/settings"))
    assert "כבר לא קיים" in picked["text"]
    assert "בית 1" in [button["text"].replace("• ", "") for button in _buttons(picked)]
    assert "בית 2" in [button["text"].replace("• ", "") for button in _buttons(picked)]
    chosen = _press(app, picked, "בית 2")
    assert "בית 2" in chosen["text"]
    ask = _press(app, chosen, "הסתרת משמרות ביומן")
    _press(app, ask, "כן")
    assert calls == [(2, False)]


def test_single_missing_household_falls_back(app):
    with app.app_context():
        from app.bot.session import save_session

        save_session("7", {"household_id": 99})
    reply = _go(app, _msg("/settings", chat=7))
    assert "עברנו" in reply["text"]
    assert "הצגת משמרות ביומן" in [button["text"] for button in _buttons(reply)]


def test_other_date_hint_and_edit_field_saved(app):
    _go(app, _msg("/add"))
    confirm = _go(app, _msg("פגישה"))
    asked = _press(app, confirm, "תאריך אחר")
    assert "DD.MM.YYYY" in asked["text"]
    assert "251026" in asked["text"]
    assert 'י"ג חשון' in asked["text"]
    chosen = _go(app, _msg('י"ג חשון'))
    assert "24.10.2026" in chosen["text"]

    _event(app, "בלי", TODAY)
    card = _press(app, _go(app, _msg("/today")), "בלי")
    editor = _press(app, card, "עריכה")
    desc = _press(app, editor, "תיאור")
    assert "בלי תיאור מוחק את התיאור." in desc["text"]
    assert "«" not in desc["text"]
    back = _press(app, desc, "בלי תיאור")
    assert "התיאור עודכן ✅ — לשנות עוד משהו?" in back["text"]
    labels = [button["text"] for button in _buttons(back)]
    for name in ("כותרת", "תאריך", "שעה", "תיאור", "תאריך סיום", "שמירה"):
        assert name in labels


def test_edit_time_and_replace_lonely_chat(app):
    _event(app, "שעה", TODAY)
    card = _press(app, _go(app, _msg("/today")), "שעה")
    editor = _press(app, card, "עריכה")
    times = _press(app, editor, "שעה")
    picked = _press(app, times, "18:00")
    saved = _press(app, picked, "שמירה")
    assert "<code>18:00</code>" in saved["text"]
    with app.app_context():
        from app.database import get_all_events

        assert get_all_events()[0]["time"] == "18:00"

    person = _person(app, "יחיד", chat=77)
    settings = _go(app, _msg("/settings"))
    conflict = _press(app, _press(app, settings, "חיבור לאדם"), "יחיד")
    assert "להחליף" in conflict["text"]
    assert "<code>77</code>" in conflict["text"]
    done = _press(app, conflict, "כן, להחליף")
    assert "יחיד" in done["text"]
    with app.app_context():
        from app.reminders.repository import get_person

        assert get_person(person["id"])["telegram_chat_id"] == "42"


def test_chats_do_not_share_a_draft(app):
    _go(app, _msg("/add", chat=1))
    other = _go(app, _msg("/start", chat=2))
    assert "בוטל" not in other["text"]
    assert "<code>2</code>" in other["text"]
    assert "מה עושים?" not in other["text"]
    still = _go(app, _msg("פגישה", chat=1))
    assert "לשמור" in still["text"]


def test_today_during_draft_cancels_it(app):
    _go(app, _msg("/add"))
    _go(app, _msg("טיוטה"))
    listed = _go(app, _msg("/today"))
    assert "הטיוטה בוטלה" in listed["text"]
    assert _titles(app) == []


def test_consume_updates_sends_menu_and_answers_buttons(app):
    # consume_updates קורא ל-handle_update בלי שעון מוזרק, אז האירוע חייב להיות על היום האמיתי.
    _event(app, "סיור", datetime.now(TZ).date())
    calls = []

    def api(token, method, payload=None, timeout=30):
        calls.append((method, payload))
        if method == "getUpdates":
            return [
                {"update_id": 7, "message": {"text": "/start", "chat": {"id": 42}}},
                {
                    "update_id": 8,
                    "callback_query": {
                        "id": "c1",
                        "data": "today",
                        "message": {"message_id": 3, "chat": {"id": 42}},
                    },
                },
            ]
        return {"ok": True}

    assert consume_updates("token", None, api=api) == 9
    sent = next(call[1] for call in calls if call[0] == "sendMessage")
    assert "<code>42</code>" in sent["text"]
    start_labels = [
        button["text"]
        for row in sent["reply_markup"]["inline_keyboard"]
        for button in row
    ]
    assert start_labels == ["חיבור כאן"]
    methods = [call[0] for call in calls]
    answers = [call for call in calls if call[0] == "answerCallbackQuery"]
    assert len(answers) == 1
    assert answers[0][1]["text"] == "פותח…"
    edit_at = next(index for index, call in enumerate(calls) if call[0] == "editMessageText")
    assert calls.index(answers[0]) < edit_at
    assert "editMessageText" in methods
    edited = next(call[1] for call in calls if call[0] == "editMessageText")
    assert "סיור" in edited["text"]
    assert edited["parse_mode"] == "HTML"


def test_people_picker_paginates(app):
    for index in range(7):
        _person(app, f"אדם-{index}")
    picker = _go(app, _cb("who"))
    assert "הבא ←" in [button["text"] for button in _buttons(picker)]
    assert "אדם-0" in picker["text"] or any(button["text"] == "אדם-0" for button in _buttons(picker))
    page2 = _press(app, picker, "הבא")
    labels = [button["text"] for button in _buttons(page2)]
    assert "אדם-6" in labels
    assert "אדם-0" not in labels


def test_all_day_word_and_shift_disabled_blocks_create(app):
    asked = _go(app, _msg("/add"))
    confirm = _go(app, _msg("בלי שעה"))
    times = _press(app, confirm, "שעה")
    custom = _press(app, times, "שעה אחרת")
    allday = _go(app, _msg("כל היום"))
    assert "כל היום" in allday["text"]
    saved = _press(app, allday, "שמירה")
    assert "נשמר" in saved["text"]
    with app.app_context():
        from app.database import get_all_events

        assert get_all_events()[0]["time"] is None


def test_shifts_board_is_one_week_and_start_stays_the_menu(app):
    from app.services.shifts import set_shifts_enabled

    with app.app_context():
        set_shifts_enabled(True)
    avihai = _person(app, "אביחי", chat=42, works_shifts=1)
    shira = _person(app, "שירה", works_shifts=1)
    sunday = TODAY - timedelta(days=weekday_index(TODAY))
    next_sunday = sunday + timedelta(days=7)
    monday = next_sunday + timedelta(days=1)
    _event(app, "בוקר", next_sunday, shift=(1, avihai["id"], "בוקר"))
    _event(app, "ערב", next_sunday, shift=(1, shira["id"], "ערב"))
    _event(app, "בוקר מוקדם", monday, shift=(1, avihai["id"], "בוקר"))
    for label in ("בוקר", "ערב", "לילה"):
        _event(app, label, monday, shift=(1, shira["id"], label))
    _event(app, "לפני", sunday - timedelta(days=1), shift=(1, avihai["id"], "לילה"))
    later = sunday + timedelta(days=14)
    _event(app, "אחר כך", later, shift=(1, avihai["id"], "בוקר"))

    listed = _go(app, _cb("shifts"))
    assert "<code>18.10.2026–24.10.2026</code> · פרשת לך לך" in listed["text"]
    assert "אין משמרות בשבוע הזה" in listed["text"]
    assert "25.10" not in listed["text"]
    assert "לפני" not in listed["text"]
    assert "אחר כך" not in listed["text"]
    assert "כל היום" not in listed["text"]
    assert "עמוד " not in listed["text"]
    assert [[button["text"] for button in row] for row in listed["markup"]["inline_keyboard"]] == [
        ["שבוע הבא ←", "→ שבוע קודם"],
        ["➕ משמרת חדשה", "🏠 תפריט ראשי"],
    ]

    nxt = _press(app, listed, "שבוע הבא")
    assert "<code>25.10.2026–31.10.2026</code> · פרשת וירא" in nxt["text"]
    assert "18.10.2026" not in nxt["text"]
    assert "א׳ 25.10 · אביחי בוקר · שירה ערב" in nxt["text"]
    assert "ב׳ 26.10 · אביחי בוקר מוקדם · שירה בוקר, ערב, לילה" in nxt["text"]
    assert "אין משמרות" not in nxt["text"]
    assert "אחר כך" not in nxt["text"]
    for letter in ("ג׳", "ד׳", "ה׳", "ו׳", "ש׳"):
        assert letter not in nxt["text"]
    assert [[button["text"] for button in row] for row in nxt["markup"]["inline_keyboard"]] == [
        ["א׳ אביחי בוקר", "א׳ שירה ערב"],
        ["ב׳ אביחי בוקר מוקדם", "ב׳ שירה בוקר", "ב׳ שירה ערב"],
        ["ב׳ שירה לילה"],
        ["שבוע הבא ←", "השבוע", "→ שבוע קודם"],
        ["➕ משמרת חדשה", "🏠 תפריט ראשי"],
    ]

    card = _press(app, nxt, "א׳ אביחי בוקר")
    assert "<b>בוקר</b>" in card["text"]
    assert "אביחי" in card["text"]

    far = _press(app, nxt, "שבוע הבא")
    assert "<code>01.11.2026–07.11.2026</code>" in far["text"]
    assert "א׳ 1.11 · אביחי אחר כך" in far["text"]
    assert "25.10" not in far["text"]

    jumped = _press(app, far, "השבוע")
    assert "<code>18.10.2026–24.10.2026</code>" in jumped["text"]
    assert "אין משמרות בשבוע הזה" in jumped["text"]
    assert "אחר כך" not in jumped["text"]
    assert "השבוע" not in [button["text"] for button in _buttons(jumped)]

    back = _press(app, nxt, "שבוע קודם")
    assert "<code>18.10.2026–24.10.2026</code>" in back["text"]
    assert "אחר כך" not in back["text"]

    earlier = _press(app, listed, "שבוע קודם")
    assert "<code>11.10.2026–17.10.2026</code>" in earlier["text"]
    assert "ש׳ 17.10 · אביחי לפני" in earlier["text"]
    assert "25.10" not in earlier["text"]

    home = _go(app, _msg("/start"))
    assert home["text"] == "📅 לוח השנה המשותף — מה להציג?"
    assert "פרשת" not in home["text"]
    assert "👷 משמרות" in [button["text"] for button in _buttons(home)]


def _shift_event_buttons(markup):
    return [
        button
        for row in markup["inline_keyboard"]
        for button in row
        if button["callback_data"].startswith("ev:")
    ]


def test_shifts_board_buttons_start_with_weekday_letter_and_duplicates_stay_unique():
    from app.bot.ui import DAY_LETTERS, shifts_board

    people = {
        1: {"id": 1, "name": "אביחי"},
        2: {"id": 2, "name": "שירה"},
    }
    sunday = date(2026, 10, 25)
    monday = date(2026, 10, 26)
    tuesday = date(2026, 10, 27)
    wednesday = date(2026, 10, 28)

    def shift(eid, person, day, label, title=None):
        return {
            "id": eid,
            "gregorian_date": day.isoformat(),
            "is_shift": 1,
            "shift_person_id": person,
            "shift_label": label,
            "title": title or label,
        }

    rows = [
        shift(10, 1, sunday, "בוקר"),
        shift(11, 1, monday, "ערב"),
        shift(12, 2, monday, "לילה"),
        shift(13, 1, tuesday, "ערב"),
        shift(14, 1, wednesday, "בוקר"),
        shift(15, 2, wednesday, "ערב"),
        shift(16, 1, sunday, "בוקר"),
    ]
    _text, markup = shifts_board(rows, people, date(2026, 10, 22), sunday)
    buttons = _shift_event_buttons(markup)
    labels = [button["text"] for button in buttons]
    assert labels
    assert all(
        any(label.startswith(f"{letter} ") for letter in DAY_LETTERS) for label in labels
    )
    assert len(labels) == len(set(labels))
    assert labels == [
        "א׳ אביחי בוקר",
        "א׳ אביחי בוקר #16",
        "ב׳ אביחי ערב",
        "ב׳ שירה לילה",
        "ג׳ אביחי ערב",
        "ד׳ אביחי בוקר",
        "ד׳ שירה ערב",
    ]
    assert not any(
        any(part in label for part in ("25.10", "26.10", "27.10", "28.10"))
        for label in labels
    )
    callbacks = [button["callback_data"] for button in buttons]
    assert callbacks == [
        "ev:10:20261025",
        "ev:16:20261025",
        "ev:11:20261026",
        "ev:12:20261026",
        "ev:13:20261027",
        "ev:14:20261028",
        "ev:15:20261028",
    ]


def test_callback_ack_is_before_the_screen_and_under_a_second(app, monkeypatch):
    """שעון החול נעצר לפני בניית המסך, לא אחריה."""
    import time

    marks = {}
    payloads = {}

    def slow(update, now=None):
        marks["handle"] = time.monotonic()
        time.sleep(0.2)
        return {
            "text": "כרטיס",
            "markup": None,
            "toast": "נשמר",
            "chat_id": 42,
            "callback_id": "c9",
            "edit_id": 4,
        }

    monkeypatch.setattr("app.bot.dispatch.handle_update", slow)

    def api(token, method, payload=None, timeout=30):
        marks[method] = time.monotonic()
        payloads[method] = payload
        if method == "getUpdates":
            return [
                {
                    "update_id": 1,
                    "callback_query": {
                        "id": "c9",
                        "data": "ev:1:20261022",
                        "message": {"message_id": 4, "chat": {"id": 42}},
                    },
                }
            ]
        return {"ok": True}

    consume_updates("token", None, api=api)
    ack_delay = marks["answerCallbackQuery"] - marks["getUpdates"]
    assert ack_delay < 0.05, ack_delay
    assert marks["answerCallbackQuery"] < marks["handle"]
    assert payloads["answerCallbackQuery"]["text"] == "פותח…"
    assert marks["editMessageText"] > marks["handle"]


def test_updates_poll_while_reminders_are_still_running():
    """לחיצה לא מחכה לסבב התזכורות (שהיה בערך 15 שניות)."""
    import threading
    import time

    from app.reminders.worker import UPDATE_LONG_POLL_SECONDS, run_loop

    stop = threading.Event()
    polled = threading.Event()
    seen = {}
    started = time.monotonic()

    def process():
        seen["overlapped"] = polled.wait(0.8)
        stop.set()

    def consume(token, offset, *, long_poll=0):
        seen.setdefault("delay", time.monotonic() - started)
        seen.setdefault("long_poll", long_poll)
        polled.set()
        return offset

    thread = threading.Thread(
        target=run_loop,
        kwargs={
            "interval": 30,
            "stop_event": stop,
            "consume": consume,
            "process": process,
            "token_fn": lambda: "token",
        },
        daemon=True,
    )
    thread.start()
    thread.join(2)
    elapsed = time.monotonic() - started
    assert not thread.is_alive()
    assert seen.get("overlapped") is True
    assert seen.get("long_poll") == UPDATE_LONG_POLL_SECONDS == 25
    assert seen["delay"] < 1.0, seen["delay"]
    assert elapsed < 1.0, elapsed


def test_person_view_groups_shifts_then_events(app):
    person = _person(app, "דני", works_shifts=1)
    later = TODAY + timedelta(days=3)
    _event(app, "לילה", later, shift=(1, person["id"], "לילה"))
    meeting = _event(app, "פגישה", TODAY, time="11:00")
    with app.app_context():
        from app.reminders.repository import replace_event_reminders

        replace_event_reminders(meeting, [{"offset_minutes": 0, "recipient_ids": [person["id"]]}])

    today = _go(app, _msg("/today"))
    assert "• <b>פגישה</b>" in today["text"]
    assert "👷" not in today["text"]
    assert "🔔" not in today["text"]
    week = _go(app, _msg("/week"))
    assert "• <b>" in week["text"]
    assert "👷" not in week["text"]
    assert "🔔" not in week["text"]

    listed = _go(app, _cb(f"who:{person['id']}"))
    text = listed["text"]
    shift_at = text.index("👷 <b>לילה</b>")
    event_at = text.index("🔔 <b>פגישה</b>")
    assert text.index("<b>משמרות</b>") < shift_at < text.index("<b>אירועים</b>") < event_at
    assert "•" not in text
    labels = [button["text"] for button in _buttons(listed)]
    assert labels.index(next(label for label in labels if "לילה" in label)) < labels.index(
        next(label for label in labels if "פגישה" in label)
    )

    only_shifts = _press(app, listed, "משמרות")
    assert "<b>משמרות</b>" in only_shifts["text"]
    assert "👷 <b>לילה</b>" in only_shifts["text"]
    assert "<b>אירועים</b>" not in only_shifts["text"]
    assert "🔔" not in only_shifts["text"]
    assert "•" not in only_shifts["text"]


def test_add_event_reminder_uses_the_same_offsets(app):
    person = _person(app, "דני", chat=42, receives_reminders=1)
    _go(app, _msg("/add"))
    confirm = _go(app, _msg("אירוע בדיקה"))
    assert "בלי תזכורת" in confirm["text"]
    timed = _press(app, _press(app, confirm, "שעה"), "12:00")
    tomorrow = _press(app, timed, "מחר")
    remind = _press(app, tomorrow, "תזכורת")
    assert "מתי להזכיר" in remind["text"]
    picked = _press(app, _press(app, remind, "15 דקות"), "יום")
    who = _press(app, picked, "למי")
    chosen = _press(app, who, "דני")
    done = _press(app, chosen, "סיום")
    assert "תזכורת: 15 דקות, יום · דני" in done["text"]
    assert "12:00" in done["text"]
    saved = _press(app, done, "שמירה")
    assert "נשמר" in saved["text"]
    with app.app_context():
        from app.database import get_all_events

        rows = get_all_events()
    assert len(rows) == 1
    assert rows[0]["title"] == "אירוע בדיקה"
    assert rows[0]["time"] == "12:00"
    assert rows[0]["gregorian_date"] == (TODAY + timedelta(days=1)).isoformat()
    reminders = rows[0]["reminders"]
    assert [item["offset_minutes"] for item in reminders] == [15, 1440]
    assert reminders[0]["recipient_ids"] == [person["id"]]
    assert reminders[1]["recipient_ids"] == [person["id"]]

    skipped = _go(app, _msg("/add"))
    plain = _go(app, _msg("בלי תזכורת עכשיו"))
    assert "בלי תזכורת" in plain["text"]
    _press(app, plain, "שמירה")
    with app.app_context():
        from app.database import get_all_events

        bare = next(row for row in get_all_events() if row["title"] == "בלי תזכורת עכשיו")
    assert bare["reminders"] == []


def test_find_shows_description_in_italics_under_the_title(app):
    _event(app, "פגישה", TODAY, time="18:30", description="להביא <עוגה>\nונרות")
    _event(app, "בלי תיאור", TODAY + timedelta(days=1))
    found = _go(app, _msg("/find עוגה"))
    assert "• <b>פגישה</b>\n  22.10.2026 · 18:30\n  <i>להביא &lt;עוגה&gt; ונרות</i>" in found["text"]
    labels = [button["text"] for button in _buttons(found)]
    assert any(label.startswith("22.10 פגישה") for label in labels)
    assert all("עוגה" not in label for label in labels)
    today = _go(app, _msg("/today"))
    assert "<i>" not in today["text"]
    assert "עוגה" not in today["text"]
    plain = _go(app, _msg("/find בלי תיאור"))
    assert "<b>בלי תיאור</b>" in plain["text"]
    assert "<i>" not in plain["text"]


def test_find_clips_a_long_description(app):
    from app.bot.ui import SEARCH_BLURB

    _event(app, "ארוך", TODAY, description="א" * (SEARCH_BLURB + 20))
    found = _go(app, _msg("/find ארוך"))
    assert f"<i>{'א' * (SEARCH_BLURB - 1)}…</i>" in found["text"]
    assert "א" * SEARCH_BLURB not in found["text"].split("<i>", 1)[1]


def test_menu_commands_are_the_ones_the_bot_handles(app):
    from app.bot.commands import BOT_COMMANDS

    _person(app, "דני", chat=42)
    names = [name for name, _description in BOT_COMMANDS]
    assert names == ["start", "today", "week", "add", "find", "settings", "help", "menu"]
    for name, description in BOT_COMMANDS:
        assert description.strip()
        assert len(description) <= 256
        reply = _go(app, _msg(f"/{name}"))
        assert "אין פקודה" not in reply["text"], name
    missing = _go(app, _msg("/nope"))
    assert "אין פקודה" in missing["text"]


def test_publish_bot_commands_uses_set_my_commands():
    from app.bot.commands import command_menu_payload
    from app.reminders.telegram import TelegramError, publish_bot_commands

    calls = []

    def api(token, method, payload=None, timeout=30):
        calls.append((token, method, payload, timeout))
        return True

    assert publish_bot_commands("secret-token", api=api) is True
    token, method, payload, timeout = calls[0]
    assert token == "secret-token"
    assert method == "setMyCommands"
    assert timeout == 30
    assert payload == command_menu_payload()
    assert "language_code" not in payload
    assert "scope" not in payload

    def boom(token, method, payload=None, timeout=30):
        raise TelegramError("setMyCommands failed: HTTP 401")

    assert publish_bot_commands("secret-token", api=boom) is False
    assert publish_bot_commands("", api=api) is False
    assert len(calls) == 1


def test_worker_registers_commands_on_startup(monkeypatch):
    import app.reminders.worker as worker

    calls = []
    monkeypatch.setattr(worker, "bot_token", lambda: "tok")
    monkeypatch.setattr(worker, "publish_bot_commands", lambda token: calls.append(token) or True)
    monkeypatch.setattr(worker, "run_once", lambda **kwargs: calls.append(("once", kwargs)))
    assert worker.main(["--once"]) == 0
    assert calls == ["tok", ("once", {"long_poll": 0})]

    calls.clear()
    monkeypatch.setattr(worker, "bot_token", lambda: "")
    assert worker.main(["--once"]) == 0
    assert calls == [("once", {"long_poll": 0})]
