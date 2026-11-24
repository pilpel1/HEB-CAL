// תזכורות במודל האירוע — לשונית לכל אדם עם offsets משלו.

const REMINDER_PRESETS = [
    [0, 'בזמן'],
    [5, '5 דק׳'],
    [10, '10 דק׳'],
    [15, '15 דק׳'],
    [30, '30 דק׳'],
    [60, 'שעה'],
    [120, 'שעתיים'],
    [180, '3 שעות'],
    [360, '6 שעות'],
    [720, '12 שעות'],
    [1440, 'יום'],
    [2880, 'יומיים'],
    [4320, '3 ימים'],
    [10080, 'שבוע'],
];

const reminderFormState = {
    fillToken: 0,
    ready: false,
    allowDefaultPrefill: false,
    people: [],
    activePersonId: null,
    /** @type {Record<number, {presets: Set<number>, customs: number[]}>} */
    byPerson: {},
};

const REMINDER_MAX_MINUTES = 365 * 24 * 60;
const REMINDER_PRESET_VALUES = new Set(REMINDER_PRESETS.map(([value]) => value));

function reminderOffsetLabel(minutes) {
    const preset = REMINDER_PRESETS.find(([value]) => value === minutes);
    if (preset) {
        return preset[1];
    }
    if (minutes % 1440 === 0) {
        const days = minutes / 1440;
        return days === 1 ? 'יום' : `${days} ימים`;
    }
    if (minutes % 60 === 0) {
        const hours = minutes / 60;
        if (hours === 1) {
            return 'שעה';
        }
        if (hours === 2) {
            return 'שעתיים';
        }
        return `${hours} שעות`;
    }
    return minutes === 1 ? 'דקה' : `${minutes} דק׳`;
}

function customOffsetMinutes(amount, unit) {
    const count = Number(amount);
    if (!Number.isInteger(count) || count <= 0) {
        return null;
    }
    const factor = { minutes: 1, hours: 60, days: 1440 }[unit];
    if (!factor) {
        return null;
    }
    const minutes = count * factor;
    if (minutes > REMINDER_MAX_MINUTES) {
        return null;
    }
    return minutes;
}

function setReminderError(message) {
    const error = document.getElementById('quick_reminder_error');
    if (!error) {
        return;
    }
    error.textContent = message || '';
    error.hidden = !message;
}

function setReminderPanelOpen(isOpen) {
    const panel = document.getElementById('quick_reminder_panel');
    if (panel) {
        panel.hidden = !isOpen;
    }
}

function emptyPersonReminderState() {
    return { presets: new Set(), customs: [] };
}

function ensurePersonReminderState(personId) {
    const id = Number(personId);
    if (!reminderFormState.byPerson[id]) {
        reminderFormState.byPerson[id] = emptyPersonReminderState();
    }
    return reminderFormState.byPerson[id];
}

function personReminderOffsets(personId) {
    const state = ensurePersonReminderState(personId);
    return new Set([...state.presets, ...state.customs]);
}

function personReminderCount(personId) {
    return personReminderOffsets(personId).size;
}

function totalReminderCount() {
    return Object.keys(reminderFormState.byPerson).reduce(
        (sum, id) => sum + personReminderCount(id),
        0,
    );
}

function setPersonOffsets(personId, offsets) {
    const state = ensurePersonReminderState(personId);
    const selected = new Set([...offsets].map(Number).filter((value) => Number.isInteger(value) && value >= 0));
    state.presets = new Set([...selected].filter((value) => REMINDER_PRESET_VALUES.has(value)));
    state.customs = [...selected].filter((value) => !REMINDER_PRESET_VALUES.has(value)).sort((a, b) => a - b);
}

function hebrewAndNames(names) {
    if (!names.length) {
        return '';
    }
    if (names.length === 1) {
        return `ל${names[0]}`;
    }
    if (names.length === 2) {
        return `ל${names[0]} ול${names[1]}`;
    }
    const head = names.slice(0, -1).map((name) => `ל${name}`).join(', ');
    return `${head} ול${names[names.length - 1]}`;
}

