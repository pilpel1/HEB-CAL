// ליבת הלוח האינסופי: הרחבה/קיצוץ, אירועי גלילה, מיקום ראשוני, ניווט

/* --- הרחבה / קיצוץ של טווח השבועות --- */

function appendWeeks(count) {
    const cal = infiniteCalendar;
    const fragment = document.createDocumentFragment();
    const rows = [];
    let added = 0;
    let next = addDaysToDateStr(cal.lastWeek, 7);
    while (added < count && isWeekReady(next)) {
        const row = buildWeekRow(next);
        rows.push(row);
        fragment.appendChild(row);
        cal.lastWeek = next;
        next = addDaysToDateStr(next, 7);
        added += 1;
    }
    if (added) {
        // הוספה מתחת לכל מה שעל המסך — לא מזיזה כלום, אין צורך בעוגן
        cal.body.appendChild(fragment);
        if (typeof fitWeekRowChips === 'function') {
            rows.forEach((row) => fitWeekRowChips(row));
        }
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
        if (typeof fitWeekRowChips === 'function') {
            rows.forEach((row) => fitWeekRowChips(row));
        }
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
        // כל batch מתקן עוגן לבד, ושגיאת עיגול נערמת כשהשורות נמוכות (טלפון).
        // תיקון אחד מול העוגן המקורי מחזיר את מה שהיה על המסך בלי הסטייה.
        const anchorBeforePrepend = captureAnchor();
        let prepended = 0;
        for (let guard = 0; guard < 50; guard += 1) {
            if (stream.scrollTop >= ahead || !prependWeeks(batch)) {
                break;
            }
            prepended += 1;
        }
        if (prepended && anchorBeforePrepend && anchorBeforePrepend.row.isConnected) {
            const slipped = anchorBeforePrepend.row.getBoundingClientRect().top
                - contentTopY()
                - anchorBeforePrepend.offset;
            const rowHeight = anchorBeforePrepend.row.getBoundingClientRect().height || 40;
            // רק סטיית עיגול. משיכה של שורה שלמה מבטלת גלילה שכבר קרה
            if (Math.abs(slipped) > 0.5 && Math.abs(slipped) < rowHeight * 0.5) {
                restoreAnchor(anchorBeforePrepend);
            }
        }
    }

    prefetchAroundRenderedRange();
    maybeExtendEventsCache();

    if (!cal.isScrolling && !cal.smoothScrolling) {
        trimFarWeeks();
    }

    cal.anchor = captureAnchor();
    updateVisibleMonthLabel();
}

