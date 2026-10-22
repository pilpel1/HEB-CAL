// פאנל יום מתחת ללוח בטלפון: הטקסט המלא שלא נכנס לתא

function isCompactCalendar() {
    return window.matchMedia('(max-width: 480px)').matches;
}

/** זום דפדפן (פינץ'), לא זום של האפליקציה. מעל 1 — גרירה אחת מפנה את העמוד. */
function isPageZoomed() {
    const vv = window.visualViewport;
    if (!vv || !Number.isFinite(vv.scale)) {
        return false;
    }
    return vv.scale > 1.01;
}

function syncPageZoomState() {
    document.documentElement.classList.toggle('is-page-zoomed', isPageZoomed());
}

function densityDivisor() {
    try {
        return localStorage.getItem('heb-cal-density') === 'compact' ? 9 : 6;
    } catch (error) {
        return 6;
    }
}

function updateDensityToggle() {
    const compact = densityDivisor() === 9;
    document.querySelectorAll('[data-density-switch]').forEach((input) => {
        input.checked = compact;
    });
}

function clampAgendaShare(value) {
    return Math.min(1, Math.max(0, value));
}

function isCollapsedShare(share) {
    return share <= 0.001 || share >= 0.999;
}

function readStoredShare() {
    try {
        const raw = localStorage.getItem('heb-cal-agenda-split');
        const value = Number(raw);
        if (raw === null || !Number.isFinite(value)) {
            return 0.2;
        }
        return clampAgendaShare(value);
    } catch (error) {
        return 0.2;
    }
}

function readStoredPrev() {
    try {
        const value = Number(localStorage.getItem('heb-cal-agenda-split-prev'));
        if (!Number.isFinite(value) || isCollapsedShare(value)) {
            return 0.2;
        }
        return clampAgendaShare(value);
    } catch (error) {
        return 0.2;
    }
}

function writeAgendaShare(share) {
    try {
        localStorage.setItem('heb-cal-agenda-split', String(share));
    } catch (error) {
        /* מצב פרטי */
    }
}

function writeAgendaPrev(share) {
    if (isCollapsedShare(share)) {
        return;
    }
    try {
        localStorage.setItem('heb-cal-agenda-split-prev', String(share));
    } catch (error) {
        /* מצב פרטי */
    }
}

/** פיקסלים לפאנל. בלי גרירה חיה הפאנל הפתוח לא יורד מ-100px. */
function agendaPixels(track, share, live) {
    const clamped = clampAgendaShare(share);
    let agendaPx = Math.round(track.available * clamped);
    if (!live && clamped > 0.001 && clamped < 0.999) {
        agendaPx = Math.min(track.available, Math.max(100, agendaPx));
    }
    return Math.max(0, Math.min(track.available, agendaPx));
}

function snapAgendaShare(share) {
    const points = [0, 0.2, 0.5, 1];
    let best = points[0];
    let dist = Infinity;
    for (const point of points) {
        const delta = Math.abs(point - share);
        if (delta < dist) {
            dist = delta;
            best = point;
        }
    }
    return best;
}

function activeAgendaShare() {
    const cal = document.querySelector('.calendar-container.infinite-calendar');
    const raw = cal && cal.dataset.agendaShare;
    const value = Number(raw);
    if (raw !== undefined && raw !== '' && Number.isFinite(value)) {
        return clampAgendaShare(value);
    }
    return readStoredShare();
}

function splitTrack() {
    const cal = document.querySelector('.calendar-container.infinite-calendar');
    const toolbar = cal && cal.querySelector('.calendar-toolbar');
    const handle = document.getElementById('agenda-resize');
    if (!cal || !toolbar || !handle) {
        return null;
    }
    const style = getComputedStyle(cal);
    const padTop = parseFloat(style.paddingTop) || 0;
    const padBottom = parseFloat(style.paddingBottom) || 0;
    const inner = cal.clientHeight - padTop - padBottom;
    const handleH = handle.offsetHeight || 28;
    const available = Math.max(0, inner - toolbar.offsetHeight - handleH);
    const contentTop = cal.getBoundingClientRect().top + padTop + toolbar.offsetHeight;
    return { available, handleH, contentTop };
}

