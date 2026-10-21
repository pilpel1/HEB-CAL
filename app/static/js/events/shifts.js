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
};

function shiftLabelNames() {
    return ['בוקר', 'ערב', 'לילה'];
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
    const editingId = document.getElementById('reminderPersonId')?.value;
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
    const toggle = document.getElementById('shiftsEnabled');
    if (toggle) {
        toggle.checked = !!shiftUiState.enabled;
    }
    const button = document.getElementById('enterShiftsBtn');
    if (button) {
        button.hidden = !shiftUiState.enabled;
    }
}

function resetPersonShiftFields() {
    setPersonColor(suggestPersonColor());
    writeShiftMatrix(document.getElementById('personShiftMatrix'), defaultShiftAllowed());
}

function fillPersonShiftFields(person) {
    setPersonColor(person.color || '');
    writeShiftMatrix(
        document.getElementById('personShiftMatrix'),
        person.shift_allowed || defaultShiftAllowed(),
    );
}

function personShiftPayload() {
    const fields = document.getElementById('personShiftFields');
    if (!fields || fields.hidden) {
        return {};
    }
    return {
        color: shiftUiState.personColor || null,
        shift_allowed: readShiftMatrix(document.getElementById('personShiftMatrix')),
    };
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
        if (!document.getElementById('reminderPersonId')?.value) {
            resetPersonShiftFields();
        }
        if (typeof loadReminderPeople === 'function') {
            await loadReminderPeople();
        }
    });
    ensureShiftSettings().then(() => {
        syncShiftSettingsVisibility();
        if (!document.getElementById('reminderPersonId')?.value) {
            resetPersonShiftFields();
        }
    });
}

function defaultShiftWeekStart(today) {
    const start = weekStartOf(today);
    const day = new Date(`${today}T00:00:00`).getDay();
    if (day >= 5) {
        return addDaysToDateStr(start, 7);
    }
    return start;
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

function renderShiftGrid(payload) {
    const grid = document.getElementById('shiftGrid');
    if (!grid) {
        return;
    }
    const letters = shiftDayLetters();
    const table = document.createElement('table');
    table.className = 'shift-matrix';
    const thead = document.createElement('thead');
    const headRow = document.createElement('tr');
    headRow.append(document.createElement('th'));
    payload.days.forEach((day) => {
        const th = document.createElement('th');
        const letter = document.createElement('div');
        letter.textContent = letters[day.weekday];
        const num = document.createElement('div');
        num.className = 'shift-day-num';
        num.textContent = String(Number(day.date.slice(8)));
        th.append(letter, num);
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
            const allowed = day.allowed.includes(label);
            const checked = day.checked.includes(label);
            input.checked = checked;
            input.disabled = !allowed;
            if (!allowed) {
                wrap.classList.add('is-disabled');
                input.title = checked
                    ? 'המשמרת הזו כבר בלוח, אבל היא לא מותרת יותר. מוחקים אותה מעריכת האירוע'
                    : 'לא מותר לאדם הזה';
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
    const label = document.getElementById('shiftWeekLabel');
    if (label) {
        label.textContent = formatShiftWeekLabel(payload.week_start);
    }
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
        setShiftEntryError(data.error || 'לא הצלחנו לטעון את השבוע');
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
    setShiftEntryError('');
    window.bootstrap.Modal.getOrCreateInstance(modalEl).show();
    const empty = document.getElementById('shiftEntryEmpty');
    const grid = document.getElementById('shiftGrid');
    const save = document.getElementById('shiftEntrySave');
    shiftUiState.weekStart = defaultShiftWeekStart(getTodayDateStr());
    const response = await fetch('/api/reminder-people');
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
            showMessage('המשמרות נשמרו');
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
