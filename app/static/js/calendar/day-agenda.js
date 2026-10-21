// פאנל יום מתחת ללוח בטלפון: הטקסט המלא שלא נכנס לתא

function isCompactCalendar() {
    return window.matchMedia('(max-width: 480px)').matches;
}

function densityDivisor() {
    try {
        return localStorage.getItem('heb-cal-density') === 'compact' ? 8 : 6;
    } catch (error) {
        return 6;
    }
}

function updateDensityToggle() {
    const button = document.getElementById('density-toggle');
    if (!button) {
        return;
    }
    const compact = densityDivisor() === 8;
    button.textContent = compact ? 'רחב' : 'צפוף';
    button.setAttribute('aria-pressed', compact ? 'true' : 'false');
    button.title = compact ? 'שורות גבוהות יותר' : 'יותר שבועות על המסך';
}

/** בטלפון גובה שורה ≈ אזור הגלילה / 6, כדי ש-5–6 שבועות ימלאו את הרשת. */
function syncWeekRowHeight() {
    const root = document.documentElement;
    const stream = infiniteCalendar.stream;
    if (!isCompactCalendar() || !stream) {
        if (root.style.getPropertyValue('--week-row-height')) {
            root.style.removeProperty('--week-row-height');
        }
        return;
    }
    const header = stream.querySelector('.weekday-header');
    const headerH = header ? header.offsetHeight : 0;
    const grid = stream.clientHeight - headerH;
    if (grid < 120) {
        return;
    }
    const next = `${Math.max(44, Math.floor(grid / densityDivisor()))}px`;
    if (root.style.getPropertyValue('--week-row-height') === next) {
        return;
    }
    const apply = () => root.style.setProperty('--week-row-height', next);
    if (infiniteCalendar.ready && infiniteCalendar.body && infiniteCalendar.body.rows.length) {
        preserveScrollAnchor(apply);
    } else {
        apply();
    }
}

function toggleCalendarDensity() {
    const next = densityDivisor() === 8 ? 'comfortable' : 'compact';
    try {
        localStorage.setItem('heb-cal-density', next);
    } catch (error) {
        /* מצב פרטי — נשאר עד רענון */
    }
    updateDensityToggle();
    syncWeekRowHeight();
    if (typeof updateVisibleMonthLabel === 'function') {
        updateVisibleMonthLabel();
    }
}

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
        items.push(
            `<li class="agenda-item agenda-event" data-event-id="${ev.id}">`
            + `<span class="agenda-swatch${ev.color ? '' : ' is-empty'}"${swatchStyle}></span>`
            + `${time}<span class="agenda-text">${escapeHtml(ev.title || '')}</span>${range}</li>`
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

    updateDensityToggle();
    document.getElementById('density-toggle')?.addEventListener('click', () => {
        toggleCalendarDensity();
    });

    document.getElementById('day-agenda-add')?.addEventListener('click', () => {
        const dateStr = infiniteCalendar.agendaDate || getTodayDateStr();
        openQuickEventModal(dateStr);
    });

    document.getElementById('day-agenda-list')?.addEventListener('click', (event) => {
        const item = event.target.closest('.agenda-event[data-event-id]');
        if (!item) {
            return;
        }
        openEditEventModal(item.getAttribute('data-event-id'));
    });

    const compactQuery = window.matchMedia('(max-width: 480px)');
    compactQuery.addEventListener('change', () => {
        if (!infiniteCalendar.ready || !infiniteCalendar.body) {
            return;
        }
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