function maybeExtendEventsCache() {
    const cal = infiniteCalendar;
    if (!cal.ready || !cal.firstWeek || !cal.lastWeek || cal.eventsExtendPending) {
        return;
    }
    const need = neededEventsRange(cal.firstWeek, cal.lastWeek);
    if (eventsCacheCovers(need.from, need.to)) {
        return;
    }
    cal.eventsExtendPending = true;
    ensureEventsCovering(cal.firstWeek, cal.lastWeek).then(() => {
        cal.eventsExtendPending = false;
        if (!cal.ready || !cal.body) {
            return;
        }
        preserveScrollAnchor(() => {
            for (const row of cal.body.rows) {
                paintWeekRow(row, cal.eventsCache || []);
            }
        });
        if (typeof renderDayAgenda === 'function' && cal.agendaDate) {
            renderDayAgenda(cal.agendaDate);
        }
    }).catch(() => {
        cal.eventsExtendPending = false;
    });
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
    if (typeof syncCalendarFrame === 'function') {
        syncCalendarFrame();
    }
    if (typeof syncWeekRowHeight === 'function') {
        syncWeekRowHeight();
    }
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

function bestWeightedKey(scores) {
    let key = '';
    let score = -1;
    for (const [candidate, value] of scores) {
        if (value > score) {
            score = value;
            key = candidate;
        }
    }
    return key;
}

function updateVisibleMonthLabel() {
    const label = document.getElementById('current-month');
    const body = infiniteCalendar.body;
    const stream = infiniteCalendar.stream;
    if (!label || !body || !stream) {
        return;
    }
    // החודש שתופס הכי הרבה פיקסלים גלויים (לא שבת של השורה העליונה — היא נשארה
    // בתשרי כשי׳ חשון היה באמצע). הטיה קטנה למרכז שוברת תיקו.
    const top = contentTopY();
    const bottom = stream.getBoundingClientRect().bottom;
    const half = (bottom - top) / 2;
    if (half <= 0) {
        return;
    }
    const mid = (top + bottom) / 2;
    const greg = new Map();
    const heb = new Map();
    const rows = body.rows;
    for (let i = 0; i < rows.length; i += 1) {
        const rect = rows[i].getBoundingClientRect();
        if (rect.bottom <= top) {
            continue;
        }
        if (rect.top >= bottom) {
            break;
        }
        const visible = Math.min(rect.bottom, bottom) - Math.max(rect.top, top);
        if (visible <= 0) {
            continue;
        }
        const rowMid = (rect.top + rect.bottom) / 2;
        const weight = visible * (1 + Math.max(0, 1 - Math.abs(rowMid - mid) / half) * 0.15);
        for (const cell of rows[i].cells) {
            const gKey = `${cell.dataset.year}-${cell.dataset.month}`;
            greg.set(gKey, (greg.get(gKey) || 0) + weight);
            if (cell.dataset.hebrewMonth) {
                const hKey = `${cell.dataset.hebrewYear || ''}\n${cell.dataset.hebrewMonth}`;
                heb.set(hKey, (heb.get(hKey) || 0) + weight);
            }
        }
    }
    const gKey = bestWeightedKey(greg);
    if (!gKey) {
        return;
    }
    const [gy, gm] = gKey.split('-');
    const hKey = bestWeightedKey(heb);
    const [hYear, hMonth] = hKey ? hKey.split('\n') : ['', ''];
    const text = formatToolbarLabel(Number(gy), Number(gm), hMonth, hYear);
    if (label.textContent !== text) {
        label.textContent = text;
    }
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

    await ensureEventsCovering(first, last);

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
    if (typeof fitRenderedWeekChips === 'function') {
        fitRenderedWeekChips();
    }

    const top = scrollTargetFor(dateStr, align);
    cal.stream.scrollTop = Math.max(0, top);
    cal.anchor = captureAnchor();
    updateVisibleMonthLabel();
    if (typeof renderDayAgenda === 'function' && cal.agendaDate) {
        renderDayAgenda(cal.agendaDate);
    }
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

function goToToday() {
    scrollToDate(getTodayDateStr(), 'center');
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
    // הפאנל תופס גובה לפני המיקום, אחרת חשיפה שלו אחרי center מזיזה את היום
    cal.agendaDate = today;
    if (typeof initDayAgenda === 'function') {
        initDayAgenda();
    }
    if (typeof renderDayAgenda === 'function') {
        renderDayAgenda(today);
    }
    if (typeof syncCalendarFrame === 'function') {
        syncCalendarFrame();
    }
    if (typeof syncWeekRowHeight === 'function') {
        syncWeekRowHeight();
    }
    const ok = await renderAround(today, 'center');
    if (!ok) {
        if (status) {
            status.textContent = 'שגיאה בטעינת הלוח. נסו לרענן.';
        }
        return;
    }

    // שורות כבר על המסך (עדיין מוסתר): מודדים שוב את הכותרת הדביקה, מתקנים גובה,
    // ומרחיבים את ה-DOM. הכול לפני שמורידים את ה-overlay, כדי שהיום לא יקפוץ.
    cal.ready = true;
    if (typeof syncCalendarFrame === 'function') {
        syncCalendarFrame();
    }
    if (typeof syncWeekRowHeight === 'function') {
        syncWeekRowHeight();
    }
    maintainInfiniteCalendar();
    const centered = scrollTargetFor(today, 'center');
    if (centered !== null) {
        cal.stream.scrollTop = Math.max(0, centered);
    }
    cal.anchor = captureAnchor();

    root?.classList.remove('is-booting');
    cal.stream.setAttribute('aria-busy', 'false');

    cal.stream.addEventListener('scroll', onStreamScroll, { passive: true });
    cal.stream.addEventListener('scrollend', onStreamScrollEnd, { passive: true });
    const resizeObserver = new ResizeObserver(onCalendarResize);
    resizeObserver.observe(cal.stream);
    resizeObserver.observe(cal.body);
    // מקשי חצים / PageDown עובדים מיד בלי ללחוץ קודם על הלוח
    cal.stream.focus({ preventScroll: true });

    scheduleMaintain();
}
