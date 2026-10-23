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
                    toggle: getComputedStyle(document.getElementById('day-agenda-toggle')).display,
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
            assert info["toggle"] == "none"
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


def _matrix_sin(transform):
    inner = transform.removeprefix("matrix(").removesuffix(")")
    return float(inner.split(",")[1])


def test_desktop_agenda_collapse_remembers_and_select_stays_closed(live_server, client):
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

            open_state = page.evaluate("""() => {
                const stream = document.querySelector('.calendar-stream').getBoundingClientRect();
                const agenda = document.querySelector('.day-agenda').getBoundingClientRect();
                const toggle = document.querySelector('.day-agenda-toggle').getBoundingClientRect();
                const heb = document.querySelector('.day-agenda-heb').getBoundingClientRect();
                const greg = document.querySelector('.day-agenda-greg').getBoundingClientRect();
                const head = getComputedStyle(document.querySelector('.day-agenda-head'));
                const panel = getComputedStyle(document.querySelector('.day-agenda'));
                const card = getComputedStyle(document.querySelector('.infinite-calendar'));
                const frame = document.querySelector('.calendar-stream-frame').getBoundingClientRect();
                const svg = getComputedStyle(document.querySelector('#day-agenda-toggle svg'));
                const seam = stream.left;
                const mid = frame.top + frame.height / 2;
                return {
                    expanded: document.getElementById('day-agenda-toggle').getAttribute('aria-expanded'),
                    label: document.getElementById('day-agenda-toggle').getAttribute('aria-label'),
                    agendaW: agenda.width,
                    toggleH: toggle.height,
                    toggleW: toggle.width,
                    chevron: parseFloat(svg.width),
                    centered: Math.abs((toggle.top + toggle.height / 2) - mid) < 2,
                    straddles: toggle.left < seam - 1 && toggle.right > seam + 1,
                    stacked: heb.top + 4 < greg.top,
                    headBorder: parseFloat(head.borderBottomWidth) >= 1,
                    separated: panel.backgroundColor !== card.backgroundColor,
                    border: parseFloat(panel.borderInlineStartWidth) >= 1,
                    arrow: svg.transform,
                    storage: localStorage.getItem('heb-cal-agenda-collapsed'),
                };
            }""")
            assert open_state["expanded"] == "true"
            assert open_state["label"] == "הסתר אירועי היום"
            assert 270 <= open_state["agendaW"] <= 390
            assert 56 <= open_state["toggleH"] <= 64
            assert 16 <= open_state["toggleW"] <= 18
            assert open_state["chevron"] >= 16
            assert open_state["centered"] is True
            assert open_state["straddles"] is True
            assert open_state["stacked"] is True
            assert open_state["headBorder"] is True
            assert open_state["separated"] is True
            assert open_state["border"] is True
            assert open_state["storage"] in (None, "0")
            assert _matrix_sin(open_state["arrow"]) < -0.9

            samples = page.evaluate("""() => new Promise((resolve) => {
                const widths = [];
                document.getElementById('day-agenda-toggle').click();
                const start = performance.now();
                const tick = () => {
                    widths.push(document.getElementById('day-agenda').getBoundingClientRect().width);
                    if (performance.now() - start < 280) requestAnimationFrame(tick);
                    else resolve(widths);
                };
                requestAnimationFrame(tick);
            })""")
            assert max(samples) > 120
            assert min(samples) < 2
            assert any(24 < width < max(samples) - 24 for width in samples)

            closed = page.evaluate("""() => {
                const cal = document.querySelector('.infinite-calendar');
                const card = cal.getBoundingClientRect();
                const style = getComputedStyle(cal);
                const pad = (parseFloat(style.paddingLeft) || 0) + (parseFloat(style.paddingRight) || 0);
                const stream = document.querySelector('.calendar-stream').getBoundingClientRect();
                const frame = document.querySelector('.calendar-stream-frame').getBoundingClientRect();
                const toggle = document.querySelector('.day-agenda-toggle').getBoundingClientRect();
                const svg = getComputedStyle(document.querySelector('#day-agenda-toggle svg'));
                const mid = frame.top + frame.height / 2;
                return {
                    collapsed: cal.classList.contains('is-agenda-collapsed'),
                    expanded: document.getElementById('day-agenda-toggle').getAttribute('aria-expanded'),
                    label: document.getElementById('day-agenda-toggle').getAttribute('aria-label'),
                    hidden: document.getElementById('day-agenda').getAttribute('aria-hidden'),
                    inert: document.getElementById('day-agenda').hasAttribute('inert'),
                    agendaW: document.getElementById('day-agenda').getBoundingClientRect().width,
                    streamRatio: stream.width / (card.width - pad),
                    toggleH: toggle.height,
                    toggleW: toggle.width,
                    toggleAtEdge: Math.abs(toggle.left - frame.left) < 2,
                    centered: Math.abs((toggle.top + toggle.height / 2) - mid) < 2,
                    arrow: svg.transform,
                    storage: localStorage.getItem('heb-cal-agenda-collapsed'),
                };
            }""")
            assert closed["collapsed"] is True
            assert closed["expanded"] == "false"
            assert closed["label"] == "הצג אירועי היום"
            assert closed["hidden"] == "true"
            assert closed["inert"] is True
            assert closed["agendaW"] < 2
            assert closed["streamRatio"] > 0.97
            assert 56 <= closed["toggleH"] <= 64
            assert 16 <= closed["toggleW"] <= 18
            assert closed["toggleAtEdge"] is True
            assert closed["centered"] is True
            assert closed["storage"] == "1"
            assert _matrix_sin(closed["arrow"]) > 0.9

            page.click(f'td[data-date="{tomorrow}"] .gregorian-date')
            page.wait_for_function(
                """(day) => {
                    const cell = document.querySelector(`td[data-date="${day}"]`);
                    return cell && cell.classList.contains('is-agenda-day');
                }""",
                arg=tomorrow,
            )
            still = page.evaluate(
                """(day) => {
                    const greg = document.getElementById('day-agenda-greg').textContent;
                    const dayNum = String(Number(day.slice(8)));
                    return {
                        collapsed: document.querySelector('.infinite-calendar').classList.contains('is-agenda-collapsed'),
                        width: document.getElementById('day-agenda').getBoundingClientRect().width,
                        storage: localStorage.getItem('heb-cal-agenda-collapsed'),
                        gregStarts: greg.startsWith(dayNum + ' '),
                    };
                }""",
                tomorrow,
            )
            assert still["collapsed"] is True
            assert still["width"] < 2
            assert still["storage"] == "1"
            assert still["gregStarts"] is True

            page.click("#day-agenda-toggle")
            page.wait_for_function(
                """() => {
                    const cal = document.querySelector('.infinite-calendar');
                    const width = document.getElementById('day-agenda').getBoundingClientRect().width;
                    return !cal.classList.contains('is-agenda-collapsed')
                        && width > 270
                        && !cal.style.getPropertyValue('--agenda-panel');
                }"""
            )
            assert page.evaluate("localStorage.getItem('heb-cal-agenda-collapsed')") == "0"
            assert "יום הולדת" in page.inner_text("#day-agenda-list")

            page.evaluate("localStorage.setItem('heb-cal-agenda-collapsed', '1')")
            page.goto(live_server + "/", wait_until="domcontentloaded")
            early = page.evaluate("""() => ({
                collapsed: document.querySelector('.infinite-calendar').classList.contains('is-agenda-collapsed'),
                width: document.getElementById('day-agenda').getBoundingClientRect().width,
                label: document.getElementById('day-agenda-toggle').getAttribute('aria-label'),
            })""")
            assert early["collapsed"] is True
            assert early["width"] < 2
            assert early["label"] == "הצג אירועי היום"
            page.wait_for_selector(".infinite-calendar:not(.is-booting)", timeout=20000)
            late = page.evaluate(
                "document.getElementById('day-agenda').getBoundingClientRect().width"
            )
            assert late < 2

            page.evaluate("""() => {
                localStorage.setItem('heb-cal-theme', 'dark');
                localStorage.setItem('heb-cal-density', 'compact');
                localStorage.setItem('heb-cal-agenda-collapsed', '0');
            }""")
            page.reload(wait_until="domcontentloaded")
            page.wait_for_selector(".infinite-calendar:not(.is-booting)", timeout=20000)
            dark_open = page.evaluate("""() => {
                const panel = getComputedStyle(document.querySelector('.day-agenda'));
                const card = getComputedStyle(document.querySelector('.infinite-calendar'));
                const toggle = getComputedStyle(document.querySelector('.day-agenda-toggle'));
                return {
                    theme: document.documentElement.dataset.bsTheme,
                    density: document.documentElement.dataset.calDensity,
                    display: toggle.display,
                    separated: panel.backgroundColor !== card.backgroundColor,
                    toggleBg: toggle.backgroundColor,
                    width: document.getElementById('day-agenda').getBoundingClientRect().width,
                    heb: parseFloat(getComputedStyle(document.querySelector('.day-agenda-heb')).fontSize),
                };
            }""")
            assert dark_open["theme"] == "dark"
            assert dark_open["density"] == "compact"
            assert dark_open["display"] in {"flex", "inline-flex"}
            assert dark_open["separated"] is True
            assert dark_open["toggleBg"] not in {"rgba(0, 0, 0, 0)", "transparent"}
            assert dark_open["width"] > 270
            assert dark_open["heb"] < 16

            page.click("#day-agenda-toggle")
            page.wait_for_function(
                "() => document.getElementById('day-agenda').getBoundingClientRect().width < 2"
            )
            assert page.evaluate(
                "getComputedStyle(document.querySelector('.day-agenda-toggle')).display"
            ) in {"flex", "inline-flex"}
        finally:
            browser.close()


