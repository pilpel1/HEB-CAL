// צבעי אירועים ואנשים: פלטה אחת מ-/api/colors (ברירת מחדל + מותאם).
// כל בורר נצבע מחדש מהתשובה האחרונה. תשובה ישנה שעדיין בדרך לא דורסת אותה.

const NAMED_EVENT_SWATCH = {
    cyan: 'rgb(0, 255, 255)',
    yellow: 'rgb(255, 255, 0)',
    orange: 'rgb(255, 165, 0)',
    green: 'rgb(0, 128, 0)',
};

let eventColorPalette = [];
let eventColorLoadSeq = 0;

function eventColorSwatchCss(colorCode) {
    const named = NAMED_EVENT_SWATCH[String(colorCode || '').toLowerCase()];
    return named || String(colorCode || '#888888');
}

function currentEventColors() {
    return eventColorPalette;
}

function eventColorName(colorCode) {
    const code = String(colorCode || '').trim().toLowerCase();
    if (!code) {
        return '';
    }
    const row = eventColorPalette.find((color) => (
        String(color.color_code || '').toLowerCase() === code
    ));
    return row && row.name ? row.name : '';
}

function paletteColorCodes() {
    const codes = eventColorPalette.map((color) => color.color_code).filter(Boolean);
    return codes.length ? codes : ['cyan', 'yellow', 'orange', 'green'];
}

function colorsForPicker(colors, selected) {
    const list = Array.isArray(colors) ? colors.slice() : [];
    const code = String(selected || '').trim();
    if (!code) {
        return list;
    }
    const known = list.some((color) => (
        String(color.color_code || '').toLowerCase() === code.toLowerCase()
    ));
    if (!known) {
        list.push({ color_code: code, name: eventColorName(code) || code });
    }
    return list;
}

async function loadEventColors() {
    const seq = ++eventColorLoadSeq;
    try {
        const response = await fetch('/api/colors', { cache: 'no-store' });
        if (!response.ok) {
            throw new Error(String(response.status));
        }
        const colors = await response.json();
        const list = Array.isArray(colors) ? colors : [];
        if (seq !== eventColorLoadSeq) {
            return null;
        }
        eventColorPalette = list;
        return list;
    } catch (error) {
        console.error('שגיאה בטעינת צבעים:', error);
        return null;
    }
}

function paintColorPicker(picker, colors) {
    if (!picker) {
        return;
    }
    picker.querySelectorAll('.quick-color-swatch:not(.is-none)').forEach((el) => el.remove());
    for (const color of colors) {
        const button = document.createElement('button');
        button.type = 'button';
        button.className = 'quick-color-swatch';
        const code = color.color_code || '';
        if (NAMED_EVENT_SWATCH[String(code).toLowerCase()]) {
            button.classList.add(`color-${String(code).toLowerCase()}`);
        } else {
            button.style.backgroundColor = eventColorSwatchCss(code);
        }
        button.dataset.color = code;
        const label = color.name || code;
        button.title = label;
        button.setAttribute('aria-label', label);
        picker.appendChild(button);
    }
}

function paintEventFormSwatches(colors) {
    const picker = document.querySelector('#quickEventModal .quick-color-picker');
    if (!picker) {
        return;
    }
    const selected = document.getElementById('quick_color')?.value || '';
    paintColorPicker(picker, colorsForPicker(colors, selected));
    if (typeof setQuickColor === 'function') {
        setQuickColor(selected);
    }
}

function paintPersonColorSwatches(colors) {
    const picker = document.getElementById('personColorPicker');
    if (!picker) {
        return;
    }
    const state = typeof shiftUiState !== 'undefined' ? shiftUiState : null;
    const editing = typeof currentShiftEditId === 'function' && currentShiftEditId();
    const dirty = Boolean(state && state.rulesDirty);
    if (
        state
        && state.colorIsSuggested
        && !editing
        && !dirty
        && typeof suggestPersonColor === 'function'
    ) {
        setPersonColor(suggestPersonColor());
    }
    const selected = state ? (state.personColor || '') : '';
    paintColorPicker(picker, colorsForPicker(colors, selected));
    if (typeof setPersonColor === 'function') {
        setPersonColor(selected);
    }
}

