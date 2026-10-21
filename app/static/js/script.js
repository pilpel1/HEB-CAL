function formatDate(date) {
    const year = date.getFullYear();
    const month = String(date.getMonth() + 1).padStart(2, '0');
    const day = String(date.getDate()).padStart(2, '0');
    return `${year}-${month}-${day}`;
}

function get_hebrew_day(day) {
    const days = {
        1: 'א', 2: 'ב', 3: 'ג', 4: 'ד', 5: 'ה', 6: 'ו', 7: 'ז', 8: 'ח', 9: 'ט', 10: 'י',
        11: 'יא', 12: 'יב', 13: 'יג', 14: 'יד', 15: 'טו', 16: 'טז', 17: 'יז', 18: 'יח', 19: 'יט', 20: 'כ',
        21: 'כא', 22: 'כב', 23: 'כג', 24: 'כד', 25: 'כה', 26: 'כו', 27: 'כז', 28: 'כח', 29: 'כט', 30: 'ל'
    };
    return days[day] || '';
}

function getShortMonthName(month) {
    const shortMonths = ['ינו', 'פבר', 'מרץ', 'אפר', 'מאי', 'יוני', 
                        'יולי', 'אוג', 'ספט', 'אוק', 'נוב', 'דצמ'];
    return shortMonths[month];
}

const END_DATE_BEFORE_START_MSG = 'תאריך הסיום חייב להיות זהה או מאוחר מתאריך ההתחלה';

function isEndDateBeforeStart(startDate, endDate) {
    if (!startDate || !endDate) {
        return false;
    }
    // YYYY-MM-DD ניתן להשוות כמחרוזת
    return endDate < startDate;
}

function syncEndDateMin(startDate, endInput) {
    if (!endInput) {
        return;
    }
    if (startDate) {
        // min של input[type=date] מאפיר וחוסם בחירה של תאריכים מוקדמים יותר בלוח של הדפדפן
        endInput.setAttribute('min', startDate);
        if (endInput.value && endInput.value < startDate) {
            endInput.value = '';
        }
        endInput.setCustomValidity(
            endInput.value && endInput.value < startDate ? END_DATE_BEFORE_START_MSG : ''
        );
    } else {
        endInput.removeAttribute('min');
        endInput.setCustomValidity('');
    }
}

function assertEndDateNotBeforeStart(startDate, endDate, endInput = null) {
    if (!isEndDateBeforeStart(startDate, endDate)) {
        if (endInput) {
            endInput.setCustomValidity('');
        }
        return true;
    }
    if (endInput) {
        endInput.setCustomValidity(END_DATE_BEFORE_START_MSG);
        endInput.reportValidity();
        return false;
    }
    alert(END_DATE_BEFORE_START_MSG);
    return false;
}

let currentDate = new Date();

// הלוח גולל בתוך #calendar-stream ולא ב-window — אין מיקום ישן שהדפדפן צריך לשחזר
if ('scrollRestoration' in history) {
    history.scrollRestoration = 'manual';
}

/*
 * לוח אינסופי — רצף שבועות (ראשון–שבת) בתוך מיכל גלילה משלו (#calendar-stream).
 *
 * כללים שהקוד הזה נשען עליהם:
 * - כל שינוי DOM שיכול להזיז תוכן מעל המסך עובר דרך preserveScrollAnchor:
 *   מודדים שורה גלויה לפני ואחרי ומתקנים scrollTop באותו task, לפני paint.
 * - overflow-anchor: none על המיכל, אחרת הדפדפן מפצה פעם שנייה.
 * - תיקוני גלילה מיידיים בלבד: Bootstrap שם scroll-behavior: smooth על :root,
 *   ו-scrollTo "מיידי" שהופך לאנימציה הוא מה שגרם לגלילה הנראית ולקפיץ.
 * - שורת שבוע נכנסת ל-DOM רק כשכל 7 הימים שלה כבר בזיכרון — אין תאים ריקים.
 */
const INFINITE_CONFIG = {
    /** חודשים סביב היעד שנטענים לפני שהלוח נחשף */
    bootMonthsRadius: 3,
    /** חודשי נתונים שנשמרים מוכנים מעבר לקצוות של מה שמרונדר */
    prefetchMonths: 18,
    /** כמה גבהי מסך מרונדרים מעבר לכל קצה */
    renderAheadScreens: 4,
    /** שורות רחוקות מזה (בגבהי מסך) נמחקות כשהגלילה נעצרת */
    trimBeyondScreens: 8,
    weeksPerBatch: 4,
    bootWeeksRadius: 14,
    idleMs: 180,
    /** קפיצה רחוקה מזה (בגבהי מסך) — מיידית במקום smooth */
    smoothJumpMaxScreens: 4,
    fontWaitMs: 1500,
};

const infiniteCalendar = {
    stream: null,
    body: null,
    monthData: new Map(), // "YYYY-M" → { days: Map(dateStr → day), jewish: { dateStr: events[] } }
    monthRequests: new Map(), // "YYYY-M" → Promise
    eventsCache: null,
    firstWeek: null, // YYYY-MM-DD של יום ראשון בשורה הראשונה ב-DOM
    lastWeek: null,
    anchor: null, // { row, offset, scrollTop } — שורה גלויה ומרחקה מראש אזור התוכן
    initialized: false,
    ready: false,
    isScrolling: false,
    smoothScrolling: false,
    idleTimer: null,
    maintainRaf: null,
};

function monthKey(year, month) {
    return `${year}-${month}`;
}

function shiftMonth(year, month, delta) {
    const d = new Date(year, month - 1 + delta, 1);
    return { year: d.getFullYear(), month: d.getMonth() + 1 };
}

function splitDateStr(dateStr) {
    return dateStr.split('-').map(Number);
}

function isInfiniteCalendarPage() {
    return Boolean(document.getElementById('calendar-weeks'));
}

function getWeeksBody() {
    return document.getElementById('calendar-weeks');
}

function weekStartOf(dateStr) {
    const [y, m, d] = splitDateStr(dateStr);
    const date = new Date(y, m - 1, d);
    date.setDate(date.getDate() - date.getDay());
    return formatDate(date);
}