function shareFromClientY(clientY) {
    const track = splitTrack();
    if (!track || track.available <= 0) {
        return 0.2;
    }
    const handleTop = clientY - track.handleH / 2;
    const agenda = track.contentTop + track.handleH + track.available - (handleTop + track.handleH);
    return clampAgendaShare(agenda / track.available);
}

function updateAgendaResizeUi(share) {
    const handle = document.getElementById('agenda-resize');
    const restore = document.getElementById('agenda-resize-restore');
    const agenda = document.getElementById('day-agenda');
    const stream = document.querySelector('.calendar-stream-frame');
    if (!handle) {
        return;
    }
    const collapsedAgenda = share <= 0.001;
    const collapsedGrid = share >= 0.999;
    const percent = Math.round(share * 100);
    handle.classList.toggle('is-collapsed', collapsedAgenda || collapsedGrid);
    handle.classList.toggle('is-collapsed-agenda', collapsedAgenda);
    handle.classList.toggle('is-collapsed-grid', collapsedGrid);
    handle.setAttribute('aria-valuenow', String(percent));
    handle.setAttribute('aria-valuetext', collapsedAgenda
        ? 'הפאנל סגור'
        : collapsedGrid
            ? 'הלוח סגור'
            : `${percent} אחוז לפאנל`);
    if (restore) {
        const label = collapsedAgenda ? 'הצג את פאנל האירועים' : 'הצג את לוח החודש';
        restore.setAttribute('aria-label', label);
        restore.setAttribute('aria-hidden', collapsedAgenda || collapsedGrid ? 'false' : 'true');
        restore.tabIndex = collapsedAgenda || collapsedGrid ? 0 : -1;
    }
    if (agenda) {
        agenda.toggleAttribute('inert', collapsedAgenda);
        agenda.setAttribute('aria-hidden', collapsedAgenda ? 'true' : 'false');
    }
    if (stream) {
        stream.toggleAttribute('inert', collapsedGrid);
    }
}

/** share הוא החלק של הפאנל מתוך השטח שמתחת לסרגל (0 סגור, 1 הלוח סגור). */
function applyAgendaSplit(share, options) {
    const cal = document.querySelector('.calendar-container.infinite-calendar');
    if (!cal) {
        return;
    }
    const next = clampAgendaShare(share);
    cal.dataset.agendaShare = String(next);
    updateAgendaResizeUi(next);
    const handle = document.getElementById('agenda-resize');
    const live = (options && options.live) || (handle && handle.dataset.agendaDragging === '1');
    if (!isCompactCalendar()) {
        if (cal.style.gridTemplateRows) {
            cal.style.removeProperty('grid-template-rows');
        }
        return;
    }
    const track = splitTrack();
    if (!track) {
        return;
    }
    const agendaPx = agendaPixels(track, next, live);
    const streamPx = Math.max(0, track.available - agendaPx);
    const rows = `auto ${streamPx}px auto ${agendaPx}px`;
    if (cal.style.gridTemplateRows !== rows) {
        cal.style.gridTemplateRows = rows;
        // חלון הרשת השתנה — למלא שבועות מעבר לקצה, בלי לגעת בגובה התא
        if (typeof scheduleMaintain === 'function') {
            scheduleMaintain();
        }
    }
}

function restoreAgendaSplit() {
    const prev = snapAgendaShare(readStoredPrev());
    applyAgendaSplit(prev);
    writeAgendaShare(prev);
    document.getElementById('agenda-resize')?.focus();
}