function setReminderChatWarn(message) {
    const node = document.getElementById('quick_reminder_chat_warn');
    if (!node) {
        return;
    }
    node.textContent = message || '';
    node.hidden = !message;
}

function updateReminderChatWarning() {
    const personId = reminderFormState.activePersonId;
    if (!personId || personReminderCount(personId) === 0) {
        setReminderChatWarn('');
        return;
    }
    const person = reminderFormState.people.find((item) => Number(item.id) === Number(personId));
    if (!person) {
        setReminderChatWarn('');
        return;
    }
    if ((person.telegram_chat_id || '').trim()) {
        setReminderChatWarn('');
        return;
    }
    setReminderChatWarn(
        `${hebrewAndNames([person.name])} אין קישור לטלגרם — התזכורת תופיע רק בדפדפן כשהלוח פתוח.`,
    );
}

function renderCustomOffsets() {
    const list = document.getElementById('quick_reminder_custom_list');
    if (!list) {
        return;
    }
    list.replaceChildren();
    const personId = reminderFormState.activePersonId;
    if (!personId) {
        return;
    }
    const state = ensurePersonReminderState(personId);
    state.customs.forEach((minutes) => {
        const chip = document.createElement('button');
        chip.type = 'button';
        chip.className = 'reminder-offset-chip is-selected';
        chip.dataset.offset = String(minutes);
        chip.textContent = `${reminderOffsetLabel(minutes)} ×`;
        chip.title = 'הסר';
        chip.addEventListener('click', () => {
            state.customs = state.customs.filter((value) => value !== minutes);
            renderPersonTabs();
            renderActivePersonOffsets();
        });
        list.append(chip);
    });
}

function renderActivePersonOffsets() {
    const personId = reminderFormState.activePersonId;
    const body = document.getElementById('quick_reminder_person_body');
    if (body) {
        body.hidden = !personId;
    }
    document.querySelectorAll('#quick_reminder_offsets .reminder-offset-chip').forEach((chip) => {
        if (!chip.dataset.offset) {
            return;
        }
        const state = personId ? ensurePersonReminderState(personId) : null;
        const on = Boolean(state && state.presets.has(Number(chip.dataset.offset)));
        chip.classList.toggle('is-selected', on);
        chip.setAttribute('aria-pressed', on ? 'true' : 'false');
    });
    renderCustomOffsets();
    updateReminderChatWarning();
}

function renderPersonTabs() {
    const root = document.getElementById('quick_reminder_person_tabs');
    const empty = document.getElementById('quick_reminder_empty_people');
    if (!root) {
        return;
    }
    root.replaceChildren();
    const people = reminderFormState.people || [];
    if (empty) {
        empty.hidden = people.length > 0;
    }
    if (!people.length) {
        reminderFormState.activePersonId = null;
        const body = document.getElementById('quick_reminder_person_body');
        if (body) {
            body.hidden = true;
        }
        return;
    }
    if (
        !reminderFormState.activePersonId
        || !people.some((person) => Number(person.id) === Number(reminderFormState.activePersonId))
    ) {
        reminderFormState.activePersonId = Number(people[0].id);
    }
    people.forEach((person) => {
        const id = Number(person.id);
        const btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'reminder-person-tab';
        btn.setAttribute('role', 'tab');
        btn.dataset.personId = String(id);
        const active = Number(reminderFormState.activePersonId) === id;
        btn.classList.toggle('is-active', active);
        btn.setAttribute('aria-selected', active ? 'true' : 'false');
        const name = document.createElement('span');
        name.className = 'reminder-person-tab-name';
        name.textContent = person.name;
        btn.append(name);
        const count = personReminderCount(id);
        /* תמיד badge (גם 0) — אותו מבנה ויזואלי לכל אדם */
        const badge = document.createElement('span');
        badge.className = 'reminder-person-tab-badge';
        badge.textContent = String(count);
        badge.title = count > 0 ? `${count} תזכורות` : 'בלי תזכורות';
        badge.hidden = count === 0;
        btn.append(badge);
        if (count > 0) {
            btn.classList.add('has-reminders');
        }
        if (!(person.telegram_chat_id || '').trim()) {
            btn.classList.add('no-telegram');
            btn.title = 'בלי קישור לטלגרם';
        }
        btn.addEventListener('click', () => {
            reminderFormState.activePersonId = id;
            renderPersonTabs();
            renderActivePersonOffsets();
            setReminderError('');
        });
        root.append(btn);
    });
}

