"""בורר דלג-לתאריך: לועזי/עברי, אדר אחד קבוע, קפיצה לחודש הלועזי הנכון."""
from __future__ import annotations

import json
import logging
import re
import subprocess
import threading
from datetime import date
from pathlib import Path

import pytest
from pyluach.dates import HebrewDate

REPO = Path(__file__).resolve().parent.parent
JUMP_JS = REPO / "app/static/js/calendar/jump-date.js"
INDEX = REPO / "app/templates/index.html"
BASE = REPO / "app/templates/base.html"
SCRIPT_JS = REPO / "app/static/js/script.js"
CALENDAR_CSS = REPO / "app/static/css/components/calendar.css"

TISHREI_FIRST = [
    (7, "תשרי"),
    (8, "חשון"),
    (9, "כסלו"),
    (10, "טבת"),
    (11, "שבט"),
    (12, "אדר"),
    (1, "ניסן"),
    (2, "אייר"),
    (3, "סיון"),
    (4, "תמוז"),
    (5, "אב"),
    (6, "אלול"),
]


def _gregorian(hebrew_date) -> str:
    greg = hebrew_date.to_greg()
    return date(greg.year, greg.month, greg.day).isoformat()


def _option_pairs(html: str, select_id: str) -> list[tuple[str, str]]:
    block = re.search(
        rf'<select[^>]*id="{select_id}"[^>]*>(.*?)</select>',
        html,
        re.S,
    )
    assert block, select_id
    return re.findall(r'<option value="([^"]+)">([^<]+)</option>', block.group(1))


def test_jump_picker_markup_is_tishrei_first_with_single_adar(client):
    html = client.get("/").get_data(as_text=True)
    assert 'id="jumpDateMenu"' in html
    assert "לועזי" in html
    assert "עברי" in html
    assert 'id="jumpCalGregorian"' in html
    assert 'id="jumpCalHebrew"' in html
    assert 'id="hebrewMonthSelect"' in html
    assert 'id="hebrewYearSelect"' in html
    assert 'id="monthSelect"' in html
    assert 'id="yearSelect"' in html
    assert 'data-bs-auto-close="outside"' in html
    assert 'onclick="jumpToDate()"' in html
    assert 'id="jumpConfirmBtn"' in html

    pairs = _option_pairs(html, "hebrewMonthSelect")
    assert [(int(value), name) for value, name in pairs] == TISHREI_FIRST
    names = [name for _, name in pairs]
    assert names[0] == "תשרי"
    assert names.count("אדר") == 1
    assert "אדר א׳" not in names
    assert "אדר ב׳" not in names
    assert len(pairs) == 12

    js = JUMP_JS.read_text(encoding="utf-8")
    assert "const JUMP_HEBREW_MONTHS" in js
    months_block = js.split("const JUMP_HEBREW_MONTHS = [", 1)[1].split("];", 1)[0]
    assert "{ value: 12, name: 'אדר' }" in months_block
    assert "אדר א׳" not in months_block
    assert "אדר ב׳" not in months_block
    assert "function jumpToDate" in js
    assert "function initJumpDatePicker" in js
    assert "calendar/jump-date.js" in BASE.read_text(encoding="utf-8")
    assert "initJumpDatePicker" in SCRIPT_JS.read_text(encoding="utf-8")
    css = CALENDAR_CSS.read_text(encoding="utf-8")
    assert ".jump-cal-toggle" in css
    assert ".jump-date-menu.is-hebrew .jump-gregorian-fields" in css
    assert "function jumpToDate" not in INDEX.read_text(encoding="utf-8")