function bindAgendaResize() {
    const handle = document.getElementById('agenda-resize');
    if (!handle || handle.dataset.bound === '1') {
        return;
    }
    handle.dataset.bound = '1';
    let drag = null;

    handle.addEventListener('pointerdown', (event) => {
        if (event.button !== undefined && event.button !== 0) {
            return;
        }
        if (isPageZoomed()) {
            return;
        }
        handle.setPointerCapture(event.pointerId);
        handle.dataset.agendaDragging = '1';
        drag = {
            id: event.pointerId,
            y: event.clientY,
            start: activeAgendaShare(),
            moved: false,
        };
    });

    handle.addEventListener('pointermove', (event) => {
        if (!drag || event.pointerId !== drag.id) {
            return;
        }
        if (Math.abs(event.clientY - drag.y) < 6) {
            return;
        }
        drag.moved = true;
        // הידית משנה רק את גובה חלון הרשת. גובה התא נשאר לפי הצפיפות.
        applyAgendaSplit(shareFromClientY(event.clientY), { live: true });
    });

    const finishDrag = (event) => {
        if (!drag || event.pointerId !== drag.id) {
            return;
        }
        const info = drag;
        drag = null;
        delete handle.dataset.agendaDragging;
        if (!info.moved) {
            // אחרי setPointerCapture היעד הוא הידית, לא הכפתור. הקשה בלי תזוזה על מצב סגור משחזרת
            if (isCollapsedShare(info.start)) {
                restoreAgendaSplit();
            }
            return;
        }
        handle.dataset.suppressClick = '1';
        const snapped = snapAgendaShare(shareFromClientY(event.clientY));
        if (isCollapsedShare(snapped) && !isCollapsedShare(info.start)) {
            writeAgendaPrev(snapAgendaShare(info.start));
        }
        if (!isCollapsedShare(snapped)) {
            writeAgendaPrev(snapped);
        }
        applyAgendaSplit(snapped);
        writeAgendaShare(snapped);
    };
    handle.addEventListener('pointerup', finishDrag);
    handle.addEventListener('pointercancel', finishDrag);

    handle.addEventListener('keydown', (event) => {
        const order = [0, 0.2, 0.5, 1];
        const current = snapAgendaShare(activeAgendaShare());
        let index = order.indexOf(current);
        if (index < 0) {
            index = 1;
        }
        let nextIndex = index;
        if (event.key === 'ArrowUp') {
            nextIndex = Math.min(order.length - 1, index + 1);
        } else if (event.key === 'ArrowDown') {
            nextIndex = Math.max(0, index - 1);
        } else if (event.key === 'Home') {
            nextIndex = 0;
        } else if (event.key === 'End') {
            nextIndex = order.length - 1;
        } else {
            return;
        }
        event.preventDefault();
        const next = order[nextIndex];
        if (next === current) {
            return;
        }
        if (isCollapsedShare(next)) {
            writeAgendaPrev(current);
        } else {
            writeAgendaPrev(next);
        }
        applyAgendaSplit(next);
        writeAgendaShare(next);
    });

    document.getElementById('agenda-resize-restore')?.addEventListener('click', (event) => {
        if (handle.dataset.suppressClick === '1') {
            delete handle.dataset.suppressClick;
            event.preventDefault();
            return;
        }
        event.preventDefault();
        restoreAgendaSplit();
    });
}

/** הכרטיס ממלא בדיוק את הגובה הנראה (כולל סרגל הכתובת באנדרואיד). */
function syncCalendarFrame() {
    const cal = document.querySelector('.calendar-container.infinite-calendar');
    if (!cal) {
        return;
    }
    syncPageZoomState();
    // בזום לא מצמצמים לגובה ה-visualViewport — זה מבטל את הפאן של הדפדפן
    if (isPageZoomed()) {
        return;
    }
    if (!isCompactCalendar()) {
        cal.style.removeProperty('height');
        applyAgendaSplit(activeAgendaShare());
        return;
    }
    const vv = window.visualViewport;
    const viewportH = Math.round(vv ? vv.height : window.innerHeight);
    const top = cal.getBoundingClientRect().top - (vv ? vv.offsetTop : 0);
    const available = Math.max(320, viewportH - Math.max(0, Math.round(top)) - 2);
    const next = `${available}px`;
    if (cal.style.height !== next) {
        cal.style.height = next;
    }
    applyAgendaSplit(activeAgendaShare());
}

/**
 * גובה הסרגל כששורת הפעולות סגורה: כותרת החודש ופס החץ בלבד.
 * זה הסרגל הנמוך, ולכן יוצא ממנו גובה התא הגדול יותר.
 */
function collapsedToolbarHeight(toolbar) {
    if (toolbar.classList.contains('is-collapsed')) {
        return toolbar.offsetHeight;
    }
    const month = toolbar.querySelector('.toolbar-month-label');
    const collapse = document.getElementById('header-collapse');
    const style = getComputedStyle(toolbar);
    const pad = (parseFloat(style.paddingTop) || 0) + (parseFloat(style.paddingBottom) || 0);
    const gap = parseFloat(style.rowGap || style.gap) || 0;
    const monthH = month ? month.offsetHeight : 0;
    const collapseShown = collapse && getComputedStyle(collapse).display !== 'none';
    const collapseH = collapseShown ? (collapse.offsetHeight || 28) : 0;
    const between = monthH > 0 && collapseH > 0 ? gap : 0;
    return monthH + collapseH + pad + between;
}

