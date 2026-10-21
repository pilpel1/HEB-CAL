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

// מונע מהדפדפן להחזיר scroll ישן אחרי רענון (זה מה שזרק אותנו ליוני/אוקטובר)
if ('scrollRestoration' in history) {
    history.scrollRestoration = 'manual';
}

/** מצב לוח אינסופי — שבועות רציפים בלי תאים ריקים בין חודשים */
const infiniteCalendar = {
    loaded: new Map(), // key "YYYY-M" → { year, month, title }
    earliest: null,
    latest: null,
    loadingPrev: false,
    loadingNext: false,
    maintainingBuffer: false,
    eventsCache: null,
    jewishCache: new Map(), // key "YYYY-M" → { dateStr: events[] }
    observers: [],
    initialized: false,
    readyForInfinite: false,
    /** כמה חודשים לשמור מכל צד של מה שעל המסך */
    bufferMonths: 3,
    /** טעינה ראשונית: היום ± הרדיוס */
    initialRadius: 3,
    maxLoadedMonths: 24,
    isScrolling: false,
    scrollIdleTimer: null,
    pendingPrune: null,
    bufferRaf: null,
    /** אחרי חשיפה — לא לרוץ buffer מיד (מונע קפיצות/prepend) */
    suppressBufferUntil: 0,
};

function monthKey(year, month) {
    return `${year}-${month}`;
}

function shiftMonth(year, month, delta) {
    const d = new Date(year, month - 1 + delta, 1);
    return { year: d.getFullYear(), month: d.getMonth() + 1 };
}

function isInfiniteCalendarPage() {
    return Boolean(document.getElementById('calendar-weeks'));
}

function getWeeksBody() {
    return document.getElementById('calendar-weeks');
}

function weekdayIndex(year, month, day) {
    // Sunday = 0 ... Saturday = 6 (תואם לסדר העמודות שלנו)
    return new Date(year, month - 1, day).getDay();
}

function createPlaceholderCell() {
    const cell = document.createElement('td');
    cell.className = 'day-placeholder';
    return cell;
}

