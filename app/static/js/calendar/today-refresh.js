// רענון «היום» בזמן אמת: חזרה לטאב, resume/pageshow, כל 60 שניות, וב-00:00 שעון ישראל

const TODAY_POLL_MS = 60000;

let todayRefreshTimer = null;
let todayPollTimer = null;
let todayLastDate = null;
let todayRolloverBusy = false;

function applyTodayClasses(now) {
    if (!now) {
        return;
    }
    document.querySelectorAll('#calendar-weeks td.current-day').forEach((td) => {
        td.classList.remove('current-day');
    });
    document.querySelectorAll(`#calendar-weeks td[data-date="${now}"]`).forEach((td) => {
        td.classList.add('current-day');
    });
    document.querySelectorAll('#calendar-weeks td[data-date]').forEach((td) => {
        const date = td.dataset.date;
        if (date < now) {
            td.classList.add('past-day');
        } else {
            td.classList.remove('past-day');
        }
    });
}

function calendarContainsDate(dateStr) {
    if (!dateStr) {
        return false;
    }
    return Boolean(document.querySelector(`#calendar-weeks td[data-date="${dateStr}"]`));
}

function todayModalBlocksRefresh() {
    return typeof isQuickEventModalOpen === 'function' && isQuickEventModalOpen();
}

function wasViewingTodayPeriod(oldDate) {
    if (calendarContainsDate(oldDate)) {
        return true;
    }
    if (typeof infiniteCalendar !== 'undefined' && infiniteCalendar.agendaDate === oldDate) {
        return true;
    }
    return false;
}

async function softRefreshForNewToday(oldDate, newDate) {
    applyTodayClasses(newDate);
    if (todayModalBlocksRefresh()) {
        return;
    }
    if (todayRolloverBusy) {
        return;
    }
    todayRolloverBusy = true;
    try {
        const onCalendar = typeof isInfiniteCalendarPage === 'function' && isInfiniteCalendarPage();
        const viewingOld = wasViewingTodayPeriod(oldDate);
        if (onCalendar && viewingOld) {
            if (typeof infiniteCalendar !== 'undefined') {
                infiniteCalendar.agendaDate = newDate;
            }
            if (typeof scrollToDate === 'function') {
                await scrollToDate(newDate, 'center');
            }
            if (typeof selectAgendaDay === 'function') {
                selectAgendaDay(newDate);
            } else if (typeof renderDayAgenda === 'function') {
                renderDayAgenda(newDate);
            }
        } else if (typeof renderDayAgenda === 'function'
            && typeof infiniteCalendar !== 'undefined'
            && infiniteCalendar.agendaDate) {
            renderDayAgenda(infiniteCalendar.agendaDate);
        }
        if (typeof updateVisibleMonthLabel === 'function') {
            updateVisibleMonthLabel();
        }
        if (typeof refreshEventsViews === 'function') {
            await refreshEventsViews();
        }
    } finally {
        todayRolloverBusy = false;
    }
}

function refreshTodayHighlight() {
    const now = getTodayDateStr();
    if (todayLastDate === now) {
        return Promise.resolve();
    }
    const oldDate = todayLastDate;
    todayLastDate = now;
    if (!oldDate) {
        applyTodayClasses(now);
        return Promise.resolve();
    }
    return softRefreshForNewToday(oldDate, now);
}

function scheduleMidnightRefresh() {
    if (todayRefreshTimer) {
        clearTimeout(todayRefreshTimer);
        todayRefreshTimer = null;
    }

    // חישוב מתי חצות הבאה בשעון ישראל
    const now = new Date();
    const parts = new Intl.DateTimeFormat('en-GB', {
        timeZone: 'Asia/Jerusalem',
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
        hour12: false,
    }).formatToParts(now);

    const lookup = {};
    for (const part of parts) {
        if (part.type !== 'literal') {
            lookup[part.type] = part.value;
        }
    }

    const jerusalemNow = new Date(
        `${lookup.year}-${lookup.month}-${lookup.day}T${lookup.hour}:${lookup.minute}:${lookup.second}`
    );
    const midnight = new Date(jerusalemNow);
    midnight.setHours(24, 0, 0, 0);
    const msUntilMidnight = midnight - jerusalemNow;

    // אם פחות מדקה עד חצות, נדחה עוד דקה כדי לוודא שעברנו
    const delay = msUntilMidnight > 60000 ? msUntilMidnight : msUntilMidnight + 60000;

    todayRefreshTimer = setTimeout(() => {
        refreshTodayHighlight();
        scheduleMidnightRefresh();
    }, delay);
}

function onTodayWake() {
    refreshTodayHighlight();
    scheduleMidnightRefresh();
}

function initTodayRefresh() {
    todayLastDate = getTodayDateStr();
    applyTodayClasses(todayLastDate);

    document.addEventListener('visibilitychange', () => {
        if (!document.hidden) {
            onTodayWake();
        }
    });

    window.addEventListener('focus', onTodayWake);
    document.addEventListener('resume', onTodayWake);
    window.addEventListener('pageshow', onTodayWake);

    if (todayPollTimer) {
        clearInterval(todayPollTimer);
    }
    todayPollTimer = setInterval(() => {
        refreshTodayHighlight();
    }, TODAY_POLL_MS);

    scheduleMidnightRefresh();
}
