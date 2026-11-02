// מודל אירוע מהיר (הוספה/עריכה): שדות, שעה מהכותרת, צבע, חזרה, שליחה

let quickSeriesSnapshot = null;
let quickOccurrenceSnapshot = null;
let quickEventFormDirty = false;
let quickEventFormMute = false;
let hebrewYearsPromise = null;
const HEBREW_PICKER_IDS = {
    start: {
        day: 'quick_hebrew_day',
        month: 'quick_hebrew_month',
        year: 'quick_hebrew_year',
        hebrew: 'quick_hebrew_date',
        gregorian: 'quick_gregorian_date',
    },
    end: {
        day: 'quick_end_hebrew_day',
        month: 'quick_end_hebrew_month',
        year: 'quick_end_hebrew_year',
        hebrew: 'quick_end_hebrew_date',
        gregorian: 'quick_end_date',
    },
};
const hebrewPickerState = {
    start: { token: 0, mute: false, contextYear: null },
    end: { token: 0, mute: false, contextYear: null },
};
// הבורר האחרון שהמשתמש נגע בו: 'hebrew' | 'gregorian' | null
let dateEntrySource = null;
// true אחרי בחירה מפורשת של לוח החזרה, או כשעורכים אירוע שכבר חוזר
let recurrenceCalendarTouched = false;
let quickModalEpoch = 0;

const FULL_EVENT_FORM_KEY = 'heb-cal-full-event-form';

function prefersFullEventForm() {
    try {
        return localStorage.getItem(FULL_EVENT_FORM_KEY) === '1';
    } catch (error) {
        return false;
    }
}

function setPrefersFullEventForm(on) {
    try {
        if (on) {
            localStorage.setItem(FULL_EVENT_FORM_KEY, '1');
        } else {
            localStorage.removeItem(FULL_EVENT_FORM_KEY);
        }
    } catch (error) {
        // localStorage חסום (מצב פרטי) — הבחירה תחזיק רק עד רענון
    }
    syncFullEventFormSwitch();
}

function syncFullEventFormSwitch() {
    const on = prefersFullEventForm();
    document.querySelectorAll('[data-full-form-switch]').forEach((input) => {
        input.checked = on;
    });
}

function eventUsesAdvancedFields(eventData) {
    if (!eventData || typeof eventData !== 'object') {
        return false;
    }
    if (eventData.end_date) {
        return true;
    }
    if (eventData.recurrence_freq) {
        return true;
    }
    if (eventData.is_shift || eventData.shift_label) {
        return true;
    }
    if (String(eventData.description || '').trim()) {
        return true;
    }
    if (Array.isArray(eventData.reminders) && eventData.reminders.length) {
        return true;
    }
    return false;
}

function isQuickAdvancedOpen() {
    const toggle = document.getElementById('quick_advanced_toggle');
    return toggle ? toggle.getAttribute('aria-expanded') === 'true' : false;
}

function setQuickAdvancedOpen(open) {
    const isOpen = Boolean(open);
    const modal = document.getElementById('quickEventModal');
    const panel = document.getElementById('quick_advanced');
    const toggle = document.getElementById('quick_advanced_toggle');
    if (modal) {
        modal.classList.toggle('is-advanced', isOpen);
    }
    if (panel) {
        panel.hidden = !isOpen;
    }
    if (toggle) {
        toggle.setAttribute('aria-expanded', isOpen ? 'true' : 'false');
    }
}

function applyQuickAdvancedDefault(eventData) {
    setQuickAdvancedOpen(prefersFullEventForm() || eventUsesAdvancedFields(eventData));
}

function syncQuickModalToVisualViewport() {
    const modal = document.getElementById('quickEventModal');
    if (!modal || !modal.classList.contains('show')) {
        return;
    }
    const vv = window.visualViewport;
    const height = Math.round(vv ? vv.height : window.innerHeight);
    const width = Math.round(vv ? vv.width : window.innerWidth);
    const offsetTop = Math.round(vv ? vv.offsetTop : 0);
    const offsetLeft = Math.round(vv ? vv.offsetLeft : 0);
    modal.style.top = `${offsetTop}px`;
    modal.style.left = `${offsetLeft}px`;
    modal.style.height = `${height}px`;
    modal.style.width = `${width}px`;
    modal.style.setProperty('--quick-vv-height', `${height}px`);
}

