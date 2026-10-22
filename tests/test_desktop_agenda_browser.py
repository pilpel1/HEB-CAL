"""פאנל יום בדסקטופ, צפיפות, ושהטלפון לא זז. צריך Chromium."""
from __future__ import annotations

import datetime as dt

import pytest

pytest.importorskip("playwright.sync_api")
from playwright.sync_api import sync_playwright  # noqa: E402
from werkzeug.serving import make_server  # noqa: E402
import threading


@pytest.fixture(scope="module")
def live_server(app):
    server = make_server("127.0.0.1", 0, app)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()


def _seed(client, day: dt.date) -> None:
    samples = [
        ("פגישת רופא", "09:00", "בדיקת דם שנתית", "cyan"),
        ("איסוף מהגן", "13:30", "לא לאחר", "orange"),
        ("ערב משפחה", "19:00", "אצל סבתא", "green"),
        ("קניות", "11:00", "", "yellow"),
        ("שיחת עבודה", "16:15", "סטטוס שבועי", None),
        ("אימון", "07:00", "ריצה קצרה", "green"),
    ]
    for title, time, description, color in samples:
        payload = {
            "title": title,
            "gregorian_date": day.isoformat(),
            "hebrew_date": "היום",
            "time": time,
            "description": description,
        }
        if color:
            payload["color"] = color
        created = client.post("/api/events", json=payload)
        assert created.status_code == 200
    nxt = day + dt.timedelta(days=1)
    created = client.post("/api/events", json={
        "title": "יום הולדת",
        "gregorian_date": nxt.isoformat(),
        "hebrew_date": "מחר",
        "description": "עוגה",
        "color": "yellow",
    })
    assert created.status_code == 200


def _hide_quick_modal(page):
    page.evaluate("""() => new Promise((resolve) => {
        const el = document.getElementById('quickEventModal');
        const inst = bootstrap.Modal.getOrCreateInstance(el);
        el.addEventListener('hidden.bs.modal', () => resolve(true), { once: true });
        const hide = () => inst.hide();
        if (inst._isTransitioning) {
            el.addEventListener('shown.bs.modal', hide, { once: true });
        } else {
            hide();
        }
    })""")


def _launch(p, **context):
    browser = p.chromium.launch(headless=True)
    ctx = browser.new_context(**context)
    page = ctx.new_page()
    return browser, page


def test_desktop_side_agenda_selects_day_and_edits(live_server, client):
    today = dt.date.today()
    _seed(client, today)
    tomorrow = (today + dt.timedelta(days=1)).isoformat()

    with sync_playwright() as p:
        browser, page = _launch(
            p,
            viewport={"width": 1400, "height": 900},
            locale="he-IL",
        )
        try:
            page.goto(live_server + "/", wait_until="domcontentloaded")
            page.wait_for_selector(".infinite-calendar:not(.is-booting)", timeout=20000)
            page.wait_for_selector(".agenda-event", timeout=10000)

            box = page.evaluate("""() => {
                const cal = document.querySelector('.infinite-calendar').getBoundingClientRect();
                const stream = document.querySelector('.calendar-stream').getBoundingClientRect();
                const agenda = document.querySelector('.day-agenda').getBoundingClientRect();
                const title = document.getElementById('day-agenda-title').textContent;
                const addIcon = getComputedStyle(document.querySelector('.day-agenda-add-icon')).display;
                const addLabel = getComputedStyle(document.querySelector('.day-agenda-add-label')).display;
                const today = document.querySelector('td.current-day');
                return {
                    agendaLeftOfStream: agenda.right <= stream.left + 2,
                    agendaW: agenda.width,
                    ratio: agenda.width / cal.width,
                    title,
                    addIcon,
                    addLabel,
                    todaySelected: today.classList.contains('is-agenda-day'),
                    desc: !!document.querySelector('.agenda-desc'),
                    time: !!document.querySelector('.agenda-time'),
                    swatch: !!document.querySelector('.agenda-swatch:not(.is-empty)'),
                    handleDisplay: getComputedStyle(document.getElementById('agenda-resize')).display,
                };
            }""")
            assert box["agendaLeftOfStream"] is True
            assert 270 <= box["agendaW"] <= 390
            assert 0.2 <= box["ratio"] <= 0.4
            assert "·" in box["title"]
            assert str(today.year) in box["title"]
            # האייקון הוא flex item בתוך הכפתור, אז computed display הוא block
            assert box["addIcon"] != "none"
            assert box["addLabel"] == "none"
            assert box["todaySelected"] is True
            assert box["desc"] is True
            assert box["time"] is True
            assert box["swatch"] is True
            assert box["handleDisplay"] == "none"

            page.click(f'td[data-date="{tomorrow}"] .gregorian-date')
            page.wait_for_function(
                """(day) => {
                    const cell = document.querySelector(`td[data-date="${day}"]`);
                    const title = document.getElementById('day-agenda-title').textContent;
                    return cell.classList.contains('is-agenda-day')
                        && title.length > 0
                        && !document.querySelector('td.current-day').classList.contains('is-agenda-day');
                }""",
                arg=tomorrow,
            )
            assert "יום הולדת" in page.inner_text("#day-agenda-list")

            # מעבר עכבר לא מחליף את היום הנבחר
            page.hover("td.current-day")
            still = page.eval_on_selector(
                f'td[data-date="{tomorrow}"]',
                "el => el.classList.contains('is-agenda-day')",
            )
            assert still is True

            page.click("#day-agenda-add")
            page.wait_for_selector("#quickEventModal.show", timeout=5000)
            assert page.input_value("#quick_gregorian_date") == tomorrow
            _hide_quick_modal(page)

            page.click('.agenda-event:has-text("יום הולדת")')
            page.wait_for_selector("#quickEventModal.show", timeout=5000)
            assert page.input_value("#quick_title") == "יום הולדת"
        finally:
            browser.close()


