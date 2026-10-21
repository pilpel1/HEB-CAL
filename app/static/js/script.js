/*
 * נקודת הכניסה של ה-UI. הקוד מפוצל לסקריפטים קלאסיים (לא ES modules) שנטענים
 * ב-base.html אחרי הקובץ הזה, וחולקים scope גלובלי אחד:
 * - onclick בתבניות (goToToday, editEvent, deleteEvent) ו-index.html (jumpToMonth)
 *   קוראים לפונקציות גלובליות.
 * - הסקריפט ב-events_list.html מגדיר deleteEvent/editEvent/getTodayDateStr לפני
 *   הקבצים האלה, ולכן הגרסאות כאן דורסות אותו; loadAllEvents שלו נבדק ב-typeof.
 * - אין קוד שרץ בזמן טעינה מעבר להצהרות (והגדרת scrollRestoration), אז סדר הקבצים
 *   לא משנה לנכונות — הכול נקרא מ-DOMContentLoaded ואילך.
 * אסור להגדיר את אותו שם const/let בשני קבצים — זו SyntaxError שמפילה קובץ שלם.
 */

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
