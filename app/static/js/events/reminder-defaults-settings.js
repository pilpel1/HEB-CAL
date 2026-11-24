// ברירות מחדל לתזכורות לפי אדם — כרטיס «תזכורות» בהגדרות.

const reminderDefaultsState = {
    people: [],
    personId: null,
    customOffsets: [],
    dirty: false,
    ready: false,
};

function setReminderDefaultsError(message) {
    const node = document.getElementById('reminderDefaultsError');
    if (!node) {
        return;
    }
    node.textContent = message || '';
    node.hidden = !message;
}

function setReminderDefaultsSaved(show) {
    const node = document.getElementById('reminderDefaultsSaved');
    if (node) {
        node.hidden = !show;
    }
}

function selectedDefaultOffsets() {
    const selected = new Set(reminderDefaultsState.customOffsets);
    document.querySelectorAll('#reminderDefaultsOffsets .reminder-offset-chip.is-selected').forEach((chip) => {
        const value = Number(chip.dataset.offset);
        if (Number.isInteger(value)) {
            selected.add(value);
        }
    });
    return [...selected].sort((a, b) => a - b);
}

function renderReminderDefaultsCustom() {
    const list = document.getElementById('reminderDefaultsCustomList');
    if (!list) {
        return;
    }
    list.replaceChildren();
    reminderDefaultsState.customOffsets.forEach((minutes) => {
        const chip = document.createElement('button');
        chip.type = 'button';
        chip.className = 'reminder-offset-chip is-selected';
        chip.dataset.offset = String(minutes);
        chip.textContent = `${reminderOffsetLabel(minutes)} ×`;
        chip.title = 'הסר';
        chip.addEventListener('click', () => {
            reminderDefaultsState.customOffsets = reminderDefaultsState.customOffsets
                .filter((value) => value !== minutes);
            renderReminderDefaultsCustom();
            reminderDefaultsState.dirty = true;
            setReminderDefaultsSaved(false);
        });
        list.append(chip);
    });
}

function paintDefaultOffsets(offsets) {
    const presetValues = new Set((typeof REMINDER_PRESETS !== 'undefined' ? REMINDER_PRESETS : []).map(([value]) => value));
    const selected = new Set((offsets || []).map(Number));
    reminderDefaultsState.customOffsets = [...selected].filter((value) => !presetValues.has(value));
    document.querySelectorAll('#reminderDefaultsOffsets .reminder-offset-chip').forEach((chip) => {
        if (!chip.dataset.offset) {
            return;
        }
        const on = selected.has(Number(chip.dataset.offset));
        chip.classList.toggle('is-selected', on);
        chip.setAttribute('aria-pressed', on ? 'true' : 'false');
    });
    renderReminderDefaultsCustom();
}

function pickReminderDefaultsPerson(personId) {
    reminderDefaultsState.personId = personId ? String(personId) : null;
    const hint = document.getElementById('reminderDefaultsPersonHint');
    const offsetsWrap = document.getElementById('reminderDefaultsOffsets');
    const customWrap = document.getElementById('reminderDefaultsCustom');
    const saveBtn = document.getElementById('reminderDefaultsSave');
    document.querySelectorAll('#reminderDefaultsPeople .reminder-defaults-person-chip').forEach((chip) => {
        const on = chip.dataset.personId === reminderDefaultsState.personId;
        chip.classList.toggle('is-selected', on);
        chip.setAttribute('aria-selected', on ? 'true' : 'false');
    });
    if (!reminderDefaultsState.personId) {
        if (hint) {
            hint.hidden = false;
        }
        if (offsetsWrap) {
            offsetsWrap.hidden = true;
        }
        if (customWrap) {
            customWrap.hidden = true;
        }
        if (saveBtn) {
            saveBtn.hidden = true;
        }
        return;
    }
    if (hint) {
        hint.hidden = true;
    }
    if (offsetsWrap) {
        offsetsWrap.hidden = false;
    }
    if (customWrap) {
        customWrap.hidden = false;
    }
    if (saveBtn) {
        saveBtn.hidden = false;
    }
    const person = reminderDefaultsState.people.find(
        (item) => String(item.id) === reminderDefaultsState.personId,
    );
    paintDefaultOffsets(person ? person.reminder_defaults : []);
    reminderDefaultsState.dirty = false;
    setReminderDefaultsSaved(false);
    setReminderDefaultsError('');
}

function buildReminderDefaultsOffsets() {
    const grid = document.getElementById('reminderDefaultsOffsets');
    if (!grid || grid.dataset.ready === '1') {
        return;
    }
    (typeof REMINDER_PRESETS !== 'undefined' ? REMINDER_PRESETS : []).forEach(([minutes, label]) => {
        const chip = document.createElement('button');
        chip.type = 'button';
        chip.className = 'reminder-offset-chip';
        chip.dataset.offset = String(minutes);
        chip.textContent = label;
        chip.setAttribute('aria-pressed', 'false');
        chip.addEventListener('click', () => {
            const on = !chip.classList.contains('is-selected');
            chip.classList.toggle('is-selected', on);
            chip.setAttribute('aria-pressed', on ? 'true' : 'false');
            reminderDefaultsState.dirty = true;
            setReminderDefaultsSaved(false);
        });
        grid.append(chip);
    });
    const other = document.createElement('button');
    other.type = 'button';
    other.className = 'reminder-offset-chip';
    other.textContent = 'אחר';
    other.setAttribute('aria-expanded', 'false');
    other.setAttribute('aria-controls', 'reminderDefaultsCustomRow');
    other.addEventListener('click', () => {
        const row = document.getElementById('reminderDefaultsCustomRow');
        if (!row) {
            return;
        }
        row.hidden = !row.hidden;
        const open = !row.hidden;
        other.setAttribute('aria-expanded', open ? 'true' : 'false');
        other.classList.toggle('is-open', open);
        if (open) {
            document.getElementById('reminderDefaultsCustomAmount')?.focus();
        }
    });
    grid.append(other);
    grid.dataset.ready = '1';
}