def test_desktop_density_fits_more_chips_and_keeps_theme(live_server, client):
    today = dt.date.today()
    _seed(client, today)

    def measure(page):
        page.goto(live_server + "/", wait_until="domcontentloaded")
        page.wait_for_selector(".infinite-calendar:not(.is-booting)", timeout=20000)
        page.wait_for_selector("td.current-day .event-item", timeout=10000)
        return page.evaluate("""() => {
            const cell = document.querySelector('td.current-day');
            const chip = cell.querySelector('.event-item');
            const cellH = cell.getBoundingClientRect().height;
            const chipH = chip.getBoundingClientRect().height;
            const count = cell.querySelectorAll('.event-item').length;
            return {
                density: document.documentElement.dataset.calDensity,
                theme: document.documentElement.dataset.bsTheme,
                minHeight: getComputedStyle(cell.querySelector('.day-cell')).minHeight,
                fontSize: parseFloat(getComputedStyle(chip).fontSize),
                cellH,
                chipH,
                count,
                per100: count / cellH * 100,
                agendaVisible: getComputedStyle(document.querySelector('.day-agenda')).display !== 'none',
            };
        }""")

    with sync_playwright() as p:
        browser, page = _launch(p, viewport={"width": 1400, "height": 900}, locale="he-IL")
        try:
            page.add_init_script("localStorage.setItem('heb-cal-density', 'comfortable');")
            comfortable = measure(page)
            page.add_init_script("localStorage.setItem('heb-cal-density', 'compact');")
            # add_init_script stacks; the later setItem wins on the next document
            compact = measure(page)
            assert comfortable["density"] == "comfortable"
            assert compact["density"] == "compact"
            assert comfortable["minHeight"] == "120px"
            assert compact["minHeight"] == "84px"
            assert compact["fontSize"] < comfortable["fontSize"] - 0.5
            assert compact["chipH"] < comfortable["chipH"] - 1
            assert compact["count"] == comfortable["count"] == 6
            assert compact["per100"] > comfortable["per100"]
            assert compact["cellH"] < comfortable["cellH"]
            assert comfortable["agendaVisible"] and compact["agendaVisible"]

            page.evaluate("localStorage.setItem('heb-cal-theme', 'dark')")
            page.reload(wait_until="domcontentloaded")
            page.wait_for_selector(".infinite-calendar:not(.is-booting)", timeout=20000)
            dark = page.evaluate("""() => {
                const agenda = getComputedStyle(document.querySelector('.day-agenda'));
                const bg = agenda.backgroundColor;
                return {
                    theme: document.documentElement.dataset.bsTheme,
                    density: document.documentElement.dataset.calDensity,
                    bg,
                    display: agenda.display,
                };
            }""")
            assert dark["theme"] == "dark"
            assert dark["density"] == "compact"
            assert dark["display"] == "flex"
            assert dark["bg"] not in {"rgb(255, 255, 255)", "rgb(248, 250, 252)"}
        finally:
            browser.close()