function clearQuickModalViewportPin() {
    const modal = document.getElementById('quickEventModal');
    if (!modal) {
        return;
    }
    modal.style.top = '';
    modal.style.left = '';
    modal.style.height = '';
    modal.style.width = '';
    modal.style.removeProperty('--quick-vv-height');
}

function loadHebrewYearLabels() {
    if (!hebrewYearsPromise) {
        hebrewYearsPromise = fetch('/api/hebrew-years?from=5660&to=5820')
            .then((response) => (response.ok ? response.json() : { years: [] }))
            .then((data) => (Array.isArray(data.years) ? data.years : []))
            .catch(() => []);
    }
    return hebrewYearsPromise;
}

function pickerEls(which) {
    const ids = HEBREW_PICKER_IDS[which] || HEBREW_PICKER_IDS.start;
    return {
        day: document.getElementById(ids.day),
        month: document.getElementById(ids.month),
        year: document.getElementById(ids.year),
        hebrew: document.getElementById(ids.hebrew),
        gregorian: document.getElementById(ids.gregorian),
    };
}

async function ensureHebrewYearSelect(select, year, label) {
    if (!select) {
        return;
    }
    if (select.dataset.filled !== '1') {
        const years = await loadHebrewYearLabels();
        if (select.dataset.filled !== '1' && years.length) {
            select.replaceChildren();
            years.forEach((item) => {
                const option = document.createElement('option');
                option.value = String(item.year);
                option.textContent = item.label || String(item.year);
                select.append(option);
            });
            select.dataset.filled = '1';
        }
    }
    if (year && ![...select.options].some((option) => option.value === String(year))) {
        const option = document.createElement('option');
        option.value = String(year);
        option.textContent = label || String(year);
        select.append(option);
    }
    if (year && select.options.length) {
        select.value = String(year);
    }
}

function fillHebrewMonthSelect(select, months, selected) {
    if (!select || !Array.isArray(months) || !months.length) {
        return;
    }
    const current = selected != null ? String(selected) : select.value;
    select.replaceChildren();
    months.forEach((item) => {
        const option = document.createElement('option');
        option.value = String(item.value);
        option.textContent = item.name;
        select.append(option);
    });
    if ([...select.options].some((option) => option.value === current)) {
        select.value = current;
    }
}

function fillHebrewDaySelect(select, count, selected) {
    if (!select) {
        return;
    }
    const days = Number(count) || 30;
    const wanted = Number(selected) || Number(select.value) || 1;
    const day = Math.min(Math.max(wanted, 1), days);
    if (select.options.length !== days) {
        select.replaceChildren();
        for (let number = 1; number <= days; number += 1) {
            const option = document.createElement('option');
            option.value = String(number);
            option.textContent = (typeof get_hebrew_day === 'function' && get_hebrew_day(number)) || String(number);
            select.append(option);
        }
    }
    select.value = String(day);
}

async function applyHebrewDatePayload(which, data, token) {
    const state = hebrewPickerState[which];
    if (!data || !state || token !== state.token) {
        return;
    }
    const els = pickerEls(which);
    if (els.hebrew && data.hebrew_date) {
        els.hebrew.value = data.hebrew_date;
    }
    await ensureHebrewYearSelect(els.year, data.year, data.year_label);
    if (token !== state.token) {
        return;
    }
    state.mute = true;
    try {
        fillHebrewMonthSelect(els.month, data.months, data.month);
        fillHebrewDaySelect(els.day, data.days_in_month, data.day);
        if (data.year) {
            if (els.year && [...els.year.options].some((option) => option.value === String(data.year))) {
                els.year.value = String(data.year);
            }
        }
        if (Array.isArray(data.months) && data.months.length) {
            state.contextYear = data.year || null;
        }
    } finally {
        state.mute = false;
    }
}

function gregorianFromHebrewUrl(year, month, day, contextYear) {
    const params = new URLSearchParams({
        year: String(year),
        month: String(month),
        day: String(day),
    });
    if (contextYear && String(contextYear) !== String(year)) {
        params.set('from_year', String(contextYear));
    }
    return `/api/gregorian-from-hebrew?${params.toString()}`;
}

function recurrenceCalendarForDateEntry(source, touched) {
    if (touched || (source !== 'hebrew' && source !== 'gregorian')) {
        return null;
    }
    return source;
}

