"""רענון «היום» אחרי הקפאת טאב: resume/pageshow, פול 60 שניות, רענון רך עם שעון מדומה."""
from __future__ import annotations

import json
import logging
import subprocess
import threading
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
TODAY_JS = REPO / "app/static/js/calendar/today-refresh.js"
DATES_JS = REPO / "app/static/js/core/dates.js"
SCRIPT_JS = REPO / "app/static/js/script.js"
BASE = REPO / "app/templates/base.html"


def test_today_refresh_listens_to_resume_pageshow_and_polls():
    js = TODAY_JS.read_text(encoding="utf-8")
    assert "document.addEventListener('resume'" in js
    assert "window.addEventListener('pageshow'" in js
    assert "window.addEventListener('focus'" in js
    assert "visibilitychange" in js
    assert "TODAY_POLL_MS = 60000" in js
    assert "setInterval" in js
    assert "function softRefreshForNewToday" in js
    assert "function todayModalBlocksRefresh" in js
    assert "isQuickEventModalOpen" in js
    assert "scrollToDate" in js
    assert "selectAgendaDay" in js
    assert "updateVisibleMonthLabel" in js
    assert "refreshEventsViews" in js
    assert "location.reload" not in js
    assert "location.replace" not in js
    html = BASE.read_text(encoding="utf-8")
    assert "calendar/today-refresh.js" in html
    script = SCRIPT_JS.read_text(encoding="utf-8")
    assert "initTodayRefresh" in script


def _eval_today_refresh(script_tail: str) -> object:
    harness = r"""
const listeners = { document: {}, window: {} };
const cells = new Map();
function classListOf(el) {
    const set = el._classes;
    return {
        add: (name) => set.add(name),
        remove: (name) => set.delete(name),
        contains: (name) => set.has(name),
        toggle: (name, on) => { if (on) set.add(name); else set.delete(name); },
    };
}
function makeCell(date, classes) {
    const el = { dataset: { date }, _classes: new Set(classes || []) };
    el.classList = classListOf(el);
    cells.set(date, el);
    return el;
}
makeCell('2026-11-01', ['past-day']);
makeCell('2026-11-02', ['current-day']);
makeCell('2026-11-03', []);

function matchCells(selector) {
    const all = [...cells.values()];
    if (selector === '#calendar-weeks td.current-day') {
        return all.filter((el) => el.classList.contains('current-day'));
    }
    if (selector === '#calendar-weeks td[data-date]') {
        return all;
    }
    const m = selector.match(/td\[data-date="([^"]+)"\]/);
    if (m) {
        return all.filter((el) => el.dataset.date === m[1]);
    }
    return [];
}

const document = {
    hidden: false,
    addEventListener: (type, fn) => {
        (listeners.document[type] ||= []).push(fn);
    },
    querySelectorAll: (sel) => matchCells(sel),
    querySelector: (sel) => matchCells(sel)[0] || null,
};
const window = {
    addEventListener: (type, fn) => {
        (listeners.window[type] ||= []).push(fn);
    },
};

let fakeToday = '2026-11-02';
function getTodayDateStr() {
    return fakeToday;
}

const timeouts = [];
const intervals = [];
function setTimeout(fn, ms) {
    timeouts.push({ fn, ms });
    return timeouts.length;
}
function clearTimeout() {}
function setInterval(fn, ms) {
    intervals.push({ fn, ms });
    return intervals.length;
}
function clearInterval() {}

let modalOpen = false;
function isQuickEventModalOpen() { return modalOpen; }
function isInfiniteCalendarPage() { return true; }
const infiniteCalendar = { agendaDate: '2026-11-02' };
const calls = { scroll: [], agenda: [], label: 0, events: 0 };
async function scrollToDate(date, align) {
    calls.scroll.push({ date, align });
}
function selectAgendaDay(date) { calls.agenda.push(date); }
function renderDayAgenda(date) { calls.agenda.push('render:' + date); }
function updateVisibleMonthLabel() { calls.label += 1; }
async function refreshEventsViews() { calls.events += 1; }

function snapshot() {
    return {
        today: fakeToday,
        current: [...cells.values()].filter((el) => el.classList.contains('current-day')).map((el) => el.dataset.date),
        past: [...cells.values()].filter((el) => el.classList.contains('past-day')).map((el) => el.dataset.date),
        agendaDate: infiniteCalendar.agendaDate,
        calls,
        intervalMs: intervals.map((item) => item.ms),
        hasResume: Boolean(listeners.document.resume && listeners.document.resume.length),
        hasPageshow: Boolean(listeners.window.pageshow && listeners.window.pageshow.length),
        hasFocus: Boolean(listeners.window.focus && listeners.window.focus.length),
        hasVisibility: Boolean(listeners.document.visibilitychange && listeners.document.visibilitychange.length),
    };
}

function flush() {
    return new Promise((resolve) => setImmediate(() => setImmediate(resolve)));
}

"""
    source = TODAY_JS.read_text(encoding="utf-8")
    script = harness + "\n" + source + "\n" + script_tail
    result = subprocess.run(
        ["node", "-e", script],
        check=True,
        capture_output=True,
        text=True,
    )
    if result.stderr:
        raise AssertionError(result.stderr)
    return json.loads(result.stdout)


