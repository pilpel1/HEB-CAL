// פאנל יום מתחת ללוח בטלפון: הטקסט המלא שלא נכנס לתא

function isCompactCalendar() {
    return window.matchMedia('(max-width: 480px)').matches;
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
    document.querySelectorAll('[data-density-choice]').forEach((button) => {
        const on = (button.getAttribute('data-density-choice') === 'compact') === compact;
        button.setAttribute('aria-pressed', on ? 'true' : 'false');
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
 * גובה אזור השורות כאילו החלוקה היא 80/20.
 * לא תלוי בידית: גרירה רק חושפת או מסתירה שורות בתוך אותו גובה תא.
 */
function referenceWeekRowsArea() {
    const stream = infiniteCalendar.stream;
    const header = stream && stream.querySelector('.weekday-header');
    const headerH = header ? header.offsetHeight : 0;
    const track = splitTrack();
    if (track && track.available > 0) {
        const streamPx = track.available - agendaPixels(track, 0.2, false);
        return streamPx - headerH;
    }
    if (!stream) {
        return 0;
    }
    return stream.clientHeight - headerH;
}

/** בטלפון גובה שורה = רשת 80/20 / 6 (או / 9 במצב צפוף). הידית לא משנה את זה. */
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

function closeQuickSettings(options) {
    const root = document.getElementById('quick-settings');
    const opener = document.getElementById('quick-settings-open');
    if (!root || root.hidden) {
        return;
    }
    root.hidden = true;
    if (opener) {
        opener.setAttribute('aria-expanded', 'false');
    }
    if (options && options.restoreFocus === false) {
        return;
    }
    if (opener && opener.offsetParent !== null) {
        opener.focus();
    }
}

function placeQuickSettings() {
    const sheet = document.querySelector('#quick-settings .quick-settings-sheet');
    const opener = document.getElementById('quick-settings-open');
    if (!sheet || !opener) {
        return;
    }
    sheet.classList.remove('is-popover');
    sheet.style.top = '';
    sheet.style.left = '';
    sheet.style.width = '';
    if (isCompactCalendar()) {
        return;
    }
    const rect = opener.getBoundingClientRect();
    const width = 300;
    let left = rect.left + rect.width / 2 - width / 2;
    left = Math.max(8, Math.min(left, window.innerWidth - width - 8));
    const estimated = 280;
    let top = rect.bottom + 8;
    if (top + estimated > window.innerHeight - 8) {
        top = Math.max(8, rect.top - estimated - 8);
    }
    sheet.classList.add('is-popover');
    sheet.style.top = `${Math.round(top)}px`;
    sheet.style.left = `${Math.round(left)}px`;
    sheet.style.width = `${width}px`;
}

function openQuickSettings() {
    const root = document.getElementById('quick-settings');
    const opener = document.getElementById('quick-settings-open');
    if (!root) {
        return;
    }
    updateDensityToggle();
    root.hidden = false;
    if (opener) {
        opener.setAttribute('aria-expanded', 'true');
    }
    placeQuickSettings();
    document.getElementById('quick-settings-close')?.focus();
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
    const expanded = document.getElementById('toolbar-expanded');
    if (expanded) {
        expanded.toggleAttribute('inert', hide);
    }
    if (hide) {
        const jump = document.getElementById('jumpToDateBtn');
        if (jump && window.bootstrap && bootstrap.Dropdown) {
            const menu = bootstrap.Dropdown.getInstance(jump);
            if (menu) {
                menu.hide();
            }
        }
        closeQuickSettings({ restoreFocus: false });
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

    document.getElementById('quick-settings-open')?.addEventListener('click', () => {
        const root = document.getElementById('quick-settings');
        if (!root || !root.hidden) {
            closeQuickSettings();
            return;
        }
        openQuickSettings();
    });
    document.getElementById('quick-settings-close')?.addEventListener('click', () => {
        closeQuickSettings();
    });
    document.getElementById('quick-settings-backdrop')?.addEventListener('click', () => {
        closeQuickSettings();
    });
    document.addEventListener('keydown', (event) => {
        if (event.key === 'Escape') {
            closeQuickSettings();
        }
    });
    document.querySelectorAll('[data-density-choice]').forEach((button) => {
        button.addEventListener('click', () => {
            setCalendarDensity(button.getAttribute('data-density-choice'));
        });
    });
}

document.addEventListener('DOMContentLoaded', () => {
    initCalendarChrome();
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
        const swatchStyle = ev.color
            ? ` style="background: rgba(${getColorRGBA(ev.color)})"`
            : '';
        const occurrence = escapeHtml(ev.occurrence_date || ev.gregorian_date || '');
        const recurring = ev.recurrence_freq ? '1' : '0';
        const icon = typeof repeatIconHtml === 'function' ? repeatIconHtml(ev) : '';
        items.push(
            `<li class="agenda-item agenda-event" data-event-id="${ev.id}" data-occurrence-date="${occurrence}" data-recurring="${recurring}">`
            + `<span class="agenda-swatch${ev.color ? '' : ' is-empty'}"${swatchStyle}></span>`
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
    const onViewport = () => {
        applyHeaderCollapsed(readHeaderCollapsed());
        syncCalendarFrame();
        syncWeekRowHeight();
        const sheet = document.getElementById('quick-settings');
        if (sheet && !sheet.hidden) {
            placeQuickSettings();
        }
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
        const sheet = document.getElementById('quick-settings');
        if (sheet && !sheet.hidden) {
            placeQuickSettings();
        }
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
