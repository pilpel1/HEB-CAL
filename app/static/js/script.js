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

async function updateCalendar() {
    const calendarBody = document.getElementById('calendar-body');
    if (!calendarBody) return; // אם אנחנו לא בדף הראשי

    try {
        const response = await fetch(`/api/calendar/${currentDate.getFullYear()}/${currentDate.getMonth() + 1}`);
        const data = await response.json();
        
        // עדכון כותרת החודש
        const monthTitle = document.getElementById('current-month');
        monthTitle.textContent = `${data.month_name} ${currentDate.getFullYear()} | ${data.hebrew_months.join(' ')} ${data.hebrew_year}`;
        
        // ניקוי הלוח
        calendarBody.innerHTML = '';
        
        // יבלת התאריך הנוכחי
        const today = new Date();
        const isCurrentMonth = today.getMonth() === currentDate.getMonth() && 
                             today.getFullYear() === currentDate.getFullYear();
        
        // יצירת שורות הלוח
        let currentRow;
        for (let i = 0; i < data.calendar.length; i++) {
            if (i % 7 === 0) {
                currentRow = document.createElement('tr');
                calendarBody.appendChild(currentRow);
            }
            
            const cell = document.createElement('td');
            const day = data.calendar[i];
            
            if (day.gregorian_day) {
                // בדיקה אם זה היום הנוכחי
                if (isCurrentMonth && day.gregorian_day === today.getDate()) {
                    cell.classList.add('current-day');
                }

                // הוספת data-date לתא
                const cellDate = new Date(currentDate.getFullYear(), currentDate.getMonth(), day.gregorian_day);
                cell.setAttribute('data-date', formatDate(cellDate));

                const isFirstOfMonth = day.gregorian_day === 1;
                const gregorianDate = isFirstOfMonth ? 
                    `${day.gregorian_day} ${getShortMonthName(currentDate.getMonth())}` : 
                    day.gregorian_day;
                
                cell.innerHTML = `
                    <div class="day-cell">
                        <div class="dates-container">
                            <span class="hebrew-date">${day.is_hebrew_month_start ? 
                                `${get_hebrew_day(day.hebrew_day)} ${day.hebrew_month}` : 
                                get_hebrew_day(day.hebrew_day)}</span>
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

        // הוספת טעינת אירועים לאחר עדכון הלוח
        await loadAndDisplayEvents();
    } catch (error) {
        console.error('Error rendering calendar:', error);
    }
}

function previousMonth() {
    currentDate.setMonth(currentDate.getMonth() - 1);
    updateCalendar();
}

function nextMonth() {
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
            const form = document.getElementById('eventForm');
            if (form) {
                form.reset();
            }

            const quickForm = document.getElementById('quickEventForm');
            if (quickForm) {
                quickForm.reset();
            }
            
            showMessage('האירוע נוסף בהצלחה');
            
            if (document.getElementById('calendar-body')) {
                await loadAndDisplayEvents();
            }

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

    // "ח אב 5786" -> "ח אב"
    return hebrewDate.replace(/\s+\d{3,4}$/, '').trim();
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
    const calendarBody = document.getElementById('calendar-body');
    const modalElement = document.getElementById('quickEventModal');
    const quickForm = document.getElementById('quickEventForm');
    if (!calendarBody || !modalElement || !quickForm) {
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

    calendarBody.addEventListener('dblclick', (event) => {
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

            if (document.getElementById('calendar-body')) {
                await loadAndDisplayEvents();
            }

            await updateEventsList();
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
            await updateEventsList();
        } else {
            alert('שגיאה במחיקת האירוע');
        }
    } catch (error) {
        console.error('Error deleting event:', error);
        alert('שגיאה במחיקת האירוע');
    }
}

// המרת תאריך לועזי לעברי בטופס הוספת אירוע
const gregorianDateInput = document.getElementById('gregorian_date');
const endDateInput = document.getElementById('end_date');
if (gregorianDateInput) {
    syncEndDateMin(gregorianDateInput.value, endDateInput);
    gregorianDateInput.addEventListener('change', async function() {
        syncEndDateMin(this.value, endDateInput);
        try {
            const response = await fetch(`/api/hebrew-date/${this.value}`);
            const data = await response.json();
            document.getElementById('hebrew_date').value = data.hebrew_date;
        } catch (error) {
            console.error('Error converting date:', error);
        }
    });
}

// טיפול בטופס הוספת אירוע
const eventForm = document.getElementById('eventForm');
if (eventForm) {
    eventForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        
        const eventData = {
            title: document.getElementById('title').value,
            gregorian_date: document.getElementById('gregorian_date').value,
            hebrew_date: document.getElementById('hebrew_date').value,
            time: document.getElementById('time').value || null,
            description: document.getElementById('description').value || '',
            end_date: document.getElementById('end_date').value || null,
            color: document.getElementById('color').value || null,
        };

        if (!assertEndDateNotBeforeStart(eventData.gregorian_date, eventData.end_date)) {
            return;
        }

        await createEvent(eventData);
    });
}

// עדכון רשימת האירועים
async function updateEventsList() {
    const eventsTable = document.getElementById('eventsTable');
    if (!eventsTable) return; // אם אנחנו לא בדף רשימת האירועים

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
        <tr id="edit-form-${event.id}" class="edit-form-row" style="display: none;">
            <td colspan="6">
                <div class="edit-event-form p-3">
                    <form onsubmit="return saveEvent(event, ${event.id})">
                        <div class="mb-3">
                            <label for="title-${event.id}" class="form-label">כותרת</label>
                            <input type="text" class="form-control" id="title-${event.id}" value="${event.title}" required>
                        </div>
                        <div class="row align-items-end">
                            <div class="col mb-3">
                                <div class="input-wrapper">
                                    <label for="gregorian_date-${event.id}" class="form-label">תאריך לועזי</label>
                                    <input type="date" class="form-control" id="gregorian_date-${event.id}" 
                                        value="${event.gregorian_date}" onchange="updateHebrewDate(${event.id})" required>
                                </div>
                            </div>
                            <div class="col mb-3">
                                <div class="input-wrapper">
                                    <label for="hebrew_date-${event.id}" class="form-label">תאריך עברי</label>
                                    <input type="text" class="form-control" id="hebrew_date-${event.id}" 
                                        value="${event.hebrew_date}" readonly>
                                </div>
                            </div>
                            <div class="col mb-3">
                                <div class="input-wrapper">
                                    <label for="time-${event.id}" class="form-label">שעה</label>
                                    <input type="time" class="form-control" id="time-${event.id}" 
                                        value="${event.time || ''}">
                                </div>
                            </div>
                            <div class="col mb-3">
                                <div class="input-wrapper">
                                    <label for="end_date-${event.id}" class="form-label">תאריך סיום</label>
                                    <input type="date" class="form-control" id="end_date-${event.id}" 
                                        value="${event.end_date || ''}" min="${event.gregorian_date}">
                                </div>
                            </div>
                            <div class="col mb-3">
                                <div class="input-wrapper">
                                    <label for="color-${event.id}" class="form-label">צבע האירוע</label>
                                    <select class="form-control" id="color-${event.id}">
                                        <option value="">ללא צבע</option>
                                        <option value="cyan" ${event.color === 'cyan' ? 'selected' : ''}>ציאן</option>
                                        <option value="yellow" ${event.color === 'yellow' ? 'selected' : ''}>צהוב</option>
                                        <option value="orange" ${event.color === 'orange' ? 'selected' : ''}>כתום</option>
                                        <option value="green" ${event.color === 'green' ? 'selected' : ''}>ירוק</option>
                                    </select>
                                </div>
                            </div>
                        </div>
                        <div class="mb-3">
                            <label for="description-${event.id}" class="form-label">תיאור</label>
                            <textarea class="form-control" id="description-${event.id}">${event.description || ''}</textarea>
                        </div>
                        <div class="text-end">
                            <button type="button" class="btn btn-secondary" onclick="cancelEdit(${event.id})">ביטול</button>
                            <button type="submit" class="btn btn-primary">שמור שינויים</button>
                        </div>
                    </form>
                </div>
            </td>
        </tr>
    `).join('');
}

async function editEvent(eventId) {
    const formRow = document.getElementById(`edit-form-${eventId}`);
    
    // אם הטופס כבר מוצג, נסגור אותו
    if (formRow.style.display === 'table-row') {
        formRow.style.display = 'none';
        return;
    }
    
    // הסתרת כל הטפסים הפתוחים
    document.querySelectorAll('.edit-form-row').forEach(row => {
        row.style.display = 'none';
    });
    
    // הצגת הטופס הנבחר
    formRow.style.display = 'table-row';
}

function cancelEdit(eventId) {
    const formRow = document.getElementById(`edit-form-${eventId}`);
    formRow.style.display = 'none';
}

async function updateHebrewDate(eventId) {
    const gregorianDate = document.getElementById(`gregorian_date-${eventId}`).value;
    syncEndDateMin(gregorianDate, document.getElementById(`end_date-${eventId}`));
    try {
        const response = await fetch(`/api/hebrew-date/${gregorianDate}`);
        const data = await response.json();
        document.getElementById(`hebrew_date-${eventId}`).value = data.hebrew_date;
    } catch (error) {
        console.error('Error converting date:', error);
    }
}

async function saveEvent(e, eventId) {
    e.preventDefault();
    
    const eventData = {
        title: document.getElementById(`title-${eventId}`).value,
        gregorian_date: document.getElementById(`gregorian_date-${eventId}`).value,
        hebrew_date: document.getElementById(`hebrew_date-${eventId}`).value,
        time: document.getElementById(`time-${eventId}`).value || null,
        description: document.getElementById(`description-${eventId}`).value || '',
        end_date: document.getElementById(`end_date-${eventId}`).value || null,
        color: document.getElementById(`color-${eventId}`).value || null
    };

    const endInput = document.getElementById(`end_date-${eventId}`);
    syncEndDateMin(eventData.gregorian_date, endInput);
    if (!assertEndDateNotBeforeStart(eventData.gregorian_date, eventData.end_date, endInput)) {
        return false;
    }

    try {
        const response = await fetch(`/api/events/${eventId}`, {
            method: 'PUT',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(eventData)
        });
        
        const result = await response.json();
        if (result.success) {
            showMessage('האירוע עודכן בהצלחה');
            await updateEventsList();
            
            // הסתרת טופס העריכה
            const formRow = document.getElementById(`edit-form-${eventId}`);
            if (formRow) {
                formRow.style.display = 'none';
            }
        } else {
            alert('שגיאה בעדכון האירוע');
        }
    } catch (error) {
        console.error('Error updating event:', error);
        alert('שגיאה בעדכון האירוע');
    }
    
    return false;
}

// אתחול הדף
document.addEventListener('DOMContentLoaded', async () => {
    // עדכון לוח השנה אם אנחנו בדף הראשי
    const calendarBody = document.getElementById('calendar-body');
    if (calendarBody) {
        initQuickEventModal();
        await updateCalendar();
    }
    
    // עדכון רשימת האירועים אם אנחנו בדף הרשימה
    const eventsTable = document.getElementById('eventsTable');
    if (eventsTable) {
        await updateEventsList();
    }
});

function goToToday() {
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
    const date = new Date(dateStr);
    const start = new Date(startStr);
    const end = endStr ? new Date(endStr) : start;
    
    // איפוס השעה בכל התאריכים להשוואה נכונה
    date.setHours(0, 0, 0, 0);
    start.setHours(0, 0, 0, 0);
    end.setHours(0, 0, 0, 0);
    
    return date >= start && date <= end;
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

// פונקציה לטעינת והצגת אירועים בלוח
async function loadAndDisplayEvents() {
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
  