function applyRecurrenceCalendarDefault() {
    const next = recurrenceCalendarForDateEntry(dateEntrySource, recurrenceCalendarTouched);
    if (!next) {
        return;
    }
    const calendar = document.getElementById('quick_recurrence_calendar');
    if (!calendar || calendar.disabled) {
        return;
    }
    calendar.value = next;
}

function noteDateEntry(source) {
    dateEntrySource = source;
    applyRecurrenceCalendarDefault();
}

function refreshQuickModalTitle() {
    const isEdit = Boolean(document.getElementById('quick_event_id')?.value);
    setQuickEventModalMode(isEdit);
}

async function fillHebrewDateFromGregorian(gregorianValue, which = 'start') {
    if (!gregorianValue) {
        return;
    }
    const state = hebrewPickerState[which] || hebrewPickerState.start;
    const token = ++state.token;
    try {
        const response = await fetch(`/api/hebrew-date/${gregorianValue}`);
        const data = await response.json();
        if (!response.ok || token !== state.token) {
            return;
        }
        await applyHebrewDatePayload(which, data, token);
        if (which === 'start' && token === state.token) {
            refreshQuickModalTitle();
        }
    } catch (error) {
        console.error('Error converting date:', error);
    }
}

async function onHebrewPickerChange(which = 'start') {
    const state = hebrewPickerState[which];
    if (!state || state.mute) {
        return;
    }
    if (which === 'start') {
        noteDateEntry('hebrew');
    }
    const els = pickerEls(which);
    const year = els.year?.value;
    const month = els.month?.value;
    const day = els.day?.value;
    if (!year || !month || !day) {
        return;
    }
    const token = ++state.token;
    try {
        const response = await fetch(gregorianFromHebrewUrl(year, month, day, state.contextYear));
        const data = await response.json();
        if (!response.ok || token !== state.token) {
            return;
        }
        if (els.gregorian && data.gregorian_date) {
            els.gregorian.value = data.gregorian_date;
            const startDate = which === 'start'
                ? data.gregorian_date
                : (document.getElementById('quick_gregorian_date')?.value || '');
            const endInput = document.getElementById('quick_end_date');
            syncEndDateMin(startDate, endInput);
            if (which === 'end' && !endInput?.value) {
                return;
            }
        }
        await applyHebrewDatePayload(which, data, token);
        if (which === 'start' && token === state.token) {
            refreshQuickModalTitle();
            const endValue = document.getElementById('quick_end_date')?.value;
            if (endValue) {
                await fillHebrewDateFromGregorian(endValue, 'end');
            }
        }
    } catch (error) {
        console.error('Error converting Hebrew date:', error);
    }
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

function syncQuickDeleteButton(isEdit, readonly) {
    const deleteBtn = document.getElementById('quick_delete_btn');
    if (!deleteBtn) {
        return;
    }
    const editing = isEdit == null
        ? Boolean(document.getElementById('quick_event_id')?.value)
        : Boolean(isEdit);
    const isReadonly = readonly == null
        ? Boolean(document.getElementById('quickEventForm')?.classList.contains('is-gcal-readonly'))
        : Boolean(readonly);
    deleteBtn.hidden = !editing || isReadonly;
}

function setQuickEventReadonly(readonly) {
    const form = document.getElementById('quickEventForm');
    const note = document.getElementById('quick_gcal_note');
    const submit = document.getElementById('quick_submit_btn');
    if (note) {
        note.hidden = !readonly;
    }
    if (submit) {
        submit.hidden = !!readonly;
    }
    if (form) {
        form.classList.toggle('is-gcal-readonly', !!readonly);
        form.querySelectorAll('input, textarea, select, button').forEach((el) => {
            if (
                el.hasAttribute('data-bs-dismiss')
                || el.id === 'quick_submit_btn'
                || el.id === 'quick_delete_btn'
                || el.id === 'quick_advanced_toggle'
            ) {
                return;
            }
            el.disabled = !!readonly;
        });
    }
    syncQuickDeleteButton(undefined, readonly);
    if (readonly) {
        const title = document.getElementById('quickEventModalLabel');
        if (title) {
            title.textContent = 'אירוע מיומן גוגל';
        }
    }
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
        submitBtn.textContent = isEdit ? 'שמירה' : 'הוסף אירוע';
    }
    syncQuickDeleteButton(isEdit);
}