function addCustomReminder() {
    const personId = reminderFormState.activePersonId;
    if (!personId) {
        setReminderError('בחרו אדם ללשונית');
        return;
    }
    const amountInput = document.getElementById('quick_reminder_custom_amount');
    const unitInput = document.getElementById('quick_reminder_custom_unit');
    const minutes = customOffsetMinutes(amountInput?.value, unitInput?.value);
    if (minutes === null) {
        setReminderError('מספר חיובי של דקות, שעות או ימים (עד שנה)');
        return;
    }
    const state = ensurePersonReminderState(personId);
    if (REMINDER_PRESET_VALUES.has(minutes)) {
        state.presets.add(minutes);
        state.customs = state.customs.filter((value) => value !== minutes);
    } else if (!state.customs.includes(minutes)) {
        state.customs.push(minutes);
        state.customs.sort((a, b) => a - b);
    }
    renderPersonTabs();
    renderActivePersonOffsets();
    setReminderError('');
    if (amountInput) {
        amountInput.value = '';
    }
}

function initReminderFields() {
    if (reminderFormState.ready) {
        return;
    }
    const grid = document.getElementById('quick_reminder_offsets');
    const checkbox = document.getElementById('quick_reminder_enabled');
    if (!grid || !checkbox) {
        return;
    }
    reminderFormState.ready = true;

    REMINDER_PRESETS.forEach(([minutes, label]) => {
        const chip = document.createElement('button');
        chip.type = 'button';
        chip.className = 'reminder-offset-chip';
        chip.dataset.offset = String(minutes);
        chip.textContent = label;
        chip.setAttribute('aria-pressed', 'false');
        chip.addEventListener('click', () => {
            const personId = reminderFormState.activePersonId;
            if (!personId) {
                return;
            }
            const state = ensurePersonReminderState(personId);
            if (state.presets.has(minutes)) {
                state.presets.delete(minutes);
            } else {
                state.presets.add(minutes);
            }
            renderPersonTabs();
            renderActivePersonOffsets();
            setReminderError('');
        });
        grid.append(chip);
    });

    const customRow = document.getElementById('quick_reminder_custom_row');
    const other = document.createElement('button');
    other.type = 'button';
    other.id = 'quick_reminder_custom_toggle';
    other.className = 'reminder-offset-chip';
    other.textContent = 'אחר';
    other.setAttribute('aria-expanded', 'false');
    other.setAttribute('aria-controls', 'quick_reminder_custom_row');
    other.addEventListener('click', () => {
        if (!customRow) {
            return;
        }
        customRow.hidden = !customRow.hidden;
        const open = !customRow.hidden;
        other.setAttribute('aria-expanded', open ? 'true' : 'false');
        other.classList.toggle('is-open', open);
        if (open) {
            document.getElementById('quick_reminder_custom_amount')?.focus();
        }
    });
    grid.append(other);

    checkbox.addEventListener('change', () => {
        setReminderPanelOpen(checkbox.checked);
        if (!checkbox.checked) {
            setReminderError('');
        }
    });

    document.getElementById('quick_reminder_custom_add')?.addEventListener('click', addCustomReminder);
    document.getElementById('quick_reminder_custom_amount')?.addEventListener('keydown', (event) => {
        if (event.key === 'Enter') {
            event.preventDefault();
            addCustomReminder();
        }
    });
}

function applyReminderDefaultsForPeople(people) {
    if (!reminderFormState.allowDefaultPrefill) {
        return;
    }
    if (totalReminderCount() > 0) {
        return;
    }
    (people || []).forEach((person) => {
        const defaults = (person.reminder_defaults || []).map(Number).filter((value) => Number.isInteger(value));
        if (!defaults.length) {
            return;
        }
        setPersonOffsets(person.id, defaults);
    });
}

