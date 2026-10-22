// הזנת משמרות: מתג בעמוד ההגדרות, וכפתור «הזן משמרות» בלוח.
// הסקריפט נטען בכל הדפים ורץ רק איפה שיש את האלמנטים.

const shiftUiState = {
    enabled: false,
    promise: null,
    people: [],
    personColor: '',
    personId: null,
    weekStart: null,
    saving: false,
    filling: false,
    rulesDirty: false,
    rulesSaving: false,
    rulesAgain: false,
    autoTitle: '',
};

function shiftLabelNames() {
    return ['בוקר', 'ערב', 'לילה'];
}

// לחיצה על בוקר/ערב/לילה קובעת את סוג המשמרת.
// את הכותרת ממלאים רק כשהיא ריקה, או שעדיין שווה למילוי האוטומטי הקודם.
// טקסט שהמשתמש כתב (למשל «בוקר מוקדם») לא נדרס.
function shiftTitleAfterPick(currentTitle, previousAuto, nextLabel) {
    const current = String(currentTitle || '').trim();
    const auto = String(previousAuto || '').trim();
    const next = String(nextLabel || '').trim();
    if (!current || (auto && current === auto)) {
        return { title: next, auto: next, filled: true };
    }
    return { title: current, auto, filled: false };
}

function shiftDayLetters() {
    return ['א׳', 'ב׳', 'ג׳', 'ד׳', 'ה׳', 'ו׳', 'ש׳'];
}

function defaultShiftAllowed() {
    const allowed = {};
    shiftLabelNames().forEach((label) => {
        allowed[label] = [0, 1, 2, 3, 4, 5, 6];
    });
    return allowed;
}

function ensureShiftSettings() {
    if (!shiftUiState.promise) {
        shiftUiState.promise = fetch('/api/shifts/settings')
            .then((response) => (response.ok ? response.json() : { enabled: false }))
            .then((data) => {
                shiftUiState.enabled = !!data.enabled;
                return data;
            })
            .catch(() => {
                shiftUiState.enabled = false;
                return { enabled: false };
            });
    }
    return shiftUiState.promise;
}

function noteShiftPeople(people) {
    shiftUiState.people = people || [];
}

function suggestPersonColor() {
    const used = new Set((shiftUiState.people || []).map((person) => person.color).filter(Boolean));
    const editingId = document.getElementById('shiftPersonEditId')?.value
        || document.getElementById('reminderPersonId')?.value;
    if (editingId) {
        const current = (shiftUiState.people || []).find((person) => String(person.id) === editingId);
        if (current && used.has(current.color)) {
            used.delete(current.color);
        }
    }
    return ['cyan', 'yellow', 'orange', 'green'].find((color) => !used.has(color)) || 'cyan';
}

function setPersonColor(color) {
    const picker = document.getElementById('personColorPicker');
    shiftUiState.personColor = color || '';
    if (!picker) {
        return;
    }
    picker.querySelectorAll('.quick-color-swatch').forEach((button) => {
        button.classList.toggle('is-selected', (button.dataset.color || '') === (color || ''));
    });
}

function readShiftMatrix(root) {
    const allowed = defaultShiftAllowed();
    shiftLabelNames().forEach((label) => {
        allowed[label] = [];
    });
    if (!root) {
        return allowed;
    }
    root.querySelectorAll('input[type="checkbox"][data-shift-label]').forEach((input) => {
        if (!input.checked) {
            return;
        }
        const label = input.dataset.shiftLabel;
        if (!allowed[label]) {
            allowed[label] = [];
        }
        allowed[label].push(Number(input.dataset.shiftDay));
    });
    return allowed;
}

function writeShiftMatrix(root, allowed) {
    if (!root) {
        return;
    }
    const source = allowed || defaultShiftAllowed();
    root.querySelectorAll('input[type="checkbox"][data-shift-label]').forEach((input) => {
        const days = source[input.dataset.shiftLabel] || [];
        input.checked = days.map(Number).includes(Number(input.dataset.shiftDay));
    });
}