def test_phone_agenda_stays_under_the_grid(live_server, client):
    today = dt.date.today()
    _seed(client, today)
    with sync_playwright() as p:
        browser, page = _launch(
            p,
            viewport={"width": 390, "height": 844},
            has_touch=True,
            is_mobile=True,
            device_scale_factor=2,
        )
        try:
            page.goto(live_server + "/", wait_until="domcontentloaded")
            page.wait_for_selector(".infinite-calendar:not(.is-booting)", timeout=20000)
            page.wait_for_selector(".agenda-event", timeout=10000)
            info = page.evaluate("""() => {
                const stream = document.querySelector('.calendar-stream').getBoundingClientRect();
                const agenda = document.querySelector('.day-agenda').getBoundingClientRect();
                const td = document.querySelector('td[data-date]');
                return {
                    agendaBelow: agenda.top >= stream.bottom - 40,
                    overlapX: agenda.left < stream.right && agenda.right > stream.left,
                    sideBySide: agenda.right <= stream.left + 2,
                    handle: getComputedStyle(document.getElementById('agenda-resize')).display,
                    touch: getComputedStyle(td).touchAction,
                    addLabel: getComputedStyle(document.querySelector('.day-agenda-add-label')).display,
                    addIcon: getComputedStyle(document.querySelector('.day-agenda-add-icon')).display,
                    labelText: document.querySelector('.day-agenda-add-label').textContent,
                };
            }""")
            assert info["agendaBelow"] is True
            assert info["overlapX"] is True
            assert info["sideBySide"] is False
            assert info["handle"] == "flex"
            assert info["touch"] in {"manipulation", "pan-x pan-y pinch-zoom"}
            assert info["addLabel"] != "none"
            assert info["addIcon"] == "none"
            assert info["labelText"] == "הוסף"

            page.evaluate("""() => {
                document.querySelector('td.current-day .event-item')
                    .dispatchEvent(new MouseEvent('click', { bubbles: true }));
            }""")
            page.wait_for_timeout(400)
            assert page.locator("#quickEventModal.show").count() == 0
            assert page.eval_on_selector(
                "td.current-day",
                "el => el.classList.contains('is-agenda-day')",
            )
        finally:
            browser.close()


def test_settings_hints_share_the_toggle_row(live_server):
    with sync_playwright() as p:
        browser, page = _launch(p, viewport={"width": 390, "height": 844}, locale="he-IL")
        try:
            page.goto(live_server + "/settings", wait_until="domcontentloaded")
            info = page.evaluate("""() => {
                function row(id) {
                    const label = document.querySelector(`label[for="${id}"]`);
                    const hint = label.querySelector('.settings-switch-hint');
                    const input = document.getElementById(id);
                    const lr = label.getBoundingClientRect();
                    const hr = hint.getBoundingClientRect();
                    const ir = input.getBoundingClientRect();
                    return {
                        hintInLabel: label.contains(hint),
                        switchOverlapsLabel: ir.top < lr.bottom && ir.bottom > lr.top,
                        hintStartsInRow: hr.top < lr.top + lr.height,
                        noSeparateParagraph: !label.closest('.card-body').querySelector('p.text-muted.small.mb-0'),
                    };
                }
                return { theme: row('themeSwitch'), density: row('densitySwitch') };
            }""")
            assert info["theme"]["hintInLabel"]
            assert info["density"]["hintInLabel"]
            assert info["theme"]["switchOverlapsLabel"]
            assert info["density"]["switchOverlapsLabel"]
            assert info["theme"]["noSeparateParagraph"]
            assert "נשמר במכשיר הזה" in page.inner_text("label[for=themeSwitch]")
            assert "בטלפון יותר שבועות" in page.inner_text("label[for=densitySwitch]")
        finally:
            browser.close()
