// עמוד «אנשים לתזכורות». רץ רק אם #reminderPeopleApp קיים.

function initReminderPeoplePage() {
    const root = document.getElementById('reminderPeopleApp');
    const form = document.getElementById('reminderPersonForm');
    if (!root || !form) {
        return;
    }
    form.addEventListener('submit', saveReminderPerson);
    document.getElementById('reminderPersonCancel')?.addEventListener('click', resetReminderPersonForm);
    loadReminderPeople();
}

function setReminderPersonError(message) {
    const node = document.getElementById('reminderPersonError');
    if (!node) {
        return;
    }
    node.textContent = message || '';
    node.hidden = !message;
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
}

function startEditReminderPerson(person) {
    document.getElementById('reminderPersonId').value = String(person.id);
    document.getElementById('reminderPersonName').value = person.name || '';
    document.getElementById('reminderPersonChat').value = person.telegram_chat_id || '';
    document.getElementById('reminderPersonSave').textContent = 'שמירה';
    document.getElementById('reminderPersonCancel').hidden = false;
    setReminderPersonError('');
    document.getElementById('reminderPersonName').focus();
}

function renderReminderPeople(people) {
    const list = document.getElementById('reminderPeopleList');
    if (!list) {
        return;
    }
    list.replaceChildren();
    if (!people.length) {
        const empty = document.createElement('p');
        empty.className = 'text-muted mb-0';
        empty.textContent = 'עדיין אין אנשים.';
        list.append(empty);
        return;
    }
    people.forEach((person) => {
        const row = document.createElement('div');
        row.className = 'reminder-person-row';
        const text = document.createElement('div');
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
    const response = await fetch('/api/reminder-people');
    if (!response.ok) {
        setReminderPersonError('לא הצלחנו לטעון את האנשים');
        return;
    }
    renderReminderPeople(await response.json());
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
    const payload = { name, telegram_chat_id: chatId || null };
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
    resetReminderPersonForm();
    await loadReminderPeople();
    if (typeof showMessage === 'function') {
        showMessage(id ? 'האדם עודכן' : 'האדם נוסף');
    }
}

async function deleteReminderPerson(person) {
    if (!confirm(`למחוק את ${person.name}?`)) {
        return;
    }
    const response = await fetch(`/api/reminder-people/${person.id}`, { method: 'DELETE' });
    if (!response.ok) {
        setReminderPersonError('מחיקה נכשלה');
        return;
    }
    if (document.getElementById('reminderPersonId').value === String(person.id)) {
        resetReminderPersonForm();
    }
    await loadReminderPeople();
}
