// צבעי אירועים: בחירה בטופס, ו-CRUD בעמוד ההגדרות

const NAMED_EVENT_SWATCH = {
    cyan: 'rgb(0, 255, 255)',
    yellow: 'rgb(255, 255, 0)',
    orange: 'rgb(255, 165, 0)',
    green: 'rgb(0, 128, 0)',
};

function eventColorSwatchCss(colorCode) {
    const named = NAMED_EVENT_SWATCH[String(colorCode || '').toLowerCase()];
    return named || String(colorCode || '#888888');
}

async function loadEventColors() {
    try {
        const response = await fetch('/api/colors');
        const colors = await response.json();
        return Array.isArray(colors) ? colors : [];
    } catch (error) {
        console.error('שגיאה בטעינת צבעים:', error);
        return [];
    }
}

function paintEventFormSwatches(colors) {
    const picker = document.querySelector('#quickEventModal .quick-color-picker');
    if (!picker) {
        return;
    }
    const selected = document.getElementById('quick_color')?.value || '';
    picker.querySelectorAll('.quick-color-swatch:not(.is-none)').forEach((el) => el.remove());
    for (const color of colors) {
        const button = document.createElement('button');
        button.type = 'button';
        button.className = 'quick-color-swatch';
        const code = color.color_code || '';
        if (NAMED_EVENT_SWATCH[code]) {
            button.classList.add(`color-${code}`);
        } else {
            button.style.backgroundColor = eventColorSwatchCss(code);
        }
        button.dataset.color = code;
        button.title = color.name || code;
        button.setAttribute('aria-label', color.name || code);
        picker.appendChild(button);
    }
    if (typeof setQuickColor === 'function') {
        setQuickColor(selected);
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
    paintEventFormSwatches(colors);
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

async function reloadSettingsColors() {
    const colors = await refreshEventColorChoices();
    paintSettingsColorsList(colors);
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
            settingsColorError(body.error || 'שגיאה בשמירת הצבע');
            return;
        }
        resetSettingsColorForm();
        await reloadSettingsColors();
    } catch (error) {
        console.error(error);
        settingsColorError('שגיאה בשמירת הצבע');
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
            settingsColorError(body.error || 'לא ניתן למחוק את הצבע');
            return;
        }
        resetSettingsColorForm();
        await reloadSettingsColors();
    } catch (error) {
        console.error(error);
        settingsColorError('לא ניתן למחוק את הצבע');
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
            const colors = await loadEventColors();
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
