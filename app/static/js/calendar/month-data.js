// טעינה ו-cache של נתוני חודשים ואירועים ללוח האינסופי

function getRealDays(calendarData) {
    return calendarData.filter((day) => day.gregorian_day);
}

/** טוען (פעם אחת) נתוני חודש: תאריכים עבריים + חגים/פרשות. מחזיר null בכישלון. */
function requestMonth(year, month) {
    const cal = infiniteCalendar;
    const key = monthKey(year, month);
    if (cal.monthData.has(key)) {
        return Promise.resolve(cal.monthData.get(key));
    }
    if (cal.monthRequests.has(key)) {
        return cal.monthRequests.get(key);
    }

    const request = Promise.all([fetchMonthData(year, month), fetchJewishMonth(year, month)])
        .then(([data, jewish]) => {
            const days = new Map();
            for (const day of getRealDays(data.calendar)) {
                days.set(formatDate(new Date(year, month - 1, day.gregorian_day)), day);
            }
            const entry = { year, month, days, jewish };
            cal.monthData.set(key, entry);
            cal.monthRequests.delete(key);
            scheduleMaintain();
            return entry;
        })
        .catch((error) => {
            console.error('Error loading month:', error);
            // ניסיון חוזר רק אחרי השהיה — שלא נציף שרת שנפל בבקשה בכל פריים גלילה
            setTimeout(() => cal.monthRequests.delete(key), 3000);
            return null;
        });
    cal.monthRequests.set(key, request);
    return request;
}

function monthEntryFor(dateStr) {
    const [y, m] = splitDateStr(dateStr);
    return infiniteCalendar.monthData.get(monthKey(y, m)) || null;
}

function dayInfoFor(dateStr) {
    return monthEntryFor(dateStr)?.days.get(dateStr) || null;
}

function isWeekReady(weekStart) {
    return weekDatesOf(weekStart).every((dateStr) => dayInfoFor(dateStr));
}

async function getCachedEvents() {
    if (!infiniteCalendar.eventsCache) {
        infiniteCalendar.eventsCache = await loadEvents();
    }
    return infiniteCalendar.eventsCache;
}

function loadMonthsAround(dateStr) {
    const [y, m] = splitDateStr(dateStr);
    const radius = INFINITE_CONFIG.bootMonthsRadius;
    const requests = [];
    for (let delta = -radius; delta <= radius; delta += 1) {
        const target = shiftMonth(y, m, delta);
        requests.push(requestMonth(target.year, target.month));
    }
    return Promise.all([...requests, getCachedEvents()]);
}