async function deleteFromQuickEventModal() {
    const eventId = document.getElementById('quick_event_id')?.value;
    if (!eventId) {
        return false;
    }
    const form = document.getElementById('quickEventForm');
    if (form?.classList.contains('is-gcal-readonly')) {
        return false;
    }
    const scope = currentEditScope();
    const occurrenceDate = quickOccurrenceSnapshot?.occurrence_date;
    let deleted = false;
    if (scope === 'occurrence' && occurrenceDate) {
        deleted = await deleteEventOccurrence(eventId, occurrenceDate);
    } else {
        const repeating = Boolean(quickSeriesSnapshot) || Boolean(quickOccurrenceSnapshot);
        deleted = await deleteEvent(eventId, repeating ? { series: true } : undefined);
    }
    if (deleted) {
        const modalElement = document.getElementById('quickEventModal');
        if (modalElement) {
            bootstrap.Modal.getOrCreateInstance(modalElement).hide();
        }
    }
    return deleted;
}

function populateQuickHourOptions() {
    // נשאר גלובלי: השעה עברה ל-input type=time, אין יותר רשימת שעות
}

function clearExtraQuickMinuteOptions() {
    // נשאר גלובלי: דקות חופשיות נכנסות ישירות לשדה השעה
}

function recurrenceEndMode(eventData) {
    if (eventData && eventData.recurrence_count) {
        return 'count';
    }
    if (eventData && eventData.recurrence_until) {
        return 'until';
    }
    return 'never';
}

function syncRecurrenceControls() {
    const freq = document.getElementById('quick_recurrence_freq');
    const calendar = document.getElementById('quick_recurrence_calendar');
    const endRow = document.getElementById('quick_recurrence_end_row');
    const mode = document.getElementById('quick_recurrence_end_mode');
    const until = document.getElementById('quick_recurrence_until');
    const count = document.getElementById('quick_recurrence_count');
    if (!freq || !calendar || !endRow || !mode || !until || !count) {
        return;
    }
    const repeating = Boolean(freq.value);
    calendar.hidden = !repeating;
    endRow.hidden = !repeating;
    until.hidden = !repeating || mode.value !== 'until';
    count.hidden = !repeating || mode.value !== 'count';
    const wrap = document.getElementById('quick_recurrence');
    if (wrap) {
        wrap.classList.toggle('is-repeating', repeating);
        wrap.classList.toggle('has-end-value', repeating && mode.value !== 'never');
    }
    const scope = document.getElementById('quick_recurrence_scope');
    const occurrenceOnly = scope && !scope.hidden && scope.querySelector('input[value="occurrence"]')?.checked;
    const lockRule = Boolean(occurrenceOnly);
    freq.disabled = lockRule;
    calendar.disabled = lockRule;
    mode.disabled = lockRule;
    until.disabled = lockRule;
    count.disabled = lockRule;
    const start = document.getElementById('quick_gregorian_date')?.value || '';
    if (start) {
        until.min = start;
        if (until.value && until.value < start) {
            until.value = start;
        }
    }
}

function setRecurrenceScopeVisible(show, which) {
    const scope = document.getElementById('quick_recurrence_scope');
    if (!scope) {
        return;
    }
    scope.hidden = !show;
    if (show) {
        const value = which || 'occurrence';
        const input = scope.querySelector(`input[value="${value}"]`);
        if (input) {
            input.checked = true;
        }
    }
    syncRecurrenceControls();
}

function applyRecurrenceFields(eventData) {
    const freq = document.getElementById('quick_recurrence_freq');
    const calendar = document.getElementById('quick_recurrence_calendar');
    const mode = document.getElementById('quick_recurrence_end_mode');
    const until = document.getElementById('quick_recurrence_until');
    const count = document.getElementById('quick_recurrence_count');
    if (!freq || !calendar || !mode || !until || !count) {
        return;
    }
    freq.value = eventData.recurrence_freq || '';
    calendar.value = eventData.recurrence_calendar === 'hebrew' ? 'hebrew' : 'gregorian';
    recurrenceCalendarTouched = Boolean(eventData.recurrence_freq);
    if (!eventData.recurrence_freq) {
        dateEntrySource = null;
    }
    mode.value = recurrenceEndMode(eventData);
    until.value = eventData.recurrence_until || '';
    count.value = eventData.recurrence_count ? String(eventData.recurrence_count) : '';
    syncRecurrenceControls();
}

