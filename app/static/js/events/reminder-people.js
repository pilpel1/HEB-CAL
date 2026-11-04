// עמוד «אנשים לתזכורות». רץ רק אם #reminderPeopleApp קיים.

const reminderPeopleState = {
    people: [],
    deletingId: null,
};

function normalizePersonName(name) {
    return String(name || '').trim().toLowerCase().replace(/[\s'"׳״]+/g, '');
}

function personNameEditDistance(left, right) {
    if (left === right) {
        return 0;
    }
    const rows = left.length + 1;
    const cols = right.length + 1;
    const grid = Array.from({ length: rows }, () => Array(cols).fill(0));
    for (let i = 0; i < rows; i += 1) {
        grid[i][0] = i;
    }
    for (let j = 0; j < cols; j += 1) {
        grid[0][j] = j;
    }
    for (let i = 1; i < rows; i += 1) {
        for (let j = 1; j < cols; j += 1) {
            const cost = left[i - 1] === right[j - 1] ? 0 : 1;
            grid[i][j] = Math.min(
                grid[i - 1][j] + 1,
                grid[i][j - 1] + 1,
                grid[i - 1][j - 1] + cost,
            );
        }
    }
    return grid[left.length][right.length];
}

function personNameSimilarity(left, right) {
    const a = normalizePersonName(left);
    const b = normalizePersonName(right);
    if (!a || !b) {
        return '';
    }
    if (a === b) {
        return 'exact';
    }
    if (a.length >= 2 && b.length >= 2 && (a.includes(b) || b.includes(a))) {
        return 'similar';
    }
    if (Math.min(a.length, b.length) >= 3 && Math.abs(a.length - b.length) <= 1
        && personNameEditDistance(a, b) <= 1) {
        return 'similar';
    }
    return '';
}

function telegramLinkStatus(person) {
    const chat = (person && person.telegram_chat_id) || '';
    if (chat) {
        return { linked: true, text: `מחובר לטלגרם · ${chat}` };
    }
    return { linked: false, text: 'אין קישור לטלגרם' };
}

function initReminderPeoplePage() {
    const root = document.getElementById('reminderPeopleApp');
    const form = document.getElementById('reminderPersonForm');
    if (!root || !form) {
        return;
    }
    form.addEventListener('submit', saveReminderPerson);
    document.getElementById('reminderPersonCancel')?.addEventListener('click', resetReminderPersonForm);
    document.getElementById('reminderPersonName')?.addEventListener('input', suggestSimilarReminderPerson);
    document.getElementById('reminderPersonReassignBtn')?.addEventListener('click', confirmReassignDeletePerson);
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
        node.textContent = `עריכת ${person.name || 'אדם'}`;
        node.classList.add('is-existing');
        return;
    }
    node.textContent = 'אדם חדש';
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
    hidePersonReassign();
    suggestSimilarReminderPerson();
}

function startEditReminderPerson(person) {
    document.getElementById('reminderPersonId').value = String(person.id);
    document.getElementById('reminderPersonName').value = person.name || '';
    const emailInput = document.getElementById('reminderPersonEmail');
    if (emailInput) {
        emailInput.value = person.google_email || '';
    }
    document.getElementById('reminderPersonChat').value = person.telegram_chat_id || '';
    document.getElementById('reminderPersonSave').textContent = 'שמירה';
    document.getElementById('reminderPersonCancel').hidden = false;
    setReminderPersonError('');
    setReminderPersonSaved(false);
    setReminderPersonContext(person);
    hidePersonReassign();
    document.getElementById('reminderPersonName').focus();
    highlightReminderPersonRow(person.id);
    suggestSimilarReminderPerson();
}

function highlightReminderPersonRow(personId) {
    document.querySelectorAll('#reminderPeopleList .reminder-person-row').forEach((row) => {
        row.classList.toggle('is-editing', String(row.dataset.personId) === String(personId || ''));
    });
}

function telegramUnlinkConfirm(person) {
    const name = (person && person.name) || 'האדם';
    const features = [];
    if (person && person.receives_reminders) {
        features.push('תזכורות');
    }
    if (person && person.daily_digest_enabled) {
        features.push('סיכום בוקר');
    }
    let question = `בטוח שרוצים לנתק את הטלגרם של ${name}?`;
    if (features.length) {
        question += ` ${features.join(' ו')} ייכבו`;
    }
    return question;
}

function appendPersonRoleSwitch(parent, person, flag, label) {
    const wrap = document.createElement('label');
    wrap.className = 'reminder-person-flag';
    const input = document.createElement('input');
    input.type = 'checkbox';
    input.className = 'form-check-input';
    const linked = Boolean((person.telegram_chat_id || '').trim());
    const needsTelegram = flag === 'daily_digest_enabled';
    input.checked = needsTelegram && !linked ? false : Boolean(person[flag]);
    input.setAttribute('aria-label', `${label} ל${person.name}`);
    const text = document.createElement('span');
    text.textContent = label;
    wrap.append(input, text);
    if (needsTelegram && !linked) {
        wrap.classList.add('is-disabled');
        wrap.title = 'דורש חיבור לטלגרם';
        input.disabled = true;
        const hint = document.createElement('span');
        hint.className = 'reminder-person-flag-hint';
        hint.textContent = 'דורש חיבור לטלגרם';
        wrap.append(hint);
        parent.append(wrap);
        return;
    }
    input.addEventListener('change', () => toggleReminderPersonFlag(person, flag, input.checked, input));
    parent.append(wrap);
}

function renderReminderPeople(people) {
    const list = document.getElementById('reminderPeopleList');
    if (!list) {
        return;
    }
    const allPeople = people || [];
    list.replaceChildren();
    if (!allPeople.length) {
        const empty = document.createElement('p');
        empty.className = 'text-muted mb-0';
        empty.textContent = 'עדיין אין אנשים.';
        list.append(empty);
        return;
    }
    const editingId = document.getElementById('reminderPersonId')?.value;
    allPeople.forEach((person) => {
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
        const status = telegramLinkStatus(person);
        const chat = document.createElement('div');
        chat.className = `reminder-person-status small ${status.linked ? 'is-linked' : 'is-missing'}`;
        chat.textContent = status.text;
        text.append(name, chat);
        if (person.google_email) {
            const email = document.createElement('div');
            email.className = 'reminder-person-status small';
            email.textContent = person.google_email;
            text.append(email);
        }
        const flags = document.createElement('div');
        flags.className = 'reminder-person-flags';
        appendPersonRoleSwitch(flags, person, 'receives_reminders', 'תזכורות');
        appendPersonRoleSwitch(flags, person, 'works_shifts', 'משמרות');
        appendPersonRoleSwitch(flags, person, 'daily_digest_enabled', 'סיכום בוקר');
        text.append(flags);
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
        setReminderPersonError('לא הצלחנו לטעון');
        return;
    }
    const people = await response.json();
    const list = Array.isArray(people) ? people : [];
    reminderPeopleState.people = list;
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
    suggestSimilarReminderPerson();
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
    const emailRaw = (document.getElementById('reminderPersonEmail')?.value || '').trim();
    if (!name) {
        setReminderPersonError('חסר שם');
        return;
    }
    if (chatId === null) {
        setReminderPersonError('מזהה הצ׳אט חייב להיות מספר');
        return;
    }
    const id = document.getElementById('reminderPersonId').value;
    const existing = (reminderPeopleState.people || []).find((item) => String(item.id) === String(id));
    const hadChat = Boolean(((existing && existing.telegram_chat_id) || '').trim());
    if (hadChat && !chatId) {
        if (!confirm(telegramUnlinkConfirm(existing))) {
            document.getElementById('reminderPersonChat').value = existing.telegram_chat_id || '';
            return;
        }
    }
    const payload = {
        name,
        telegram_chat_id: chatId || null,
        google_email: emailRaw || null,
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

function personWritePayload(person, extra) {
    return {
        name: person.name,
        telegram_chat_id: person.telegram_chat_id || null,
        color: person.color,
        shift_allowed: person.shift_allowed,
        receives_reminders: person.receives_reminders,
        works_shifts: person.works_shifts,
        daily_digest_enabled: person.daily_digest_enabled,
        google_email: person.google_email || null,
        ...extra,
    };
}

async function toggleReminderPersonFlag(person, flag, value, input) {
    const response = await fetch(`/api/reminder-people/${person.id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(personWritePayload(person, { [flag]: value })),
    });
    const result = await response.json().catch(() => ({}));
    if (!response.ok) {
        if (input) {
            input.checked = !value;
        }
        setReminderPersonError(result.error || 'שמירה נכשלה');
        return;
    }
    setReminderPersonError('');
    await loadReminderPeople();
}

function hidePersonReassign() {
    reminderPeopleState.deletingId = null;
    const box = document.getElementById('reminderPersonReassign');
    if (box) {
        box.hidden = true;
    }
}

function showPersonReassign(person, message) {
    reminderPeopleState.deletingId = person.id;
    setReminderPersonError(message);
    const box = document.getElementById('reminderPersonReassign');
    const select = document.getElementById('reminderPersonReassignTo');
    if (!box || !select) {
        return;
    }
    const others = (reminderPeopleState.people || []).filter((item) => (
        String(item.id) !== String(person.id)
    ));
    select.replaceChildren();
    others.forEach((item) => {
        const option = document.createElement('option');
        option.value = String(item.id);
        option.textContent = item.name;
        select.append(option);
    });
    box.hidden = others.length === 0;
}

function suggestSimilarReminderPerson() {
    const node = document.getElementById('reminderPersonSuggest');
    const nameInput = document.getElementById('reminderPersonName');
    if (!node || !nameInput) {
        return;
    }
    const typed = nameInput.value.trim();
    const editingId = document.getElementById('reminderPersonId')?.value || '';
    node.replaceChildren();
    if (!typed) {
        node.hidden = true;
        return;
    }
    const matches = (reminderPeopleState.people || [])
        .map((person) => ({ person, kind: personNameSimilarity(typed, person.name) }))
        .filter((item) => item.kind && String(item.person.id) !== String(editingId));
    if (!matches.length) {
        node.hidden = true;
        return;
    }
    matches.sort((left, right) => {
        if (left.kind === right.kind) {
            return left.person.id - right.person.id;
        }
        return left.kind === 'exact' ? -1 : 1;
    });
    const { person, kind } = matches[0];
    const status = telegramLinkStatus(person);
    const roles = [];
    if (person.receives_reminders) {
        roles.push('תזכורות');
    }
    if (person.works_shifts) {
        roles.push('משמרות');
    }
    if (person.daily_digest_enabled) {
        roles.push('סיכום בוקר');
    }
    const bits = [status.text];
    if (roles.length) {
        bits.unshift(roles.join(' ו'));
    }
    const text = document.createElement('span');
    text.textContent = kind === 'exact'
        ? `כבר יש ${person.name} (${bits.join(' · ')}). הוספה תעדכן את אותה שורה.`
        : `שם דומה: ${person.name} (${bits.join(' · ')}). להשתמש בה במקום ליצור אדם חדש?`;
    const use = document.createElement('button');
    use.type = 'button';
    use.className = 'btn btn-outline-secondary btn-sm';
    use.textContent = `עריכת ${person.name}`;
    use.addEventListener('click', () => startEditReminderPerson(person));
    node.append(text, use);
    node.hidden = false;
}

async function sendDeleteReminderPerson(person, reassignTo) {
    const url = reassignTo
        ? `/api/reminder-people/${person.id}?reassign_to=${encodeURIComponent(reassignTo)}`
        : `/api/reminder-people/${person.id}`;
    const response = await fetch(url, { method: 'DELETE' });
    const result = await response.json().catch(() => ({}));
    return { response, result };
}

async function deleteReminderPerson(person) {
    const bits = [];
    if (person.receives_reminders) {
        bits.push('תזכורות');
    }
    if (person.works_shifts) {
        bits.push('משמרות');
    }
    const extra = bits.length ? ` גם ${bits.join(' ו')} יימחקו.` : '';
    const question = `למחוק את ${person.name}?${extra}`;
    if (!confirm(question)) {
        return;
    }
    const { response, result } = await sendDeleteReminderPerson(person);
    if (response.status === 409) {
        showPersonReassign(person, result.error || 'אי אפשר למחוק בלי להעביר תזכורות');
        return;
    }
    if (!response.ok) {
        setReminderPersonError(result.error || 'מחיקה נכשלה');
        return;
    }
    hidePersonReassign();
    if (document.getElementById('reminderPersonId').value === String(person.id)) {
        resetReminderPersonForm();
    }
    await loadReminderPeople();
}

async function confirmReassignDeletePerson() {
    const personId = reminderPeopleState.deletingId;
    const select = document.getElementById('reminderPersonReassignTo');
    const targetId = select?.value;
    const person = (reminderPeopleState.people || []).find((item) => String(item.id) === String(personId));
    if (!person || !targetId) {
        setReminderPersonError('בחרו למי להעביר את התזכורות');
        return;
    }
    const { response, result } = await sendDeleteReminderPerson(person, targetId);
    if (!response.ok) {
        setReminderPersonError(result.error || 'מחיקה נכשלה');
        return;
    }
    hidePersonReassign();
    if (document.getElementById('reminderPersonId').value === String(person.id)) {
        resetReminderPersonForm();
    }
    await loadReminderPeople();
}
