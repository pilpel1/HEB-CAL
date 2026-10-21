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

function neededEventsRange(firstWeek, lastWeek) {
    return {
        from: addDaysToDateStr(firstWeek, -21),
        to: addDaysToDateStr(lastWeek, 6 + 21),
    };
}

function eventsCacheCovers(from, to) {
    const cal = infiniteCalendar;
    return Boolean(
        cal.eventsCache
        && cal.eventsFrom
        && cal.eventsTo
        && cal.eventsFrom <= from
        && cal.eventsTo >= to
    );
}

/** טוען מופעים לחלון רחב סביב השבועות המרונדרים. בלי לגעת ב-DOM. */
async function ensureEventsCovering(firstWeek, lastWeek) {
    const cal = infiniteCalendar;
    const need = neededEventsRange(firstWeek, lastWeek);
    if (eventsCacheCovers(need.from, need.to)) {
        return cal.eventsCache;
    }
    const from = addDaysToDateStr(need.from, -400);
    const to = addDaysToDateStr(need.to, 400);
    const gen = (cal.eventsFetchGen || 0) + 1;
    cal.eventsFetchGen = gen;
    const events = await loadEvents(from, to);
    if (cal.eventsFetchGen !== gen) {
        return cal.eventsCache || events;
    }
    cal.eventsCache = events;
    cal.eventsFrom = from;
    cal.eventsTo = to;
    return events;
}

async function getCachedEvents() {
    const cal = infiniteCalendar;
    const today = typeof getTodayDateStr === 'function' ? getTodayDateStr() : '';
    const first = cal.firstWeek || today;
    const last = cal.lastWeek || first;
    if (!first || !last) {
        if (!cal.eventsCache) {
            cal.eventsCache = await loadEvents();
        }
        return cal.eventsCache;
    }
    if (cal.eventsCache && eventsCacheCovers(neededEventsRange(first, last).from, neededEventsRange(first, last).to)) {
        return cal.eventsCache;
    }
    return ensureEventsCovering(first, last);
}

function loadMonthsAround(dateStr) {
    const [y, m] = splitDateStr(dateStr);
    const radius = INFINITE_CONFIG.bootMonthsRadius;
    const requests = [];
    for (let delta = -radius; delta <= radius; delta += 1) {
        const target = shiftMonth(y, m, delta);
        requests.push(requestMonth(target.year, target.month));
    }
    return Promise.all(requests);
}