function readRecurrenceFields() {
    const freq = document.getElementById('quick_recurrence_freq')?.value || '';
    if (!freq) {
        return {
            recurrence_freq: '',
            recurrence_calendar: null,
            recurrence_until: null,
            recurrence_count: null,
        };
    }
    const mode = document.getElementById('quick_recurrence_end_mode')?.value || 'never';
    const untilValue = document.getElementById('quick_recurrence_until')?.value || '';
    const countRaw = document.getElementById('quick_recurrence_count')?.value || '';
    return {
        recurrence_freq: freq,
        recurrence_calendar: document.getElementById('quick_recurrence_calendar')?.value || 'gregorian',
        recurrence_until: mode === 'until' ? (untilValue || null) : null,
        recurrence_count: mode === 'count' ? Number(countRaw) : null,
    };
}

function currentEditScope() {
    const scope = document.getElementById('quick_recurrence_scope');
    if (!scope || scope.hidden) {
        return 'all';
    }
    const checked = scope.querySelector('input:checked');
    return checked ? checked.value : 'occurrence';
}

function setEndDateOpen(isOpen) {
    const wrap = document.querySelector('#quickEventModal .quick-end-wrap');
    if (wrap) {
        wrap.classList.toggle('is-open', Boolean(isOpen));
    }
    const toggle = document.getElementById('quick_end_toggle');
    if (!toggle) {
        return;
    }
    toggle.setAttribute('aria-expanded', isOpen ? 'true' : 'false');
    toggle.textContent = isOpen ? 'הסר תאריך סיום' : '+ תאריך סיום';
}

function setQuickTime(timeValue) {
    const input = document.getElementById('quick_time');
    if (!input) {
        return;
    }
    if (!timeValue) {
        input.value = '';
        return;
    }
    const match = String(timeValue).match(/^(\d{1,2}):(\d{2})/);
    if (!match) {
        input.value = '';
        return;
    }
    input.value = `${match[1].padStart(2, '0')}:${match[2]}`;
}

function getQuickTimeValue() {
    const input = document.getElementById('quick_time');
    const value = (input?.value || '').trim();
    const match = value.match(/^(\d{2}):(\d{2})/);
    if (!match) {
        return null;
    }
    return `${match[1]}:${match[2]}`;
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

function isQuickEventFormDirty() {
    return quickEventFormDirty;
}

function isQuickEventModalOpen() {
    const el = document.getElementById('quickEventModal');
    return Boolean(el && el.classList.contains('show'));
}

function getOpenQuickEventId() {
    const raw = document.getElementById('quick_event_id')?.value;
    const number = Number(raw);
    return Number.isInteger(number) && number > 0 ? number : null;
}

function fillQuickEventForm(eventData = {}, options = {}) {
    quickEventFormMute = true;
    if (typeof hideLiveSyncModalNotice === 'function') {
        hideLiveSyncModalNotice();
    }
    document.getElementById('quick_event_id').value = eventData.id || '';
    document.getElementById('quick_title').value = eventData.title || '';
    document.getElementById('quick_gregorian_date').value = eventData.gregorian_date || '';
    document.getElementById('quick_hebrew_date').value = eventData.hebrew_date || '';
    setQuickTime(eventData.time || '');
    document.getElementById('quick_end_date').value = eventData.end_date || '';
    setEndDateOpen(Boolean(eventData.end_date));
    document.getElementById('quick_description').value = eventData.description || '';
    if (typeof fillReminderFields === 'function') {
        fillReminderFields(eventData.reminders || []);
    }
    setQuickColor(eventData.color || '');
    applyRecurrenceFields(eventData);
    if (!options.keepScope) {
        quickSeriesSnapshot = null;
        quickOccurrenceSnapshot = null;
        setRecurrenceScopeVisible(false);
    } else {
        syncRecurrenceControls();
    }
    syncEndDateMin(
        eventData.gregorian_date || '',
        document.getElementById('quick_end_date')
    );
    if (typeof fillQuickShiftFields === 'function') {
        const pending = fillQuickShiftFields(eventData);
        if (typeof shiftUiState !== 'undefined') {
            shiftUiState.quickShiftFill = pending;
        }
    }
    applyQuickAdvancedDefault(eventData);
    const finishFill = () => {
        quickEventFormDirty = false;
        quickEventFormMute = false;
    };
    const jobs = [];
    if (eventData.gregorian_date) {
        jobs.push(fillHebrewDateFromGregorian(eventData.gregorian_date, 'start'));
    }
    if (eventData.end_date) {
        jobs.push(fillHebrewDateFromGregorian(eventData.end_date, 'end'));
    } else if (eventData.gregorian_date) {
        jobs.push(fillHebrewDateFromGregorian(eventData.gregorian_date, 'end'));
    }
    if (jobs.length) {
        return Promise.all(jobs).then(finishFill, finishFill);
    }
    finishFill();
    return Promise.resolve();
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
        reminders: typeof readReminderFields === 'function' ? readReminderFields() : [],
        ...readRecurrenceFields(),
        ...(typeof readQuickShiftFields === 'function' ? readQuickShiftFields() : {}),
    };
}

