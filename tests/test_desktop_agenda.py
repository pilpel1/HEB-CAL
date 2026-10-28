"""פאנל יום בדסקטופ, צפיפות במסך רחב, ורמזים בהגדרות — בלי דפדפן."""
from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
AGENDA_JS = REPO / "app/static/js/calendar/day-agenda.js"
WEEK_JS = REPO / "app/static/js/calendar/week-rows.js"
MODAL_JS = REPO / "app/static/js/events/quick-event-modal.js"
CALENDAR_CSS = REPO / "app/static/css/components/calendar.css"
FORMS_CSS = REPO / "app/static/css/components/forms.css"


def test_desktop_agenda_is_side_column_only_from_992(client):
    css = CALENDAR_CSS.read_text(encoding="utf-8")
    html = client.get("/").get_data(as_text=True)
    agenda = AGENDA_JS.read_text(encoding="utf-8")
    weeks = WEEK_JS.read_text(encoding="utf-8")
    modal = MODAL_JS.read_text(encoding="utf-8")

    side = css.split("@media (min-width: 992px)", 1)[1].split("@media", 1)[0]
    assert "clamp(280px, 25%, 380px)" in side
    assert "grid-column: 2" in side
    assert "grid-column: 1 / -1" in side
    assert ".day-agenda" in side
    assert "display: flex" in side
    # עמודה 2 ב-RTL היא הצד השמאלי. אין hover לבחירה.
    assert ":hover" not in side
    assert "day-agenda-add-icon" in side
    assert "day-agenda-add-label" in side

    phone = css.split("@media (max-width: 480px)", 1)[1].split("@media", 1)[0]
    assert "grid-template-rows: auto minmax(0, 1fr) auto minmax(0, 0.25fr)" in phone
    assert "clamp(280px, 25%, 380px)" not in phone
    assert "data-cal-density" not in phone
    assert "touch-action: pan-x pan-y pinch-zoom" in css

    assert "function isDesktopAgenda" in agenda
    assert "min-width: 992px" in agenda
    assert "function showsDayAgenda" in agenda
    assert "if (!showsDayAgenda()" in agenda
    assert "removeAttribute('data-cal-density')" not in agenda
    assert "root.dataset.calDensity" in agenda
    assert "showsDayAgenda()" in weeks
    assert "isDesktopAgenda()" in modal
    # בטלפון עדיין חוזרים לפני עריכת צ'יפ; בדסקטופ הבחירה לא בולעת את הלחיצה על אירוע
    click = modal.split("calendarRoot.addEventListener('click'", 1)[1].split(
        "calendarRoot.addEventListener('dblclick'", 1
    )[0]
    select_at = click.index("selectAgendaDay")
    compact_return = click.index("if (cell && compact)")
    event_edit = click.index("openEditEventModal")
    assert select_at < compact_return < event_edit

    assert 'id="day-agenda"' in html
    assert "day-agenda-add-icon" in html
    assert "day-agenda-add-label" in html
    assert 'aria-label="הוסף אירוע"' in html


def test_compact_density_css_applies_above_phone():
    css = CALENDAR_CSS.read_text(encoding="utf-8")
    block = css.split("@media (min-width: 481px) {", 1)[-1]
    # הבלוק השני (אחרי כפתורי הסרגל) הוא הצפיפות
    density = block.split("@media (min-width: 481px) {", 1)[-1].split("@media", 1)[0]
    assert 'html[data-cal-density="compact"] .day-cell' in density
    assert "min-height: 84px" in density
    assert 'html[data-cal-density="compact"] .event-item' in density
    assert "font-size: 0.72rem" in density
    phone = css.split("@media (max-width: 480px)", 1)[1].split("@media (min-width: 481px)", 1)[0]
    assert "data-cal-density" not in phone


