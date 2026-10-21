// תצוגת חודש בודד ישנה (#calendar-body)

/** תאימות לאחור — דף ישן עם #calendar-body בודד */
async function updateCalendar() {
    if (isInfiniteCalendarPage()) {
        await initInfiniteCalendar();
        return;
    }

    const calendarBody = document.getElementById('calendar-body');
    if (!calendarBody) return;

    try {
        const response = await fetch(`/api/calendar/${currentDate.getFullYear()}/${currentDate.getMonth() + 1}`);
        const data = await response.json();

        const monthTitle = document.getElementById('current-month');
        monthTitle.textContent = `${data.month_name} ${currentDate.getFullYear()} | ${data.hebrew_months.join(' ')} ${data.hebrew_year}`;

        calendarBody.innerHTML = '';

        const today = new Date();
        const isCurrentMonth = today.getMonth() === currentDate.getMonth()
            && today.getFullYear() === currentDate.getFullYear();

        let currentRow;
        for (let i = 0; i < data.calendar.length; i++) {
            if (i % 7 === 0) {
                currentRow = document.createElement('tr');
                calendarBody.appendChild(currentRow);
            }

            const cell = document.createElement('td');
            const day = data.calendar[i];

            if (day.gregorian_day) {
                if (isCurrentMonth && day.gregorian_day === today.getDate()) {
                    cell.classList.add('current-day');
                }

                const cellDate = new Date(currentDate.getFullYear(), currentDate.getMonth(), day.gregorian_day);
                cell.setAttribute('data-date', formatDate(cellDate));

                const isFirstOfMonth = day.gregorian_day === 1;
                const gregorianDate = isFirstOfMonth
                    ? `${day.gregorian_day} ${getShortMonthName(currentDate.getMonth())}`
                    : day.gregorian_day;

                cell.innerHTML = `
                    <div class="day-cell">
                        <div class="dates-container">
                            <span class="hebrew-date">${day.is_hebrew_month_start
                                ? `${get_hebrew_day(day.hebrew_day)} ${day.hebrew_month}`
                                : get_hebrew_day(day.hebrew_day)}</span>
                            <span class="gregorian-date">${gregorianDate}</span>
                        </div>
                        <div class="cell-content">
                            <div class="multi-day-rail"></div>
                            <div class="jewish-events-container"></div>
                            <div class="day-content"></div>
                        </div>
                    </div>`;
            }

            currentRow.appendChild(cell);
        }

        await loadAndDisplayEvents();
    } catch (error) {
        console.error('Error rendering calendar:', error);
    }
}

function previousMonth() {
    if (isInfiniteCalendarPage()) {
        const target = shiftMonth(currentDate.getFullYear(), currentDate.getMonth() + 1, -1);
        jumpToMonth(target.year, target.month);
        return;
    }
    currentDate.setMonth(currentDate.getMonth() - 1);
    updateCalendar();
}

function nextMonth() {
    if (isInfiniteCalendarPage()) {
        const target = shiftMonth(currentDate.getFullYear(), currentDate.getMonth() + 1, 1);
        jumpToMonth(target.year, target.month);
        return;
    }
    currentDate.setMonth(currentDate.getMonth() + 1);
    updateCalendar();
}

// פונקציה לטעינת והצגת אירועים בלוח (דף ישן / fallback)
async function loadAndDisplayEvents() {
    if (isInfiniteCalendarPage()) {
        await repaintInfiniteCalendarEvents();
        return;
    }

    try {
        const events = await loadEvents();
        const multiDayEvents = events.filter(isMultiDayEvent);
        const singleDayEvents = events.filter((event) => !isMultiDayEvent(event));

        const rows = document.querySelectorAll('#calendar-body tr');
        for (const row of rows) {
            const cells = [...row.querySelectorAll('td[data-date]')];
            if (cells.length === 0) {
                continue;
            }

            const weekDates = cells.map((cell) => cell.getAttribute('data-date'));
            const { eventLanes } = assignMultiDayLanes(multiDayEvents, weekDates);

            for (const cell of cells) {
                const date = cell.getAttribute('data-date');

                // טעינת אירועים יהודיים לתאריך
                const response = await fetch(`/api/jewish-events/${date}`);
                if (!response.ok) {
                    console.error(`Error loading Jewish events for ${date}:`, await response.text());
                    continue;
                }
                const jewishEvents = await response.json();

                const jewishContainer = cell.querySelector('.jewish-events-container');
                if (jewishEvents && jewishEvents.length > 0) {
                    const sortedEvents = jewishEvents.sort((a, b) => {
                        const order = { parasha: 1, holiday: 2, fast: 3 };
                        return order[a.type] - order[b.type];
                    });

                    jewishContainer.innerHTML = sortedEvents
                        .map((event) => `<div class="${event.type}" style="color: ${event.color}">${event.name}</div>`)
                        .join('');
                } else {
                    jewishContainer.innerHTML = '';
                }

                renderMultiDayRail(
                    cell,
                    date,
                    multiDayEvents,
                    eventLanes,
                    weekDates
                );

                const dayEvents = singleDayEvents.filter((event) => (
                    isDateInRange(date, event.gregorian_date, event.end_date)
                ));

                const contentContainer = cell.querySelector('.day-content');
                if (dayEvents.length > 0) {
                    contentContainer.innerHTML = dayEvents
                        .map((event) => buildEventItemHtml(event))
                        .join('');
                } else {
                    contentContainer.innerHTML = '';
                }
            }
        }
    } catch (error) {
        console.error('Error loading events:', error);
    }
}