def test_agenda_collapse_preference_does_not_change_layout_below_992(live_server, client):
    today = dt.date.today()
    _seed(client, today)

    def measure(page):
        page.goto(live_server + "/", wait_until="domcontentloaded")
        page.wait_for_selector(".infinite-calendar:not(.is-booting)", timeout=20000)
        return page.evaluate("""() => {
            const stream = document.querySelector('.calendar-stream').getBoundingClientRect();
            const agenda = document.querySelector('.day-agenda').getBoundingClientRect();
            const cal = document.querySelector('.infinite-calendar');
            return {
                toggle: getComputedStyle(document.getElementById('day-agenda-toggle')).display,
                agendaDisplay: getComputedStyle(document.querySelector('.day-agenda')).display,
                collapsed: cal.classList.contains('is-agenda-collapsed'),
                inert: document.getElementById('day-agenda').hasAttribute('inert'),
                sideBySide: agenda.right <= stream.left + 2 && agenda.width > 40,
                agendaBelow: agenda.top >= stream.bottom - 40 && agenda.height > 40,
            };
        }""")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            phone = browser.new_context(
                viewport={"width": 390, "height": 844},
                has_touch=True,
                is_mobile=True,
                device_scale_factor=2,
            )
            phone.add_init_script("localStorage.setItem('heb-cal-agenda-collapsed', '1');")
            phone_page = phone.new_page()
            phone_info = measure(phone_page)
            assert phone_info["toggle"] == "none"
            assert phone_info["collapsed"] is False
            assert phone_info["inert"] is False
            assert phone_info["agendaBelow"] is True
            assert phone_info["sideBySide"] is False
            phone.close()

            tablet = browser.new_context(viewport={"width": 800, "height": 700}, locale="he-IL")
            tablet.add_init_script("localStorage.setItem('heb-cal-agenda-collapsed', '1');")
            tablet_page = tablet.new_page()
            tablet_info = measure(tablet_page)
            assert tablet_info["toggle"] == "none"
            assert tablet_info["agendaDisplay"] == "none"
            assert tablet_info["collapsed"] is False
            assert tablet_info["sideBySide"] is False
            tablet.close()
        finally:
            browser.close()