function paintColorSearchOptions(colors) {
    const select = document.getElementById('colorSearch');
    if (!select) {
        return;
    }
    const current = select.value;
    const keep = [
        { value: '', label: 'כל הצבעים' },
        { value: 'null', label: 'ללא צבע' },
    ];
    select.innerHTML = '';
    for (const item of keep) {
        const option = document.createElement('option');
        option.value = item.value;
        option.textContent = item.label;
        select.appendChild(option);
    }
    for (const color of colors) {
        const option = document.createElement('option');
        option.value = color.color_code;
        option.textContent = color.name;
        select.appendChild(option);
    }
    if ([...select.options].some((option) => option.value === current)) {
        select.value = current;
    }
}

async function refreshEventColorChoices() {
    const colors = await loadEventColors();
    if (!colors) {
        return null;
    }
    paintEventFormSwatches(colors);
    paintPersonColorSwatches(colors);
    paintColorSearchOptions(colors);
    return colors;
}

function bindEventFormColorPicker() {
    const picker = document.querySelector('#quickEventModal .quick-color-picker');
    if (!picker || picker.dataset.colorBound === '1') {
        return;
    }
    picker.dataset.colorBound = '1';
    picker.addEventListener('click', (event) => {
        const swatch = event.target.closest('.quick-color-swatch');
        if (!swatch || !picker.contains(swatch)) {
            return;
        }
        if (typeof setQuickColor === 'function') {
            setQuickColor(swatch.dataset.color || '');
        }
    });
}

function settingsColorError(message) {
    const box = document.getElementById('settingsColorError');
    if (!box) {
        return;
    }
    if (!message) {
        box.hidden = true;
        box.textContent = '';
        return;
    }
    box.hidden = false;
    box.textContent = message;
}

function resetSettingsColorForm() {
    const idInput = document.getElementById('settingsColorId');
    const nameInput = document.getElementById('settingsColorName');
    const hexInput = document.getElementById('settingsColorHex');
    const saveBtn = document.getElementById('settingsColorSave');
    const cancelBtn = document.getElementById('settingsColorCancel');
    if (idInput) {
        idInput.value = '';
    }
    if (nameInput) {
        nameInput.value = '';
    }
    if (hexInput) {
        hexInput.value = '#8899aa';
        hexInput.disabled = false;
    }
    if (saveBtn) {
        saveBtn.textContent = 'הוספה';
    }
    if (cancelBtn) {
        cancelBtn.hidden = true;
    }
    settingsColorError('');
}

function paintSettingsColorsList(colors) {
    const list = document.getElementById('settingsColorsList');
    if (!list) {
        return;
    }
    list.innerHTML = colors.map((color) => {
        const code = escapeHtml(color.color_code || '');
        const name = escapeHtml(color.name || '');
        const swatch = eventColorSwatchCss(color.color_code);
        const actions = color.is_default
            ? '<span class="text-muted small">ברירת מחדל</span>'
            : `<button type="button" class="btn btn-outline-secondary btn-sm" data-color-edit="${color.id}">עריכה</button>`
                + `<button type="button" class="btn btn-outline-danger btn-sm" data-color-delete="${color.id}">מחיקה</button>`;
        return `<li class="settings-color-row" data-color-id="${color.id}">`
            + `<span class="settings-color-swatch" style="background:${swatch}"></span>`
            + `<span class="settings-color-name">${name}</span>`
            + `<span class="settings-color-code" dir="ltr">${code}</span>`
            + `<span class="settings-color-actions">${actions}</span></li>`;
    }).join('');
}

