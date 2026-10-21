// מודל אירוע מהיר (הוספה/עריכה): שדות, שעה מהכותרת, צבע, שליחה

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

    const calendarRoot = document.getElementById('calendar-stream');
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
