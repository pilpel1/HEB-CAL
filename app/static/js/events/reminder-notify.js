// התראות דפדפן כשהלוח פתוח (Notification API).
// Web Push כשהטאב סגור דורש HTTPS ו-service worker — מתוכנן אחר כך.
// נקודת ההרחבה: אותו payload של /api/reminders/due (title, body, tag).

const reminderNotifyState = {
    timer: null,
    started: false,
};

const REMINDER_POLL_MS = 30000;
const REMINDER_SHOWN_KEY = 'heb-cal-reminder-shown';

function reminderPermissionLabel() {
    if (!('Notification' in window)) {
        return 'הדפדפן הזה לא תומך בהתראות';
    }
    if (Notification.permission === 'granted') {
        return 'התראות הדפדפן פעילות כשהלוח פתוח';
    }
    if (Notification.permission === 'denied') {
        return 'ההתראות חסומות בדפדפן. אפשר לאפשר אותן בהגדרות האתר';
    }
    return 'התראות הדפדפן עדיין לא אושרו';
}

function setReminderNotifyStatus(message) {
    const node = document.getElementById('reminderNotifyStatus');
    if (node && message) {
        node.textContent = message;
    }
}

function loadShownReminders() {
    try {
        const parsed = JSON.parse(localStorage.getItem(REMINDER_SHOWN_KEY) || '{}');
        if (!parsed || typeof parsed !== 'object') {
            return {};
        }
        const cutoff = Date.now() - 7 * 24 * 60 * 60 * 1000;
        const kept = {};
        Object.entries(parsed).forEach(([key, stamp]) => {
            if (typeof stamp === 'number' && stamp >= cutoff) {
                kept[key] = stamp;
            }
        });
        return kept;
    } catch (error) {
        return {};
    }
}

function saveShownReminders(shown) {
    try {
        localStorage.setItem(REMINDER_SHOWN_KEY, JSON.stringify(shown));
    } catch (error) {
        // localStorage חסום — נציג שוב בסבב הבא, בלי להפיל את הדף
    }
}

function startReminderPoll() {
    if (reminderNotifyState.started) {
        return;
    }
    reminderNotifyState.started = true;
    pollDueReminders();
    reminderNotifyState.timer = setInterval(pollDueReminders, REMINDER_POLL_MS);
}

async function pollDueReminders() {
    if (!('Notification' in window) || Notification.permission !== 'granted') {
        return;
    }
    if (document.visibilityState === 'hidden') {
        return;
    }
    try {
        const response = await fetch('/api/reminders/due?within_seconds=90');
        if (!response.ok) {
            return;
        }
        const data = await response.json();
        const shown = loadShownReminders();
        let changed = false;
        for (const item of data.reminders || []) {
            if (!item || !item.tag || shown[item.tag]) {
                continue;
            }
            try {
                // eslint-disable-next-line no-new
                new Notification(item.title || 'תזכורת', {
                    body: item.body || '',
                    tag: item.tag,
                    lang: 'he',
                });
            } catch (error) {
                return;
            }
            shown[item.tag] = Date.now();
            changed = true;
        }
        if (changed) {
            saveShownReminders(shown);
        }
    } catch (error) {
        // הסבב הבא ינסה שוב
    }
}

function maybeRequestReminderPermission() {
    if (!('Notification' in window)) {
        return;
    }
    if (Notification.permission === 'granted') {
        startReminderPoll();
        setReminderNotifyStatus(reminderPermissionLabel());
        return;
    }
    if (Notification.permission !== 'default') {
        setReminderNotifyStatus(reminderPermissionLabel());
        return;
    }
    Notification.requestPermission().then((permission) => {
        setReminderNotifyStatus(reminderPermissionLabel());
        if (permission === 'granted') {
            startReminderPoll();
        }
    }).catch(() => {});
}

function initReminderNotifications() {
    setReminderNotifyStatus(reminderPermissionLabel());
    if (('Notification' in window) && Notification.permission === 'granted') {
        startReminderPoll();
    }
    document.addEventListener('visibilitychange', () => {
        if (document.visibilityState === 'visible' && ('Notification' in window) && Notification.permission === 'granted') {
            pollDueReminders();
        }
    });
    document.addEventListener('click', (event) => {
        if (event.target.closest('[data-reminder-notify-enable]')) {
            maybeRequestReminderPermission();
        }
    });
}
