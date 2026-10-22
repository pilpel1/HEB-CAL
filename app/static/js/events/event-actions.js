// יצירה/עדכון/מחיקה של אירועים מול ה-API, הודעת הצלחה, רענון התצוגות

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
            const quickForm = document.getElementById('quickEventForm');
            if (quickForm) {
                quickForm.reset();
            }
            
            showMessage('האירוע נוסף');
            await refreshEventsViews();
            return true;
        }

        const errorMessage = result.error || 'לא הצלחנו להוסיף';
        alert(errorMessage);
        return false;
    } catch (error) {
        console.error('Error creating event:', error);
        alert('לא הצלחנו להוסיף');
        return false;
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
            showMessage('האירוע עודכן');
            await refreshEventsViews();
            return true;
        }

        alert(result.error || 'לא הצלחנו לעדכן');
        return false;
    } catch (error) {
        console.error('Error updating event:', error);
        alert('לא הצלחנו לעדכן');
        return false;
    }
}

async function deleteEvent(eventId, options) {
    const series = options && options.series;
    const message = series
        ? 'למחוק את כל הסדרה?'
        : 'למחוק את האירוע?';
    if (!confirm(message)) {
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
            
            showMessage('האירוע נמחק');
            await refreshEventsViews();
        } else {
            alert('לא הצלחנו למחוק');
        }
    } catch (error) {
        console.error('Error deleting event:', error);
        alert('לא הצלחנו למחוק');
    }
}

async function deleteEventOccurrence(eventId, occurrenceDate) {
    if (!confirm('למחוק רק את המופע הזה? שאר הסדרה נשארת.')) {
        return;
    }
    try {
        const response = await fetch(
            `/api/events/${eventId}?scope=occurrence&occurrence_date=${encodeURIComponent(occurrenceDate)}`,
            { method: 'DELETE' },
        );
        const result = await response.json();
        if (result.success) {
            showMessage('המופע נמחק');
            await refreshEventsViews();
            return;
        }
        alert(result.error || 'לא הצלחנו למחוק');
    } catch (error) {
        console.error('Error deleting occurrence:', error);
        alert('לא הצלחנו למחוק');
    }
}

async function refreshEventsViews() {
    infiniteCalendar.eventsCache = null;
    infiniteCalendar.eventsFrom = null;
    infiniteCalendar.eventsTo = null;

    if (isInfiniteCalendarPage()) {
        await repaintInfiniteCalendarEvents();
    }

    // loadAllEvents מוגדר ב-events_list.html ומרנדר את טבלת האירועים
    if (typeof loadAllEvents === 'function') {
        await loadAllEvents();
    }
}

async function editEvent(eventId, occurrenceDate) {
    if (typeof openEditEventModal === 'function') {
        await openEditEventModal(eventId, occurrenceDate || null);
        return;
    }
    alert('לא ניתן לפתוח את האירוע');
}