def test_settings_hints_are_inline_and_events_list_drops_reminders_link(client):
    settings = client.get("/settings").get_data(as_text=True)
    display = settings.split('id="settings-display-title"', 1)[1].split('id="settingsColors"', 1)[0]
    assert display.count("settings-switch-hint") == 2
    assert display.count("נשמר במכשיר הזה") == 2
    assert "בטלפון יותר שבועות, במסך רחב תאים וצ'יפים קטנים יותר." in display
    assert "בטלפון, תצוגה צפופה מציגה יותר שבועות" not in settings
    assert '<p class="text-muted small mb-0">' not in display
    # הרמז יושב בתוך הלייבל, לא בשורה נפרדת מתחת למתג
    theme_label = display.split('for="themeSwitch"', 1)[1].split("</label>", 1)[0]
    density_label = display.split('for="densitySwitch"', 1)[1].split("</label>", 1)[0]
    assert "נשמר במכשיר הזה" in theme_label
    assert "בטלפון יותר שבועות" in density_label
    forms = FORMS_CSS.read_text(encoding="utf-8")
    assert ".settings-switch-hint" in forms
    assert "flex-wrap" in forms or "min-width: 0" in forms

    events_list = client.get("/events_list").get_data(as_text=True)
    assert '>תזכורות</a>' not in events_list
    assert 'href="/settings" class="btn btn-outline-secondary btn-sm"' not in events_list
    assert 'aria-label="הגדרות תזכורות"' in events_list
    assert 'href="/settings#settings-reminders"' in events_list
    assert '<h2 class="h5">תזכורות</h2>' in settings

    head = client.get("/").get_data(as_text=True).split("</head>", 1)[0]
    assert "heb-cal-density" in head
    assert "data-cal-density" in head


def test_desktop_agenda_collapse_is_stored_and_stays_collapsed_on_select(client):
    css = CALENDAR_CSS.read_text(encoding="utf-8")
    html = client.get("/").get_data(as_text=True)
    agenda = AGENDA_JS.read_text(encoding="utf-8")
    dark = (REPO / "app/static/css/components/dark-theme.css").read_text(encoding="utf-8")

    side = css.split("@media (min-width: 992px)", 1)[1].split("@media", 1)[0]
    assert ".day-agenda-toggle" in side
    assert "is-agenda-collapsed" in side
    assert "--agenda-panel: 0px" in side
    assert "rotate(-90deg)" in side
    assert "rotate(90deg)" in side
    assert "height: 60px" in side
    assert "width: 18px" in side
    assert "top: 50%" in side
    assert "translateY(-50%)" in side
    assert "scrollbar-width: none" in side
    assert "-ms-overflow-style: none" in side
    assert ".day-agenda-list::-webkit-scrollbar" in side
    first_list = css.split(".day-agenda-list {", 1)[1].split("}", 1)[0]
    assert "overflow-y: auto" in first_list
    assert ".day-agenda-toggle:hover" in css
    assert ".day-agenda-toggle:hover" in dark
    assert "day-agenda-heb" in side
    assert "day-agenda-greg" in side
    assert ":hover" not in side

    phone = css.split("@media (max-width: 480px)", 1)[1].split("@media", 1)[0]
    assert "day-agenda-toggle" not in phone
    assert "is-agenda-collapsed" not in phone
    assert "scrollbar-width" not in phone

    assert 'id="day-agenda-toggle"' in html
    assert 'aria-controls="day-agenda"' in html
    assert 'aria-label="הסתר אירועי היום"' in html
    assert "heb-cal-agenda-collapsed" in html
    assert "day-agenda-heb" in html
    assert "day-agenda-greg" in html

    assert "function setAgendaCollapsed" in agenda
    assert "function applyAgendaCollapsed" in agenda
    assert "heb-cal-agenda-collapsed" in agenda
    assert "animateAgendaPanel" in agenda
    select = agenda.split("function selectAgendaDay", 1)[1].split("function initDayAgenda", 1)[0]
    assert "setAgendaCollapsed" not in select
    assert "is-agenda-collapsed" not in select
    assert "heb-cal-agenda-collapsed" not in select

    assert ".day-agenda-toggle" in dark
    assert ".day-agenda-greg" in dark
    assert "is-agenda-collapsed .day-agenda-toggle" in dark