function buildShiftMatrix(root, options) {
    if (!root || root.dataset.ready === '1') {
        return;
    }
    const letters = shiftDayLetters();
    const table = document.createElement('table');
    table.className = 'shift-matrix';
    const thead = document.createElement('thead');
    const headRow = document.createElement('tr');
    const corner = document.createElement('th');
    corner.className = 'shift-label-cell';
    headRow.append(corner);
    letters.forEach((letter) => {
        const th = document.createElement('th');
        th.textContent = letter;
        headRow.append(th);
    });
    thead.append(headRow);
    const tbody = document.createElement('tbody');
    shiftLabelNames().forEach((label) => {
        const tr = document.createElement('tr');
        const th = document.createElement('th');
        th.className = 'shift-label-cell';
        const labelText = document.createElement('span');
        labelText.textContent = label;
        th.append(labelText);
        if (options && options.allDays) {
            const button = document.createElement('button');
            button.type = 'button';
            button.className = 'shift-all-days';
            button.textContent = 'הכל';
            button.addEventListener('click', () => {
                const boxes = [...tr.querySelectorAll('input[type="checkbox"]')];
                const allOn = boxes.every((box) => box.checked);
                boxes.forEach((box) => {
                    box.checked = !allOn;
                });
                noteShiftRulesEdited();
            });
            th.append(button);
        }
        tr.append(th);
        for (let day = 0; day < 7; day += 1) {
            const td = document.createElement('td');
            const wrap = document.createElement('label');
            wrap.className = 'shift-cell';
            const input = document.createElement('input');
            input.type = 'checkbox';
            input.checked = true;
            input.dataset.shiftLabel = label;
            input.dataset.shiftDay = String(day);
            input.setAttribute('aria-label', `${label} ${letters[day]}`);
            input.addEventListener('change', () => noteShiftRulesEdited());
            wrap.append(input);
            td.append(wrap);
            tr.append(td);
        }
        tbody.append(tr);
    });
    table.append(thead, tbody);
    root.replaceChildren(table);
    root.dataset.ready = '1';
}

function shiftRulesSummary(allowed) {
    const letters = shiftDayLetters();
    const parts = [];
    shiftLabelNames().forEach((label) => {
        const days = (allowed && allowed[label] ? allowed[label] : []).map(Number).sort((a, b) => a - b);
        if (!days.length) {
            return;
        }
        if (days.length === 7) {
            parts.push(label);
            return;
        }
        parts.push(`${label} ${days.map((day) => letters[day]).join(' ')}`);
    });
    return parts.length ? parts.join(' · ') : 'בלי משמרות';
}

function appendShiftPersonMeta(container, person) {
    if (!shiftUiState.enabled || !container) {
        return;
    }
    const line = document.createElement('div');
    line.className = 'shift-person-meta';
    if (person.color) {
        const dot = document.createElement('span');
        dot.className = `shift-color-dot color-${person.color}`;
        dot.title = person.color;
        line.append(dot);
    }
    const text = document.createElement('span');
    text.textContent = shiftRulesSummary(person.shift_allowed);
    line.append(text);
    container.append(line);
}

function syncShiftSettingsVisibility() {
    const fields = document.getElementById('personShiftFields');
    if (fields) {
        fields.hidden = !shiftUiState.enabled;
    }
    const panel = document.getElementById('shiftPeoplePanel');
    if (panel) {
        panel.hidden = !shiftUiState.enabled;
    }
    const toggle = document.getElementById('shiftsEnabled');
    if (toggle) {
        toggle.checked = !!shiftUiState.enabled;
    }
    const button = document.getElementById('enterShiftsBtn');
    if (button) {
        button.hidden = !shiftUiState.enabled;
    }
}

function peopleByRole(role) {
    const list = shiftUiState.people || [];
    if (role === 'reminders') {
        return list.filter((person) => person.receives_reminders);
    }
    if (role === 'shifts') {
        return list.filter((person) => person.works_shifts);
    }
    return list;
}

function resetPersonShiftFields() {
    shiftUiState.filling = true;
    try {
        setPersonColor(suggestPersonColor());
        writeShiftMatrix(document.getElementById('personShiftMatrix'), defaultShiftAllowed());
    } finally {
        shiftUiState.filling = false;
    }
}

function fillPersonShiftFields(person) {
    shiftUiState.filling = true;
    clearShiftRulesDraft();
    try {
        setPersonColor(person.color || '');
        writeShiftMatrix(
            document.getElementById('personShiftMatrix'),
            person.shift_allowed || defaultShiftAllowed(),
        );
    } finally {
        shiftUiState.filling = false;
    }
}

function clearShiftRulesDraft() {
    shiftUiState.rulesDirty = false;
    shiftUiState.rulesAgain = false;
}

function personShiftPayload() {
    if (!shiftUiState.enabled) {
        return {};
    }
    const matrix = document.getElementById('personShiftMatrix');
    if (!matrix || !matrix.querySelector('input[type="checkbox"][data-shift-label]')) {
        return {};
    }
    return {
        color: shiftUiState.personColor || null,
        shift_allowed: readShiftMatrix(matrix),
    };
}

