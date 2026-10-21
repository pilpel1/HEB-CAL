// בניית שורות שבוע ותאי יום, וצביעה מחדש של אירועים בשורות קיימות

function monthMarkHtml(fullName, shortName) {
    return `<span class="month-mark month-mark-full">${escapeHtml(fullName)}</span><span class="month-mark month-mark-short">${escapeHtml(shortName)}</span>`;
}

function buildDayCell(year, month, day) {
    const cell = document.createElement('td');
    const today = new Date();
    const isToday = today.getFullYear() === year
        && today.getMonth() + 1 === month
        && today.getDate() === day.gregorian_day;

    if (isToday) {
        cell.classList.add('current-day');
    }

    const cellDate = new Date(year, month - 1, day.gregorian_day);
    const dateStr = formatDate(cellDate);
    cell.setAttribute('data-date', dateStr);
    cell.dataset.year = String(year);
    cell.dataset.month = String(month);
    cell.dataset.hebrewMonth = day.hebrew_month || '';
    cell.dataset.hebrewYear = day.hebrew_year || '';

    const isFirstOfMonth = day.gregorian_day === 1;
    if (isFirstOfMonth) {
        cell.classList.add('greg-month-start');
    }
    if (day.is_hebrew_month_start) {
        cell.classList.add('heb-month-start');
    }
    if (typeof isCompactCalendar === 'function'
        && isCompactCalendar()
        && infiniteCalendar.agendaDate === dateStr) {
        cell.classList.add('is-agenda-day');
    }

    const hebLetter = get_hebrew_day(day.hebrew_day);
    const hebMonth = day.hebrew_month || '';
    const gregFullMonth = GREGORIAN_MONTH_NAMES_HE[month - 1] || '';
    const gregShortMonth = getShortMonthName(month - 1) || '';
    const hebrewTitle = day.is_hebrew_month_start ? `${hebLetter} ${hebMonth}` : hebLetter;
    const gregTitle = isFirstOfMonth
        ? `${day.gregorian_day} ${gregFullMonth}`
        : String(day.gregorian_day);
    const hebrewClass = day.is_hebrew_month_start ? 'hebrew-date month-start' : 'hebrew-date';
    const gregorianClass = isFirstOfMonth ? 'gregorian-date month-start' : 'gregorian-date';
    const hebrewInner = day.is_hebrew_month_start
        ? `<span class="day-num">${escapeHtml(hebLetter)}</span>${monthMarkHtml(hebMonth, shortHebrewMonthName(hebMonth))}`
        : `<span class="day-num">${escapeHtml(hebLetter)}</span>`;
    const gregInner = isFirstOfMonth
        ? `<span class="day-num">${day.gregorian_day}</span>${monthMarkHtml(gregFullMonth, gregShortMonth)}`
        : `<span class="day-num">${day.gregorian_day}</span>`;

    cell.innerHTML = `
        <div class="day-cell">
            <div class="dates-container">
                <span class="${hebrewClass}" dir="rtl" title="${escapeHtml(hebrewTitle)}">${hebrewInner}</span>
                <span class="${gregorianClass}" dir="ltr" title="${escapeHtml(gregTitle)}">${gregInner}</span>
            </div>
            <div class="cell-content">
                <div class="multi-day-rail"></div>
                <div class="jewish-events-container"></div>
                <div class="day-content"></div>
            </div>
        </div>`;

    return cell;
}

function paintWeekRow(row, events) {
    const multiDayEvents = events.filter(isMultiDayEvent);
    const singleDayEvents = events.filter((event) => !isMultiDayEvent(event));
    const cells = [...row.querySelectorAll('td[data-date]')];
    const weekDates = cells.map((cell) => cell.dataset.date);
    const jewishByDate = {};
    for (const dateStr of weekDates) {
        jewishByDate[dateStr] = monthEntryFor(dateStr)?.jewish[dateStr] || [];
    }
    const { eventLanes } = assignMultiDayLanes(multiDayEvents, weekDates);

    for (const cell of cells) {
        paintCellEvents(
            cell,
            cell.dataset.date,
            jewishByDate,
            multiDayEvents,
            singleDayEvents,
            eventLanes,
            weekDates
        );
    }
}

function buildWeekRow(weekStart) {
    const row = document.createElement('tr');
    row.className = 'week-row';
    row.dataset.weekStart = weekStart;
    for (const dateStr of weekDatesOf(weekStart)) {
        const [y, m] = splitDateStr(dateStr);
        row.appendChild(buildDayCell(y, m, dayInfoFor(dateStr)));
    }
    paintWeekRow(row, infiniteCalendar.eventsCache || []);
    return row;
}

async function repaintInfiniteCalendarEvents() {
    const cal = infiniteCalendar;
    if (!cal.ready) {
        return;
    }
    const events = await getCachedEvents();
    preserveScrollAnchor(() => {
        for (const row of cal.body.rows) {
            paintWeekRow(row, events);
        }
    });
    if (typeof renderDayAgenda === 'function' && cal.agendaDate) {
        renderDayAgenda(cal.agendaDate);
    }
}
