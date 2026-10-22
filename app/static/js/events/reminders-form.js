// טופס התזכורת בתוך מודל האירוע. נשאר סגור עד שמסמנים «תזכורת».

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
    customOffsets: [],
    ready: false,
};

const REMINDER_MAX_MINUTES = 365 * 24 * 60;

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

function renderCustomOffsets() {
    const list = document.getElementById('quick_reminder_custom_list');
    if (!list) {
        return;
    }
    list.replaceChildren();
    reminderFormState.customOffsets.forEach((minutes) => {
        const chip = document.createElement('button');
        chip.type = 'button';
        chip.className = 'reminder-offset-chip is-selected';
        chip.dataset.offset = String(minutes);
        chip.textContent = `${reminderOffsetLabel(minutes)} ×`;
        chip.title = 'הסר';
        chip.addEventListener('click', () => {
            reminderFormState.customOffsets = reminderFormState.customOffsets.filter((value) => value !== minutes);
            renderCustomOffsets();
        });
        list.append(chip);
    });
}

function renderReminderRecipients(people, selected) {
    const root = document.getElementById('quick_reminder_recipients');
    if (!root) {
        return;
    }
    root.replaceChildren();
    if (!people.length) {
        const empty = document.createElement('p');
        empty.className = 'reminder-empty-people';
        empty.textContent = 'עדיין אין אנשים. בלי נמען התזכורת תופיע בדפדפן כשהלוח פתוח.';
        root.append(empty);
        return;
    }
    const wrap = document.createElement('div');
    wrap.className = 'reminder-recipient-list';
    people.forEach((person) => {
        const label = document.createElement('label');
        const input = document.createElement('input');
        input.type = 'checkbox';
        input.value = String(person.id);
        input.checked = selected.has(Number(person.id));
        const name = document.createElement('span');
        name.textContent = person.name;
        label.append(input, name);
        wrap.append(label);
    });
    root.append(wrap);
}

function selectPreset(minutes) {
    const chip = document.querySelector(`#quick_reminder_offsets .reminder-offset-chip[data-offset="${minutes}"]`);
    if (!chip) {
        return false;
    }
    chip.classList.add('is-selected');
    chip.setAttribute('aria-pressed', 'true');
    return true;
}

function addCustomReminder() {
    const amountInput = document.getElementById('quick_reminder_custom_amount');
    const unitInput = document.getElementById('quick_reminder_custom_unit');
    const minutes = customOffsetMinutes(amountInput?.value, unitInput?.value);
    if (minutes === null) {
        setReminderError('מספר חיובי של דקות, שעות או ימים (עד שנה)');
        return;
    }
    if (selectPreset(minutes)) {
        reminderFormState.customOffsets = reminderFormState.customOffsets.filter((value) => value !== minutes);
        renderCustomOffsets();
        setReminderError('');
        if (amountInput) {
            amountInput.value = '';
        }
        return;
    }
    if (!reminderFormState.customOffsets.includes(minutes)) {
        reminderFormState.customOffsets.push(minutes);
        reminderFormState.customOffsets.sort((a, b) => a - b);
    }
    renderCustomOffsets();
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
            const on = !chip.classList.contains('is-selected');
            chip.classList.toggle('is-selected', on);
            chip.setAttribute('aria-pressed', on ? 'true' : 'false');
            setReminderError('');
        });
        grid.append(chip);
    });

    checkbox.addEventListener('change', () => {
        setReminderPanelOpen(checkbox.checked);
        if (!checkbox.checked) {
            setReminderError('');
        }
    });

    const customToggle = document.getElementById('quick_reminder_custom_toggle');
    const customRow = document.getElementById('quick_reminder_custom_row');
    if (customToggle && customRow) {
        customToggle.addEventListener('click', () => {
            customRow.hidden = !customRow.hidden;
            customToggle.setAttribute('aria-expanded', customRow.hidden ? 'false' : 'true');
            if (!customRow.hidden) {
                document.getElementById('quick_reminder_custom_amount')?.focus();
            }
        });
    }

    document.getElementById('quick_reminder_custom_add')?.addEventListener('click', addCustomReminder);
    document.getElementById('quick_reminder_custom_amount')?.addEventListener('keydown', (event) => {
        if (event.key === 'Enter') {
            event.preventDefault();
            addCustomReminder();
        }
    });
}

async function fillReminderFields(reminders) {
    initReminderFields();
    const token = ++reminderFormState.fillToken;
    const list = Array.isArray(reminders) ? reminders : [];
    const offsets = list
        .map((item) => Number(item.offset_minutes))
        .filter((value) => Number.isInteger(value) && value >= 0);
    const presetValues = new Set(REMINDER_PRESETS.map(([value]) => value));
    reminderFormState.customOffsets = [...new Set(offsets.filter((value) => !presetValues.has(value)))];
    const selectedPresets = new Set(offsets.filter((value) => presetValues.has(value)));
    document.querySelectorAll('#quick_reminder_offsets .reminder-offset-chip').forEach((chip) => {
        const on = selectedPresets.has(Number(chip.dataset.offset));
        chip.classList.toggle('is-selected', on);
        chip.setAttribute('aria-pressed', on ? 'true' : 'false');
    });
    renderCustomOffsets();
    const checkbox = document.getElementById('quick_reminder_enabled');
    const enabled = offsets.length > 0;
    if (checkbox) {
        checkbox.checked = enabled;
    }
    setReminderPanelOpen(enabled);
    setReminderError('');

    const selectedPeople = new Set();
    list.forEach((item) => {
        (item.recipient_ids || []).forEach((id) => selectedPeople.add(Number(id)));
    });

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
    renderReminderRecipients(Array.isArray(people) ? people : [], selectedPeople);
}

function readReminderFields() {
    const checkbox = document.getElementById('quick_reminder_enabled');
    if (!checkbox || !checkbox.checked) {
        setReminderError('');
        return [];
    }
    const offsets = new Set(reminderFormState.customOffsets);
    document.querySelectorAll('#quick_reminder_offsets .reminder-offset-chip.is-selected').forEach((chip) => {
        offsets.add(Number(chip.dataset.offset));
    });
    if (!offsets.size) {
        setReminderError('בחרו מתי להזכיר, או בטלו את התזכורת');
        return null;
    }
    setReminderError('');
    const recipientIds = [];
    document.querySelectorAll('#quick_reminder_recipients input:checked').forEach((input) => {
        recipientIds.push(Number(input.value));
    });
    return [...offsets].sort((a, b) => a - b).map((offset) => ({
        offset_minutes: offset,
        recipient_ids: recipientIds,
    }));
}