function noteShiftRulesEdited() {
    if (shiftUiState.filling) {
        return;
    }
    shiftUiState.rulesDirty = true;
    setShiftPersonSaved(false);
}

function confirmDiscardShiftEdits() {
    if (!shiftUiState.rulesDirty) {
        return true;
    }
    return window.confirm('יש שינויים שלא נשמרו. לעזוב בלי לשמור?');
}

async function flushShiftRulesSave() {
    if (shiftUiState.rulesDirty && !confirmDiscardShiftEdits()) {
        throw new Error('unsaved-shift-edits');
    }
}

function setShiftPersonError(message) {
    const node = document.getElementById('shiftPersonError');
    if (!node) {
        return;
    }
    node.textContent = message || '';
    node.hidden = !message;
}

function setShiftPersonSaved(visible) {
    const node = document.getElementById('shiftPersonSaved');
    if (!node) {
        return;
    }
    node.hidden = !visible;
}

function setShiftPersonContext(person) {
    const node = document.getElementById('shiftPersonContext');
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

function currentShiftEditId() {
    return document.getElementById('shiftPersonEditId')?.value || '';
}

function fillShiftPersonSource(people) {
    const select = document.getElementById('shiftPersonSource');
    if (!select) {
        return;
    }
    const editingId = currentShiftEditId();
    const keep = select.value;
    const candidates = (people || []).filter((person) => {
        if (person.works_shifts && String(person.id) !== String(editingId)) {
            return false;
        }
        return true;
    });
    select.replaceChildren();
    const blank = document.createElement('option');
    blank.value = '';
    blank.textContent = 'אדם חדש';
    select.append(blank);
    candidates.forEach((person) => {
        if (person.works_shifts && String(person.id) === String(editingId)) {
            return;
        }
        const option = document.createElement('option');
        option.value = String(person.id);
        option.textContent = person.receives_reminders
            ? `${person.name} (תזכורות)`
            : person.name;
        select.append(option);
    });
    if ([...select.options].some((option) => option.value === keep)) {
        select.value = keep;
    }
    const wrap = document.getElementById('shiftPersonSourceWrap');
    if (wrap) {
        wrap.hidden = Boolean(editingId);
    }
}

function renderShiftPeopleList(people) {
    const list = document.getElementById('shiftPeopleList');
    if (!list) {
        return;
    }
    const workers = (people || []).filter((person) => person.works_shifts);
    list.replaceChildren();
    if (!workers.length) {
        const empty = document.createElement('p');
        empty.className = 'text-muted mb-0';
        empty.textContent = 'עדיין אין אנשים.';
        list.append(empty);
        return;
    }
    const editingId = currentShiftEditId();
    workers.forEach((person) => {
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
        text.append(name);
        appendShiftPersonMeta(text, person);
        const actions = document.createElement('div');
        actions.className = 'd-flex gap-2';
        const edit = document.createElement('button');
        edit.type = 'button';
        edit.className = 'btn btn-outline-primary btn-sm';
        edit.textContent = 'עריכה';
        edit.addEventListener('click', () => startEditShiftPerson(person));
        const remove = document.createElement('button');
        remove.type = 'button';
        remove.className = 'btn btn-outline-danger btn-sm';
        remove.textContent = 'הסרה';
        remove.addEventListener('click', () => removeShiftPerson(person));
        actions.append(edit, remove);
        row.append(text, actions);
        list.append(row);
    });
}

function resetShiftPersonForm() {
    const idInput = document.getElementById('shiftPersonEditId');
    if (idInput) {
        idInput.value = '';
    }
    const nameInput = document.getElementById('shiftPersonName');
    if (nameInput) {
        nameInput.value = '';
        nameInput.readOnly = false;
    }
    const source = document.getElementById('shiftPersonSource');
    if (source) {
        source.value = '';
        source.disabled = false;
    }
    const cancel = document.getElementById('shiftPersonCancel');
    if (cancel) {
        cancel.hidden = true;
    }
    setShiftPersonError('');
    setShiftPersonSaved(false);
    setShiftPersonContext(null);
    resetPersonShiftFields();
    clearShiftRulesDraft();
    fillShiftPersonSource(shiftUiState.people);
    renderShiftPeopleList(shiftUiState.people);
}

function startEditShiftPerson(person, options) {
    if (!(options && options.force) && !confirmDiscardShiftEdits()) {
        return;
    }
    document.getElementById('shiftPersonEditId').value = String(person.id);
    document.getElementById('shiftPersonName').value = person.name || '';
    document.getElementById('shiftPersonName').readOnly = false;
    const source = document.getElementById('shiftPersonSource');
    if (source) {
        source.value = '';
        source.disabled = true;
    }
    document.getElementById('shiftPersonCancel').hidden = false;
    setShiftPersonError('');
    setShiftPersonSaved(false);
    setShiftPersonContext(person);
    fillPersonShiftFields(person);
    fillShiftPersonSource(shiftUiState.people);
    renderShiftPeopleList(shiftUiState.people);
    document.getElementById('shiftPersonName').focus();
}

async function saveShiftPerson(event) {
    event.preventDefault();
    const existingId = currentShiftEditId();
    const sourceId = document.getElementById('shiftPersonSource')?.value || '';
    const personId = existingId || sourceId;
    const nameInput = document.getElementById('shiftPersonName');
    const typedName = (nameInput?.value || '').trim();
    const existing = (shiftUiState.people || []).find((person) => String(person.id) === String(personId));
    const name = typedName || (existing && existing.name) || '';
    if (!name) {
        setShiftPersonError('חסר שם');
        return;
    }
    const extra = personShiftPayload();
    const payload = {
        name,
        telegram_chat_id: existing ? existing.telegram_chat_id || null : null,
        color: extra.color || null,
        shift_allowed: extra.shift_allowed || defaultShiftAllowed(),
        works_shifts: true,
    };
    if (existing && existing.receives_reminders) {
        payload.receives_reminders = true;
    } else if (!personId) {
        payload.receives_reminders = false;
    }
    setShiftPersonError('');
    const response = await fetch(personId ? `/api/reminder-people/${personId}` : '/api/reminder-people', {
        method: personId ? 'PUT' : 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
    });
    const saved = await response.json().catch(() => ({}));
    if (!response.ok) {
        setShiftPersonError(saved.error || 'השמירה נכשלה');
        return;
    }
    clearShiftRulesDraft();
    setShiftPersonSaved(true);
    if (typeof showMessage === 'function') {
        showMessage('נשמר');
    }
    if (typeof loadReminderPeople === 'function') {
        await loadReminderPeople();
    }
    startEditShiftPerson({ ...saved, id: saved.id }, { force: true });
    clearShiftRulesDraft();
    setShiftPersonSaved(true);
}

async function removeShiftPerson(person) {
    if (!confirmDiscardShiftEdits()) {
        return;
    }
    const alsoReminders = Boolean(person.receives_reminders);
    const question = alsoReminders
        ? `להסיר את ${person.name} מהמשמרות? התזכורות יישארו.`
        : `למחוק את ${person.name}?`;
    if (!confirm(question)) {
        return;
    }
    let response;
    if (alsoReminders) {
        response = await fetch(`/api/reminder-people/${person.id}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                name: person.name,
                telegram_chat_id: person.telegram_chat_id || null,
                color: person.color,
                shift_allowed: person.shift_allowed,
                receives_reminders: true,
                works_shifts: false,
            }),
        });
    } else {
        response = await fetch(`/api/reminder-people/${person.id}`, { method: 'DELETE' });
    }
    if (!response.ok) {
        setShiftPersonError('ההסרה נכשלה');
        return;
    }
    if (currentShiftEditId() === String(person.id)) {
        resetShiftPersonForm();
    }
    if (typeof loadReminderPeople === 'function') {
        await loadReminderPeople();
    }
}

function initShiftSettings() {
    const toggle = document.getElementById('shiftsEnabled');
    if (!toggle) {
        return;
    }
    buildShiftMatrix(document.getElementById('personShiftMatrix'), { allDays: true });
    document.getElementById('personColorPicker')?.addEventListener('click', (event) => {
        const button = event.target.closest('[data-color]');
        if (!button) {
            return;
        }
        setPersonColor(button.dataset.color || '');
        noteShiftRulesEdited();
    });
    document.getElementById('shiftPersonForm')?.addEventListener('submit', saveShiftPerson);
    document.getElementById('shiftPersonCancel')?.addEventListener('click', () => {
        if (!confirmDiscardShiftEdits()) {
            return;
        }
        resetShiftPersonForm();
    });
    document.getElementById('shiftPersonName')?.addEventListener('input', noteShiftRulesEdited);
    document.getElementById('shiftPersonSource')?.addEventListener('change', (event) => {
        const id = event.target.value;
        if (!id) {
            document.getElementById('shiftPersonEditId').value = '';
            setShiftPersonContext(null);
            fillShiftPersonSource(shiftUiState.people);
            noteShiftRulesEdited();
            return;
        }
        const person = (shiftUiState.people || []).find((item) => String(item.id) === String(id));
        if (!person) {
            return;
        }
        document.getElementById('shiftPersonEditId').value = String(person.id);
        document.getElementById('shiftPersonName').value = person.name || '';
        document.getElementById('shiftPersonCancel').hidden = false;
        setShiftPersonContext(person);
        fillPersonShiftFields(person);
        fillShiftPersonSource(shiftUiState.people);
        noteShiftRulesEdited();
    });
    window.addEventListener('beforeunload', (event) => {
        if (!shiftUiState.rulesDirty) {
            return;
        }
        event.preventDefault();
        event.returnValue = '';
    });
    toggle.addEventListener('change', async () => {
        const enabled = toggle.checked;
        const response = await fetch('/api/shifts/settings', {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ enabled }),
        });
        if (!response.ok) {
            toggle.checked = !enabled;
            return;
        }
        shiftUiState.enabled = enabled;
        shiftUiState.promise = Promise.resolve({ enabled });
        syncShiftSettingsVisibility();
        if (!currentShiftEditId() && !shiftUiState.rulesDirty) {
            resetPersonShiftFields();
        }
        if (typeof loadReminderPeople === 'function') {
            await loadReminderPeople();
        }
    });
    ensureShiftSettings().then(() => {
        syncShiftSettingsVisibility();
        if (!currentShiftEditId() && !shiftUiState.rulesDirty) {
            resetPersonShiftFields();
        }
        renderShiftPeopleList(shiftUiState.people);
        fillShiftPersonSource(shiftUiState.people);
    });
}

function defaultShiftWeekStart(today) {
    return addDaysToDateStr(weekStartOf(today), 7);
}

function formatShiftWeekLabel(weekStart) {
    const end = addDaysToDateStr(weekStart, 6);
    const [startYear, startMonth, startDay] = weekStart.split('-').map(Number);
    const [endYear, endMonth, endDay] = end.split('-').map(Number);
    const startText = `${startDay} ב${getShortMonthName(startMonth - 1)}`;
    const endText = `${endDay} ב${getShortMonthName(endMonth - 1)}`;
    const year = startYear === endYear ? String(endYear) : `${startYear}–${endYear}`;
    return `${startText} – ${endText} ${year}`;
}

function setShiftEntryError(message) {
    const node = document.getElementById('shiftEntryError');
    if (!node) {
        return;
    }
    node.textContent = message || '';
    node.hidden = !message;
}

function updateShiftPersonDot() {
    const dot = document.getElementById('shiftPersonDot');
    const select = document.getElementById('shiftPersonSelect');
    if (!dot || !select) {
        return;
    }
    const person = (shiftUiState.people || []).find((item) => String(item.id) === select.value);
    dot.className = 'shift-color-dot';
    if (!person || !person.color) {
        dot.hidden = true;
        return;
    }
    dot.hidden = false;
    dot.classList.add(`color-${person.color}`);
}

function selectedShiftPerson() {
    const select = document.getElementById('shiftPersonSelect');
    const id = select ? select.value : String(shiftUiState.personId || '');
    return (shiftUiState.people || []).find((person) => String(person.id) === String(id)) || null;
}

function personAllowsLabel(person, dateStr, label) {
    const rules = person && person.shift_allowed;
    if (!rules || typeof rules !== 'object') {
        return true;
    }
    const days = rules[label];
    if (!Array.isArray(days)) {
        return false;
    }
    return days.map(Number).includes(new Date(`${dateStr}T00:00:00`).getDay());
}

function renderShiftWeekLabel(payload) {
    const label = document.getElementById('shiftWeekLabel');
    if (!label) {
        return;
    }
    label.replaceChildren();
    const heb = document.createElement('div');
    heb.className = 'shift-week-heb';
    heb.textContent = payload.hebrew_range || payload.week_title || '';
    label.append(heb);
    if (payload.parasha) {
        const parasha = document.createElement('div');
        parasha.className = 'shift-week-parasha';
        parasha.textContent = `פרשת ${payload.parasha}`;
        label.append(parasha);
    }
    const greg = document.createElement('div');
    greg.className = 'shift-week-greg';
    greg.textContent = formatShiftWeekLabel(payload.week_start);
    label.append(greg);
}

function renderShiftGrid(payload) {
    const grid = document.getElementById('shiftGrid');
    if (!grid) {
        return;
    }
    shiftUiState.weekDays = payload.days || [];
    const person = selectedShiftPerson();
    const letters = shiftDayLetters();
    const table = document.createElement('table');
    table.className = 'shift-matrix';
    const thead = document.createElement('thead');
    const headRow = document.createElement('tr');
    const corner = document.createElement('th');
    corner.className = 'shift-label-cell';
    headRow.append(corner);
    payload.days.forEach((day) => {
        const th = document.createElement('th');
        const letter = document.createElement('div');
        letter.textContent = letters[day.weekday];
        const num = document.createElement('div');
        num.className = 'shift-day-num';
        num.textContent = String(Number(day.date.slice(8)));
        const hebDay = document.createElement('div');
        hebDay.className = 'shift-day-heb';
        hebDay.textContent = day.hebrew_day || '';
        const hebMonth = document.createElement('div');
        hebMonth.className = 'shift-day-heb-month';
        hebMonth.textContent = day.hebrew_month || '';
        th.append(letter, num, hebDay, hebMonth);
        headRow.append(th);
    });
    thead.append(headRow);
    const tbody = document.createElement('tbody');
    const personName = document.getElementById('shiftPersonSelect')?.selectedOptions?.[0]?.textContent || '';
    payload.labels.forEach((label) => {
        const tr = document.createElement('tr');
        const th = document.createElement('th');
        th.className = 'shift-label-cell';
        th.textContent = label;
        tr.append(th);
        payload.days.forEach((day) => {
            const td = document.createElement('td');
            const wrap = document.createElement('label');
            wrap.className = 'shift-cell';
            const input = document.createElement('input');
            input.type = 'checkbox';
            input.dataset.date = day.date;
            input.dataset.label = label;
            const serverAllowed = !day.allowed || day.allowed.includes(label);
            const allowed = serverAllowed && personAllowsLabel(person, day.date, label);
            const checked = day.checked.includes(label);
            if (!allowed && !checked) {
                wrap.classList.add('is-blocked');
                wrap.textContent = '–';
                wrap.title = 'לא מותר';
                td.append(wrap);
                tr.append(td);
                return;
            }
            input.checked = checked;
            input.disabled = !allowed;
            if (!allowed) {
                wrap.classList.add('is-disabled');
                input.title = 'כבר בלוח, אבל כבר לא מותרת';
            }
            input.setAttribute('aria-label', `${personName} ${label} ${letters[day.weekday]} ${day.date}`);
            wrap.append(input);
            td.append(wrap);
            tr.append(td);
        });
        tbody.append(tr);
    });
    table.append(thead, tbody);
    grid.replaceChildren(table);
    renderShiftWeekLabel(payload);
}

async function loadShiftWeek() {
    if (!shiftUiState.personId || !shiftUiState.weekStart) {
        return;
    }
    setShiftEntryError('');
    const params = new URLSearchParams({
        person_id: String(shiftUiState.personId),
        week_start: shiftUiState.weekStart,
    });
    const response = await fetch(`/api/shifts/week?${params}`);
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
        setShiftEntryError(data.error || 'לא הצלחנו לטעון');
        return;
    }
    renderShiftGrid(data);
}

function fillShiftPersonSelect(people) {
    const select = document.getElementById('shiftPersonSelect');
    if (!select) {
        return;
    }
    const previous = shiftUiState.personId ? String(shiftUiState.personId) : '';
    select.replaceChildren();
    people.forEach((person) => {
        const option = document.createElement('option');
        option.value = String(person.id);
        option.textContent = person.name;
        select.append(option);
    });
    let stored = '';
    try {
        stored = sessionStorage.getItem('heb-cal-shift-person') || '';
    } catch (error) {
        stored = '';
    }
    const ids = people.map((person) => String(person.id));
    const chosen = [previous, stored].find((id) => ids.includes(id)) || ids[0];
    select.value = chosen;
    shiftUiState.personId = Number(chosen);
    updateShiftPersonDot();
}

async function openShiftEntry() {
    const modalEl = document.getElementById('shiftEntryModal');
    if (!modalEl || !window.bootstrap) {
        return;
    }
    try {
        await flushShiftRulesSave();
    } catch (error) {
        return;
    }
    setShiftEntryError('');
    window.bootstrap.Modal.getOrCreateInstance(modalEl).show();
    const empty = document.getElementById('shiftEntryEmpty');
    const grid = document.getElementById('shiftGrid');
    const save = document.getElementById('shiftEntrySave');
    shiftUiState.weekStart = defaultShiftWeekStart(getTodayDateStr());
    const response = await fetch('/api/reminder-people?role=shifts');
    const people = response.ok ? await response.json() : [];
    shiftUiState.people = Array.isArray(people) ? people : [];
    const hasPeople = shiftUiState.people.length > 0;
    if (empty) {
        empty.hidden = hasPeople;
    }
    if (grid) {
        grid.hidden = !hasPeople;
    }
    document.querySelectorAll('.shift-week-nav, .shift-person-row').forEach((node) => {
        node.hidden = !hasPeople;
    });
    if (save) {
        save.disabled = !hasPeople;
    }
    if (!hasPeople) {
        if (grid) {
            grid.replaceChildren();
        }
        return;
    }
    fillShiftPersonSelect(shiftUiState.people);
    await loadShiftWeek();
}

async function saveShiftWeek() {
    if (shiftUiState.saving || !shiftUiState.personId) {
        return;
    }
    const cells = [];
    document.querySelectorAll('#shiftGrid input[type="checkbox"]').forEach((input) => {
        if (input.checked) {
            cells.push({ date: input.dataset.date, label: input.dataset.label });
        }
    });
    shiftUiState.saving = true;
    const save = document.getElementById('shiftEntrySave');
    if (save) {
        save.disabled = true;
    }
    try {
        const response = await fetch('/api/shifts/week', {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                person_id: shiftUiState.personId,
                week_start: shiftUiState.weekStart,
                cells,
            }),
        });
        const data = await response.json().catch(() => ({}));
        if (!response.ok) {
            setShiftEntryError(data.error || 'השמירה נכשלה');
            return;
        }
        const modalEl = document.getElementById('shiftEntryModal');
        window.bootstrap.Modal.getInstance(modalEl)?.hide();
        if (typeof showMessage === 'function') {
            showMessage('נשמר');
        }
        if (typeof refreshEventsViews === 'function') {
            await refreshEventsViews();
        }
        if (typeof scrollToDate === 'function' && shiftUiState.weekStart) {
            await scrollToDate(shiftUiState.weekStart, 'center');
        }
    } finally {
        shiftUiState.saving = false;
        if (save) {
            save.disabled = false;
        }
    }
}

function initShiftEntry() {
    const button = document.getElementById('enterShiftsBtn');
    if (!button) {
        return;
    }
    button.addEventListener('click', () => {
        openShiftEntry();
    });
    document.getElementById('shiftWeekPrev')?.addEventListener('click', () => {
        if (!shiftUiState.weekStart) {
            return;
        }
        shiftUiState.weekStart = addDaysToDateStr(shiftUiState.weekStart, -7);
        loadShiftWeek();
    });
    document.getElementById('shiftWeekNext')?.addEventListener('click', () => {
        if (!shiftUiState.weekStart) {
            return;
        }
        shiftUiState.weekStart = addDaysToDateStr(shiftUiState.weekStart, 7);
        loadShiftWeek();
    });
    document.getElementById('shiftPersonSelect')?.addEventListener('change', (event) => {
        shiftUiState.personId = Number(event.target.value);
        try {
            sessionStorage.setItem('heb-cal-shift-person', event.target.value);
        } catch (error) {
            // sessionStorage חסום — נשארים על הבחירה הנוכחית
        }
        updateShiftPersonDot();
        loadShiftWeek();
    });
    document.getElementById('shiftEntrySave')?.addEventListener('click', () => {
        saveShiftWeek();
    });
    ensureShiftSettings().then(syncShiftSettingsVisibility);
}

function fillQuickShiftPeople(selectedId) {
    const select = document.getElementById('quick_shift_person');
    if (!select) {
        return;
    }
    const people = [...peopleByRole('shifts')];
    if (selectedId && !people.some((person) => String(person.id) === String(selectedId))) {
        const extra = (shiftUiState.people || []).find((person) => String(person.id) === String(selectedId));
        if (extra) {
            people.unshift(extra);
        }
    }
    const previous = selectedId ? String(selectedId) : select.value;
    select.replaceChildren();
    if (!people.length) {
        const empty = document.createElement('option');
        empty.value = '';
        empty.textContent = 'אין אנשים';
        select.append(empty);
        return;
    }
    people.forEach((person) => {
        const option = document.createElement('option');
        option.value = String(person.id);
        option.textContent = person.name;
        select.append(option);
    });
    if (previous && [...select.options].some((option) => option.value === previous)) {
        select.value = previous;
    }
}

function paintQuickShiftPicks() {
    const label = (document.getElementById('quick_shift_label')?.value || '').trim();
    document.querySelectorAll('#quick_shift_picks [data-shift-pick]').forEach((button) => {
        const on = button.dataset.shiftPick === label;
        button.classList.toggle('is-selected', on);
        button.setAttribute('aria-pressed', on ? 'true' : 'false');
    });
}

function rememberShiftAutoTitle() {
    const label = (document.getElementById('quick_shift_label')?.value || '').trim();
    const title = (document.getElementById('quick_title')?.value || '').trim();
    shiftUiState.autoTitle = shiftLabelNames().includes(label) && title === label ? label : '';
}

function applyQuickShiftLook() {
    const on = Boolean(document.getElementById('quick_shift_enabled')?.checked);
    const panel = document.getElementById('quick_shift_panel');
    if (panel) {
        panel.hidden = !on;
    }
    const recurrence = document.getElementById('quick_recurrence');
    if (recurrence) {
        recurrence.hidden = on;
    }
    document.querySelector('#quickEventModal .quick-color-picker')?.classList.toggle('is-shift-locked', on);
    paintQuickShiftPicks();
    if (!on || shiftUiState.filling) {
        return;
    }
    const personId = document.getElementById('quick_shift_person')?.value;
    const person = (shiftUiState.people || []).find((item) => String(item.id) === String(personId));
    if (typeof setQuickColor === 'function') {
        setQuickColor(person && person.color ? person.color : '');
    }
    if (typeof setQuickTime === 'function') {
        setQuickTime('');
    }
    const end = document.getElementById('quick_end_date');
    if (end) {
        end.value = '';
    }
    if (typeof setEndDateOpen === 'function') {
        setEndDateOpen(false);
    }
}

function chooseQuickShiftLabel(label) {
    const title = document.getElementById('quick_title');
    const result = shiftTitleAfterPick(title ? title.value : '', shiftUiState.autoTitle, label);
    if (title && result.filled) {
        title.value = result.title;
    }
    shiftUiState.autoTitle = result.auto;
    const hidden = document.getElementById('quick_shift_label');
    if (hidden) {
        hidden.value = label;
    }
    applyQuickShiftLook();
}

function initQuickShiftFields() {
    const box = document.getElementById('quick_shift_enabled');
    if (!box || box.dataset.bound === '1') {
        return;
    }
    box.dataset.bound = '1';
    box.addEventListener('change', applyQuickShiftLook);
    document.getElementById('quick_shift_person')?.addEventListener('change', applyQuickShiftLook);
    document.getElementById('quick_shift_picks')?.addEventListener('click', (event) => {
        const button = event.target.closest('[data-shift-pick]');
        if (!button) {
            return;
        }
        chooseQuickShiftLabel(button.dataset.shiftPick || '');
    });
}

async function fillQuickShiftFields(eventData) {
    const block = document.getElementById('quickShiftBlock');
    if (!block) {
        return;
    }
    const data = eventData || {};
    await ensureShiftSettings();
    const isShift = Boolean(Number(data.is_shift));
    block.hidden = !shiftUiState.enabled && !isShift;
    const box = document.getElementById('quick_shift_enabled');
    const panel = document.getElementById('quick_shift_panel');
    const recurrence = document.getElementById('quick_recurrence');
    if (block.hidden) {
        if (box) {
            box.checked = false;
        }
        if (panel) {
            panel.hidden = true;
        }
        if (recurrence) {
            recurrence.hidden = false;
        }
        document.querySelector('#quickEventModal .quick-color-picker')?.classList.remove('is-shift-locked');
        return;
    }
    const response = await fetch('/api/reminder-people');
    if (response.ok) {
        const people = await response.json();
        shiftUiState.people = Array.isArray(people) ? people : [];
    }
    shiftUiState.filling = true;
    try {
        fillQuickShiftPeople(data.shift_person_id);
        if (box) {
            box.checked = isShift;
        }
        const label = document.getElementById('quick_shift_label');
        if (label) {
            label.value = data.shift_label || '';
        }
        rememberShiftAutoTitle();
        paintQuickShiftPicks();
        if (panel) {
            panel.hidden = !isShift;
        }
        if (recurrence) {
            recurrence.hidden = isShift;
        }
        document.querySelector('#quickEventModal .quick-color-picker')?.classList.toggle('is-shift-locked', isShift);
        if (isShift && typeof setQuickColor === 'function') {
            const person = (shiftUiState.people || []).find((item) => String(item.id) === String(data.shift_person_id));
            setQuickColor(person && person.color ? person.color : (data.color || ''));
        }
    } finally {
        shiftUiState.filling = false;
    }
}

function readQuickShiftFields() {
    const block = document.getElementById('quickShiftBlock');
    if (!block || block.hidden) {
        return {};
    }
    const enabled = Boolean(document.getElementById('quick_shift_enabled')?.checked);
    if (!enabled) {
        return { is_shift: false, shift_person_id: null, shift_label: null };
    }
    const personId = document.getElementById('quick_shift_person')?.value;
    let label = (document.getElementById('quick_shift_label')?.value || '').trim();
    if (!label) {
        label = (document.getElementById('quick_title')?.value || '').trim();
    }
    return {
        is_shift: true,
        shift_person_id: personId ? Number(personId) : null,
        shift_label: label,
    };
}
