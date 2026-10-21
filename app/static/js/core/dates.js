// תאריכים כמחרוזות YYYY-MM-DD וחישובי שבוע/חודש — בלי DOM

function formatDate(date) {
    const year = date.getFullYear();
    const month = String(date.getMonth() + 1).padStart(2, '0');
    const day = String(date.getDate()).padStart(2, '0');
    return `${year}-${month}-${day}`;
}

function addDaysToDateStr(dateStr, days) {
    const date = new Date(`${dateStr}T00:00:00`);
    date.setDate(date.getDate() + days);
    return formatDate(date);
}

function splitDateStr(dateStr) {
    return dateStr.split('-').map(Number);
}

function monthKey(year, month) {
    return `${year}-${month}`;
}

function shiftMonth(year, month, delta) {
    const d = new Date(year, month - 1 + delta, 1);
    return { year: d.getFullYear(), month: d.getMonth() + 1 };
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

function getTodayDateStr() {
    return formatDate(new Date());
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

function getEventDurationDays(event) {
    const start = new Date(`${event.gregorian_date}T00:00:00`);
    const end = new Date(`${event.end_date || event.gregorian_date}T00:00:00`);
    return Math.round((end - start) / 86400000) + 1;
}
