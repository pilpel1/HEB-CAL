// מצב משותף של הלוח האינסופי: הגדרות, אובייקט המצב, זיהוי הדף

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
    eventsFrom: null,
    eventsTo: null,
    eventsFetchGen: 0,
    firstWeek: null, // YYYY-MM-DD של יום ראשון בשורה הראשונה ב-DOM
    lastWeek: null,
    anchor: null, // { row, offset, scrollTop } — שורה גלויה ומרחקה מראש אזור התוכן
    zoomScrollTop: null, // scrollTop שננעל בזמן פינץ', כדי שהחודש לא יזוז ~13px
    restingScrollTop: null, // הערך האחרון לפני הפינץ'
    initialized: false,
    ready: false,
    isScrolling: false,
    smoothScrolling: false,
    idleTimer: null,
    maintainRaf: null,
};

function isInfiniteCalendarPage() {
    return Boolean(document.getElementById('calendar-weeks'));
}

function getWeeksBody() {
    return document.getElementById('calendar-weeks');
}