/**
 * גובה אזור השורות כאילו החלוקה היא 80/20 והסרגל העליון סגור.
 * לא תלוי בידית ולא בפתיחת שורת הפעולות: שתיהן רק חושפות או מסתירות שורות.
 */
function referenceWeekRowsArea() {
    const stream = infiniteCalendar.stream;
    const header = stream && stream.querySelector('.weekday-header');
    const headerH = header ? header.offsetHeight : 0;
    const cal = document.querySelector('.calendar-container.infinite-calendar');
    const toolbar = cal && cal.querySelector('.calendar-toolbar');
    const handle = document.getElementById('agenda-resize');
    if (cal && toolbar && handle) {
        const style = getComputedStyle(cal);
        const padTop = parseFloat(style.paddingTop) || 0;
        const padBottom = parseFloat(style.paddingBottom) || 0;
        const inner = cal.clientHeight - padTop - padBottom;
        const handleH = handle.offsetHeight || 28;
        const chrome = Math.min(toolbar.offsetHeight, collapsedToolbarHeight(toolbar));
        const available = Math.max(0, inner - chrome - handleH);
        const streamPx = available - agendaPixels({ available, handleH }, 0.2, false);
        return streamPx - headerH;
    }
    if (!stream) {
        return 0;
    }
    return stream.clientHeight - headerH;
}

/** בטלפון גובה שורה = רשת 80/20 של הסרגל הסגור / 6 (או / 9 במצב צפוף). */
function syncWeekRowHeight() {
    const root = document.documentElement;
    const stream = infiniteCalendar.stream;
    if (!isCompactCalendar() || !stream) {
        if (root.style.getPropertyValue('--week-row-height')) {
            root.style.removeProperty('--week-row-height');
        }
        root.removeAttribute('data-cal-density');
        if (typeof fitRenderedWeekChips === 'function') {
            fitRenderedWeekChips();
        }
        return;
    }
    const grid = referenceWeekRowsArea();
    if (grid < 80) {
        return;
    }
    const divisor = densityDivisor();
    root.dataset.calDensity = divisor === 9 ? 'compact' : 'comfortable';
    const next = `${Math.max(28, Math.floor(grid / divisor))}px`;
    const width = stream.clientWidth;
    if (root.style.getPropertyValue('--week-row-height') === next) {
        // הרוחב משנה שבירת שורה בלי לשנות את גובה הצפיפות
        if (infiniteCalendar.chipFitWidth !== width
            && infiniteCalendar.ready
            && infiniteCalendar.body
            && infiniteCalendar.body.rows.length
            && typeof fitRenderedWeekChips === 'function') {
            preserveScrollAnchor(() => fitRenderedWeekChips());
        }
        return;
    }
    const apply = () => {
        root.style.setProperty('--week-row-height', next);
        if (typeof fitRenderedWeekChips === 'function') {
            fitRenderedWeekChips();
        }
    };
    if (infiniteCalendar.ready && infiniteCalendar.body && infiniteCalendar.body.rows.length) {
        preserveScrollAnchor(apply);
    } else {
        apply();
    }
}

function setCalendarDensity(mode) {
    const next = mode === 'compact' ? 'compact' : 'comfortable';
    const already = (densityDivisor() === 9) === (next === 'compact');
    if (!already) {
        try {
            localStorage.setItem('heb-cal-density', next);
        } catch (error) {
            /* מצב פרטי — נשאר עד רענון */
        }
    }
    updateDensityToggle();
    if (already) {
        return;
    }
    syncCalendarFrame();
    syncWeekRowHeight();
    if (typeof updateVisibleMonthLabel === 'function') {
        updateVisibleMonthLabel();
    }
}

function toggleCalendarDensity() {
    setCalendarDensity(densityDivisor() === 9 ? 'comfortable' : 'compact');
}

function readHeaderCollapsed() {
    try {
        return localStorage.getItem('heb-cal-header-collapsed') === '1';
    } catch (error) {
        return false;
    }
}