function createEmptyWeekRow() {
    const row = document.createElement('tr');
    row.className = 'week-row';
    for (let i = 0; i < 7; i += 1) {
        row.appendChild(createPlaceholderCell());
    }
    return row;
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

function weekRowsOf(tbody) {
    return [...tbody.querySelectorAll('tr.week-row')];
}

/**
 * שבוע מתחיל ביום ראשון — מפתח YYYY-MM-DD לזיהוי שורת שבוע משותפת בין חודשים.
 */
function weekStartOf(year, month, day) {
    const d = new Date(year, month - 1, day);
    d.setDate(d.getDate() - d.getDay());
    return formatDate(d);
}

function ensureWeekRow(tbody, weekStartStr) {
    let row = tbody.querySelector(`tr.week-row[data-week-start="${weekStartStr}"]`);
    if (row) {
        return row;
    }

    row = createEmptyWeekRow();
    row.dataset.weekStart = weekStartStr;

    const following = weekRowsOf(tbody).find((w) => w.dataset.weekStart > weekStartStr);
    if (following) {
        tbody.insertBefore(row, following);
    } else {
        tbody.appendChild(row);
    }
    return row;
}

/**
 * תופר ימי חודש לתוך רשת שבועות רציפה.
 * placeholders נשארים רק בקצוות הטווח שטרם נטען — לא בין חודשים.
 */
function stitchMonthDays(tbody, year, month, days) {
    if (!days.length) {
        return;
    }

    for (const day of days) {
        const ws = weekStartOf(year, month, day.gregorian_day);
        const dow = weekdayIndex(year, month, day.gregorian_day);
        const weekRow = ensureWeekRow(tbody, ws);
        const slot = weekRow.children[dow];
        if (slot && !slot.hasAttribute('data-date')) {
            weekRow.replaceChild(buildDayCell(year, month, day), slot);
        }
    }
}

function monthTitleFromData(year, data) {
    return `${data.month_name} ${year} | ${data.hebrew_months.join(' ')} ${data.hebrew_year}`;
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
    const key = monthKey(year, month);
    if (infiniteCalendar.jewishCache.has(key)) {
        return infiniteCalendar.jewishCache.get(key);
    }
    try {
        const response = await fetch(`/api/jewish-events/month/${year}/${month}`);
        const data = response.ok ? await response.json() : {};
        infiniteCalendar.jewishCache.set(key, data);
        return data;
    } catch (error) {
        console.error('Error loading monthly jewish events:', error);
        return {};
    }
}

function updateEarliestLatest(year, month) {
    if (!infiniteCalendar.earliest
        || year < infiniteCalendar.earliest.year
        || (year === infiniteCalendar.earliest.year && month < infiniteCalendar.earliest.month)) {
        infiniteCalendar.earliest = { year, month };
    }
    if (!infiniteCalendar.latest
        || year > infiniteCalendar.latest.year
        || (year === infiniteCalendar.latest.year && month > infiniteCalendar.latest.month)) {
        infiniteCalendar.latest = { year, month };
    }
}

/** פיצוי גלילה אחרי שינוי גובה מעל ה-viewport (prepend/prune). */
function adjustScrollForHeightDelta(beforeHeight) {
    const delta = document.documentElement.scrollHeight - beforeHeight;
    if (delta !== 0) {
        window.scrollTo(0, window.scrollY + delta);
    }
}

/** מוחק חודש רחוק מהקצה הנגדי — רק כשהגלילה רגועה */
function pruneFarMonths(keepNearYear, keepNearMonth) {
    if (infiniteCalendar.isScrolling) {
        infiniteCalendar.pendingPrune = { year: keepNearYear, month: keepNearMonth };
        return;
    }

    while (infiniteCalendar.loaded.size > infiniteCalendar.maxLoadedMonths) {
        const keys = [...infiniteCalendar.loaded.keys()];
        const center = keepNearYear * 12 + keepNearMonth;
        let farthestKey = keys[0];
        let farthestDist = -1;
        for (const key of keys) {
            const meta = infiniteCalendar.loaded.get(key);
            const dist = Math.abs(meta.year * 12 + meta.month - center);
            if (dist > farthestDist) {
                farthestDist = dist;
                farthestKey = key;
            }
        }
        if (farthestDist <= 3) {
            break;
        }
        removeMonthFromStream(farthestKey);
    }
    infiniteCalendar.pendingPrune = null;
}

function removeMonthFromStream(key) {
    const meta = infiniteCalendar.loaded.get(key);
    if (!meta) {
        return;
    }

    const tbody = getWeeksBody();
    if (!tbody) {
        return;
    }

    const removingFromTop = infiniteCalendar.earliest
        && meta.year === infiniteCalendar.earliest.year
        && meta.month === infiniteCalendar.earliest.month;

    const beforeHeight = removingFromTop ? document.documentElement.scrollHeight : 0;

    tbody.querySelectorAll(`td[data-year="${meta.year}"][data-month="${meta.month}"]`).forEach((cell) => {
        const row = cell.parentElement;
        row.replaceChild(createPlaceholderCell(), cell);
    });

    weekRowsOf(tbody).forEach((row) => {
        const hasDay = [...row.children].some((c) => c.hasAttribute('data-date'));
        if (!hasDay) {
            row.remove();
        }
    });

    infiniteCalendar.loaded.delete(key);
    infiniteCalendar.jewishCache.delete(key);

    const remaining = [...infiniteCalendar.loaded.values()]
        .sort((a, b) => (a.year * 12 + a.month) - (b.year * 12 + b.month));
    infiniteCalendar.earliest = remaining[0] || null;
    infiniteCalendar.latest = remaining[remaining.length - 1] || null;

    if (removingFromTop) {
        adjustScrollForHeightDelta(beforeHeight);
    }
}

async function loadMonth(year, month, { prepend = false } = {}) {
    const key = monthKey(year, month);
    if (infiniteCalendar.loaded.has(key)) {
        return infiniteCalendar.loaded.get(key);
    }

    const tbody = getWeeksBody();
    if (!tbody) {
        return null;
    }

    try {
        // רשת קודם — רק אחר כך נוגעים ב-DOM
        const [data, jewishByDate] = await Promise.all([
            fetchMonthData(year, month),
            fetchJewishMonth(year, month),
        ]);
        // מוודאים שאירועי משתמש ב-cache לפני צביעה סינכרונית
        await getCachedEvents();

        const days = getRealDays(data.calendar);
        const meta = {
            year,
            month,
            monthName: data.month_name,
            title: monthTitleFromData(year, data),
        };

        infiniteCalendar.loaded.set(key, meta);
        updateEarliestLatest(year, month);

        if (prepend) {
            const booting = document.querySelector('.infinite-calendar.is-booting');
            const todayCell = !booting ? getTodayCell() : null;
            const beforeTop = todayCell ? todayCell.getBoundingClientRect().top : null;
            const beforeHeight = document.documentElement.scrollHeight;

            stitchMonthDays(tbody, year, month, days);
            await paintEventsForMonth(year, month, jewishByDate);

            // בזמן boot לא מיישרים — קופצים ל"היום" פעם אחת בסוף
            if (!booting) {
                if (todayCell && todayCell.isConnected && beforeTop !== null) {
                    window.scrollBy(0, todayCell.getBoundingClientRect().top - beforeTop);
                } else {
                    adjustScrollForHeightDelta(beforeHeight);
                }
            }
        } else {
            stitchMonthDays(tbody, year, month, days);
            await paintEventsForMonth(year, month, jewishByDate);
        }

        if (infiniteCalendar.readyForInfinite) {
            pruneFarMonths(year, month);
            updateVisibleMonthLabel();
        }
        return meta;
    } catch (error) {
        console.error('Error loading month:', error);
        infiniteCalendar.loaded.delete(key);
        return null;
    }
}

async function resetStreamAround(year, month) {
    const tbody = getWeeksBody();
    if (!tbody) {
        return;
    }

    tbody.innerHTML = '';
    infiniteCalendar.loaded.clear();
    infiniteCalendar.jewishCache.clear();
    infiniteCalendar.earliest = null;
    infiniteCalendar.latest = null;
    infiniteCalendar.eventsCache = null;

    const prev = shiftMonth(year, month, -1);
    const next = shiftMonth(year, month, 1);
    await loadMonth(prev.year, prev.month, { prepend: false });
    await loadMonth(year, month, { prepend: false });
    await loadMonth(next.year, next.month, { prepend: false });
}

async function ensureMonthLoaded(year, month) {
    const key = monthKey(year, month);
    if (infiniteCalendar.loaded.has(key)) {
        return infiniteCalendar.loaded.get(key);
    }

    const farFromRange = !infiniteCalendar.earliest || !infiniteCalendar.latest
        || (Math.abs(
            (year * 12 + month)
            - (infiniteCalendar.latest.year * 12 + infiniteCalendar.latest.month)
        ) > 2
        && Math.abs(
            (year * 12 + month)
            - (infiniteCalendar.earliest.year * 12 + infiniteCalendar.earliest.month)
        ) > 2);

    if (farFromRange) {
        await resetStreamAround(year, month);
        return infiniteCalendar.loaded.get(key);
    }

    if (infiniteCalendar.latest) {
        let cursor = { ...infiniteCalendar.latest };
        while (
            cursor.year < year
            || (cursor.year === year && cursor.month < month)
        ) {
            cursor = shiftMonth(cursor.year, cursor.month, 1);
            // eslint-disable-next-line no-await-in-loop
            await loadMonth(cursor.year, cursor.month, { prepend: false });
        }
    }
    if (infiniteCalendar.earliest) {
        let cursor = { ...infiniteCalendar.earliest };
        while (
            cursor.year > year
            || (cursor.year === year && cursor.month > month)
        ) {
            cursor = shiftMonth(cursor.year, cursor.month, -1);
            // eslint-disable-next-line no-await-in-loop
            await loadMonth(cursor.year, cursor.month, { prepend: true });
        }
    }

    if (!infiniteCalendar.loaded.has(key)) {
        await loadMonth(year, month, { prepend: false });
    }
    return infiniteCalendar.loaded.get(key);
}

async function loadPreviousMonth() {
    if (!infiniteCalendar.readyForInfinite
        || infiniteCalendar.loadingPrev
        || !infiniteCalendar.earliest) {
        return null;
    }
    infiniteCalendar.loadingPrev = true;
    try {
        const prev = shiftMonth(
            infiniteCalendar.earliest.year,
            infiniteCalendar.earliest.month,
            -1
        );
        return await loadMonth(prev.year, prev.month, { prepend: true });
    } finally {
        infiniteCalendar.loadingPrev = false;
    }
}

async function loadNextMonth() {
    if (!infiniteCalendar.readyForInfinite
        || infiniteCalendar.loadingNext
        || !infiniteCalendar.latest) {
        return null;
    }
    infiniteCalendar.loadingNext = true;
    try {
        const next = shiftMonth(
            infiniteCalendar.latest.year,
            infiniteCalendar.latest.month,
            1
        );
        // append למטה — לא מזיז scroll, בטוח גם באמצע גלילה
        return await loadMonth(next.year, next.month, { prepend: false });
    } finally {
        infiniteCalendar.loadingNext = false;
    }
}

function visibleMonthIndex() {
    const probe = findProbeDayCell();
    if (probe) {
        return Number(probe.dataset.year) * 12 + Number(probe.dataset.month);
    }
    if (infiniteCalendar.latest) {
        return infiniteCalendar.latest.year * 12 + infiniteCalendar.latest.month;
    }
    return null;
}

/**
 * שומר באפר של חודשים מסביב למה שרואים.
 * למטה (עתיד): מותר לטעון גם תוך כדי גלילה — אין קפיצה.
 * למעלה (עבר): רק כשהגלילה רגועה — prepend מזיז את ה-scroll.
 */
async function maintainMonthBuffer() {
    if (!infiniteCalendar.readyForInfinite
        || infiniteCalendar.maintainingBuffer
        || !infiniteCalendar.earliest
        || !infiniteCalendar.latest
        || Date.now() < infiniteCalendar.suppressBufferUntil) {
        return;
    }

    infiniteCalendar.maintainingBuffer = true;
    try {
        const buffer = infiniteCalendar.bufferMonths;
        let guard = 0;

        // --- עתיד (append) — תמיד מותר ---
        while (guard < 8) {
            guard += 1;
            const vis = visibleMonthIndex();
            if (vis === null) {
                break;
            }
            const late = infiniteCalendar.latest.year * 12 + infiniteCalendar.latest.month;
            if (late - vis >= buffer) {
                break;
            }
            // eslint-disable-next-line no-await-in-loop
            const loaded = await loadNextMonth();
            if (!loaded) {
                break;
            }
        }

        // --- עבר (prepend) — רק בלי מומנטום ---
        if (infiniteCalendar.isScrolling) {
            return;
        }

        guard = 0;
        while (guard < 8) {
            guard += 1;
            const vis = visibleMonthIndex();
            if (vis === null) {
                break;
            }
            const early = infiniteCalendar.earliest.year * 12 + infiniteCalendar.earliest.month;
            if (vis - early >= buffer) {
                break;
            }
            // eslint-disable-next-line no-await-in-loop
            const loaded = await loadPreviousMonth();
            if (!loaded) {
                break;
            }
        }

        const vis = visibleMonthIndex();
        if (vis !== null) {
            const year = Math.floor((vis - 1) / 12);
            const month = ((vis - 1) % 12) + 1;
            pruneFarMonths(year, month);
        }
    } finally {
        infiniteCalendar.maintainingBuffer = false;
    }
}

function scheduleMaintainBuffer() {
    if (infiniteCalendar.bufferRaf) {
        return;
    }
    infiniteCalendar.bufferRaf = requestAnimationFrame(() => {
        infiniteCalendar.bufferRaf = null;
        maintainMonthBuffer();
    });
}

function onInfiniteCalendarScroll() {
    infiniteCalendar.isScrolling = true;
    updateVisibleMonthLabel();

    // עתיד אפשר למלא תוך כדי גלילה — מונע משבצות ריקות ב-fling למטה
    scheduleMaintainBuffer();

    if (infiniteCalendar.scrollIdleTimer) {
        clearTimeout(infiniteCalendar.scrollIdleTimer);
    }
    // fallback לדפדפנים בלי scrollend — ארוך מספיק לא לירות באמצע fling
    infiniteCalendar.scrollIdleTimer = setTimeout(onInfiniteCalendarScrollEnd, 380);
}

function onInfiniteCalendarScrollEnd() {
    infiniteCalendar.isScrolling = false;
    if (infiniteCalendar.scrollIdleTimer) {
        clearTimeout(infiniteCalendar.scrollIdleTimer);
        infiniteCalendar.scrollIdleTimer = null;
    }
    if (infiniteCalendar.pendingPrune) {
        const { year, month } = infiniteCalendar.pendingPrune;
        pruneFarMonths(year, month);
    }
    maintainMonthBuffer();
}

function findProbeDayCell() {
    const chrome = document.querySelector('.calendar-sticky-chrome');
    const probeY = (chrome ? chrome.getBoundingClientRect().bottom : 0) + 48;
    const probeX = Math.min(window.innerWidth / 2, window.innerWidth - 8);
    const hitY = Math.min(Math.max(probeY, 8), window.innerHeight - 8);

    const hits = document.elementsFromPoint(probeX, hitY);
    const fromHit = hits.find((el) => el.matches?.('td[data-date]'))
        || hits.map((el) => el.closest?.('td[data-date]')).find(Boolean);
    if (fromHit) {
        return fromHit;
    }

    // fallback: התא הקרוב ביותר לקו הגלילה מתחת לכרום
    const cells = [...document.querySelectorAll('#calendar-weeks td[data-date]')];
    let best = null;
    let bestDist = Infinity;
    for (const cell of cells) {
        const rect = cell.getBoundingClientRect();
        if (rect.bottom < hitY - 120 || rect.top > window.innerHeight) {
            continue;
        }
        const dist = Math.abs(rect.top - hitY);
        if (dist < bestDist) {
            bestDist = dist;
            best = cell;
        }
    }
    return best;
}

function updateVisibleMonthLabel() {
    const label = document.getElementById('current-month');
    if (!label) {
        return;
    }

    const dayCell = findProbeDayCell();
    if (!dayCell) {
        return;
    }

    const gregYear = Number(dayCell.dataset.year);
    const gregMonth = Number(dayCell.dataset.month);
    const hebrewMonth = dayCell.dataset.hebrewMonth || '';
    const hebrewYear = dayCell.dataset.hebrewYear || '';

    label.textContent = formatToolbarLabel(gregYear, gregMonth, hebrewMonth, hebrewYear);
    currentDate = new Date(gregYear, gregMonth - 1, 1);
}

function getTodayDateStr() {
    return formatDate(new Date());
}

function getTodayCell() {
    return document.querySelector('#calendar-weeks td.current-day')
        || document.querySelector(`#calendar-weeks td[data-date="${getTodayDateStr()}"]`);
}

/** קפיצה ישירה ל"היום" — scrollTo מוחלט, בלי scrollIntoView */
function forceScrollToToday() {
    const todayCell = getTodayCell();
    if (!todayCell) {
        return false;
    }
    if (!todayCell.classList.contains('current-day')) {
        todayCell.classList.add('current-day');
    }

    syncChromeHeightVar();
    const chrome = document.querySelector('.calendar-sticky-chrome');
    const chromeH = chrome ? chrome.getBoundingClientRect().height : 0;
    const absoluteTop = todayCell.getBoundingClientRect().top + window.scrollY;
    const target = Math.max(0, absoluteTop - chromeH - 12);
    // גם assignment ישיר — יותר אמין מול overflow/restoration
    window.scrollTo(0, target);
    document.documentElement.scrollTop = target;
    if (document.body) {
        document.body.scrollTop = target;
    }
    updateVisibleMonthLabel();
    return true;
}

/** האם תא "היום" כבר מתחת לכותרת בטווח סביר */
function isTodaySettledInView() {
    const todayCell = getTodayCell();
    if (!todayCell) {
        return false;
    }
    const chrome = document.querySelector('.calendar-sticky-chrome');
    const chromeH = chrome ? chrome.getBoundingClientRect().height : 0;
    const top = todayCell.getBoundingClientRect().top;
    return top >= chromeH - 8 && top <= chromeH + 80;
}

/**
 * ממקם על היום מתחת ל-overlay.
 * חשוב: קודם משחררים overflow:hidden (calendar-booting) — אחרת scrollTo לא נתפס.
 */
async function settleOnTodayBeforeReveal() {
    // Phase 1: unlock scroll, overlay עדיין מכסה
    document.body.classList.remove('calendar-booting');
    syncChromeHeightVar();
    await waitAnimationFrames(2);

    for (let i = 0; i < 4; i += 1) {
        forceScrollToToday();
        // eslint-disable-next-line no-await-in-loop
        await waitAnimationFrames(1);
        if (isTodaySettledInView()) {
            break;
        }
    }

    // פריים נוסף אחרי fonts/layout
    await waitAnimationFrames(1);
    if (!isTodaySettledInView()) {
        forceScrollToToday();
        await waitAnimationFrames(1);
    }
    return isTodaySettledInView();
}

function scrollTodayCellIntoView(todayCell, behavior = 'auto') {
    if (!todayCell.classList.contains('current-day')) {
        todayCell.classList.add('current-day');
    }
    if (behavior === 'smooth') {
        syncChromeHeightVar();
        const chrome = document.querySelector('.calendar-sticky-chrome');
        const chromeH = chrome ? chrome.getBoundingClientRect().height : 0;
        const cellTop = todayCell.getBoundingClientRect().top + window.scrollY;
        const available = Math.max(window.innerHeight - chromeH, 1);
        const targetTop = Math.max(0, cellTop - chromeH - (available / 2) + (todayCell.offsetHeight / 2));
        window.scrollTo({ top: targetTop, behavior: 'smooth' });
        setTimeout(updateVisibleMonthLabel, 350);
        return;
    }
    forceScrollToToday();
}

function scrollToToday(behavior = 'auto') {
    if (getTodayCell()) {
        if (behavior === 'smooth') {
            scrollTodayCellIntoView(getTodayCell(), 'smooth');
            return Promise.resolve(true);
        }
        return Promise.resolve(forceScrollToToday());
    }

    const now = new Date();
    return ensureMonthLoaded(now.getFullYear(), now.getMonth() + 1).then(() => forceScrollToToday());
}

function waitAnimationFrames(count = 2) {
    return new Promise((resolve) => {
        const step = () => {
            if (count <= 0) {
                resolve();
                return;
            }
            count -= 1;
            requestAnimationFrame(step);
        };
        requestAnimationFrame(step);
    });
}

async function jumpToMonth(year, month) {
    const meta = await ensureMonthLoaded(year, month);
    const firstDay = document.querySelector(
        `#calendar-weeks td[data-year="${year}"][data-month="${month}"][data-date$="-01"]`
    ) || document.querySelector(
        `#calendar-weeks td[data-year="${year}"][data-month="${month}"]`
    );

    if (firstDay) {
        syncChromeHeightVar();
        const chrome = document.querySelector('.calendar-sticky-chrome');
        const chromeH = chrome ? chrome.getBoundingClientRect().height : 0;
        const top = firstDay.getBoundingClientRect().top + window.scrollY - chromeH - 8;
        window.scrollTo({ top: Math.max(0, top), behavior: 'smooth' });
        updateVisibleMonthLabel();
    }
    return meta;
}

function syncChromeHeightVar() {
    const chrome = document.querySelector('.calendar-sticky-chrome');
    if (!chrome) {
        return;
    }
    const height = chrome.getBoundingClientRect().height;
    document.documentElement.style.setProperty('--calendar-chrome-height', `${height}px`);
}

function setupInfiniteScrollObservers() {
    infiniteCalendar.observers.forEach((obs) => obs.disconnect());
    infiniteCalendar.observers = [];

    const topSentinel = document.getElementById('scroll-sentinel-top');
    const bottomSentinel = document.getElementById('scroll-sentinel-bottom');
    if (!topSentinel || !bottomSentinel) {
        return;
    }

    syncChromeHeightVar();

    // רשת בטחון: אם ממש מתקרבים לקצה — ממלאים באפר
    const topObs = new IntersectionObserver((entries) => {
        if (entries.some((e) => e.isIntersecting)) {
            maintainMonthBuffer();
        }
    }, { rootMargin: '600px 0px 0px 0px' });

    const bottomObs = new IntersectionObserver((entries) => {
        if (entries.some((e) => e.isIntersecting)) {
            maintainMonthBuffer();
        }
    }, { rootMargin: '0px 0px 900px 0px' });

    topObs.observe(topSentinel);
    bottomObs.observe(bottomSentinel);
    infiniteCalendar.observers.push(topObs, bottomObs);

    window.addEventListener('scroll', onInfiniteCalendarScroll, { passive: true });
    window.addEventListener('scrollend', onInfiniteCalendarScrollEnd, { passive: true });
    window.addEventListener('resize', syncChromeHeightVar, { passive: true });
}

async function initInfiniteCalendar() {
    if (infiniteCalendar.initialized || !isInfiniteCalendarPage()) {
        return;
    }
    infiniteCalendar.initialized = true;
    infiniteCalendar.readyForInfinite = false;
    infiniteCalendar.suppressBufferUntil = Number.MAX_SAFE_INTEGER;

    if ('scrollRestoration' in history) {
        history.scrollRestoration = 'manual';
    }
    window.scrollTo(0, 0);

    const root = document.querySelector('.infinite-calendar');
    const stream = document.getElementById('calendar-stream');
    root?.classList.add('is-booting');
    document.body.classList.add('calendar-booting');

    const now = new Date();
    const year = now.getFullYear();
    const month = now.getMonth() + 1;
    const radius = infiniteCalendar.initialRadius;

    // stitchMonthDays מסדר לפי weekStart — אפשר לטעון כולם כ-append בלי יישורי scroll
    for (let delta = -radius; delta <= radius; delta += 1) {
        const target = shiftMonth(year, month, delta);
        // eslint-disable-next-line no-await-in-loop
        await loadMonth(target.year, target.month, { prepend: false });
    }

    // ממקמים על היום מתחת ל-overlay (משחרר overflow קודם — אחרת scroll לא נתפס)
    await settleOnTodayBeforeReveal();
    updateVisibleMonthLabel();

    // וידוא אחרון עדיין מתחת ל-overlay — אחרי זה אין scroll
    await waitAnimationFrames(1);
    if (!isTodaySettledInView()) {
        forceScrollToToday();
        await waitAnimationFrames(1);
    }

    // חושפים — בלי forceScroll / maintainMonthBuffer בפריים הזה
    root?.classList.remove('is-booting');
    document.body.classList.remove('calendar-booting');
    if (stream) {
        stream.setAttribute('aria-busy', 'false');
    }

    infiniteCalendar.readyForInfinite = true;
    // חוסמים buffer/observers-driven loads לרגע אחרי חשיפה
    infiniteCalendar.suppressBufferUntil = Date.now() + 900;
    setupInfiniteScrollObservers();
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
    if (isInfiniteCalendarPage() && infiniteCalendar.earliest) {
        const target = shiftMonth(infiniteCalendar.earliest.year, infiniteCalendar.earliest.month, -1);
        loadMonth(target.year, target.month, { prepend: true }).then(() => {
            jumpToMonth(target.year, target.month);
        });
        return;
    }
    currentDate.setMonth(currentDate.getMonth() - 1);
    updateCalendar();
}

function nextMonth() {
    if (isInfiniteCalendarPage() && infiniteCalendar.latest) {
        const target = shiftMonth(infiniteCalendar.latest.year, infiniteCalendar.latest.month, 1);
        loadMonth(target.year, target.month, { prepend: false }).then(() => {
            jumpToMonth(target.year, target.month);
        });
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
        const metas = [...infiniteCalendar.loaded.values()];
        await Promise.all(metas.map((meta) => paintEventsForMonth(meta.year, meta.month)));
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
        scrollToToday('smooth');
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

function mergedJewishCache() {
    const all = {};
    for (const data of infiniteCalendar.jewishCache.values()) {
        Object.assign(all, data);
    }
    return all;
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

/** צובע אירועים לחודש — כולל שבועות משותפים עם חודש שכן */
async function paintEventsForMonth(year, month, jewishByDate = null) {
    try {
        if (!jewishByDate) {
            jewishByDate = await fetchJewishMonth(year, month);
        } else {
            infiniteCalendar.jewishCache.set(monthKey(year, month), jewishByDate);
        }

        const events = await getCachedEvents();
        const multiDayEvents = events.filter(isMultiDayEvent);
        const singleDayEvents = events.filter((event) => !isMultiDayEvent(event));
        const allJewish = mergedJewishCache();

        const monthCells = [...document.querySelectorAll(
            `#calendar-weeks td[data-year="${year}"][data-month="${month}"]`
        )];
        const rows = [...new Set(monthCells.map((cell) => cell.parentElement))];

        for (const row of rows) {
            const cells = [...row.querySelectorAll('td[data-date]')];
            if (cells.length === 0) {
                continue;
            }
            const weekDates = cells.map((cell) => cell.getAttribute('data-date'));
            const { eventLanes } = assignMultiDayLanes(multiDayEvents, weekDates);

            for (const cell of cells) {
                const date = cell.getAttribute('data-date');
                paintCellEvents(
                    cell,
                    date,
                    allJewish,
                    multiDayEvents,
                    singleDayEvents,
                    eventLanes,
                    weekDates
                );
            }
        }
    } catch (error) {
        console.error('Error painting events for month:', error);
    }
}

// פונקציה לטעינת והצגת אירועים בלוח (דף ישן / fallback)
async function loadAndDisplayEvents() {
    if (isInfiniteCalendarPage()) {
        const metas = [...infiniteCalendar.loaded.values()];
        await Promise.all(metas.map((meta) => paintEventsForMonth(meta.year, meta.month)));
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
  
