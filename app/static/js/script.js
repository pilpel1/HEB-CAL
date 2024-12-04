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
                    <div class="dates-container">
                        <span class="gregorian-date">${gregorianDate}</span>
                        <span class="hebrew-date">${day.is_hebrew_month_start ? 
                            `${get_hebrew_day(day.hebrew_day)} ${day.hebrew_month}` : 
                            get_hebrew_day(day.hebrew_day)}</span>
                    </div>
                    <div class="jewish-events-container"></div>
                    <div class="day-content"></div>`;
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
            
            showMessage('האירוע נוסף בהצלחה');
            
            if (document.getElementById('calendar-body')) {
                await loadAndDisplayEvents();
            }
        } else {
            const errorMessage = result.error || 'שגיאה בהוספת האירוע';
            alert(errorMessage);
        }
    } catch (error) {
        console.error('Error creating event:', error);
        alert('שגיאה בהוספת האירוע');
    }
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
            await updateEventsList();
        } else {
            alert('שגיאה בעדכון האירוע');
        }
    } catch (error) {
        console.error('Error updating event:', error);
        alert('שגיאה בעדכון האירוע');
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
if (gregorianDateInput) {
    gregorianDateInput.addEventListener('change', async function() {
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
                                        value="${event.end_date || ''}">
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
    // הסתרת כל הטפסים הפתוחים
    document.querySelectorAll('.edit-form-row').forEach(row => {
        row.style.display = 'none';
    });
    
    // הצגת הטופס הנבחר
    const formRow = document.getElementById(`edit-form-${eventId}`);
    formRow.style.display = 'table-row';
}

function cancelEdit(eventId) {
    const formRow = document.getElementById(`edit-form-${eventId}`);
    formRow.style.display = 'none';
}

async function updateHebrewDate(eventId) {
    const gregorianDate = document.getElementById(`gregorian_date-${eventId}`).value;
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

// פונקציה לטעינת והצגת אירועים בלוח
async function loadAndDisplayEvents() {
    try {
        // טעינת כל האירועים
        const events = await loadEvents();
        
        // עבור על כל התאים בלוח
        const cells = document.querySelectorAll('#calendar-body td[data-date]');
        for (const cell of cells) {
            const date = cell.getAttribute('data-date');
            
            // טעינת אירועים יהודיים לתאריך
            const response = await fetch(`/api/jewish-events/${date}`);
            if (!response.ok) {
                console.error(`Error loading Jewish events for ${date}:`, await response.text());
                continue;
            }
            const jewishEvents = await response.json();
            
            // הצגת אירועים יהודיים
            const jewishContainer = cell.querySelector('.jewish-events-container');
            if (jewishEvents && jewishEvents.length > 0) {
                // מיון האירועים לפי סדר: פרשה, חג, צום
                const sortedEvents = jewishEvents.sort((a, b) => {
                    const order = { parasha: 1, holiday: 2, fast: 3 };
                    return order[a.type] - order[b.type];
                });
                
                jewishContainer.innerHTML = sortedEvents
                    .map(event => `<div class="${event.type}" style="color: ${event.color}">${event.name}</div>`)
                    .join('');
            } else {
                jewishContainer.innerHTML = '';
            }
            
            // סינון וקיבוץ האירועים הרגילים לתאריך זה
            const dayEvents = events.filter(event => isDateInRange(date, event.gregorian_date, event.end_date));

            // הצגת האירועים הרגילים
            const contentContainer = cell.querySelector('.day-content');
            if (dayEvents.length > 0) {
                contentContainer.innerHTML = dayEvents
                    .map(event => {
                        const timeStr = event.time ? `${event.time} - ` : '';
                        const style = event.color ? `background-color: rgba(${getColorRGBA(event.color)})` : '';
                        return `<div class="event-item" style="${style}">${timeStr}${event.title}</div>`;
                    })
                    .join('');
            } else {
                contentContainer.innerHTML = '';
            }
        }
    } catch (error) {
        console.error('Error loading events:', error);
    }
}
  
