// גיאומטריה ועוגן גלילה — כל שינוי DOM מעל המסך עובר דרך preserveScrollAnchor

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