function renderReminderDefaultsPeople(people) {
    const root = document.getElementById('reminderDefaultsPeople');
    if (!root) {
        return;
    }
    root.replaceChildren();
    const list = (people || []).filter((person) => person.receives_reminders);
    if (!list.length) {
        const empty = document.createElement('p');
        empty.className = 'text-muted small mb-0';
        empty.textContent = 'אין אנשים לתזכורות. הוסיפו אדם בכרטיס המשתמשים.';
        root.append(empty);
        pickReminderDefaultsPerson(null);
        return;
    }
    list.forEach((person) => {
        const chip = document.createElement('button');
        chip.type = 'button';
        chip.className = 'reminder-defaults-person-chip';
        chip.dataset.personId = String(person.id);
        chip.textContent = person.name;
        chip.setAttribute('role', 'tab');
        chip.addEventListener('click', () => pickReminderDefaultsPerson(person.id));
        root.append(chip);
    });
    if (reminderDefaultsState.personId
        && list.some((person) => String(person.id) === reminderDefaultsState.personId)) {
        pickReminderDefaultsPerson(reminderDefaultsState.personId);
    } else {
        pickReminderDefaultsPerson(list[0].id);
    }
}

async function loadReminderDefaultsEditor() {
    const section = document.getElementById('settingsReminderDefaults');
    if (!section) {
        return;
    }
    try {
        const response = await fetch('/api/users?role=reminders');
        if (!response.ok) {
            return;
        }
        const people = await response.json();
        reminderDefaultsState.people = Array.isArray(people) ? people : [];
        renderReminderDefaultsPeople(reminderDefaultsState.people);
    } catch (error) {
        reminderDefaultsState.people = [];
        renderReminderDefaultsPeople([]);
    }
}

async function saveReminderDefaults() {
    const personId = reminderDefaultsState.personId;
    if (!personId) {
        return;
    }
    const person = reminderDefaultsState.people.find((item) => String(item.id) === String(personId));
    if (!person) {
        return;
    }
    const offsets = selectedDefaultOffsets();
    setReminderDefaultsError('');
    const response = await fetch(`/api/users/${personId}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            name: person.name,
            telegram_chat_id: person.telegram_chat_id,
            reminder_defaults: offsets,
        }),
    });
    const saved = await response.json().catch(() => ({}));
    if (!response.ok) {
        setReminderDefaultsError(saved.error || 'השמירה נכשלה');
        return;
    }
    reminderDefaultsState.people = reminderDefaultsState.people.map((item) => (
        String(item.id) === String(personId) ? { ...item, reminder_defaults: offsets } : item
    ));
    if (typeof shiftUiState !== 'undefined') {
        shiftUiState.people = (shiftUiState.people || []).map((item) => (
            String(item.id) === String(personId) ? { ...item, reminder_defaults: offsets } : item
        ));
    }
    reminderDefaultsState.dirty = false;
    setReminderDefaultsSaved(true);
    if (typeof showMessage === 'function') {
        showMessage('נשמר');
    }
}

function addReminderDefaultsCustom() {
    const amountInput = document.getElementById('reminderDefaultsCustomAmount');
    const unitInput = document.getElementById('reminderDefaultsCustomUnit');
    const minutes = customOffsetMinutes(amountInput?.value, unitInput?.value);
    if (minutes === null) {
        setReminderDefaultsError('מספר חיובי של דקות, שעות או ימים (עד שנה)');
        return;
    }
    const presetChip = document.querySelector(
        `#reminderDefaultsOffsets .reminder-offset-chip[data-offset="${minutes}"]`,
    );
    if (presetChip) {
        presetChip.classList.add('is-selected');
        presetChip.setAttribute('aria-pressed', 'true');
    } else if (!reminderDefaultsState.customOffsets.includes(minutes)) {
        reminderDefaultsState.customOffsets.push(minutes);
        reminderDefaultsState.customOffsets.sort((a, b) => a - b);
        renderReminderDefaultsCustom();
    }
    reminderDefaultsState.dirty = true;
    setReminderDefaultsSaved(false);
    setReminderDefaultsError('');
    if (amountInput) {
        amountInput.value = '';
    }
}

function initReminderDefaultsSettings() {
    const section = document.getElementById('settingsReminderDefaults');
    if (!section || reminderDefaultsState.ready) {
        return;
    }
    reminderDefaultsState.ready = true;
    buildReminderDefaultsOffsets();
    document.getElementById('reminderDefaultsSave')?.addEventListener('click', saveReminderDefaults);
    document.getElementById('reminderDefaultsCustomAdd')?.addEventListener('click', addReminderDefaultsCustom);
    document.getElementById('reminderDefaultsCustomAmount')?.addEventListener('keydown', (event) => {
        if (event.key === 'Enter') {
            event.preventDefault();
            addReminderDefaultsCustom();
        }
    });
    const openSection = () => {
        if (section.classList.contains('is-open')) {
            loadReminderDefaultsEditor();
        }
    };
    section.querySelector('.settings-section-toggle')?.addEventListener('click', () => {
        window.setTimeout(openSection, 0);
    });
    if (section.classList.contains('is-open')) {
        loadReminderDefaultsEditor();
    }
}

document.addEventListener('DOMContentLoaded', () => {
    initReminderDefaultsSettings();
});