def test_mocked_clock_resume_navigates_to_new_today():
    out = _eval_today_refresh(
        """
initTodayRefresh();
const before = snapshot();
fakeToday = '2026-11-03';
listeners.document.resume.forEach((fn) => fn({ type: 'resume' }));
flush().then(() => {
    const after = snapshot();
    process.stdout.write(JSON.stringify({ before, after }));
});
"""
    )
    assert out["before"]["current"] == ["2026-11-02"]
    assert out["before"]["hasResume"] is True
    assert out["before"]["hasPageshow"] is True
    assert out["before"]["hasFocus"] is True
    assert out["before"]["hasVisibility"] is True
    assert out["before"]["intervalMs"] == [60000]
    assert out["after"]["current"] == ["2026-11-03"]
    assert "2026-11-02" in out["after"]["past"]
    assert "2026-11-03" not in out["after"]["past"]
    assert out["after"]["calls"]["scroll"] == [{"date": "2026-11-03", "align": "center"}]
    assert out["after"]["agendaDate"] == "2026-11-03"
    assert "2026-11-03" in out["after"]["calls"]["agenda"]
    assert out["after"]["calls"]["label"] >= 1
    assert out["after"]["calls"]["events"] >= 1


def test_mocked_clock_pageshow_and_interval_also_roll_today():
    out = _eval_today_refresh(
        """
initTodayRefresh();
fakeToday = '2026-11-03';
listeners.window.pageshow.forEach((fn) => fn({ type: 'pageshow' }));
flush().then(() => {
    const afterPageshow = JSON.parse(JSON.stringify({
        current: snapshot().current,
        scroll: snapshot().calls.scroll,
    }));
    fakeToday = '2026-11-01';
    todayLastDate = '2026-11-03';
    cells.get('2026-11-03').classList.add('current-day');
    cells.get('2026-11-03').classList.remove('past-day');
    cells.get('2026-11-01').classList.remove('current-day');
    intervals[0].fn();
    return flush().then(() => {
        const afterInterval = snapshot();
        process.stdout.write(JSON.stringify({ afterPageshow, afterInterval }));
    });
});
"""
    )
    assert out["afterPageshow"]["current"] == ["2026-11-03"]
    assert out["afterPageshow"]["scroll"][0]["date"] == "2026-11-03"
    assert out["afterInterval"]["current"] == ["2026-11-01"]
    assert out["afterInterval"]["calls"]["scroll"][-1]["date"] == "2026-11-01"