function applyShiftPersonReminderDefaults(personId) {
    if (!reminderFormState.allowDefaultPrefill || !personId) {
        return;
    }
    if (personReminderCount(personId) > 0) {
        return;
    }
    const person = (reminderFormState.people.length
        ? reminderFormState.people
        : (typeof shiftUiState !== 'undefined' ? shiftUiState.people : [])
    ).find((item) => String(item.id) === String(personId));
    const offsets = (person?.reminder_defaults || []).map(Number);
    if (!offsets.length) {
        return;
    }
    setPersonOffsets(personId, offsets);
    reminderFormState.activePersonId = Number(personId);
    const checkbox = document.getElementById('quick_reminder_enabled');
    if (checkbox) {
        checkbox.checked = true;
    }
    setReminderPanelOpen(true);
    renderPersonTabs();
    renderActivePersonOffsets();
}

async function fillReminderFields(reminders) {
    initReminderFields();
    const token = ++reminderFormState.fillToken;
    const list = Array.isArray(reminders) ? reminders : [];
    reminderFormState.byPerson = {};
    reminderFormState.activePersonId = null;

    list.forEach((item) => {
        const offset = Number(item.offset_minutes);
        if (!Number.isInteger(offset) || offset < 0) {
            return;
        }
        let personIds = [];
        if (item.person_id != null && item.person_id !== '') {
            personIds = [Number(item.person_id)];
        } else {
            personIds = (item.recipient_ids || []).map(Number);
        }
        personIds.forEach((personId) => {
            if (!Number.isInteger(personId) || personId <= 0) {
                return;
            }
            const state = ensurePersonReminderState(personId);
            if (REMINDER_PRESET_VALUES.has(offset)) {
                state.presets.add(offset);
            } else if (!state.customs.includes(offset)) {
                state.customs.push(offset);
                state.customs.sort((a, b) => a - b);
            }
        });
    });

    const enabled = totalReminderCount() > 0;
    const checkbox = document.getElementById('quick_reminder_enabled');
    if (checkbox) {
        checkbox.checked = enabled;
    }
    setReminderPanelOpen(enabled);
    setReminderError('');
    reminderFormState.allowDefaultPrefill = (
        !document.getElementById('quick_event_id')?.value && !enabled
    );

    let people = [];
    try {
        const response = await fetch('/api/reminder-people?role=reminders');
        if (response.ok) {
            people = await response.json();
        }
    } catch (error) {
        people = [];
    }
    if (token !== reminderFormState.fillToken) {
        return;
    }
    reminderFormState.people = Array.isArray(people) ? people : [];
    if (reminderFormState.allowDefaultPrefill) {
        applyReminderDefaultsForPeople(reminderFormState.people);
        if (totalReminderCount() > 0) {
            if (checkbox) {
                checkbox.checked = true;
            }
            setReminderPanelOpen(true);
        }
    }
    const withReminders = reminderFormState.people.find(
        (person) => personReminderCount(person.id) > 0,
    );
    reminderFormState.activePersonId = withReminders
        ? Number(withReminders.id)
        : (reminderFormState.people[0] ? Number(reminderFormState.people[0].id) : null);
    renderPersonTabs();
    renderActivePersonOffsets();
}

function readReminderFields() {
    const checkbox = document.getElementById('quick_reminder_enabled');
    if (!checkbox || !checkbox.checked) {
        setReminderError('');
        return [];
    }
    const payload = [];
    Object.keys(reminderFormState.byPerson).forEach((rawId) => {
        const personId = Number(rawId);
        const offsets = [...personReminderOffsets(personId)].sort((a, b) => a - b);
        offsets.forEach((offset) => {
            payload.push({
                person_id: personId,
                offset_minutes: offset,
                recipient_ids: [personId],
            });
        });
    });
    if (!payload.length) {
        setReminderError('בחרו מתי להזכיר בלשונית של לפחות אדם אחד, או בטלו את התזכורת');
        return null;
    }
    setReminderError('');
    return payload;
}
