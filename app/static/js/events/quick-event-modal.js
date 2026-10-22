// מודל אירוע מהיר (הוספה/עריכה): שדות, שעה מהכותרת, צבע, חזרה, שליחה

let quickSeriesSnapshot = null;
let quickOccurrenceSnapshot = null;
let hebrewDateToken = 0;
let hebrewPickerMute = false;
let hebrewYearsPromise = null;
// השנה שאליה שייכת רשימת החודשים שעל המסך (אדר פשוט ואדר א׳ שניהם 12)
let hebrewPickerContextYear = null;
// הבורר האחרון שהמשתמש נגע בו: 'hebrew' | 'gregorian' | null
let dateEntrySource = null;
// true אחרי בחירה מפורשת של לוח החזרה, או כשעורכים אירוע שכבר חוזר
let recurrenceCalendarTouched = false;

function loadHebrewYearLabels() {
    if (!hebrewYearsPromise) {
        hebrewYearsPromise = fetch('/api/hebrew-years?from=5660&to=5820')
            .then((response) => (response.ok ? response.json() : { years: [] }))
            .then((data) => (Array.isArray(data.years) ? data.years : []))
            .catch(() => []);
    }
    return hebrewYearsPromise;
}

async function ensureHebrewYearSelect(year, label) {
    const select = document.getElementById('quick_hebrew_year');
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

function fillHebrewMonthSelect(months, selected) {
    const select = document.getElementById('quick_hebrew_month');
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

function fillHebrewDaySelect(count, selected) {
    const select = document.getElementById('quick_hebrew_day');
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

async function applyHebrewDatePayload(data, token) {
    if (!data || token !== hebrewDateToken) {
        return;
    }
    const hebrewInput = document.getElementById('quick_hebrew_date');
    if (hebrewInput && data.hebrew_date) {
        hebrewInput.value = data.hebrew_date;
    }
    await ensureHebrewYearSelect(data.year, data.year_label);
    if (token !== hebrewDateToken) {
        return;
    }
    hebrewPickerMute = true;
    try {
        fillHebrewMonthSelect(data.months, data.month);
        fillHebrewDaySelect(data.days_in_month, data.day);
        if (data.year) {
            const yearSelect = document.getElementById('quick_hebrew_year');
            if (yearSelect && [...yearSelect.options].some((option) => option.value === String(data.year))) {
                yearSelect.value = String(data.year);
            }
        }
        if (Array.isArray(data.months) && data.months.length) {
            hebrewPickerContextYear = data.year || null;
        }
    } finally {
        hebrewPickerMute = false;
    }
}

function gregorianFromHebrewUrl(year, month, day) {
    const params = new URLSearchParams({
        year: String(year),
        month: String(month),
        day: String(day),
    });
    if (hebrewPickerContextYear && String(hebrewPickerContextYear) !== String(year)) {
        params.set('from_year', String(hebrewPickerContextYear));
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

async function fillHebrewDateFromGregorian(gregorianValue, hebrewInputId) {
    if (!gregorianValue) {
        return;
    }
    const token = ++hebrewDateToken;
    try {
        const response = await fetch(`/api/hebrew-date/${gregorianValue}`);
        const data = await response.json();
        if (!response.ok || token !== hebrewDateToken) {
            return;
        }
        const hebrewInput = document.getElementById(hebrewInputId);
        if (hebrewInput && data.hebrew_date && hebrewInputId !== 'quick_hebrew_date') {
            hebrewInput.value = data.hebrew_date;
        }
        await applyHebrewDatePayload(data, token);
        if (token === hebrewDateToken) {
            refreshQuickModalTitle();
        }
    } catch (error) {
        console.error('Error converting date:', error);
    }
}

async function onHebrewPickerChange() {
    if (hebrewPickerMute) {
        return;
    }
    noteDateEntry('hebrew');
    const year = document.getElementById('quick_hebrew_year')?.value;
    const month = document.getElementById('quick_hebrew_month')?.value;
    const day = document.getElementById('quick_hebrew_day')?.value;
    if (!year || !month || !day) {
        return;
    }
    const token = ++hebrewDateToken;
    try {
        const response = await fetch(gregorianFromHebrewUrl(year, month, day));
        const data = await response.json();
        if (!response.ok || token !== hebrewDateToken) {
            return;
        }
        const gregorian = document.getElementById('quick_gregorian_date');
        if (gregorian && data.gregorian_date) {
            gregorian.value = data.gregorian_date;
            syncEndDateMin(data.gregorian_date, document.getElementById('quick_end_date'));
        }
        await applyHebrewDatePayload(data, token);
        if (token === hebrewDateToken) {
            refreshQuickModalTitle();
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
    const toggle = document.getElementById('quick_end_toggle');
    if (!wrap || !toggle) {
        return;
    }
    wrap.classList.toggle('is-open', Boolean(isOpen));
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

function fillQuickEventForm(eventData = {}, options = {}) {
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
    if (eventData.gregorian_date) {
        return fillHebrewDateFromGregorian(eventData.gregorian_date, 'quick_hebrew_date');
    }
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

    const form = document.getElementById('quickEventForm');
    if (form) {
        form.reset();
    }

    const pendingHebrew = fillQuickEventForm({ gregorian_date: dateStr });
    // אחרי reset — מוודאים שוב שה-min על תאריך הסיום ננעל לתאריך ההתחלה
    syncEndDateMin(dateStr, document.getElementById('quick_end_date'));
    await pendingHebrew;
    setQuickEventModalMode(false);

    bootstrap.Modal.getOrCreateInstance(modalElement).show();
}

async function openEditEventModal(eventId, occurrenceDate) {
    const modalElement = document.getElementById('quickEventModal');
    if (!modalElement) {
        return;
    }

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
        if (series) {
            setRecurrenceScopeVisible(true, 'occurrence');
        }
        setQuickEventModalMode(true);
        bootstrap.Modal.getOrCreateInstance(modalElement).show();
    } catch (error) {
        console.error('Error loading event for edit:', error);
        alert('לא ניתן לטעון את האירוע');
    }
}

function initQuickEventModal() {
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
        document.getElementById(id)?.addEventListener('change', onHebrewPickerChange);
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
            await fillHebrewDateFromGregorian(startDate, 'quick_hebrew_date');
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
        quickEndDate.addEventListener('change', () => {
            const startDate = document.getElementById('quick_gregorian_date').value;
            syncEndDateMin(startDate, quickEndDate);
        });
    }

    quickForm.addEventListener('submit', async (e) => {
        e.preventDefault();

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