function syncOpenPersonColor(colors) {
    if (typeof shiftUiState === 'undefined' || typeof setPersonColor !== 'function') {
        return;
    }
    if (shiftUiState.rulesDirty) {
        return;
    }
    const editingId = typeof currentShiftEditId === 'function' ? currentShiftEditId() : '';
    if (!editingId) {
        return;
    }
    const person = (shiftUiState.people || []).find((item) => String(item.id) === String(editingId));
    if (!person || (person.color || '') === (shiftUiState.personColor || '')) {
        return;
    }
    setPersonColor(person.color || '');
    paintPersonColorSwatches(colors);
}

async function reloadSettingsColors() {
    const colors = await refreshEventColorChoices();
    if (!colors) {
        return currentEventColors();
    }
    paintSettingsColorsList(colors);
    if (typeof loadReminderPeople === 'function') {
        await loadReminderPeople();
    }
    syncOpenPersonColor(colors);
    return colors;
}

function startEditSettingsColor(color) {
    document.getElementById('settingsColorId').value = String(color.id);
    document.getElementById('settingsColorName').value = color.name || '';
    const hexInput = document.getElementById('settingsColorHex');
    hexInput.value = /^#[0-9a-fA-F]{6}$/.test(color.color_code) ? color.color_code : '#8899aa';
    hexInput.disabled = Boolean(color.is_default);
    document.getElementById('settingsColorSave').textContent = 'שמירה';
    document.getElementById('settingsColorCancel').hidden = false;
    settingsColorError('');
}

async function saveSettingsColor(event) {
    event.preventDefault();
    const id = document.getElementById('settingsColorId').value;
    const name = document.getElementById('settingsColorName').value;
    const colorCode = document.getElementById('settingsColorHex').value;
    const payload = { name, color_code: colorCode };
    try {
        const response = await fetch(id ? `/api/colors/${id}` : '/api/colors', {
            method: id ? 'PUT' : 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
        });
        const body = await response.json();
        if (!response.ok) {
            settingsColorError(body.error || 'לא הצלחנו לשמור');
            return;
        }
        resetSettingsColorForm();
        await reloadSettingsColors();
    } catch (error) {
        console.error(error);
        settingsColorError('לא הצלחנו לשמור');
    }
}

async function deleteSettingsColor(colorId) {
    if (!confirm('למחוק את הצבע?')) {
        return;
    }
    try {
        const response = await fetch(`/api/colors/${colorId}`, { method: 'DELETE' });
        const body = await response.json().catch(() => ({}));
        if (!response.ok) {
            settingsColorError(body.error || 'אי אפשר למחוק את הצבע');
            return;
        }
        resetSettingsColorForm();
        await reloadSettingsColors();
    } catch (error) {
        console.error(error);
        settingsColorError('אי אפשר למחוק את הצבע');
    }
}

function initSettingsColors() {
    const root = document.getElementById('settingsColors');
    if (!root || root.dataset.bound === '1') {
        return;
    }
    root.dataset.bound = '1';
    document.getElementById('settingsColorForm')?.addEventListener('submit', saveSettingsColor);
    document.getElementById('settingsColorCancel')?.addEventListener('click', resetSettingsColorForm);
    document.getElementById('settingsColorsList')?.addEventListener('click', async (event) => {
        const editBtn = event.target.closest('[data-color-edit]');
        if (editBtn) {
            const colors = (await loadEventColors()) || currentEventColors();
            const color = colors.find((item) => String(item.id) === String(editBtn.getAttribute('data-color-edit')));
            if (color) {
                startEditSettingsColor(color);
            }
            return;
        }
        const deleteBtn = event.target.closest('[data-color-delete]');
        if (deleteBtn) {
            await deleteSettingsColor(deleteBtn.getAttribute('data-color-delete'));
        }
    });
    reloadSettingsColors();
}

function initEventColorChoices() {
    bindEventFormColorPicker();
    if (document.getElementById('settingsColors')) {
        initSettingsColors();
        return;
    }
    refreshEventColorChoices();
}

document.addEventListener('DOMContentLoaded', initEventColorChoices);