async function openQuickEventModal(dateStr) {
    const modalElement = document.getElementById('quickEventModal');
    if (!modalElement) {
        return;
    }
    const epoch = ++quickModalEpoch;

    const form = document.getElementById('quickEventForm');
    if (form) {
        form.reset();
    }

    setQuickEventReadonly(false);
    const pendingHebrew = fillQuickEventForm({ gregorian_date: dateStr });
    // אחרי reset — מוודאים שוב שה-min על תאריך הסיום ננעל לתאריך ההתחלה
    syncEndDateMin(dateStr, document.getElementById('quick_end_date'));
    setQuickEventModalMode(false);
    bootstrap.Modal.getOrCreateInstance(modalElement).show();
    await pendingHebrew;
    if (epoch !== quickModalEpoch) {
        return;
    }
    setQuickEventModalMode(false);
}

async function openEditEventModal(eventId, occurrenceDate) {
    const modalElement = document.getElementById('quickEventModal');
    if (!modalElement) {
        return;
    }
    const epoch = ++quickModalEpoch;

    try {
        const url = occurrenceDate
            ? `/api/events/${eventId}?occurrence_date=${encodeURIComponent(occurrenceDate)}`
            : `/api/events/${eventId}`;
        const response = await fetch(url);
        if (!response.ok) {
            alert('לא ניתן לטעון את האירוע');
            return;
        }

        const event = await response.json();
        const series = event.series || null;
        quickOccurrenceSnapshot = series ? { ...event } : null;
        quickSeriesSnapshot = series;
        await fillQuickEventForm(event, { keepScope: Boolean(series) });
        if (epoch !== quickModalEpoch) {
            return;
        }
        if (series) {
            setRecurrenceScopeVisible(true, 'occurrence');
        }
        setQuickEventModalMode(true);
        const fromGoogle = typeof isGoogleEvent === 'function' && isGoogleEvent(event);
        setQuickEventReadonly(fromGoogle);
        bootstrap.Modal.getOrCreateInstance(modalElement).show();
    } catch (error) {
        console.error('Error loading event for edit:', error);
        alert('לא ניתן לטעון את האירוע');
    }
}

