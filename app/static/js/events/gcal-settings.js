// עמוד ההגדרות: חיבור ליומן גוגל. הכתובת המלאה לא חוזרת מהשרת.

function initGcalSettings() {
    const form = document.getElementById('gcalSourceForm');
    if (!form) {
        return;
    }
    form.addEventListener('submit', saveGcalSource);
    document.getElementById('gcalSyncAll')?.addEventListener('click', syncAllGcalSources);
    document.getElementById('gcalNoColor')?.addEventListener('change', syncGcalColorInput);
    document.getElementById('gcalSourceList')?.addEventListener('click', onGcalListClick);
    document.getElementById('gcalSourceList')?.addEventListener('change', onGcalListChange);
    syncGcalColorInput();
    loadGcalSources();
}

function syncGcalColorInput() {
    const box = document.getElementById('gcalNoColor');
    const color = document.getElementById('gcalColor');
    if (!box || !color) {
        return;
    }
    color.disabled = box.checked;
}

function gcalError(message) {
    const el = document.getElementById('gcalFormError');
    if (!el) {
        return;
    }
    if (!message) {
        el.hidden = true;
        el.textContent = '';
        return;
    }
    el.hidden = false;
    el.textContent = message;
}

function formatGcalSyncTime(iso) {
    if (!iso) {
        return '';
    }
    const parsed = new Date(iso);
    if (Number.isNaN(parsed.getTime())) {
        return '';
    }
    return new Intl.DateTimeFormat('he-IL', {
        timeZone: 'Asia/Jerusalem',
        day: '2-digit',
        month: '2-digit',
        year: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
    }).format(parsed);
}

async function loadGcalSources() {
    const list = document.getElementById('gcalSourceList');
    if (!list) {
        return;
    }
    const response = await fetch('/api/gcal/sources');
    if (!response.ok) {
        gcalError('לא הצלחנו לטעון את החיבורים');
        return;
    }
    const sources = await response.json();
    renderGcalSources(sources);
}

function renderGcalSources(sources) {
    const list = document.getElementById('gcalSourceList');
    if (!list) {
        return;
    }
    if (!sources.length) {
        list.innerHTML = '<p class="text-muted mb-0">עדיין אין יומן מחובר.</p>';
        return;
    }
    list.innerHTML = sources.map(renderGcalSource).join('');
}

function renderGcalSource(source) {
    const id = Number(source.id);
    const label = escapeHtml(source.label || 'יומן גוגל');
    const masked = escapeHtml(source.url_masked || '');
    const color = /^#[0-9a-fA-F]{6}$/.test(source.color || '') ? source.color : '#4285f4';
    const noColor = !source.color;
    const enabled = source.enabled ? 'checked' : '';
    const when = formatGcalSyncTime(source.last_sync_at);
    const synced = when ? `סונכרן לאחרונה: ${escapeHtml(when)}` : 'עדיין לא סונכרן בהצלחה';
    const error = source.last_error
        ? `<p class="reminder-form-error gcal-source-error">${escapeHtml(source.last_error)}</p>`
        : '';
    const count = Number(source.event_count) || 0;
    return `
        <article class="gcal-source" data-source-id="${id}">
            <div class="gcal-source-head">
                <strong>${label}</strong>
                <span class="text-muted">${count} אירועים</span>
            </div>
            <p class="gcal-source-url" dir="ltr">${masked}</p>
            <p class="gcal-source-sync text-muted">${synced}</p>
            ${error}
            <div class="row g-2 align-items-end">
                <div class="col-12 col-md-5">
                    <label class="form-label" for="gcal-label-${id}">שם</label>
                    <input class="form-control" id="gcal-label-${id}" data-gcal-label value="${label === 'יומן גוגל' && !source.label ? '' : escapeHtml(source.label || '')}" maxlength="80">
                </div>
                <div class="col-auto">
                    <label class="form-label" for="gcal-color-${id}">צבע</label>
                    <input type="color" class="form-control form-control-color" id="gcal-color-${id}" data-gcal-color value="${color}" ${noColor ? 'disabled' : ''}>
                </div>
                <div class="col-auto">
                    <div class="form-check mb-2">
                        <input class="form-check-input" type="checkbox" id="gcal-nocolor-${id}" data-gcal-nocolor ${noColor ? 'checked' : ''}>
                        <label class="form-check-label" for="gcal-nocolor-${id}">בלי צבע</label>
                    </div>
                </div>
                <div class="col-auto">
                    <div class="form-check form-switch mb-2">
                        <input class="form-check-input" type="checkbox" role="switch" id="gcal-enabled-${id}" data-gcal-enabled ${enabled}>
                        <label class="form-check-label" for="gcal-enabled-${id}">פעיל</label>
                    </div>
                </div>
                <div class="col-12">
                    <label class="form-label" for="gcal-url-${id}">החלפת כתובת (רק אם מעתיקים חדשה)</label>
                    <input type="url" class="form-control" id="gcal-url-${id}" data-gcal-url dir="ltr" autocomplete="off" spellcheck="false" placeholder="השאירו ריק כדי לא לשנות">
                </div>
            </div>
            <div class="d-flex flex-wrap gap-2 mt-2">
                <button type="button" class="btn btn-primary btn-sm" data-gcal-action="save">שמירה</button>
                <button type="button" class="btn btn-outline-secondary btn-sm" data-gcal-action="sync">סנכרן עכשיו</button>
                <button type="button" class="btn btn-outline-danger btn-sm" data-gcal-action="delete">מחיקה</button>
            </div>
        </article>
    `;
}