function weekDatesOf(weekStart) {
    return Array.from({ length: 7 }, (_, i) => addDaysToDateStr(weekStart, i));
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

function getRealDays(calendarData) {
    return calendarData.filter((day) => day.gregorian_day);
}

const GREGORIAN_MONTH_NAMES_HE = [
    'ינואר', 'פברואר', 'מרץ', 'אפריל', 'מאי', 'יוני',
    'יולי', 'אוגוסט', 'ספטמבר', 'אוקטובר', 'נובמבר', 'דצמבר',
];

function formatToolbarLabel(gregYear, gregMonth, hebrewMonth, hebrewYear) {
    const gregPart = `${GREGORIAN_MONTH_NAMES_HE[gregMonth - 1]} ${gregYear}`;
    const hebPart = [hebrewMonth, hebrewYear].filter(Boolean).join(' ');
    return hebPart ? `${gregPart} | ${hebPart}` : gregPart;
}

async function fetchMonthData(year, month) {
    const response = await fetch(`/api/calendar/${year}/${month}`);
    if (!response.ok) {
        throw new Error(`Failed to load calendar ${year}-${month}`);
    }
    return response.json();
}

async function fetchJewishMonth(year, month) {
    const response = await fetch(`/api/jewish-events/month/${year}/${month}`);
    if (!response.ok) {
        throw new Error(`Failed to load jewish events ${year}-${month}`);
    }
    return response.json();
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

/* --- גיאומטריה ועוגן גלילה --- */

/** Y (ב-viewport) שבו מתחיל התוכן הגלוי — מתחת לשורת ימי השבוע הדביקה */
function contentTopY() {
    const { stream } = infiniteCalendar;
    const header = stream.querySelector('.weekday-header');
    return header ? header.getBoundingClientRect().bottom : stream.getBoundingClientRect().top;
}

/** השורה הראשונה שתחתיתה מתחת ל-y (חיפוש בינארי — השורות ממוינות) */
function rowAtY(y) {
    const rows = infiniteCalendar.body.rows;
    let lo = 0;
    let hi = rows.length - 1;
    let found = null;
    while (lo <= hi) {
        const mid = (lo + hi) >> 1;
        if (rows[mid].getBoundingClientRect().bottom > y) {
            found = rows[mid];
            hi = mid - 1;
        } else {
            lo = mid + 1;
        }
    }
    return found;
}

function captureAnchor() {
    const top = contentTopY();
    const row = rowAtY(top);
    if (!row) {
        return null;
    }
    return {
        row,
        offset: row.getBoundingClientRect().top - top,
        scrollTop: infiniteCalendar.stream.scrollTop,
    };
}

function restoreAnchor(anchor) {
    if (!anchor || !anchor.row.isConnected) {
        return;
    }
    const delta = anchor.row.getBoundingClientRect().top - contentTopY() - anchor.offset;
    if (Math.abs(delta) >= 0.5) {
        infiniteCalendar.stream.scrollTop += delta;
    }
}

/** מריץ שינוי DOM סינכרוני ומשאיר את מה שעל המסך בדיוק באותו מקום */
function preserveScrollAnchor(mutate) {
    const anchor = captureAnchor();
    const result = mutate();
    restoreAnchor(anchor);
    infiniteCalendar.anchor = captureAnchor();
    return result;
}

/** scrollTop שמציב את התאריך למעלה (מתחת לכותרת) או במרכז; null אם לא מרונדר */
function scrollTargetFor(dateStr, align) {
    const { stream, body } = infiniteCalendar;
    const cell = body.querySelector(`td[data-date="${dateStr}"]`);
    if (!cell) {
        return null;
    }
    const row = cell.parentElement;
    const streamTop = stream.getBoundingClientRect().top;
    const headerHeight = contentTopY() - streamTop;
    const rowTop = row.getBoundingClientRect().top - streamTop + stream.scrollTop;
    if (align === 'center') {
        const visibleHeight = stream.clientHeight - headerHeight;
        return rowTop - headerHeight - Math.max(0, (visibleHeight - row.offsetHeight) / 2);
    }
    return rowTop - headerHeight;
}

/* --- הרחבה / קיצוץ של טווח השבועות --- */

function appendWeeks(count) {
    const cal = infiniteCalendar;
    const fragment = document.createDocumentFragment();
    let added = 0;
    let next = addDaysToDateStr(cal.lastWeek, 7);
    while (added < count && isWeekReady(next)) {
        fragment.appendChild(buildWeekRow(next));
        cal.lastWeek = next;
        next = addDaysToDateStr(next, 7);
        added += 1;
    }
    if (added) {
        // הוספה מתחת לכל מה שעל המסך — לא מזיזה כלום, אין צורך בעוגן
        cal.body.appendChild(fragment);
    }
    return added;
}

function prependWeeks(count) {
    const cal = infiniteCalendar;
    const rows = [];
    let prev = addDaysToDateStr(cal.firstWeek, -7);
    while (rows.length < count && isWeekReady(prev)) {
        rows.unshift(buildWeekRow(prev));
        prev = addDaysToDateStr(prev, -7);
    }
    if (!rows.length) {
        return 0;
    }
    preserveScrollAnchor(() => {
        cal.body.prepend(...rows);
        cal.firstWeek = rows[0].dataset.weekStart;
    });
    return rows.length;
}

function trimFarWeeks() {
    const cal = infiniteCalendar;
    const { stream, body } = cal;
    const limit = stream.clientHeight * INFINITE_CONFIG.trimBeyondScreens;
    const viewTop = stream.getBoundingClientRect().top;
    const viewBottom = viewTop + stream.clientHeight;

    const below = [];
    for (let i = body.rows.length - 1; i > 0; i -= 1) {
        if (body.rows[i].getBoundingClientRect().top - viewBottom <= limit) {
            break;
        }
        below.push(body.rows[i]);
    }
    if (below.length) {
        below.forEach((row) => row.remove());
        cal.lastWeek = body.rows[body.rows.length - 1].dataset.weekStart;
    }

    const above = [];
    for (let i = 0; i < body.rows.length - 1; i += 1) {
        if (viewTop - body.rows[i].getBoundingClientRect().bottom <= limit) {
            break;
        }
        above.push(body.rows[i]);
    }
    if (above.length) {
        preserveScrollAnchor(() => {
            above.forEach((row) => row.remove());
            cal.firstWeek = body.rows[0].dataset.weekStart;
        });
    }
}

function prefetchAroundRenderedRange() {
    const cal = infiniteCalendar;
    const [fy, fm] = splitDateStr(cal.firstWeek);
    const [ly, lm] = splitDateStr(addDaysToDateStr(cal.lastWeek, 6));
    // הקרובים קודם — הם אלה שהגלילה תצטרך ראשונים
    for (let i = 0; i <= INFINITE_CONFIG.prefetchMonths; i += 1) {
        const before = shiftMonth(fy, fm, -i);
        const after = shiftMonth(ly, lm, i);
        if (!cal.monthData.has(monthKey(before.year, before.month))) {
            requestMonth(before.year, before.month);
        }
        if (!cal.monthData.has(monthKey(after.year, after.month))) {
            requestMonth(after.year, after.month);
        }
    }
}

/**
 * שומר מספיק תוכן מרונדר מעל ומתחת למסך, מזמין נתונים מראש, ומקצץ רחוק כשרגוע.
 * prepend מותר גם באמצע גלילה מהירה — העוגן מתקן לפני paint, אז אין קפיצה,
 * ואין "קיר" בראש הרשימה. רק בזמן smooth scroll תכנותי לא מוסיפים למעלה,
 * כי שינוי scrollTop היה עוצר את האנימציה באמצע הדרך.
 */
function maintainInfiniteCalendar() {
    const cal = infiniteCalendar;
    if (!cal.ready) {
        return;
    }
    const { stream } = cal;
    const ahead = stream.clientHeight * INFINITE_CONFIG.renderAheadScreens;
    const batch = INFINITE_CONFIG.weeksPerBatch;

    for (let guard = 0; guard < 50; guard += 1) {
        if (stream.scrollHeight - stream.scrollTop - stream.clientHeight >= ahead
            || !appendWeeks(batch)) {
            break;
        }
    }

    if (!cal.smoothScrolling) {
        for (let guard = 0; guard < 50; guard += 1) {
            if (stream.scrollTop >= ahead || !prependWeeks(batch)) {
                break;
            }
        }
    }

    prefetchAroundRenderedRange();

    if (!cal.isScrolling && !cal.smoothScrolling) {
        trimFarWeeks();
    }

    cal.anchor = captureAnchor();
    updateVisibleMonthLabel();
}

function scheduleMaintain() {
    const cal = infiniteCalendar;
    if (!cal.ready || cal.maintainRaf) {
        return;
    }
    cal.maintainRaf = requestAnimationFrame(() => {
        cal.maintainRaf = null;
        maintainInfiniteCalendar();
    });
}

function onStreamScroll() {
    const cal = infiniteCalendar;
    cal.isScrolling = true;
    clearTimeout(cal.idleTimer);
    // גיבוי לדפדפנים בלי scrollend (Safari)
    cal.idleTimer = setTimeout(onStreamScrollEnd, INFINITE_CONFIG.idleMs);
    scheduleMaintain();
}

function onStreamScrollEnd() {
    const cal = infiniteCalendar;
    clearTimeout(cal.idleTimer);
    cal.idleTimer = null;
    cal.isScrolling = false;
    cal.smoothScrolling = false;
    scheduleMaintain();
}

/** גובה שורה השתנה בלי שאנחנו ביקשנו (פונט, רוחב חלון) — מחזירים את העוגן לפני paint */
function onCalendarResize() {
    const cal = infiniteCalendar;
    if (!cal.ready || !cal.anchor) {
        return;
    }
    // אם נגללו מאז שנמדד העוגן, הוא כבר לא מתאר את המסך — שחזור היה מושך אחורה
    if (cal.stream.scrollTop === cal.anchor.scrollTop) {
        restoreAnchor(cal.anchor);
    }
    cal.anchor = captureAnchor();
    scheduleMaintain();
}

function updateVisibleMonthLabel() {
    const label = document.getElementById('current-month');
    if (!label || !infiniteCalendar.body) {
        return;
    }
    // שבת של השורה העליונה: ברגע שה-1 לחודש (לועזי או עברי) מגיע לשורה העליונה, הכותרת מתחלפת
    const row = rowAtY(contentTopY() + 48);
    const cell = row?.cells[6];
    if (!cell) {
        return;
    }

    const gregYear = Number(cell.dataset.year);
    const gregMonth = Number(cell.dataset.month);
    const text = formatToolbarLabel(
        gregYear,
        gregMonth,
        cell.dataset.hebrewMonth || '',
        cell.dataset.hebrewYear || ''
    );
    if (label.textContent !== text) {
        label.textContent = text;
    }
    currentDate = new Date(gregYear, gregMonth - 1, 1);
}

function getTodayDateStr() {
    return formatDate(new Date());
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

/** ממתין לפונט Heebo כדי שגובה השורות לא ישתנה אחרי המיקום הראשוני (עם תקרת זמן) */
function waitForFonts() {
    if (!document.fonts || !document.fonts.load) {
        return Promise.resolve();
    }
    const loads = Promise.all(
        ['400 1em Heebo', '700 1em Heebo'].map((font) => document.fonts.load(font))
    ).catch(() => {});
    const timeout = new Promise((resolve) => setTimeout(resolve, INFINITE_CONFIG.fontWaitMs));
    return Promise.race([loads, timeout]);
}

/** בונה מחדש את הרצף סביב תאריך וממקם אותו מיידית (למעלה או במרכז) */
async function renderAround(dateStr, align) {
    const cal = infiniteCalendar;
    await loadMonthsAround(dateStr);

    const target = weekStartOf(dateStr);
    if (!isWeekReady(target)) {
        return false;
    }

    let first = target;
    let last = target;
    for (let i = 0; i < INFINITE_CONFIG.bootWeeksRadius; i += 1) {
        const prev = addDaysToDateStr(first, -7);
        if (!isWeekReady(prev)) {
            break;
        }
        first = prev;
    }
    for (let i = 0; i < INFINITE_CONFIG.bootWeeksRadius; i += 1) {
        const next = addDaysToDateStr(last, 7);
        if (!isWeekReady(next)) {
            break;
        }
        last = next;
    }

    const fragment = document.createDocumentFragment();
    for (let ws = first; ws <= last; ws = addDaysToDateStr(ws, 7)) {
        fragment.appendChild(buildWeekRow(ws));
    }

    // הכותרת לפני המיקום — אם היא משנה גובה, זה יקרה לפני שמודדים
    const day = dayInfoFor(dateStr);
    const [y, m] = splitDateStr(dateStr);
    document.getElementById('current-month').textContent = formatToolbarLabel(
        y,
        m,
        day.hebrew_month,
        day.hebrew_year
    );

    cal.smoothScrolling = false;
    cal.body.replaceChildren(fragment);
    cal.firstWeek = first;
    cal.lastWeek = last;

    const top = scrollTargetFor(dateStr, align);
    cal.stream.scrollTop = Math.max(0, top);
    cal.anchor = captureAnchor();
    updateVisibleMonthLabel();
    return true;
}

/**
 * גלילה לתאריך. קרוב ומרונדר → smooth; רחוק → מיידי;
 * לא מרונדר או שאין מספיק תוכן סביבו → בנייה מחדש סביבו.
 */
async function scrollToDate(dateStr, align = 'top') {
    const cal = infiniteCalendar;
    if (!cal.ready) {
        return;
    }
    const { stream } = cal;
    const target = scrollTargetFor(dateStr, align);
    const maxTop = stream.scrollHeight - stream.clientHeight;
    if (target === null || target < 0 || target > maxTop) {
        await renderAround(dateStr, align);
        scheduleMaintain();
        return;
    }

    const distance = Math.abs(target - stream.scrollTop);
    if (distance < 1) {
        return;
    }
    if (distance <= stream.clientHeight * INFINITE_CONFIG.smoothJumpMaxScreens) {
        cal.smoothScrolling = true;
        stream.scrollTo({ top: target, behavior: 'smooth' });
    } else {
        stream.scrollTop = target;
    }
}

function jumpToMonth(year, month) {
    return scrollToDate(formatDate(new Date(year, month - 1, 1)), 'top');
}

async function initInfiniteCalendar() {
    const cal = infiniteCalendar;
    if (cal.initialized || !isInfiniteCalendarPage()) {
        return;
    }
    cal.initialized = true;
    cal.stream = document.getElementById('calendar-stream');
    cal.body = getWeeksBody();

    const root = document.querySelector('.infinite-calendar');
    const status = document.getElementById('calendar-boot-status');
    const today = getTodayDateStr();

    // הכול מתחת ל-overlay: נתונים + פונט → רינדור → מיקום על היום → חשיפה. אין גלילה אחרי החשיפה.
    await Promise.all([loadMonthsAround(today), waitForFonts()]);
    const ok = await renderAround(today, 'center');
    if (!ok) {
        if (status) {
            status.textContent = 'שגיאה בטעינת הלוח. נסה לרענן את הדף.';
        }
        return;
    }

    root?.classList.remove('is-booting');
    cal.stream.setAttribute('aria-busy', 'false');
    cal.ready = true;

    cal.stream.addEventListener('scroll', onStreamScroll, { passive: true });
    cal.stream.addEventListener('scrollend', onStreamScrollEnd, { passive: true });
    const resizeObserver = new ResizeObserver(onCalendarResize);
    resizeObserver.observe(cal.stream);
    resizeObserver.observe(cal.body);
    // מקשי חצים / PageDown עובדים מיד בלי ללחוץ קודם על הלוח
    cal.stream.focus({ preventScroll: true });

    scheduleMaintain();
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

// פונקציות טיפול באירועים
async function loadEvents() {
    try {
        const response = await fetch('/api/events');
        const events = await response.json();
        return events;
    } catch (error) {
        console.error('Error loading events:', error);
        return [];
    }
}

// פונקציה להצגת הודעות
function showMessage(message) {
    const successMessage = document.getElementById('success-message');
    if (successMessage) {
        successMessage.textContent = message;
        successMessage.style.display = 'block';
        successMessage.style.opacity = '1';
        
        setTimeout(() => {
            successMessage.style.opacity = '0';
            setTimeout(() => {
                successMessage.style.display = 'none';
            }, 300);
        }, 1500);
    }
}

async function createEvent(eventData) {
    try {
        const response = await fetch('/api/events', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(eventData),
        });
        
        const result = await response.json();
        
        if (response.ok) {
            const quickForm = document.getElementById('quickEventForm');
            if (quickForm) {
                quickForm.reset();
            }
            
            showMessage('האירוע נוסף בהצלחה');
            await refreshEventsViews();
            return true;
        }

        const errorMessage = result.error || 'שגיאה בהוספת האירוע';
        alert(errorMessage);
        return false;
    } catch (error) {
        console.error('Error creating event:', error);
        alert('שגיאה בהוספת האירוע');
        return false;
    }
}

async function refreshEventsViews() {
    infiniteCalendar.eventsCache = null;

    if (isInfiniteCalendarPage()) {
        await repaintInfiniteCalendarEvents();
    } else if (document.getElementById('calendar-body')) {
        await loadAndDisplayEvents();
    }

    // בדף ניהול האירועים יש רנדור משלו — לא לדרוס אותו עם updateEventsList
    if (typeof loadAllEvents === 'function') {
        await loadAllEvents();
        return;
    }

    if (document.getElementById('eventsTable')) {
        await updateEventsList();
    }
}

async function fillHebrewDateFromGregorian(gregorianValue, hebrewInputId) {
    if (!gregorianValue) {
        return;
    }

    try {
        const response = await fetch(`/api/hebrew-date/${gregorianValue}`);
        const data = await response.json();
        const hebrewInput = document.getElementById(hebrewInputId);
        if (hebrewInput) {
            hebrewInput.value = data.hebrew_date;
        }
    } catch (error) {
        console.error('Error converting date:', error);
    }
}

function formatShortGregorian(dateStr) {
    if (!dateStr) {
        return '';
    }

    const parts = dateStr.split('-');
    if (parts.length !== 3) {
        return dateStr;
    }

    return `${Number(parts[2])}/${Number(parts[1])}`;
}

function formatShortHebrew(hebrewDate) {
    if (!hebrewDate) {
        return '';
    }

    // "ח אב 5786" / "ח אב תשפ\"ו" / "ח אב ה'תשפ\"ו" -> "ח אב"
    return hebrewDate
        .replace(/\s+\d{3,4}$/, '')
        .replace(/\s+ה?'?[\u05d0-\u05ea]+"?[\u05d0-\u05ea]*$/, '')
        .trim();
}

function setQuickColor(colorValue) {
    const colorInput = document.getElementById('quick_color');
    if (colorInput) {
        colorInput.value = colorValue || '';
    }

    document.querySelectorAll('#quickEventModal .quick-color-swatch').forEach((swatch) => {
        const isSelected = (swatch.dataset.color || '') === (colorValue || '');
        swatch.classList.toggle('is-selected', isSelected);
        swatch.setAttribute('aria-checked', isSelected ? 'true' : 'false');
    });
}

function setQuickEventModalMode(isEdit) {
    const title = document.getElementById('quickEventModalLabel');
    const submitBtn = document.getElementById('quick_submit_btn');
    const modeLabel = isEdit ? 'עריכת אירוע' : 'אירוע חדש';
    const hebrewShort = formatShortHebrew(document.getElementById('quick_hebrew_date')?.value || '');
    const gregorianShort = formatShortGregorian(document.getElementById('quick_gregorian_date')?.value || '');
    const datePart = [hebrewShort, gregorianShort].filter(Boolean).join(' ');

    if (title) {
        title.textContent = datePart ? `${modeLabel}, ${datePart}` : modeLabel;
    }
    if (submitBtn) {
        submitBtn.textContent = isEdit ? 'שמור שינויים' : 'הוסף אירוע';
    }
}

function populateQuickHourOptions() {
    const hourSelect = document.getElementById('quick_hour');
    if (!hourSelect || hourSelect.dataset.filled === '1') {
        return;
    }

    for (let hour = 0; hour < 24; hour++) {
        const value = String(hour).padStart(2, '0');
        const option = document.createElement('option');
        option.value = value;
        option.textContent = value;
        hourSelect.appendChild(option);
    }
    hourSelect.dataset.filled = '1';
}

function clearExtraQuickMinuteOptions() {
    const minuteSelect = document.getElementById('quick_minute');
    if (!minuteSelect) {
        return;
    }

    minuteSelect.querySelectorAll('option[data-extra="1"]').forEach((option) => option.remove());
}

function setQuickTime(timeValue) {
    const hourSelect = document.getElementById('quick_hour');
    const minuteSelect = document.getElementById('quick_minute');
    if (!hourSelect || !minuteSelect) {
        return;
    }

    clearExtraQuickMinuteOptions();

    if (!timeValue) {
        hourSelect.value = '';
        minuteSelect.value = '';
        return;
    }

    const [hour = '', minute = ''] = timeValue.split(':');
    hourSelect.value = hour;

    const normalizedMinute = String(minute).padStart(2, '0');
    const allowedMinutes = ['00', '15', '30', '45'];
    if (!allowedMinutes.includes(normalizedMinute)) {
        // שומר שעה קיימת שאינה בקפיצות של 15 בלי לאבד אותה
        const extraOption = document.createElement('option');
        extraOption.value = normalizedMinute;
        extraOption.textContent = normalizedMinute;
        extraOption.dataset.extra = '1';
        minuteSelect.appendChild(extraOption);
    }
    minuteSelect.value = normalizedMinute;
}

function getQuickTimeValue() {
    const hourSelect = document.getElementById('quick_hour');
    const minuteSelect = document.getElementById('quick_minute');
    const hour = hourSelect?.value || '';
    let minute = minuteSelect?.value || '';

    if (!hour) {
        return null;
    }

    // שעה בלי דקות → 00
    if (!minute) {
        minute = '00';
        if (minuteSelect) {
            minuteSelect.value = '00';
        }
    }

    return `${hour}:${minute}`;
}

function extractTimeFromTitle(titleValue) {
    const text = (titleValue || '')
        .replace(/[\u200e\u200f\u202a-\u202e]/g, '')
        .trim();

    if (!text) {
        return null;
    }

    // תומך ב־0600, 11:00; גם אם ב־RTL הספרות בסוף הלוגי
    // כולל את כל הטוקן ב-match[0] כדי להסיר אותו מהכותרת
    const patterns = [
        /^(\d{2}):(\d{2})(?!\d)\s*/,
        /^(\d{2})(\d{2})(?!\d)\s*/,
        /\s+(\d{2}):(\d{2})$/,
        /\s+(\d{2})(\d{2})$/,
        /\s+(\d{2}):(\d{2})(?=\s|$)/,
        /\s+(\d{2})(\d{2})(?=\s|$)/,
    ];

    for (const pattern of patterns) {
        const match = text.match(pattern);
        if (!match) {
            continue;
        }

        const hours = Number(match[1]);
        const minutes = Number(match[2]);
        if (hours > 23 || minutes > 59) {
            continue;
        }

        const cleanedTitle = text.replace(match[0], ' ').replace(/\s+/g, ' ').trim();
        return {
            time: `${String(hours).padStart(2, '0')}:${String(minutes).padStart(2, '0')}`,
            cleanedTitle,
        };
    }

    return null;
}

function applyTimeFromTitlePrefix(titleValue) {
    const extracted = extractTimeFromTitle(titleValue);
    if (!extracted) {
        return false;
    }

    setQuickTime(extracted.time);

    const titleInput = document.getElementById('quick_title');
    if (titleInput && titleInput.value !== extracted.cleanedTitle) {
        titleInput.value = extracted.cleanedTitle;
        if (document.activeElement === titleInput) {
            const cursor = titleInput.value.length;
            titleInput.setSelectionRange(cursor, cursor);
        }
    }

    return true;
}

function fillQuickEventForm(eventData = {}) {
    document.getElementById('quick_event_id').value = eventData.id || '';
    document.getElementById('quick_title').value = eventData.title || '';
    document.getElementById('quick_gregorian_date').value = eventData.gregorian_date || '';
    document.getElementById('quick_hebrew_date').value = eventData.hebrew_date || '';
    setQuickTime(eventData.time || '');
    document.getElementById('quick_end_date').value = eventData.end_date || '';
    document.getElementById('quick_description').value = eventData.description || '';
    setQuickColor(eventData.color || '');
    syncEndDateMin(
        eventData.gregorian_date || '',
        document.getElementById('quick_end_date')
    );
}

function getQuickEventFormData() {
    return {
        title: document.getElementById('quick_title').value,
        gregorian_date: document.getElementById('quick_gregorian_date').value,
        hebrew_date: document.getElementById('quick_hebrew_date').value,
        time: getQuickTimeValue(),
        description: document.getElementById('quick_description').value || '',
        end_date: document.getElementById('quick_end_date').value || null,
        color: document.getElementById('quick_color').value || null,
    };
}

async function openQuickEventModal(dateStr) {
    const modalElement = document.getElementById('quickEventModal');
    if (!modalElement) {
        return;
    }

    const form = document.getElementById('quickEventForm');
    if (form) {
        form.reset();
    }

    fillQuickEventForm({ gregorian_date: dateStr });
    // אחרי reset — מוודאים שוב שה-min על תאריך הסיום ננעל לתאריך ההתחלה
    syncEndDateMin(dateStr, document.getElementById('quick_end_date'));
    await fillHebrewDateFromGregorian(dateStr, 'quick_hebrew_date');
    setQuickEventModalMode(false);

    bootstrap.Modal.getOrCreateInstance(modalElement).show();
}

async function openEditEventModal(eventId) {
    const modalElement = document.getElementById('quickEventModal');
    if (!modalElement) {
        return;
    }

    try {
        const response = await fetch(`/api/events/${eventId}`);
        if (!response.ok) {
            alert('לא ניתן לטעון את האירוע');
            return;
        }

        const event = await response.json();
        fillQuickEventForm(event);
        setQuickEventModalMode(true);
        bootstrap.Modal.getOrCreateInstance(modalElement).show();
    } catch (error) {
        console.error('Error loading event for edit:', error);
        alert('שגיאה בטעינת האירוע');
    }
}

function initCalendarContextMenu(calendarBody) {
    let menu = document.getElementById('calendarContextMenu');
    if (!menu) {
        menu = document.createElement('div');
        menu.id = 'calendarContextMenu';
        menu.className = 'calendar-context-menu';
        menu.setAttribute('role', 'menu');
        document.body.appendChild(menu);
    }

    let menuState = { dateStr: null, eventId: null };

    function hideMenu() {
        menu.classList.remove('is-open');
        menu.innerHTML = '';
        menuState = { dateStr: null, eventId: null };
    }

    function positionMenu(clientX, clientY) {
        menu.style.visibility = 'hidden';
        menu.classList.add('is-open');

        const menuRect = menu.getBoundingClientRect();
        const viewportWidth = window.innerWidth;
        const viewportHeight = window.innerHeight;
        // ב-RTL נפתח מעט שמאלה מהסמן, בלי לצאת מהמסך
        let left = clientX - menuRect.width;
        let top = clientY;

        if (left < 8) {
            left = 8;
        }
        if (left + menuRect.width > viewportWidth - 8) {
            left = viewportWidth - menuRect.width - 8;
        }
        if (top + menuRect.height > viewportHeight - 8) {
            top = viewportHeight - menuRect.height - 8;
        }
        if (top < 8) {
            top = 8;
        }

        menu.style.left = `${left}px`;
        menu.style.top = `${top}px`;
        menu.style.visibility = 'visible';
    }

    function buildMenuItems() {
        const items = [];

        if (menuState.eventId) {
            items.push(
                { label: 'ערוך אירוע', action: 'edit-event' },
                { label: 'מחק אירוע', action: 'delete-event', danger: true },
                { separator: true },
            );
        }

        items.push(
            { label: 'הוסף אירוע', action: 'add-event' },
            { label: 'רשימת אירועים', action: 'events-list' },
        );

        return items;
    }

    function showMenu(clientX, clientY) {
        const items = buildMenuItems();
        menu.innerHTML = items.map((item) => {
            if (item.separator) {
                return '<div class="context-menu-separator" role="separator"></div>';
            }
            const dangerClass = item.danger ? ' is-danger' : '';
            return `<button type="button" role="menuitem" data-action="${item.action}" class="${dangerClass.trim()}">${item.label}</button>`;
        }).join('');

        positionMenu(clientX, clientY);
    }

    calendarBody.addEventListener('contextmenu', (event) => {
        const cell = event.target.closest('td[data-date]');
        if (!cell) {
            hideMenu();
            return;
        }

        event.preventDefault();
        event.stopPropagation();

        const eventItem = event.target.closest('.event-item[data-event-id]');
        menuState = {
            dateStr: cell.getAttribute('data-date'),
            eventId: eventItem ? eventItem.getAttribute('data-event-id') : null,
        };
        showMenu(event.clientX, event.clientY);
    });

    menu.addEventListener('click', async (event) => {
        const button = event.target.closest('button[data-action]');
        if (!button) {
            return;
        }

        const action = button.getAttribute('data-action');
        const { dateStr, eventId } = menuState;
        hideMenu();

        if (action === 'add-event' && dateStr) {
            await openQuickEventModal(dateStr);
            return;
        }
        if (action === 'edit-event' && eventId) {
            await openEditEventModal(eventId);
            return;
        }
        if (action === 'delete-event' && eventId) {
            await deleteEvent(eventId);
            return;
        }
        if (action === 'events-list') {
            window.location.href = '/events_list';
        }
    });

    document.addEventListener('click', (event) => {
        if (!menu.contains(event.target)) {
            hideMenu();
        }
    });

    document.addEventListener('keydown', (event) => {
        if (event.key === 'Escape') {
            hideMenu();
        }
    });

    window.addEventListener('scroll', hideMenu, true);
    window.addEventListener('resize', hideMenu);
}

function initQuickEventModal() {
    const modalElement = document.getElementById('quickEventModal');
    const quickForm = document.getElementById('quickEventForm');
    if (!modalElement || !quickForm) {
        return;
    }

    populateQuickHourOptions();

    // אחרי סיום הפתיחה של Bootstrap — פוקוס יציב על הכותרת
    modalElement.addEventListener('shown.bs.modal', () => {
        requestAnimationFrame(() => {
            const titleInput = document.getElementById('quick_title');
            if (titleInput) {
                titleInput.focus({ preventScroll: true });
            }
        });
    });

    modalElement.addEventListener('hidden.bs.modal', () => {
        fillQuickEventForm();
        setQuickEventModalMode(false);
    });

    const calendarRoot = document.getElementById('calendar-stream')
        || document.getElementById('calendar-body');
    if (calendarRoot) {
        calendarRoot.addEventListener('dblclick', (event) => {
            const eventItem = event.target.closest('.event-item[data-event-id]');
            if (eventItem) {
                event.stopPropagation();
                openEditEventModal(eventItem.getAttribute('data-event-id'));
                return;
            }

            const cell = event.target.closest('td[data-date]');
            if (!cell) {
                return;
            }

            openQuickEventModal(cell.getAttribute('data-date'));
        });

        initCalendarContextMenu(calendarRoot);
    }

    modalElement.querySelectorAll('.quick-color-swatch').forEach((swatch) => {
        swatch.addEventListener('click', () => {
            setQuickColor(swatch.dataset.color || '');
        });
    });

    const hourSelect = document.getElementById('quick_hour');
    const minuteSelect = document.getElementById('quick_minute');
    if (hourSelect && minuteSelect) {
        hourSelect.addEventListener('change', () => {
            if (hourSelect.value && !minuteSelect.value) {
                minuteSelect.value = '00';
            }
            if (!hourSelect.value) {
                minuteSelect.value = '';
                clearExtraQuickMinuteOptions();
            }
        });
    }

    const titleInput = document.getElementById('quick_title');
    if (titleInput) {
        const syncTimeFromTitle = () => applyTimeFromTitlePrefix(titleInput.value);
        titleInput.addEventListener('input', syncTimeFromTitle);
        titleInput.addEventListener('keyup', syncTimeFromTitle);
        titleInput.addEventListener('blur', syncTimeFromTitle);
    }

    const quickGregorianDate = document.getElementById('quick_gregorian_date');
    if (quickGregorianDate) {
        quickGregorianDate.addEventListener('change', async () => {
            const startDate = quickGregorianDate.value;
            syncEndDateMin(startDate, document.getElementById('quick_end_date'));
            await fillHebrewDateFromGregorian(startDate, 'quick_hebrew_date');
            const isEdit = Boolean(document.getElementById('quick_event_id').value);
            setQuickEventModalMode(isEdit);
        });
    }

    const quickEndDate = document.getElementById('quick_end_date');
    if (quickEndDate) {
        // אם בכל זאת הוקלד תאריך לא תקין ידנית — מנקים מיד
        quickEndDate.addEventListener('change', () => {
            const startDate = document.getElementById('quick_gregorian_date').value;
            syncEndDateMin(startDate, quickEndDate);
        });
    }

    quickForm.addEventListener('submit', async (e) => {
        e.preventDefault();

        // ניסיון אחרון לחלץ שעה מהכותרת לפני שמירה
        applyTimeFromTitlePrefix(document.getElementById('quick_title').value);

        // אם נשארו דקות בלי שעה — מתעלמים מהדקות
        if (!document.getElementById('quick_hour').value) {
            document.getElementById('quick_minute').value = '';
            clearExtraQuickMinuteOptions();
        }

        const eventData = getQuickEventFormData();
        const endInput = document.getElementById('quick_end_date');
        syncEndDateMin(eventData.gregorian_date, endInput);
        if (!assertEndDateNotBeforeStart(eventData.gregorian_date, eventData.end_date, endInput)) {
            return;
        }

        const eventId = document.getElementById('quick_event_id').value;
        const saved = eventId
            ? await updateEvent(eventId, eventData)
            : await createEvent(eventData);

        if (saved) {
            bootstrap.Modal.getOrCreateInstance(modalElement).hide();
        }
    });
}

async function updateEvent(eventId, eventData) {
    try {
        const response = await fetch(`/api/events/${eventId}`, {
            method: 'PUT',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(eventData),
        });
        
        const result = await response.json();
        if (result.success) {
            showMessage('האירוע עודכן בהצלחה');
            await refreshEventsViews();
            return true;
        }

        alert(result.error || 'שגיאה בעדכון האירוע');
        return false;
    } catch (error) {
        console.error('Error updating event:', error);
        alert('שגיאה בעדכון האירוע');
        return false;
    }
}

async function deleteEvent(eventId) {
    if (!confirm('האם אתה בטוח שברצונך למחוק אירוע זה?')) {
        return;
    }

    try {
        const response = await fetch(`/api/events/${eventId}`, {
            method: 'DELETE',
        });
        
        const result = await response.json();
        if (result.success) {
            // ניקוי שדה החיפוש ותגיות החיפוש
            const searchInput = document.getElementById('searchInput');
            if (searchInput) {
                searchInput.value = '';
            }
            
            // ניקוי תגיות החיפוש
            const filterChips = document.querySelector('.filter-chips');
            if (filterChips) {
                filterChips.innerHTML = '';
            }
            
            showMessage('האירוע נמחק בהצלחה');
            await refreshEventsViews();
        } else {
            alert('שגיאה במחיקת האירוע');
        }
    } catch (error) {
        console.error('Error deleting event:', error);
        alert('שגיאה במחיקת האירוע');
    }
}

// אתחול הדף
document.addEventListener('DOMContentLoaded', async () => {
    initQuickEventModal();

    if (isInfiniteCalendarPage()) {
        await initInfiniteCalendar();
    } else if (document.getElementById('calendar-body')) {
        await updateCalendar();
    }

    const addEventFromCalendarBtn = document.getElementById('addEventFromCalendarBtn');
    if (addEventFromCalendarBtn) {
        addEventFromCalendarBtn.addEventListener('click', () => {
            openQuickEventModal(formatDate(new Date()));
        });
    }

    // בדף ניהול האירועים הטעינה נעשית בסקריפט של הדף עצמו
    if (document.getElementById('eventsTable') && typeof loadAllEvents !== 'function') {
        await updateEventsList();
    }
});

async function updateEventsList() {
    const eventsTable = document.getElementById('eventsTable');
    if (!eventsTable) return; // אם אנחנו לא בדף רשימת האירועים

    // בדף ניהול האירועים יש רנדור משלו
    if (typeof loadAllEvents === 'function') {
        await loadAllEvents();
        return;
    }

    const events = await loadEvents();
    
    eventsTable.innerHTML = events.map(event => `
        <tr id="row-${event.id}">
            <td>${event.color ? `<span style="background-color: rgba(${getColorRGBA(event.color)})">${event.title}</span>` : event.title}</td>
            <td>${event.gregorian_date}</td>
            <td>${event.hebrew_date}</td>
            <td>${event.time || ''}</td>
            <td>${event.description || ''}</td>
            <td>
                <div class="btn-group" role="group">
                    <button class="btn btn-outline-primary btn-sm" onclick="editEvent(${event.id})" title="ערוך אירוע">
                        <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" fill="currentColor" class="bi bi-pencil" viewBox="0 0 16 16">
                            <path d="M12.146.146a.5.5 0 0 1 .708 0l3 3a.5.5 0 0 1 0 .708l-10 10a.5.5 0 0 1-.168.11l-5 2a.5.5 0 0 1-.65-.65l2-5a.5.5 0 0 1 .11-.168l10-10zM11.207 2.5 13.5 4.793 14.793 3.5 12.5 1.207zm1.586 3L10.5 3.207 4 9.707V10h.5a.5.5 0 0 1 .5.5v.5h.5a.5.5 0 0 1 .5.5v.5h.293zm-9.761 5.175-.106.106-1.528 3.821 3.821-1.528.106-.106A.5.5 0 0 1 5 12.5V12h-.5a.5.5 0 0 1-.5-.5V11h-.5a.5.5 0 0 1-.468-.325z"/>
                        </svg>
                    </button>
                    <button class="btn btn-outline-danger btn-sm" onclick="deleteEvent(${event.id})" title="מחק אירוע">
                        <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" fill="currentColor" class="bi bi-trash" viewBox="0 0 16 16">
                            <path d="M5.5 5.5A.5.5 0 0 1 6 6v6a.5.5 0 0 1-1 0V6a.5.5 0 0 1 .5-.5m2.5 0a.5.5 0 0 1 .5.5v6a.5.5 0 0 1-1 0V6a.5.5 0 0 1 .5-.5m3 .5a.5.5 0 0 0-1 0v6a.5.5 0 0 0 1 0z"/>
                            <path d="M14.5 3a1 1 0 0 1-1 1H13v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V4h-.5a1 1 0 0 1-1-1V2a1 1 0 0 1 1-1H6a1 1 0 0 1 1-1h2a1 1 0 0 1 1 1h3.5a1 1 0 0 1 1 1zM4.118 4 4 4.059V13a1 1 0 0 0 1 1h6a1 1 0 0 0 1-1V4.059L11.882 4zM2.5 3h11V2h-11z"/>
                        </svg>
                    </button>
                </div>
            </td>
        </tr>
    `).join('');
}

async function editEvent(eventId) {
    if (typeof openEditEventModal === 'function') {
        await openEditEventModal(eventId);
        return;
    }
    alert('לא ניתן לפתוח את עריכת האירוע');
}

function goToToday() {
    if (isInfiniteCalendarPage()) {
        scrollToDate(getTodayDateStr(), 'center');
        return;
    }
    currentDate = new Date();
    updateCalendar();
}

// פונקציה להמרת שם צבע ל-RGBA
function getColorRGBA(color) {
    const colorMap = {
        'cyan': '0, 255, 255, 0.4',
        'yellow': '255, 255, 0, 0.4',
        'orange': '255, 165, 0, 0.4',
        'green': '0, 128, 0, 0.4'
    };
    return colorMap[color] || '0, 0, 0, 0';
}

// פונקציה לבדיקה אם תאריך נמצא בטווח
function isDateInRange(dateStr, startStr, endStr) {
    if (!dateStr || !startStr) {
        return false;
    }

    // YYYY-MM-DD — השוואת מחרוזות בטוחה יותר מ-Date (בלי באגי timezone)
    // end_date לא תקין (לפני ההתחלה) מתייחסים אליו כאילו אין סיום
    const effectiveEnd = (endStr && endStr >= startStr) ? endStr : startStr;
    return dateStr >= startStr && dateStr <= effectiveEnd;
}

function isMultiDayEvent(event) {
    return Boolean(event.end_date && event.end_date > event.gregorian_date);
}

function addDaysToDateStr(dateStr, days) {
    const date = new Date(`${dateStr}T00:00:00`);
    date.setDate(date.getDate() + days);
    return formatDate(date);
}

function getEventDurationDays(event) {
    const start = new Date(`${event.gregorian_date}T00:00:00`);
    const end = new Date(`${event.end_date || event.gregorian_date}T00:00:00`);
    return Math.round((end - start) / 86400000) + 1;
}

function getMultiDaySegmentRole(dateStr, event, weekDates) {
    const prev = addDaysToDateStr(dateStr, -1);
    const next = addDaysToDateStr(dateStr, 1);
    const continuesFromPrev = weekDates.includes(prev)
        && isDateInRange(prev, event.gregorian_date, event.end_date);
    const continuesToNext = weekDates.includes(next)
        && isDateInRange(next, event.gregorian_date, event.end_date);

    if (!continuesFromPrev && continuesToNext) {
        return 'start';
    }
    if (continuesFromPrev && continuesToNext) {
        return 'middle';
    }
    if (continuesFromPrev && !continuesToNext) {
        return 'end';
    }
    return 'single';
}

function assignMultiDayLanes(multiDayEvents, weekDates) {
    const relevant = multiDayEvents
        .filter((event) => weekDates.some((date) => (
            isDateInRange(date, event.gregorian_date, event.end_date)
        )))
        .sort((a, b) => {
            if (a.gregorian_date !== b.gregorian_date) {
                return a.gregorian_date < b.gregorian_date ? -1 : 1;
            }
            return getEventDurationDays(b) - getEventDurationDays(a);
        });

    const laneEnds = [];
    const eventLanes = new Map();

    for (const event of relevant) {
        const daysInWeek = weekDates.filter((date) => (
            isDateInRange(date, event.gregorian_date, event.end_date)
        ));
        if (daysInWeek.length === 0) {
            continue;
        }

        const startInWeek = daysInWeek[0];
        const endInWeek = daysInWeek[daysInWeek.length - 1];
        let lane = 0;
        while (lane < laneEnds.length && laneEnds[lane] >= startInWeek) {
            lane += 1;
        }

        if (lane === laneEnds.length) {
            laneEnds.push(endInWeek);
        } else {
            laneEnds[lane] = endInWeek;
        }
        eventLanes.set(event.id, lane);
    }

    return { eventLanes, laneCount: laneEnds.length };
}

function buildEventItemHtml(event, extraClasses = []) {
    const timeStr = event.time ? `${event.time} - ` : '';
    const classes = ['event-item', ...extraClasses];
    if (!event.color) {
        classes.push('event-uncolored');
    }

    const style = event.color
        ? `background-color: rgba(${getColorRGBA(event.color)})`
        : '';

    return `<div class="${classes.join(' ')}" data-event-id="${event.id}" style="${style}">${timeStr}${event.title}</div>`;
}

function renderMultiDayRail(cell, date, multiDayEvents, eventLanes, weekDates) {
    const rail = cell.querySelector('.multi-day-rail');
    if (!rail) {
        return;
    }

    const laneHtml = new Map();

    for (const event of multiDayEvents) {
        if (!isDateInRange(date, event.gregorian_date, event.end_date)) {
            continue;
        }

        const lane = eventLanes.get(event.id);
        if (lane === undefined) {
            continue;
        }

        const role = getMultiDaySegmentRole(date, event, weekDates);
        laneHtml.set(lane, buildEventItemHtml(event, [
            'event-multi',
            `event-multi-${role}`,
        ]));
    }

    if (laneHtml.size === 0) {
        rail.innerHTML = '';
        return;
    }

    const maxLaneToday = Math.max(...laneHtml.keys());
    const lanes = [];
    for (let lane = 0; lane <= maxLaneToday; lane += 1) {
        lanes.push(
            laneHtml.get(lane)
            || '<div class="event-lane-spacer" aria-hidden="true"></div>'
        );
    }

    rail.innerHTML = lanes.join('');
}

async function getCachedEvents() {
    if (!infiniteCalendar.eventsCache) {
        infiniteCalendar.eventsCache = await loadEvents();
    }
    return infiniteCalendar.eventsCache;
}

function paintCellEvents(cell, date, jewishByDate, multiDayEvents, singleDayEvents, eventLanes, weekDates) {
    const jewishEvents = jewishByDate[date] || [];
    const jewishContainer = cell.querySelector('.jewish-events-container');
    if (jewishEvents.length > 0) {
        const sortedEvents = [...jewishEvents].sort((a, b) => {
            const order = { parasha: 1, holiday: 2, fast: 3 };
            return (order[a.type] || 9) - (order[b.type] || 9);
        });
        jewishContainer.innerHTML = sortedEvents
            .map((event) => `<div class="${event.type}" style="color: ${event.color}">${event.name}</div>`)
            .join('');
    } else {
        jewishContainer.innerHTML = '';
    }

    renderMultiDayRail(cell, date, multiDayEvents, eventLanes, weekDates);

    const dayEvents = singleDayEvents.filter((event) => (
        isDateInRange(date, event.gregorian_date, event.end_date)
    ));
    const contentContainer = cell.querySelector('.day-content');
    contentContainer.innerHTML = dayEvents.length > 0
        ? dayEvents.map((event) => buildEventItemHtml(event)).join('')
        : '';
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
  