function initQuickEventModal() {
    syncFullEventFormSwitch();
    if (!initQuickEventModal._boundFullForm) {
        document.addEventListener('change', (event) => {
            const input = event.target.closest('[data-full-form-switch]');
            if (!input) {
                return;
            }
            setPrefersFullEventForm(input.checked);
        });
        initQuickEventModal._boundFullForm = true;
    }
    const modalElement = document.getElementById('quickEventModal');
    const quickForm = document.getElementById('quickEventForm');
    if (!modalElement || !quickForm) {
        return;
    }

    populateQuickHourOptions();
    if (typeof initReminderFields === 'function') {
        initReminderFields();
    }
    if (typeof initQuickShiftFields === 'function') {
        initQuickShiftFields();
    }
    const markDirty = () => {
        if (!quickEventFormMute) {
            quickEventFormDirty = true;
        }
    };
    quickForm.addEventListener('input', markDirty);
    quickForm.addEventListener('change', markDirty);
    modalElement.addEventListener('click', (event) => {
        if (!quickEventFormMute && event.target.closest('.quick-color-swatch, .quick-shift-pick')) {
            quickEventFormDirty = true;
        }
    });

    document.getElementById('quick_delete_btn')?.addEventListener('click', () => {
        deleteFromQuickEventModal();
    });

    document.getElementById('quick_advanced_toggle')?.addEventListener('click', () => {
        setQuickAdvancedOpen(!isQuickAdvancedOpen());
    });

    if (window.visualViewport) {
        window.visualViewport.addEventListener('resize', syncQuickModalToVisualViewport);
        window.visualViewport.addEventListener('scroll', syncQuickModalToVisualViewport);
    }
    window.addEventListener('resize', syncQuickModalToVisualViewport);

    // אחרי סיום הפתיחה של Bootstrap — פוקוס יציב על הכותרת
    modalElement.addEventListener('shown.bs.modal', () => {
        syncQuickModalToVisualViewport();
        requestAnimationFrame(() => {
            syncQuickModalToVisualViewport();
            const titleInput = document.getElementById('quick_title');
            if (titleInput) {
                titleInput.focus({ preventScroll: true });
            }
        });
    });

    modalElement.addEventListener('hidden.bs.modal', () => {
        const epochAtClose = quickModalEpoch;
        clearQuickModalViewportPin();
        // סגירה ואז פתיחה מיידית: אל תאפסו טופס שכבר נפתח מחדש
        requestAnimationFrame(() => {
            if (modalElement.classList.contains('show') || epochAtClose !== quickModalEpoch) {
                return;
            }
            setQuickEventReadonly(false);
            fillQuickEventForm();
            setQuickEventModalMode(false);
        });
    });

    const calendarRoot = document.getElementById('calendar-stream');
    if (calendarRoot) {
        // לחיצה בודדת פותחת עריכה (בטלפון אין דאבל-קליק). ההשהיה מבטלת את עצמה בדאבל-קליק
        // כדי ש-smoke_ui לא ימשוך את האירוע שלוש פעמים.
        let tapTimer = null;
        calendarRoot.addEventListener('click', (event) => {
            const cell = event.target.closest('td[data-date]');
            const compact = typeof isCompactCalendar === 'function' && isCompactCalendar();
            const desktopAgenda = typeof isDesktopAgenda === 'function' && isDesktopAgenda();
            // בטלפון כל לחיצה על היום (כולל צ'יפ ו-"+N") רק בוחרת אותו. הוספה: "הוסף" בפאנל.
            // בדסקטופ לחיצה על היום בוחרת אותו בפאנל; לחיצה על אירוע ממשיכה לעריכה.
            if (cell && (compact || desktopAgenda)) {
                // בלי גלילה: הזזת השורה בין שני הקליקים של דאבל-קליק מפספסת את הצ'יפ
                selectAgendaDay(cell.getAttribute('data-date'));
            }
            if (cell && compact) {
                return;
            }
            const eventItem = event.target.closest('.event-item[data-event-id]');
            if (eventItem) {
                const eventId = eventItem.getAttribute('data-event-id');
                const occurrenceDate = eventItem.getAttribute('data-occurrence-date');
                clearTimeout(tapTimer);
                tapTimer = setTimeout(() => openEditEventModal(eventId, occurrenceDate), 280);
                return;
            }
            if (!window.matchMedia('(pointer: coarse)').matches) {
                return;
            }
            if (!cell) {
                return;
            }
            openQuickEventModal(cell.getAttribute('data-date'));
        });

        calendarRoot.addEventListener('dblclick', (event) => {
            clearTimeout(tapTimer);
            if (typeof isCompactCalendar === 'function'
                && isCompactCalendar()
                && !event.target.closest('.event-item')) {
                return;
            }
            const eventItem = event.target.closest('.event-item[data-event-id]');
            if (eventItem) {
                event.stopPropagation();
                openEditEventModal(
                    eventItem.getAttribute('data-event-id'),
                    eventItem.getAttribute('data-occurrence-date')
                );
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

    ['quick_hebrew_day', 'quick_hebrew_month', 'quick_hebrew_year'].forEach((id) => {
        document.getElementById(id)?.addEventListener('change', () => onHebrewPickerChange('start'));
    });
    ['quick_end_hebrew_day', 'quick_end_hebrew_month', 'quick_end_hebrew_year'].forEach((id) => {
        document.getElementById(id)?.addEventListener('change', () => onHebrewPickerChange('end'));
    });

    const endToggle = document.getElementById('quick_end_toggle');
    if (endToggle) {
        endToggle.addEventListener('click', () => {
            const wrap = document.querySelector('#quickEventModal .quick-end-wrap');
            const endInput = document.getElementById('quick_end_date');
            if (wrap?.classList.contains('is-open')) {
                if (endInput) {
                    endInput.value = '';
                }
                setEndDateOpen(false);
                return;
            }
            setEndDateOpen(true);
            endInput?.focus();
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
            noteDateEntry('gregorian');
            const startDate = quickGregorianDate.value;
            syncEndDateMin(startDate, document.getElementById('quick_end_date'));
            await fillHebrewDateFromGregorian(startDate, 'start');
            const endValue = document.getElementById('quick_end_date')?.value;
            if (endValue) {
                await fillHebrewDateFromGregorian(endValue, 'end');
            } else if (startDate) {
                await fillHebrewDateFromGregorian(startDate, 'end');
            }
            const isEdit = Boolean(document.getElementById('quick_event_id').value);
            setQuickEventModalMode(isEdit);
        });
    }

    const recurrenceFreq = document.getElementById('quick_recurrence_freq');
    const recurrenceMode = document.getElementById('quick_recurrence_end_mode');
    if (recurrenceFreq) {
        recurrenceFreq.addEventListener('change', syncRecurrenceControls);
    }
    document.getElementById('quick_recurrence_calendar')?.addEventListener('change', () => {
        recurrenceCalendarTouched = true;
    });
    if (recurrenceMode) {
        recurrenceMode.addEventListener('change', syncRecurrenceControls);
    }
    document.getElementById('quick_recurrence_scope')?.addEventListener('change', () => {
        const scope = currentEditScope();
        const source = scope === 'all' ? quickSeriesSnapshot : quickOccurrenceSnapshot;
        if (source) {
            fillQuickEventForm(source, { keepScope: true });
            setRecurrenceScopeVisible(true, scope);
        } else {
            syncRecurrenceControls();
        }
    });

    const quickEndDate = document.getElementById('quick_end_date');
    if (quickEndDate) {
        // אם בכל זאת הוקלד תאריך לא תקין ידנית — מנקים מיד
        quickEndDate.addEventListener('change', async () => {
            const startDate = document.getElementById('quick_gregorian_date').value;
            syncEndDateMin(startDate, quickEndDate);
            if (quickEndDate.value) {
                await fillHebrewDateFromGregorian(quickEndDate.value, 'end');
            } else if (startDate) {
                await fillHebrewDateFromGregorian(startDate, 'end');
            }
        });
    }

    quickForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        if (quickForm.classList.contains('is-gcal-readonly')) {
            return;
        }

        if (typeof shiftUiState !== 'undefined' && shiftUiState.quickShiftFill) {
            await shiftUiState.quickShiftFill;
        }

        // ניסיון אחרון לחלץ שעה מהכותרת לפני שמירה
        applyTimeFromTitlePrefix(document.getElementById('quick_title').value);

        const eventData = getQuickEventFormData();
        if (eventData.reminders === null) {
            return;
        }
        if (eventData.recurrence_freq && eventData.recurrence_count !== null) {
            if (!Number.isInteger(eventData.recurrence_count) || eventData.recurrence_count < 1) {
                alert('מספר הפעמים חייב להיות שלם וחיובי');
                return;
            }
        }
        if (eventData.recurrence_freq && document.getElementById('quick_recurrence_end_mode')?.value === 'until' && !eventData.recurrence_until) {
            alert('חסר תאריך סיום');
            return;
        }
        if (eventData.is_shift && !String(eventData.shift_label || '').trim()) {
            alert('כתבו מה המשמרת');
            return;
        }
        if (eventData.is_shift) {
            eventData.recurrence_freq = '';
            eventData.recurrence_until = null;
            eventData.recurrence_count = null;
        }
        const scope = currentEditScope();
        if (!eventData.is_shift && scope === 'occurrence' && quickOccurrenceSnapshot?.occurrence_date) {
            eventData.scope = 'occurrence';
            eventData.occurrence_date = quickOccurrenceSnapshot.occurrence_date;
            delete eventData.reminders;
        }
        if (eventData.reminders && eventData.reminders.length && typeof maybeRequestReminderPermission === 'function') {
            maybeRequestReminderPermission();
        }
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
