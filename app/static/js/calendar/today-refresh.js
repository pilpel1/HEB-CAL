// רענון «היום» בזמן אמת: לחיצה, חזרה לטאב, וב-00:00 מקומית

let todayRefreshTimer = null;
let todayLastDate = null;

function refreshTodayHighlight() {
    const now = getTodayDateStr();
    if (todayLastDate === now) {
        return;
    }
    todayLastDate = now;

    // עדכון הדגשת היום בלוח
    document.querySelectorAll('#calendar-weeks td.current-day').forEach((td) => {
        td.classList.remove('current-day');
    });
    document.querySelectorAll(`#calendar-weeks td[data-date="${now}"]`).forEach((td) => {
        td.classList.add('current-day');
    });

    // עדכון past-day
    document.querySelectorAll('#calendar-weeks td[data-date]').forEach((td) => {
        const date = td.dataset.date;
        if (date < now) {
            td.classList.add('past-day');
        } else {
            td.classList.remove('past-day');
        }
    });
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

function initTodayRefresh() {
    todayLastDate = getTodayDateStr();

    // רענון על חזרה לטאב
    document.addEventListener('visibilitychange', () => {
        if (!document.hidden) {
            refreshTodayHighlight();
            scheduleMidnightRefresh();
        }
    });

    // רענון על focus
    window.addEventListener('focus', () => {
        refreshTodayHighlight();
        scheduleMidnightRefresh();
    });

    // הפעלת טיימר לחצות
    scheduleMidnightRefresh();
}
