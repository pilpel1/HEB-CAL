// עמוד «אנשים לתזכורות». רץ רק אם #reminderPeopleApp קיים.

function initReminderPeoplePage() {
    const root = document.getElementById('reminderPeopleApp');
    const form = document.getElementById('reminderPersonForm');
    if (!root || !form) {
        return;
    }
    form.addEventListener('submit', saveReminderPerson);
    document.getElementById('reminderPersonCancel')?.addEventListener('click', resetReminderPersonForm);
    initChatIdHelp();
    loadReminderPeople();
}

function placeChatIdHelp() {
    const button = document.getElementById('chatIdHelpBtn');
    const pop = document.getElementById('chatIdHelp');
    if (!button || !pop || pop.hidden) {
        return;
    }
    const margin = 8;
    const rect = button.getBoundingClientRect();
    const width = pop.offsetWidth;
    const height = pop.offsetHeight;
    let top = rect.bottom + margin;
    if (top + height > window.innerHeight - margin) {
        top = rect.top - margin - height;
    }
    if (top < margin) {
        top = margin;
    }
    let left = rect.right - width;
    if (left < margin) {
        left = margin;
    }
    if (left + width > window.innerWidth - margin) {
        left = window.innerWidth - margin - width;
    }
    pop.style.top = `${Math.round(top)}px`;
    pop.style.left = `${Math.round(left)}px`;
}

function initChatIdHelp() {
    const button = document.getElementById('chatIdHelpBtn');
    const pop = document.getElementById('chatIdHelp');
    if (!button || !pop) {
        return;
    }
    const close = () => {
        pop.hidden = true;
        button.setAttribute('aria-expanded', 'false');
    };
    button.addEventListener('click', (event) => {
        event.preventDefault();
        event.stopPropagation();
        const open = pop.hidden;
        pop.hidden = !open;
        button.setAttribute('aria-expanded', open ? 'true' : 'false');
        if (open) {
            placeChatIdHelp();
        }
    });
    document.addEventListener('click', (event) => {
        if (pop.hidden) {
            return;
        }
        if (pop.contains(event.target) || button.contains(event.target)) {
            return;
        }
        close();
    });
    document.addEventListener('keydown', (event) => {
        if (event.key === 'Escape' && !pop.hidden) {
            close();
            button.focus();
        }
    });
    window.addEventListener('resize', placeChatIdHelp);
    window.addEventListener('scroll', placeChatIdHelp, true);
}

function setReminderPersonError(message) {
    const node = document.getElementById('reminderPersonError');
    if (!node) {
        return;
    }
    node.textContent = message || '';
    node.hidden = !message;
}

function setReminderPersonSaved(visible) {
    const node = document.getElementById('reminderPersonSaved');
    if (!node) {
        return;
    }
    node.hidden = !visible;
}

function setReminderPersonContext(person) {
    const node = document.getElementById('reminderPersonContext');
    if (!node) {
        return;
    }
    if (person && person.id) {
        node.textContent = `עריכת ${person.name || 'אדם'} לתזכורות`;
        node.classList.add('is-existing');
        return;
    }
    node.textContent = 'אדם חדש לתזכורות';
    node.classList.remove('is-existing');
}

function resetReminderPersonForm() {
    const form = document.getElementById('reminderPersonForm');
    if (form) {
        form.reset();
    }
    const idInput = document.getElementById('reminderPersonId');
    if (idInput) {
        idInput.value = '';
    }
    const save = document.getElementById('reminderPersonSave');
    if (save) {
        save.textContent = 'הוספה';
    }
    const cancel = document.getElementById('reminderPersonCancel');
    if (cancel) {
        cancel.hidden = true;
    }
    setReminderPersonError('');
    setReminderPersonSaved(false);
    setReminderPersonContext(null);
}

function startEditReminderPerson(person) {
    document.getElementById('reminderPersonId').value = String(person.id);
    document.getElementById('reminderPersonName').value = person.name || '';
    document.getElementById('reminderPersonChat').value = person.telegram_chat_id || '';
    document.getElementById('reminderPersonSave').textContent = 'שמירה';
    document.getElementById('reminderPersonCancel').hidden = false;
    setReminderPersonError('');
    setReminderPersonSaved(false);
    setReminderPersonContext(person);
    document.getElementById('reminderPersonName').focus();
    highlightReminderPersonRow(person.id);
}

function highlightReminderPersonRow(personId) {
    document.querySelectorAll('#reminderPeopleList .reminder-person-row').forEach((row) => {
        row.classList.toggle('is-editing', String(row.dataset.personId) === String(personId || ''));
    });
}

