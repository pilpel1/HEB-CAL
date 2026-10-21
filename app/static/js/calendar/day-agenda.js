// פאנל יום מתחת ללוח בטלפון: הטקסט המלא שלא נכנס לתא

function isCompactCalendar() {
    return window.matchMedia('(max-width: 480px)').matches;
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
    if (rect.top >= top - 1 && rect.bottom <= bottom + 1) {
        return;
    }
    const delta = rect.top < top ? rect.top - top : rect.bottom - bottom;
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