function applyHeaderCollapsed(collapsed) {
    const toolbar = document.getElementById('calendar-toolbar');
    if (!toolbar) {
        return;
    }
    const hide = Boolean(collapsed) && isCompactCalendar();
    toolbar.classList.toggle('is-collapsed', Boolean(collapsed));
    const toggle = document.getElementById('header-collapse');
    if (toggle) {
        toggle.setAttribute('aria-expanded', hide ? 'false' : 'true');
        toggle.setAttribute('aria-label', hide ? 'הצג את סרגל הפעולות' : 'כווץ את סרגל הפעולות');
    }
    const actions = document.getElementById('toolbar-actions');
    if (actions) {
        actions.toggleAttribute('inert', hide);
    }
    if (hide) {
        const jump = document.getElementById('jumpToDateBtn');
        if (jump && window.bootstrap && bootstrap.Dropdown) {
            const menu = bootstrap.Dropdown.getInstance(jump);
            if (menu) {
                menu.hide();
            }
        }
    }
}

function setHeaderCollapsed(collapsed) {
    try {
        localStorage.setItem('heb-cal-header-collapsed', collapsed ? '1' : '0');
    } catch (error) {
        /* מצב פרטי — נשאר עד רענון */
    }
    applyHeaderCollapsed(collapsed);
    syncCalendarFrame();
    syncWeekRowHeight();
}

function initCalendarChrome() {
    const toolbar = document.getElementById('calendar-toolbar');
    if (!toolbar || toolbar.dataset.chromeBound === '1') {
        return;
    }
    toolbar.dataset.chromeBound = '1';
    applyHeaderCollapsed(readHeaderCollapsed());
    updateDensityToggle();

    document.getElementById('header-collapse')?.addEventListener('click', () => {
        setHeaderCollapsed(!readHeaderCollapsed());
    });
}

function initDensitySwitch() {
    const input = document.querySelector('[data-density-switch]');
    if (!input || input.dataset.bound === '1') {
        return;
    }
    input.dataset.bound = '1';
    updateDensityToggle();
    input.addEventListener('change', () => {
        setCalendarDensity(input.checked ? 'compact' : 'comfortable');
    });
}

document.addEventListener('DOMContentLoaded', () => {
    initCalendarChrome();
    initDensitySwitch();
});

function syncAgendaSelection() {
    document.querySelectorAll('#calendar-weeks td.is-agenda-day').forEach((td) => {
        td.classList.remove('is-agenda-day');
    });
    if (!isCompactCalendar() || !infiniteCalendar.agendaDate) {
        return;
    }
    const cell = document.querySelector(
        `#calendar-weeks td[data-date="${infiniteCalendar.agendaDate}"]`
    );
    if (cell) {
        cell.classList.add('is-agenda-day');
    }
}

function ensureAgendaDayVisible(dateStr) {
    const cell = document.querySelector(`#calendar-weeks td[data-date="${dateStr}"]`);
    const stream = infiniteCalendar.stream;
    if (!cell || !stream) {
        return;
    }
    const row = cell.parentElement;
    const top = contentTopY();
    const bottom = stream.getBoundingClientRect().bottom;
    const rect = row.getBoundingClientRect();
    if (rect.height < 1) {
        return;
    }
    const visible = Math.min(rect.bottom, bottom) - Math.max(rect.top, top);
    const need = Math.min(rect.height, bottom - top);
    if (visible >= need * 0.6) {
        return;
    }
    const delta = rect.top < top ? rect.top - top : rect.bottom - bottom;
    if (Math.abs(delta) > stream.clientHeight) {
        return;
    }
    stream.scrollTop += delta;
}