function gcalCard(target) {
    return target.closest('.gcal-source');
}

function gcalCardPayload(card) {
    const noColor = card.querySelector('[data-gcal-nocolor]')?.checked;
    const url = (card.querySelector('[data-gcal-url]')?.value || '').trim();
    const payload = {
        label: card.querySelector('[data-gcal-label]')?.value || '',
        color: noColor ? '' : (card.querySelector('[data-gcal-color]')?.value || ''),
        enabled: Boolean(card.querySelector('[data-gcal-enabled]')?.checked),
    };
    if (url) {
        payload.ical_url = url;
    }
    return payload;
}

async function onGcalListClick(event) {
    const button = event.target.closest('[data-gcal-action]');
    if (!button) {
        return;
    }
    const card = gcalCard(button);
    if (!card) {
        return;
    }
    const id = card.getAttribute('data-source-id');
    const action = button.getAttribute('data-gcal-action');
    gcalError('');
    if (action === 'delete') {
        if (!window.confirm('למחוק את החיבור ואת האירועים שנמשכו ממנו?')) {
            return;
        }
        const response = await fetch(`/api/gcal/sources/${id}`, { method: 'DELETE' });
        if (!response.ok) {
            const body = await response.json().catch(() => ({}));
            gcalError(body.error || 'לא הצלחנו למחוק');
            return;
        }
        await loadGcalSources();
        return;
    }
    if (action === 'save') {
        const response = await fetch(`/api/gcal/sources/${id}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(gcalCardPayload(card)),
        });
        const body = await response.json().catch(() => ({}));
        if (!response.ok) {
            gcalError(body.error || 'לא הצלחנו לשמור');
            return;
        }
        await loadGcalSources();
        return;
    }
    if (action === 'sync') {
        button.disabled = true;
        const response = await fetch(`/api/gcal/sources/${id}/sync`, { method: 'POST' });
        const body = await response.json().catch(() => ({}));
        button.disabled = false;
        if (!response.ok) {
            gcalError(body.error || 'הסנכרון נכשל');
            return;
        }
        if (body.last_error) {
            gcalError(body.last_error);
        }
        await loadGcalSources();
    }
}

function onGcalListChange(event) {
    const box = event.target.closest('[data-gcal-nocolor]');
    if (!box) {
        return;
    }
    const card = gcalCard(box);
    const color = card?.querySelector('[data-gcal-color]');
    if (color) {
        color.disabled = box.checked;
    }
}

async function saveGcalSource(event) {
    event.preventDefault();
    gcalError('');
    const button = document.getElementById('gcalAdd');
    const noColor = document.getElementById('gcalNoColor')?.checked;
    const payload = {
        ical_url: document.getElementById('gcalUrl')?.value || '',
        label: document.getElementById('gcalLabel')?.value || '',
        color: noColor ? '' : (document.getElementById('gcalColor')?.value || ''),
        enabled: Boolean(document.getElementById('gcalEnabled')?.checked),
    };
    if (button) {
        button.disabled = true;
    }
    try {
        const response = await fetch('/api/gcal/sources', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
        });
        const body = await response.json().catch(() => ({}));
        if (!response.ok) {
            gcalError(body.error || 'לא הצלחנו לחבר את היומן');
            return;
        }
        document.getElementById('gcalSourceForm')?.reset();
        const enabled = document.getElementById('gcalEnabled');
        if (enabled) {
            enabled.checked = true;
        }
        const color = document.getElementById('gcalColor');
        if (color) {
            color.value = '#4285f4';
        }
        syncGcalColorInput();
        if (body.last_error) {
            gcalError(body.last_error);
        }
        await loadGcalSources();
    } finally {
        if (button) {
            button.disabled = false;
        }
    }
}

async function syncAllGcalSources() {
    const button = document.getElementById('gcalSyncAll');
    gcalError('');
    if (button) {
        button.disabled = true;
    }
    try {
        const response = await fetch('/api/gcal/sync', { method: 'POST' });
        const body = await response.json().catch(() => ({}));
        if (!response.ok) {
            gcalError(body.error || 'הסנכרון נכשל');
            return;
        }
        const failed = (Array.isArray(body) ? body : []).find((item) => item.last_error);
        if (failed) {
            gcalError(failed.last_error);
        }
        await loadGcalSources();
    } finally {
        if (button) {
            button.disabled = false;
        }
    }
}