def test_mocked_clock_skips_navigation_when_modal_is_open():
    out = _eval_today_refresh(
        """
initTodayRefresh();
modalOpen = true;
const title = { value: 'טיוטה' };
fakeToday = '2026-11-03';
listeners.document.resume.forEach((fn) => fn({ type: 'resume' }));
flush().then(() => {
    const after = snapshot();
    process.stdout.write(JSON.stringify({ after, title: title.value, modalOpen }));
});
"""
    )
    assert out["modalOpen"] is True
    assert out["title"] == "טיוטה"
    assert out["after"]["current"] == ["2026-11-03"]
    assert out["after"]["calls"]["scroll"] == []
    assert out["after"]["calls"]["agenda"] == []
    assert out["after"]["calls"]["events"] == 0
    assert out["after"]["agendaDate"] == "2026-11-02"


def test_get_today_date_str_is_jerusalem_midnight():
    script = (
        DATES_JS.read_text(encoding="utf-8")
        + """
const cases = [
    '2026-11-01T21:59:00.000Z',
    '2026-11-01T22:00:00.000Z',
];
const out = cases.map((iso) => getTodayDateStr(new Date(iso)));
process.stdout.write(JSON.stringify(out));
"""
    )
    result = subprocess.run(["node", "-e", script], check=True, capture_output=True, text=True)
    before, after = json.loads(result.stdout)
    assert before == "2026-11-01"
    assert after == "2026-11-02"


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


def test_browser_resume_moves_today_but_skips_open_modal(live_server):
    pytest.importorskip("playwright.sync_api")
    from playwright.sync_api import expect, sync_playwright

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(viewport={"width": 1280, "height": 800}, locale="he-IL")
        page.set_default_timeout(15000)
        page.goto(live_server + "/", wait_until="domcontentloaded")
        page.wait_for_selector(".infinite-calendar:not(.is-booting)", timeout=20000)
        page.wait_for_selector("td.current-day", timeout=10000)

        rolled = page.evaluate(
            """() => {
                const oldToday = getTodayDateStr();
                const [y, m, d] = oldToday.split('-').map(Number);
                const next = new Date(y, m - 1, d + 1);
                const nextStr = [
                    next.getFullYear(),
                    String(next.getMonth() + 1).padStart(2, '0'),
                    String(next.getDate()).padStart(2, '0'),
                ].join('-');
                window.getTodayDateStr = () => nextStr;
                document.dispatchEvent(new Event('resume'));
                window.dispatchEvent(new Event('pageshow'));
                return { oldToday, nextStr };
            }"""
        )
        page.wait_for_function(
            """(nextStr) => {
                const current = document.querySelector('td.current-day');
                return current && current.dataset.date === nextStr;
            }""",
            arg=rolled["nextStr"],
        )
        old_classes = page.locator(f'td[data-date="{rolled["oldToday"]}"]').first.get_attribute("class") or ""
        assert "current-day" not in old_classes.split()

        page.evaluate("async (day) => { await openQuickEventModal(day); }", rolled["nextStr"])
        expect(page.locator("#quickEventModal")).to_be_visible()
        page.fill("#quick_title", "טיוטה פתוחה")
        page.wait_for_function("() => document.getElementById('quick_title').value === 'טיוטה פתוחה'")

        further = page.evaluate(
            """() => {
                const current = getTodayDateStr();
                const [y, m, d] = current.split('-').map(Number);
                const next = new Date(y, m - 1, d + 1);
                const nextStr = [
                    next.getFullYear(),
                    String(next.getMonth() + 1).padStart(2, '0'),
                    String(next.getDate()).padStart(2, '0'),
                ].join('-');
                const prevDate = document.getElementById('quick_gregorian_date').value;
                window.getTodayDateStr = () => nextStr;
                document.dispatchEvent(new Event('resume'));
                return {
                    nextStr,
                    prevDate,
                    title: document.getElementById('quick_title').value,
                    modalOpen: document.getElementById('quickEventModal').classList.contains('show'),
                };
            }"""
        )
        page.wait_for_timeout(200)
        expect(page.locator("#quickEventModal")).to_be_visible()
        expect(page.locator("#quick_title")).to_have_value("טיוטה פתוחה")
        expect(page.locator("#quick_gregorian_date")).to_have_value(further["prevDate"])
        assert further["modalOpen"] is True
        assert page.evaluate("() => document.getElementById('quick_title').value") == "טיוטה פתוחה"
        browser.close()