function renderDayAgenda(dateStr) {
    const title = document.getElementById('day-agenda-title');
    const list = document.getElementById('day-agenda-list');
    if (!title || !list || !dateStr) {
        return;
    }

    const day = typeof dayInfoFor === 'function' ? dayInfoFor(dateStr) : null;
    const heb = day ? `${get_hebrew_day(day.hebrew_day)}׳ ${day.hebrew_month}` : '';
    const greg = formatShortGregorian(dateStr);
    title.textContent = [heb, greg].filter(Boolean).join(' · ');

    const items = [];
    const jewish = (typeof monthEntryFor === 'function'
        ? monthEntryFor(dateStr)?.jewish[dateStr]
        : null) || [];
    const sortedJewish = [...jewish].sort((a, b) => {
        const order = { parasha: 1, holiday: 2, fast: 3 };
        return (order[a.type] || 9) - (order[b.type] || 9);
    });
    for (const ev of sortedJewish) {
        const kind = ['parasha', 'holiday', 'fast'].includes(ev.type) ? ev.type : 'holiday';
        items.push(
            `<li class="agenda-item agenda-${kind}"><span class="agenda-text">${escapeHtml(ev.name)}</span></li>`
        );
    }

    const events = (infiniteCalendar.eventsCache || [])
        .filter((ev) => isDateInRange(dateStr, ev.gregorian_date, ev.end_date))
        .sort(compareEventsByTime);
    for (const ev of events) {
        const time = ev.time
            ? `<span class="agenda-time">${escapeHtml(ev.time)}</span>`
            : '';
        const range = ev.end_date && ev.end_date > ev.gregorian_date
            ? `<span class="agenda-range">עד ${escapeHtml(formatShortGregorian(ev.end_date))}</span>`
            : '';
        const color = typeof resolveEventColor === 'function' ? resolveEventColor(ev) : ev.color;
        const fill = typeof eventChipFill === 'function'
            ? eventChipFill(ev, 1)
            : (color && typeof getColorRGBA === 'function' ? `rgba(${getColorRGBA(color, 1)})` : '');
        const swatchStyle = fill ? ` style="background: ${fill}"` : '';
        const occurrence = escapeHtml(ev.occurrence_date || ev.gregorian_date || '');
        const recurring = ev.recurrence_freq ? '1' : '0';
        const icon = typeof repeatIconHtml === 'function' ? repeatIconHtml(ev) : '';
        items.push(
            `<li class="agenda-item agenda-event" data-event-id="${ev.id}" data-occurrence-date="${occurrence}" data-recurring="${recurring}">`
            + `<span class="agenda-swatch${fill ? '' : ' is-empty'}"${swatchStyle}></span>`
            + `${time}<span class="agenda-text">${icon}${escapeHtml(ev.title || '')}</span>${range}</li>`
        );
    }

    list.innerHTML = items.length
        ? items.join('')
        : '<li class="agenda-empty">אין אירועים ביום זה</li>';
    syncAgendaSelection();
}

function selectAgendaDay(dateStr, options) {
    if (!document.getElementById('day-agenda') || !dateStr) {
        return;
    }
    infiniteCalendar.agendaDate = dateStr;
    renderDayAgenda(dateStr);
    if (options && options.reveal) {
        ensureAgendaDayVisible(dateStr);
    }
}

function initDayAgenda() {
    const root = document.getElementById('day-agenda');
    if (!root || root.dataset.bound === '1') {
        return;
    }
    root.dataset.bound = '1';

    initCalendarChrome();
    bindAgendaResize();
    syncPageZoomState();
    const onViewport = () => {
        syncPageZoomState();
        if (isPageZoomed()) {
            return;
        }
        applyHeaderCollapsed(readHeaderCollapsed());
        syncCalendarFrame();
        syncWeekRowHeight();
    };
    window.addEventListener('resize', onViewport);
    window.addEventListener('orientationchange', onViewport);
    if (window.visualViewport) {
        window.visualViewport.addEventListener('resize', onViewport);
        window.visualViewport.addEventListener('scroll', onViewport);
    }

    document.getElementById('day-agenda-add')?.addEventListener('click', () => {
        const dateStr = infiniteCalendar.agendaDate || getTodayDateStr();
        openQuickEventModal(dateStr);
    });

    document.getElementById('day-agenda-list')?.addEventListener('click', (event) => {
        const item = event.target.closest('.agenda-event[data-event-id]');
        if (!item) {
            return;
        }
        openEditEventModal(
            item.getAttribute('data-event-id'),
            item.getAttribute('data-occurrence-date')
        );
    });

    const compactQuery = window.matchMedia('(max-width: 480px)');
    compactQuery.addEventListener('change', () => {
        applyHeaderCollapsed(readHeaderCollapsed());
        if (!infiniteCalendar.ready || !infiniteCalendar.body) {
            return;
        }
        syncCalendarFrame();
        syncWeekRowHeight();
        const events = infiniteCalendar.eventsCache || [];
        preserveScrollAnchor(() => {
            for (const row of infiniteCalendar.body.rows) {
                paintWeekRow(row, events);
            }
        });
        if (infiniteCalendar.agendaDate) {
            renderDayAgenda(infiniteCalendar.agendaDate);
        }
    });
}