def test_adar_jump_api_uses_adar_one_in_a_leap_year(client):
    regular = client.get("/api/gregorian-from-hebrew?year=5786&month=12&day=1")
    assert regular.status_code == 200, regular.get_json()
    assert regular.get_json()["gregorian_date"] == _gregorian(HebrewDate(5786, 12, 1))
    assert regular.get_json()["gregorian_date"] == "2026-02-18"

    leap = client.get("/api/gregorian-from-hebrew?year=5787&month=12&day=1")
    assert leap.status_code == 200, leap.get_json()
    body = leap.get_json()
    assert body["gregorian_date"] == _gregorian(HebrewDate(5787, 12, 1))
    assert body["gregorian_date"] == "2027-02-08"
    assert body["month"] == 12
    assert body["leap"] is True
    assert "אדר א׳" in body["hebrew_date"]

    adar_two = client.get("/api/gregorian-from-hebrew?year=5787&month=13&day=1")
    assert adar_two.get_json()["gregorian_date"] == "2027-03-10"


def _eval_jump_picker(script_tail: str) -> object:
    harness = r"""
function classListOf(el) {
    return {
        add: (name) => el._classes.add(name),
        remove: (name) => el._classes.delete(name),
        contains: (name) => el._classes.has(name),
        toggle: (name, on) => {
            if (on === undefined) {
                if (el._classes.has(name)) el._classes.delete(name);
                else el._classes.add(name);
            } else if (on) el._classes.add(name);
            else el._classes.delete(name);
        },
    };
}

function makeEl(id, extra) {
    const el = {
        id,
        tagName: 'DIV',
        value: '',
        hidden: false,
        dataset: {},
        textContent: '',
        innerHTML: '',
        children: [],
        options: [],
        _classes: new Set(),
        _listeners: {},
        _attrs: {},
        style: {},
        addEventListener(type, fn) { (el._listeners[type] ||= []).push(fn); },
        dispatchEvent(type) {
            const event = typeof type === 'string' ? type : type.type;
            (el._listeners[event] || []).forEach((fn) => fn({ type: event, target: el }));
        },
        setAttribute(name, value) { el._attrs[name] = String(value); },
        getAttribute(name) { return el._attrs[name]; },
        replaceChildren() { el.children = []; el.options = []; },
        append(child) {
            el.children.push(child);
            if (child && child.value != null) el.options.push(child);
        },
        appendChild(child) { el.append(child); },
        querySelector() { return null; },
    };
    el.classList = classListOf(el);
    Object.assign(el, extra || {});
    return el;
}

const els = {
    jumpDateMenu: makeEl('jumpDateMenu', { _classes: new Set(['jump-date-menu', 'is-gregorian']) }),
    jumpCalGregorian: makeEl('jumpCalGregorian'),
    jumpCalHebrew: makeEl('jumpCalHebrew'),
    jumpGregorianFields: makeEl('jumpGregorianFields'),
    jumpHebrewFields: makeEl('jumpHebrewFields', { hidden: true }),
    monthSelect: makeEl('monthSelect'),
    yearSelect: makeEl('yearSelect'),
    hebrewMonthSelect: makeEl('hebrewMonthSelect'),
    hebrewYearSelect: makeEl('hebrewYearSelect'),
    jumpToDateBtn: makeEl('jumpToDateBtn'),
    currentMonth: makeEl('current-month'),
    calendarWeeks: makeEl('calendar-weeks'),
};
['ינואר','פברואר','מרץ','אפריל','מאי','יוני','יולי','אוגוסט','ספטמבר','אוקטובר','נובמבר','דצמבר']
    .forEach((name, i) => {
        els.monthSelect.append({ value: String(i), textContent: name });
    });

const document = {
    getElementById: (id) => {
        const map = {
            jumpDateMenu: els.jumpDateMenu,
            jumpCalGregorian: els.jumpCalGregorian,
            jumpCalHebrew: els.jumpCalHebrew,
            jumpGregorianFields: els.jumpGregorianFields,
            jumpHebrewFields: els.jumpHebrewFields,
            monthSelect: els.monthSelect,
            yearSelect: els.yearSelect,
            hebrewMonthSelect: els.hebrewMonthSelect,
            hebrewYearSelect: els.hebrewYearSelect,
            jumpToDateBtn: els.jumpToDateBtn,
            'current-month': els.currentMonth,
            'calendar-weeks': els.calendarWeeks,
        };
        return map[id] || null;
    },
    createElement: (tag) => makeEl('', { tagName: String(tag).toUpperCase() }),
    querySelector: () => null,
};

const window = { bootstrap: { Dropdown: { getInstance: () => ({ hide() { calls.hide += 1; } }) } } };
const bootstrap = window.bootstrap;
const GREGORIAN_MONTH_NAMES_HE = [
    'ינואר', 'פברואר', 'מרץ', 'אפריל', 'מאי', 'יוני',
    'יולי', 'אוגוסט', 'ספטמבר', 'אוקטובר', 'נובמבר', 'דצמבר',
];

const gregorianMap = {
    '5786-12-1': '2026-02-18',
    '5787-12-1': '2027-02-08',
    '5786-7-1': '2025-09-23',
    '5787-7-1': '2026-09-12',
    '5786-1-1': '2026-03-19',
};
const hebrewDateMap = {
    '2026-02-18': { year: 5786, month: 12, year_label: 'תשפ״ו' },
    '2027-02-08': { year: 5787, month: 12, year_label: 'תשפ״ז' },
};
const hebrewYears = [
    { year: 5786, label: 'תשפ״ו', leap: false },
    { year: 5787, label: 'תשפ״ז', leap: true },
];
async function fetch(url) {
    const href = String(url);
    if (href.startsWith('/api/hebrew-years')) {
        return { ok: true, json: async () => ({ years: hebrewYears }) };
    }
    const converted = href.match(/year=(\d+)&month=(\d+)&day=(\d+)/);
    if (converted) {
        const key = `${converted[1]}-${converted[2]}-${Number(converted[3])}`;
        return { ok: true, json: async () => ({ gregorian_date: gregorianMap[key], year: Number(converted[1]), month: Number(converted[2]) }) };
    }
    const heb = href.match(/\/api\/hebrew-date\/(\d{4}-\d{2}-\d{2})/);
    if (heb) {
        return { ok: true, json: async () => hebrewDateMap[heb[1]] || { year: 5786, month: 7 } };
    }
    return { ok: false, json: async () => ({}) };
}

const calls = { jumps: [], hide: 0 };
function jumpToMonth(year, month) { calls.jumps.push({ year, month }); }

function snapshot() {
    const month = els.hebrewMonthSelect;
    return {
        mode: jumpCalendarMode,
        monthValue: month.value,
        yearValue: els.hebrewYearSelect.value,
        names: [...month.options].map((option) => option.textContent),
        values: [...month.options].map((option) => option.value),
        hebrewHidden: els.jumpHebrewFields.hidden,
        gregorianHidden: els.jumpGregorianFields.hidden,
        menuHebrew: els.jumpDateMenu.classList.contains('is-hebrew'),
        jumps: calls.jumps.slice(),
        hide: calls.hide,
        yearLabels: [...els.hebrewYearSelect.options].map((option) => option.textContent),
    };
}

"""
    source = JUMP_JS.read_text(encoding="utf-8")
    script = harness + "\n" + source + "\n" + script_tail
    result = subprocess.run(
        ["node", "-e", script],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise AssertionError(result.stdout + "\n" + result.stderr)
    if result.stderr:
        raise AssertionError(result.stderr)
    return json.loads(result.stdout)


def test_hebrew_month_list_stays_fixed_in_both_selection_orders():
    out = _eval_jump_picker(
        """
async function run() {
    await initJumpDatePicker();
    const results = {};

    setJumpCalendarMode('hebrew');
    els.hebrewMonthSelect.value = '12';
    onJumpHebrewYearChange();
    els.hebrewYearSelect.value = '5786';
    onJumpHebrewYearChange();
    results.monthThenRegular = snapshot();
    els.hebrewYearSelect.value = '5787';
    onJumpHebrewYearChange();
    results.monthThenLeap = snapshot();
    await jumpToDate();
    results.monthThenLeapJump = snapshot();

    calls.jumps = [];
    setJumpCalendarMode('hebrew');
    els.hebrewMonthSelect.value = '12';
    els.hebrewYearSelect.value = '5787';
    onJumpHebrewYearChange();
    els.hebrewYearSelect.value = '5786';
    onJumpHebrewYearChange();
    results.monthThenBackToRegular = snapshot();
    await jumpToDate();
    results.monthThenRegularJump = snapshot();

    calls.jumps = [];
    setJumpCalendarMode('hebrew');
    els.hebrewYearSelect.value = '5786';
    onJumpHebrewYearChange();
    els.hebrewMonthSelect.value = '12';
    results.yearThenMonthRegular = snapshot();
    await jumpToDate();
    results.yearThenMonthRegularJump = snapshot();

    calls.jumps = [];
    setJumpCalendarMode('hebrew');
    els.hebrewYearSelect.value = '5787';
    onJumpHebrewYearChange();
    els.hebrewMonthSelect.value = '12';
    results.yearThenMonthLeap = snapshot();
    await jumpToDate();
    results.yearThenMonthLeapJump = snapshot();

    process.stdout.write(JSON.stringify(results));
}
run();
"""
    )

    def assert_fixed_adar(snap):
        assert snap["monthValue"] == "12"
        assert snap["names"] == [name for _, name in TISHREI_FIRST]
        assert snap["names"].count("אדר") == 1
        assert "אדר א׳" not in snap["names"]
        assert "אדר ב׳" not in snap["names"]
        assert snap["values"] == [str(value) for value, _ in TISHREI_FIRST]
        assert snap["mode"] == "hebrew"
        assert snap["hebrewHidden"] is False
        assert snap["gregorianHidden"] is True
        assert snap["menuHebrew"] is True

    assert_fixed_adar(out["monthThenRegular"])
    assert out["monthThenRegular"]["yearValue"] == "5786"
    assert_fixed_adar(out["monthThenLeap"])
    assert out["monthThenLeap"]["yearValue"] == "5787"
    assert out["monthThenLeapJump"]["jumps"] == [{"year": 2027, "month": 2}]

    assert_fixed_adar(out["monthThenBackToRegular"])
    assert out["monthThenBackToRegular"]["yearValue"] == "5786"
    assert out["monthThenRegularJump"]["jumps"] == [{"year": 2026, "month": 2}]

    assert_fixed_adar(out["yearThenMonthRegular"])
    assert out["yearThenMonthRegularJump"]["jumps"] == [{"year": 2026, "month": 2}]
    assert_fixed_adar(out["yearThenMonthLeap"])
    assert out["yearThenMonthLeapJump"]["jumps"] == [{"year": 2027, "month": 2}]


def test_hebrew_confirm_jumps_tishrei_and_maps_adar_ii_name_to_single_adar():
    out = _eval_jump_picker(
        """
async function run() {
    await initJumpDatePicker();
    setJumpCalendarMode('hebrew');
    els.hebrewYearSelect.value = '5787';
    onJumpHebrewYearChange();
    els.hebrewMonthSelect.value = '7';
    await jumpToDate();
    const tishrei = snapshot();

    const fromAdarII = jumpHebrewMonthFromName('אדר ב׳');
    const fromAdarI = jumpHebrewMonthFromName('אדר א׳');
    const fromPlain = jumpHebrewMonthFromName('אדר');
    const fromApi = jumpHebrewMonthFromApi(13);

    process.stdout.write(JSON.stringify({
        tishreiJumps: tishrei.jumps,
        names: tishrei.names,
        fromAdarII, fromAdarI, fromPlain, fromApi,
        yearLabels: tishrei.yearLabels,
    }));
}
run();
"""
    )
    assert out["tishreiJumps"] == [{"year": 2026, "month": 9}]
    assert out["names"][0] == "תשרי"
    assert out["fromAdarII"] == 12
    assert out["fromAdarI"] == 12
    assert out["fromPlain"] == 12
    assert out["fromApi"] == 12
    assert out["yearLabels"] == ["תשפ״ו", "תשפ״ז"]


def test_gregorian_confirm_still_uses_zero_based_month_select():
    out = _eval_jump_picker(
        """
async function run() {
    await initJumpDatePicker();
    setJumpCalendarMode('gregorian');
    els.monthSelect.value = '2';
    els.yearSelect.value = '2031';
    await jumpToDate();
    process.stdout.write(JSON.stringify(snapshot()));
}
run();
"""
    )
    assert out["mode"] == "gregorian"
    assert out["jumps"] == [{"year": 2031, "month": 3}]
    assert out["hide"] == 1
    assert out["hebrewHidden"] is True
    assert out["gregorianHidden"] is False


@pytest.fixture(autouse=True)
def _quiet_app_logs():
    log = logging.getLogger("app")
    previous = log.level
    log.setLevel(logging.WARNING)
    yield
    log.setLevel(previous)


@pytest.fixture(scope="module")
def live_server(app):
    pytest.importorskip("playwright.sync_api")
    from werkzeug.serving import make_server

    server = make_server("127.0.0.1", 0, app, threaded=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()


def _hebrew_month_names(page):
    return page.evaluate(
        """() => [...document.getElementById('hebrewMonthSelect').options].map((option) => option.textContent)"""
    )


def _assert_fixed_adar_list(page, year, month="12"):
    from playwright.sync_api import expect

    expect(page.locator("#hebrewYearSelect")).to_have_value(year)
    expect(page.locator("#hebrewMonthSelect")).to_have_value(month)
    names = _hebrew_month_names(page)
    assert names == [name for _, name in TISHREI_FIRST]
    assert names.count("אדר") == 1
    assert "אדר א׳" not in names
    assert "אדר ב׳" not in names


def _open_hebrew_jump(page):
    from playwright.sync_api import expect

    page.click("#jumpToDateBtn")
    expect(page.locator("#jumpDateMenu")).to_be_visible()
    if page.locator("#hebrewMonthSelect").is_hidden():
        page.click("#jumpCalHebrew")
    expect(page.locator("#hebrewMonthSelect")).to_be_visible()
    page.wait_for_function(
        """() => {
            const year = document.getElementById('hebrewYearSelect');
            return year && [...year.options].some((option) => option.value === '5786');
        }"""
    )
    page.evaluate("async () => { if (typeof whenJumpPickerSynced === 'function') await whenJumpPickerSynced(); }")


def _confirm_jump(page, month_text):
    from playwright.sync_api import expect

    page.click("#jumpConfirmBtn")
    expect(page.locator("#current-month")).to_contain_text(month_text, timeout=15000)


def test_browser_hebrew_jump_orders_and_adar_confirm(live_server):
    pytest.importorskip("playwright.sync_api")
    from playwright.sync_api import expect, sync_playwright

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(viewport={"width": 1280, "height": 800}, locale="he-IL")
        errors = []
        page.on("pageerror", lambda err: errors.append(str(err)))
        page.goto(live_server + "/", wait_until="domcontentloaded")
        page.wait_for_selector(".infinite-calendar:not(.is-booting)")
        expect(page.locator("#jumpToDateBtn")).to_be_visible()

        _open_hebrew_jump(page)
        page.select_option("#hebrewMonthSelect", "12")
        page.select_option("#hebrewYearSelect", "5786")
        _assert_fixed_adar_list(page, "5786")
        page.select_option("#hebrewYearSelect", "5787")
        _assert_fixed_adar_list(page, "5787")
        _confirm_jump(page, "פברואר 2027")

        _open_hebrew_jump(page)
        page.select_option("#hebrewMonthSelect", "12")
        page.select_option("#hebrewYearSelect", "5787")
        _assert_fixed_adar_list(page, "5787")
        page.select_option("#hebrewYearSelect", "5786")
        _assert_fixed_adar_list(page, "5786")
        _confirm_jump(page, "פברואר 2026")

        _open_hebrew_jump(page)
        page.select_option("#hebrewYearSelect", "5786")
        page.select_option("#hebrewMonthSelect", "12")
        _assert_fixed_adar_list(page, "5786")
        _confirm_jump(page, "פברואר 2026")

        _open_hebrew_jump(page)
        page.select_option("#hebrewYearSelect", "5787")
        page.select_option("#hebrewMonthSelect", "12")
        _assert_fixed_adar_list(page, "5787")
        _confirm_jump(page, "פברואר 2027")

        assert errors == [], errors
        browser.close()
