// בניית שורות שבוע ותאי יום, וצביעה מחדש של אירועים בשורות קיימות

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
    cell.setAttribute('data-date', formatDate(cellDate));
    cell.dataset.year = String(year);
    cell.dataset.month = String(month);
    cell.dataset.hebrewMonth = day.hebrew_month || '';
    cell.dataset.hebrewYear = day.hebrew_year || '';

    const isFirstOfMonth = day.gregorian_day === 1;
    const gregorianDate = isFirstOfMonth
        ? `${day.gregorian_day} ${getShortMonthName(month - 1)}`
        : day.gregorian_day;
    const gregorianClass = isFirstOfMonth ? 'gregorian-date month-start' : 'gregorian-date';

    const hebrewLabel = day.is_hebrew_month_start
        ? `${get_hebrew_day(day.hebrew_day)} ${day.hebrew_month}`
        : get_hebrew_day(day.hebrew_day);
    const hebrewClass = day.is_hebrew_month_start ? 'hebrew-date month-start' : 'hebrew-date';

    cell.innerHTML = `
        <div class="day-cell">
            <div class="dates-container">
                <span class="${hebrewClass}">${hebrewLabel}</span>
                <span class="${gregorianClass}">${gregorianDate}</span>
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
}
