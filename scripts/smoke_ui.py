"""בדיקת smoke בדפדפן (Playwright + Chromium) לזרימות העיקריות של ה-UI.

לא חלק מ-pytest (דורש דפדפן ושרת רץ). מוסיף ומוחק אירועים — להריץ מול DB זמני:

    DATABASE_PATH=/tmp/smoke.sqlite python -m flask --app app run --port 5000
    python scripts/smoke_ui.py --base-url http://127.0.0.1:5000 --snapshot /tmp/smoke.json

בודק:
  לוח: הוספה (כולל חילוץ שעה מהכותרת), עריכה בדאבל-קליק, הפיכה לרב-יומי, מחיקה
       מתפריט ההקשר, "הוסף אירוע" מתפריט ההקשר, כפתור "היום", "דלג לתאריך".
  רשימת אירועים: הוספה מהמודל, חיפוש, ייצוא JSON, מחיקה מהטבלה.
  בכל הדפים: אין שגיאות console ואין חריגות JS.

--snapshot כותב JSON של מצב ה-UI (פונקציות גלובליות, HTML של הלוח אחרי טעינה,
כותרות מודל וכו') — להשוואה לפני/אחרי ריפקטור (diff בין שתי ריצות על אותו יום).
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
import urllib.request

from playwright.sync_api import Page, expect, sync_playwright

# שמות שהוגדרו ב-script.js המקורי — לבדוק שכולם עדיין גלובליים באותו סוג
GLOBAL_NAMES = [
    "formatDate", "get_hebrew_day", "getShortMonthName", "isEndDateBeforeStart",
    "syncEndDateMin", "assertEndDateNotBeforeStart", "monthKey", "shiftMonth",
    "splitDateStr", "isInfiniteCalendarPage", "getWeeksBody", "weekStartOf",
    "weekDatesOf", "buildDayCell", "getRealDays", "formatToolbarLabel",
    "fetchMonthData", "fetchJewishMonth", "requestMonth", "monthEntryFor",
    "dayInfoFor", "isWeekReady", "paintWeekRow", "buildWeekRow", "contentTopY",
    "rowAtY", "captureAnchor", "restoreAnchor", "preserveScrollAnchor",
    "scrollTargetFor", "appendWeeks", "prependWeeks", "trimFarWeeks",
    "prefetchAroundRenderedRange", "maintainInfiniteCalendar", "scheduleMaintain",
    "onStreamScroll", "onStreamScrollEnd", "onCalendarResize",
    "updateVisibleMonthLabel", "getTodayDateStr", "loadMonthsAround",
    "waitForFonts", "renderAround", "scrollToDate", "jumpToMonth",
    "initInfiniteCalendar", "repaintInfiniteCalendarEvents", "loadEvents",
    "showMessage", "createEvent", "refreshEventsViews",
    "fillHebrewDateFromGregorian", "formatShortGregorian", "formatShortHebrew",
    "setQuickColor", "setQuickEventModalMode", "populateQuickHourOptions",
    "clearExtraQuickMinuteOptions", "setQuickTime", "getQuickTimeValue",
    "extractTimeFromTitle", "applyTimeFromTitlePrefix", "fillQuickEventForm",
    "getQuickEventFormData", "openQuickEventModal", "openEditEventModal",
    "initCalendarContextMenu", "initQuickEventModal", "updateEvent", "deleteEvent",
    "goToToday", "getColorRGBA", "resolveEventColor", "eventChipFill",
    "isPageZoomed", "isDateInRange", "isMultiDayEvent",
    "addDaysToDateStr", "getEventDurationDays", "getMultiDaySegmentRole",
    "assignMultiDayLanes", "buildEventItemHtml", "renderMultiDayRail",
    "getCachedEvents", "paintCellEvents",
]
# lexical globals (const/let) — לא על window, נבדקים ב-typeof דרך eval
LEXICAL_NAMES = ["END_DATE_BEFORE_START_MSG", "INFINITE_CONFIG", "infiniteCalendar", "GREGORIAN_MONTH_NAMES_HE"]


def api(base: str, method: str, path: str, body: dict | None = None) -> dict:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        base + path, data=data, method=method, headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req) as res:
        return json.loads(res.read() or b"null")


def wait_calendar(page: Page) -> None:
    page.wait_for_selector(".infinite-calendar:not(.is-booting)")
    page.wait_for_timeout(300)


def globals_snapshot(page: Page) -> dict:
    return page.evaluate(
        """([names, lexical]) => {
            const out = {};
            for (const n of names) out[n] = typeof window[n];
            for (const n of lexical) out[n] = (0, eval)(`typeof ${n}`);
            return out;
        }""",
        [GLOBAL_NAMES, LEXICAL_NAMES],
    )


def cell(page: Page, date: str):
    return page.locator(f'#calendar-weeks td[data-date="{date}"]')


def context_action(page: Page, target, action: str) -> str:
    """פותח תפריט הקשר ולוחץ על פעולה. כל scroll (גם תיקון עוגן של הלוח) סוגר
    את התפריט בכוונה, ו-click() אמיתי גולל לתצוגה — לכן dispatch + ניסיון חוזר."""
    menu = page.locator("#calendarContextMenu")
    for _ in range(5):
        page.wait_for_timeout(500)
        target.click(button="right")
        html = menu.inner_html()
        button = menu.locator(f'button[data-action="{action}"]')
        if button.count():
            button.dispatch_event("click")
            return html
    raise AssertionError(f"context menu action {action} not available")


def submit_modal(page: Page) -> None:
    page.click("#quick_submit_btn")
    expect(page.locator("#quickEventModal")).to_be_hidden()


def check_calendar(page: Page, base: str, snap: dict) -> None:
    today = dt.date.today().isoformat()
    in3 = (dt.date.today() + dt.timedelta(days=2)).isoformat()

    page.goto(base + "/")
    wait_calendar(page)
    snap["calendar_globals"] = globals_snapshot(page)
    snap["toolbar_label"] = page.text_content("#current-month")
    snap["calendar_html_after_boot"] = page.inner_html("#calendar-weeks")
    snap["calendar_rows_after_boot"] = page.locator("#calendar-weeks tr").count()

    # הוספה מכפתור הכלים + חילוץ שעה מהכותרת
    page.click("#addEventFromCalendarBtn")
    expect(page.locator("#quickEventModal")).to_be_visible()
    expect(page.locator("#quick_hebrew_date")).not_to_have_value("")
    snap["modal_title_new"] = page.text_content("#quickEventModalLabel")
    snap["modal_submit_new"] = page.text_content("#quick_submit_btn")
    page.fill("#quick_title", "סמוק 0930")
    page.dispatch_event("#quick_title", "input")
    assert page.input_value("#quick_time") == "09:30", page.input_value("#quick_time")
    assert page.input_value("#quick_title") == "סמוק"
    page.click('.quick-color-swatch[data-color="green"]')
    submit_modal(page)
    item = cell(page, today).locator(".event-item", has_text="סמוק")
    expect(item).to_have_text("09:30 - סמוק")
    expect(page.locator("#success-message")).to_have_text("האירוע נוסף בהצלחה")
    snap["event_item_style"] = item.get_attribute("style")
    print("  add event: OK")

    # עריכה בדאבל-קליק → רב-יומי
    item.dblclick()
    expect(page.locator("#quickEventModal")).to_be_visible()
    expect(page.locator("#quick_title")).to_have_value("סמוק")
    snap["modal_title_edit"] = page.text_content("#quickEventModalLabel")
    snap["modal_submit_edit"] = page.text_content("#quick_submit_btn")
    page.fill("#quick_title", "סמוק ערוך")
    end_input = page.locator("#quick_end_date")
    if not end_input.is_visible():
        page.click("#quick_end_toggle")
    page.fill("#quick_end_date", in3)
    submit_modal(page)
    expect(page.locator("#success-message")).to_have_text("האירוע עודכן בהצלחה")
    expect(cell(page, today).locator(".event-multi", has_text="סמוק ערוך")).to_be_visible()
    expect(cell(page, in3).locator(".event-item")).to_have_count(1)
    snap["multi_day_classes"] = [
        cell(page, (dt.date.today() + dt.timedelta(days=d)).isoformat())
        .locator(".event-item")
        .get_attribute("class")
        for d in range(3)
    ]
    print("  edit event (dblclick, multi-day): OK")

    # מחיקה מתפריט ההקשר
    page.once("dialog", lambda d: d.accept())
    snap["context_menu_event"] = context_action(
        page, cell(page, today).locator(".event-item"), "delete-event"
    )
    expect(page.locator("#success-message")).to_have_text("האירוע נמחק בהצלחה")
    expect(cell(page, today).locator(".event-item")).to_have_count(0)
    print("  delete event (context menu): OK")

    # הוספה מתפריט הקשר על תא ריק
    snap["context_menu_cell"] = context_action(page, cell(page, in3), "add-event")
    expect(page.locator("#quickEventModal")).to_be_visible()
    expect(page.locator("#quick_gregorian_date")).to_have_value(in3)
    page.wait_for_timeout(400)
    page.click('#quickEventModal button:has-text("ביטול")')
    expect(page.locator("#quickEventModal")).to_be_hidden()
    print("  add from context menu opens modal: OK")

    # דלג לתאריך, ואז "היום"
    page.click("#jumpToDateBtn")
    page.select_option("#monthSelect", "2")
    page.select_option("#yearSelect", "2031")
    page.click("text=אישור")
    page.wait_for_timeout(800)
    expect(page.locator("#current-month")).to_contain_text("מרץ 2031")
    snap["toolbar_after_jump"] = page.text_content("#current-month")
    page.click("#goToTodayBtn")
    page.wait_for_timeout(1500)
    box = cell(page, today).bounding_box()
    stream = page.locator("#calendar-stream").bounding_box()
    assert box and stream and stream["y"] <= box["y"] <= stream["y"] + stream["height"], (box, stream)
    snap["toolbar_after_today"] = page.text_content("#current-month")
    print("  jump to date + today button: OK")


def check_events_list(page: Page, base: str, snap: dict) -> None:
    api(base, "POST", "/api/events", {
        "title": "רשימה אלפא", "gregorian_date": "2026-03-04", "hebrew_date": "ט״ו אדר",
    })
    api(base, "POST", "/api/events", {
        "title": "רשימה בטא", "gregorian_date": "2026-03-05", "hebrew_date": "ט״ז אדר",
    })

    created = next(e for e in api(base, "GET", "/api/events") if e["title"] == "רשימה אלפא")
    page.goto(base + "/events_list")
    page.wait_for_selector("#eventsTable tr")
    snap["list_globals"] = globals_snapshot(page)
    snap["list_overrides"] = page.evaluate(
        "['deleteEvent','editEvent','getTodayDateStr','loadAllEvents']"
        ".map((n) => [n, String(window[n]).slice(0, 60)])"
    )

    # הוספה מהמודל המשותף (script.js) → רענון הטבלה (loadAllEvents של הדף)
    page.click("#addEventFromListBtn")
    expect(page.locator("#quickEventModal")).to_be_visible()
    expect(page.locator("#quick_hebrew_date")).not_to_have_value("")
    page.fill("#quick_title", "רשימה גמא")
    submit_modal(page)
    expect(page.locator("#eventsTable")).to_contain_text("רשימה גמא")
    print("  add from list modal: OK")

    page.fill("#searchInput", "אלפא")
    page.dispatch_event("#searchInput", "input")
    expect(page.locator("#eventsTable")).to_contain_text("רשימה אלפא")
    expect(page.locator("#eventsTable")).not_to_contain_text("רשימה בטא")
    print("  search: OK")

    page.fill("#searchInput", "")
    page.dispatch_event("#searchInput", "input")
    expect(page.locator("#eventsTable")).to_contain_text("רשימה בטא")

    page.click("#eventsToolsBtn")
    with page.expect_download() as dl:
        page.click("#exportEventsBtn")
    path = dl.value.path()
    exported = json.loads(open(path, encoding="utf-8").read())
    titles = sorted(e["title"] for e in exported.get("events", exported if isinstance(exported, list) else []))
    assert {"רשימה אלפא", "רשימה בטא", "רשימה גמא"} <= set(titles), titles
    snap["export_filename"] = dl.value.suggested_filename
    print(f"  export: OK ({dl.value.suggested_filename}, {len(titles)} events)")
    page.keyboard.press("Escape")

    # עריכה מהטבלה (editEvent של הדף → openEditEventModal מ-script.js)
    page.locator(f'#eventsTable button[onclick="editEvent({created["id"]})"]').click()
    expect(page.locator("#quickEventModal")).to_be_visible()
    expect(page.locator("#quick_title")).to_have_value("רשימה אלפא")
    page.fill("#quick_title", "רשימה אלפא ערוך")
    submit_modal(page)
    expect(page.locator("#eventsTable")).to_contain_text("רשימה אלפא ערוך")
    print("  edit from list: OK")

    page.once("dialog", lambda d: d.accept())
    page.locator(f'#eventsTable button[onclick="deleteEvent({created["id"]})"]').click()
    expect(page.locator("#eventsTable")).not_to_contain_text("רשימה אלפא")
    print("  delete from list: OK")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:5000")
    parser.add_argument("--snapshot", help="נתיב לכתיבת JSON של מצב ה-UI")
    parser.add_argument("--width", type=int, default=1280)
    parser.add_argument("--height", type=int, default=800)
    parser.add_argument("--color-scheme", choices=["light", "dark"], default=None)
    args = parser.parse_args()
    base = args.base_url.rstrip("/")

    problems: list[str] = []
    snap: dict = {}
    with sync_playwright() as p:
        browser = p.chromium.launch()
        context_kwargs = {
            "viewport": {"width": args.width, "height": args.height},
            "accept_downloads": True,
        }
        if args.color_scheme:
            context_kwargs["color_scheme"] = args.color_scheme
        context = browser.new_context(**context_kwargs)
        page = context.new_page()
        page.set_default_timeout(8000)
        page.on("pageerror", lambda e: problems.append(f"pageerror: {e}"))
        page.on(
            "console",
            lambda m: problems.append(f"console.{m.type}: {m.text}") if m.type == "error" else None,
        )
        page.on("requestfailed", lambda r: problems.append(f"requestfailed: {r.url}"))
        page.on(
            "response",
            lambda r: problems.append(f"HTTP {r.status}: {r.url}") if r.status >= 400 else None,
        )

        print("[calendar]")
        check_calendar(page, base, snap)
        print("[events list]")
        check_events_list(page, base, snap)
        browser.close()

    if args.snapshot:
        with open(args.snapshot, "w", encoding="utf-8") as f:
            json.dump(snap, f, ensure_ascii=False, indent=2, sort_keys=True)

    if problems:
        print("\nCONSOLE/JS PROBLEMS:")
        for line in problems:
            print("  " + line)
        return 1
    print("\nALL SMOKE CHECKS PASSED (no console errors)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
