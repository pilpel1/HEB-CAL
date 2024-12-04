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

async function loadAndDisplayEvents() {
    const events = await loadEvents();
    const cells = document.querySelectorAll('td[data-date]');
    
    cells.forEach(cell => {
        const cellDate = cell.getAttribute('data-date');
        const dayEvents = events.filter(event => event.gregorian_date === cellDate);
        
        const dayContent = cell.querySelector('.day-content');
        dayContent.innerHTML = '';
        
        dayEvents.forEach(event => {
            const eventElement = document.createElement('div');
            eventElement.className = 'event';
            if (event.color) {
                eventElement.classList.add(`event-${event.color}`);
            }
            eventElement.textContent = event.title;
            dayContent.appendChild(eventElement);
        });
    });
}

async function updateEventsList() {
    const eventsTable = document.getElementById('eventsTable');
    if (!eventsTable) return;

    const events = await loadEvents();
    eventsTable.innerHTML = '';

    events.forEach(event => {
        const row = document.createElement('tr');
        row.innerHTML = `
            <td>${event.title}</td>
            <td>${event.gregorian_date}</td>
            <td>${event.hebrew_date}</td>
            <td>${event.time || ''}</td>
            <td>${event.description || ''}</td>
            <td>
                <div class="btn-group">
                    <button class="btn btn-sm btn-primary" onclick="editEvent(${event.id})">
                        <i class="fas fa-edit"></i>
                    </button>
                    <button class="btn btn-sm btn-danger" onclick="deleteEvent(${event.id})">
                        <i class="fas fa-trash"></i>
                    </button>
                </div>
            </td>
        `;
        eventsTable.appendChild(row);
    });
}

async function editEvent(eventId) {
    const event = await getEvent(eventId);
    if (!event) return;

    const row = document.querySelector(`tr[data-event-id="${eventId}"]`);
    if (!row) return;

    const editForm = document.createElement('tr');
    editForm.className = 'edit-form-row';
    editForm.innerHTML = `
        <td colspan="6">
            <form class="edit-event-form" onsubmit="handleEditSubmit(event, ${eventId})">
                <div class="row">
                    <div class="col-md-2">
                        <input type="text" class="form-control" name="title" value="${event.title}" required>
                    </div>
                    <div class="col-md-2">
                        <input type="date" class="form-control" name="gregorian_date" value="${event.gregorian_date}" required>
                    </div>
                    <div class="col-md-2">
                        <input type="text" class="form-control" name="hebrew_date" value="${event.hebrew_date}" required>
                    </div>
                    <div class="col-md-2">
                        <input type="time" class="form-control" name="time" value="${event.time || ''}">
                    </div>
                    <div class="col-md-2">
                        <input type="text" class="form-control" name="description" value="${event.description || ''}">
                    </div>
                    <div class="col-md-2">
                        <button type="submit" class="btn btn-success">שמור</button>
                        <button type="button" class="btn btn-secondary" onclick="cancelEdit(${eventId})">בטל</button>
                    </div>
                </div>
            </form>
        </td>
    `;

    row.parentNode.insertBefore(editForm, row.nextSibling);
    row.style.display = 'none';
}

async function handleEditSubmit(e, eventId) {
    e.preventDefault();
    const form = e.target;
    const eventData = {
        title: form.title.value,
        gregorian_date: form.gregorian_date.value,
        hebrew_date: form.hebrew_date.value,
        time: form.time.value || null,
        description: form.description.value || '',
    };

    await updateEvent(eventId, eventData);
    await updateEventsList();
}

function cancelEdit(eventId) {
    const row = document.querySelector(`tr[data-event-id="${eventId}"]`);
    const editForm = row.nextElementSibling;
    row.style.display = '';
    editForm.remove();
}

// עדכון הלוח בטעינת העמוד
document.addEventListener('DOMContentLoaded', function() {
    if (document.getElementById('calendar-body')) {
        updateCalendar();
    } else if (document.getElementById('eventsTable')) {
        updateEventsList();
    }
}); 