function renderReminderPeople(people) {
    const list = document.getElementById('reminderPeopleList');
    if (!list) {
        return;
    }
    const reminderPeople = (people || []).filter((person) => person.receives_reminders);
    list.replaceChildren();
    if (!reminderPeople.length) {
        const empty = document.createElement('p');
        empty.className = 'text-muted mb-0';
        empty.textContent = 'עדיין אין אנשים לתזכורות.';
        list.append(empty);
        return;
    }
    const editingId = document.getElementById('reminderPersonId')?.value;
    reminderPeople.forEach((person) => {
        const row = document.createElement('div');
        row.className = 'reminder-person-row';
        row.dataset.personId = String(person.id);
        if (editingId && String(person.id) === String(editingId)) {
            row.classList.add('is-editing');
        }
        const text = document.createElement('div');
        text.className = 'reminder-person-text';
        const name = document.createElement('div');
        name.textContent = person.name;
        const chat = document.createElement('div');
        chat.className = 'reminder-person-chat text-muted small';
        chat.textContent = person.telegram_chat_id || 'בלי מזהה צ׳אט';
        text.append(name, chat);
        const actions = document.createElement('div');
        actions.className = 'd-flex gap-2';
        const edit = document.createElement('button');
        edit.type = 'button';
        edit.className = 'btn btn-outline-primary btn-sm';
        edit.textContent = 'עריכה';
        edit.addEventListener('click', () => startEditReminderPerson(person));
        const remove = document.createElement('button');
        remove.type = 'button';
        remove.className = 'btn btn-outline-danger btn-sm';
        remove.textContent = 'מחיקה';
        remove.addEventListener('click', () => deleteReminderPerson(person));
        actions.append(edit, remove);
        row.append(text, actions);
        list.append(row);
    });
}

async function loadReminderPeople() {
    if (typeof ensureShiftSettings === 'function') {
        await ensureShiftSettings();
    }
    const response = await fetch('/api/reminder-people');
    if (!response.ok) {
        setReminderPersonError('לא הצלחנו לטעון את האנשים');
        return;
    }
    const people = await response.json();
    const list = Array.isArray(people) ? people : [];
    if (typeof noteShiftPeople === 'function') {
        noteShiftPeople(list);
    }
    renderReminderPeople(list);
    if (typeof renderShiftPeopleList === 'function') {
        renderShiftPeopleList(list);
    }
    if (typeof fillShiftPersonSource === 'function') {
        fillShiftPersonSource(list);
    }
}

function cleanChatId(value) {
    const text = (value || '').trim();
    if (!text) {
        return '';
    }
    if (!/^-?\d{1,20}$/.test(text)) {
        return null;
    }
    return text;
}

async function saveReminderPerson(event) {
    event.preventDefault();
    const name = document.getElementById('reminderPersonName').value.trim();
    const chatId = cleanChatId(document.getElementById('reminderPersonChat').value);
    if (!name) {
        setReminderPersonError('חסר שם');
        return;
    }
    if (chatId === null) {
        setReminderPersonError('מזהה צ׳אט חייב להיות מספר');
        return;
    }
    const id = document.getElementById('reminderPersonId').value;
    const payload = {
        name,
        telegram_chat_id: chatId || null,
        receives_reminders: true,
    }
    const response = await fetch(id ? `/api/reminder-people/${id}` : '/api/reminder-people', {
        method: id ? 'PUT' : 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
    });
    const result = await response.json().catch(() => ({}));
    if (!response.ok) {
        setReminderPersonError(result.error || 'שמירה נכשלה');
        return;
    }
    setReminderPersonSaved(true);
    if (id) {
        startEditReminderPerson(result);
    } else {
        resetReminderPersonForm();
    }
    await loadReminderPeople();
    if (id) {
        highlightReminderPersonRow(result.id);
        setReminderPersonContext(result);
    }
    if (typeof showMessage === 'function') {
        showMessage('נשמר');
    }
}

async function deleteReminderPerson(person) {
    const alsoShifts = Boolean(person.works_shifts);
    const question = alsoShifts
        ? `להסיר את ${person.name} מאנשי התזכורות? המשמרות יישארו.`
        : `למחוק את ${person.name}?`;
    if (!confirm(question)) {
        return;
    }
    let response;
    if (alsoShifts) {
        response = await fetch(`/api/reminder-people/${person.id}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                name: person.name,
                telegram_chat_id: person.telegram_chat_id || null,
                color: person.color,
                shift_allowed: person.shift_allowed,
                works_shifts: true,
                receives_reminders: false,
            }),
        });
    } else {
        response = await fetch(`/api/reminder-people/${person.id}`, { method: 'DELETE' });
    }
    if (!response.ok) {
        setReminderPersonError('מחיקה נכשלה');
        return;
    }
    if (document.getElementById('reminderPersonId').value === String(person.id)) {
        resetReminderPersonForm();
    }
    await loadReminderPeople();
}
