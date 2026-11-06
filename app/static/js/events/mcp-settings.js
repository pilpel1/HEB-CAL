// עמוד ההגדרות: מפתחות MCP. הטוקן המלא מוצג פעם אחת, בחלון שנפתח אחרי היצירה.

let mcpUserPayload = null;

function initMcpSettings() {
    const form = document.getElementById('mcpKeyForm');
    if (!form) {
        return;
    }
    form.addEventListener('submit', createMcpKey);
    document.getElementById('mcpKeyList')?.addEventListener('click', onMcpKeyListClick);
    document.getElementById('mcpKeyModal')?.addEventListener('click', onMcpCopyClick);
    document.getElementById('settings-mcp')?.addEventListener('settings-section-toggle', (event) => {
        if (!event.detail || !event.detail.open) {
            return;
        }
        // הגוף היה display:none. בדפדפן של טלפון רשימה שמתמלאת כשהאב מוסתר
        // נשארת ריקה בבורר, והטופס אומר «יש לבחור פריט מהרשימה». בונים מחדש
        // אחרי שהכרטיס באמת מוצג.
        window.requestAnimationFrame(() => {
            paintMcpUsers(true);
            loadMcpKeys();
        });
    });
    loadMcpKeys();
}

function mcpSectionIsOpen() {
    return Boolean(document.getElementById('settings-mcp')?.classList.contains('is-open'));
}

function mcpError(message) {
    const el = document.getElementById('mcpKeyError');
    if (!el) {
        return;
    }
    el.hidden = !message;
    el.textContent = message || '';
}

function mcpPermissionLabel(permission) {
    return permission === 'write' ? 'קריאה וכתיבה' : 'קריאה בלבד';
}

function mcpStatusLabel(status) {
    if (status === 'revoked') {
        return 'מבוטל';
    }
    if (status === 'expired') {
        return 'פג תוקף';
    }
    return 'פעיל';
}

function formatMcpStamp(iso) {
    if (!iso) {
        return '—';
    }
    const parsed = new Date(iso);
    if (Number.isNaN(parsed.getTime())) {
        return '—';
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

async function loadMcpKeys() {
    const list = document.getElementById('mcpKeyList');
    const select = document.getElementById('mcpKeyUser');
    if (!list || !select) {
        return;
    }
    const response = await fetch('/api/mcp-keys');
    if (!response.ok) {
        mcpError('לא הצלחנו לטעון את המפתחות');
        return;
    }
    const data = await response.json();
    const form = document.getElementById('mcpKeyForm');
    if (form) {
        form.dataset.csrf = data.csrf_token || '';
    }
    mcpUserPayload = data;
    paintMcpUsers(mcpSectionIsOpen());
    renderMcpKeys(data.keys || []);
}

function paintMcpUsers(remount) {
    const select = document.getElementById('mcpKeyUser');
    const empty = document.getElementById('mcpKeyNoUsers');
    const form = document.getElementById('mcpKeyForm');
    if (!select || !mcpUserPayload) {
        return;
    }
    const users = mcpUserPayload.users || [];
    if (!users.length) {
        select.required = false;
        select.disabled = true;
        select.innerHTML = '';
        select.removeAttribute('data-mcp-mounted');
        if (form) {
            form.hidden = true;
        }
        if (empty) {
            empty.hidden = false;
        }
        const create = document.getElementById('mcpKeyCreate');
        if (create) {
            create.disabled = true;
        }
        return;
    }
    if (form) {
        form.hidden = false;
    }
    if (empty) {
        empty.hidden = true;
    }
    const create = document.getElementById('mcpKeyCreate');
    if (create) {
        create.disabled = false;
    }
    const previous = select.value;
    const options = users.map((user) => (
        `<option value="${Number(user.id)}">${escapeHtml(user.name || '')}</option>`
    )).join('');
    let target = select;
    if (remount) {
        const fresh = select.cloneNode(false);
        fresh.removeAttribute('data-mcp-mounted');
        select.replaceWith(fresh);
        target = fresh;
    }
    target.disabled = false;
    target.required = true;
    target.innerHTML = options;
    const preferred = previous || (mcpUserPayload.default_user_id ? String(mcpUserPayload.default_user_id) : '');
    if (preferred && target.querySelector(`option[value="${preferred}"]`)) {
        target.value = preferred;
    } else {
        target.selectedIndex = 0;
    }
    target.dataset.mcpMounted = mcpSectionIsOpen() ? 'visible' : 'hidden';
}

function renderMcpKeys(keys) {
    const list = document.getElementById('mcpKeyList');
    if (!list) {
        return;
    }
    if (!keys.length) {
        list.innerHTML = '<p class="text-muted mb-0">עדיין אין מפתחות.</p>';
        return;
    }
    const rows = keys.map((key) => {
        const id = Number(key.id);
        const revoke = key.status === 'active'
            ? `<button type="button" class="btn btn-outline-danger btn-sm" data-mcp-revoke="${id}">ביטול</button>`
            : '';
        return `
            <tr>
                <td data-label="קידומת" dir="ltr">${escapeHtml(key.prefix || '')}</td>
                <td data-label="שם">${escapeHtml(key.label || '')}</td>
                <td data-label="משתמש">${escapeHtml(key.user_name || '')}</td>
                <td data-label="הרשאה">${escapeHtml(mcpPermissionLabel(key.permission))}</td>
                <td data-label="שימוש אחרון">${escapeHtml(formatMcpStamp(key.last_used_at))}</td>
                <td data-label="תפוגה">${escapeHtml(formatMcpStamp(key.effective_expires_at || key.expires_at))} (${escapeHtml(mcpStatusLabel(key.status))})</td>
                <td data-label="">${revoke}</td>
            </tr>
        `;
    }).join('');
    list.innerHTML = `
        <table class="table mcp-keys-table mb-0">
            <thead>
                <tr>
                    <th>קידומת</th>
                    <th>שם</th>
                    <th>משתמש</th>
                    <th>הרשאה</th>
                    <th>שימוש אחרון</th>
                    <th>תפוגה</th>
                    <th></th>
                </tr>
            </thead>
            <tbody>${rows}</tbody>
        </table>
    `;
}

function mcpCursorConfig(origin) {
    return JSON.stringify({
        mcpServers: {
            'heb-cal': {
                url: `${origin}/mcp`,
                headers: { Authorization: 'Bearer ${env:HEB_CAL_MCP_KEY}' },
            },
        },
    }, null, 2);
}

function mcpClaudeConfig(origin, token) {
    return JSON.stringify({
        mcpServers: {
            'heb-cal': {
                command: 'npx',
                args: ['-y', 'mcp-remote@0.16.0', `${origin}/mcp`, '--header', 'Authorization:${HEB_CAL_AUTH}'],
                env: { HEB_CAL_AUTH: `Bearer ${token}` },
            },
        },
    }, null, 2);
}

function showMcpKeyOnce(token) {
    const origin = window.location.origin;
    document.getElementById('mcpKeyToken').textContent = token;
    document.getElementById('mcpCursorConfig').textContent = mcpCursorConfig(origin);
    document.getElementById('mcpClaudeConfig').textContent = mcpClaudeConfig(origin, token);
    const status = document.getElementById('mcpCopyStatus');
    if (status) {
        status.hidden = true;
    }
    const modal = document.getElementById('mcpKeyModal');
    if (modal && window.bootstrap?.Modal) {
        window.bootstrap.Modal.getOrCreateInstance(modal).show();
    }
}

async function createMcpKey(event) {
    event.preventDefault();
    mcpError('');
    const form = document.getElementById('mcpKeyForm');
    const userId = document.getElementById('mcpKeyUser')?.value;
    const payload = {
        user_id: userId ? Number(userId) : null,
        label: document.getElementById('mcpKeyLabel')?.value || '',
        permission: document.getElementById('mcpKeyPermission')?.value || 'read',
    };
    const absolute = document.getElementById('mcpKeyAbsolute')?.value;
    if (absolute) {
        payload.absolute_expires_on = absolute;
    }
    const response = await fetch('/api/mcp-keys', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-CSRF-Token': form?.dataset.csrf || '',
        },
        body: JSON.stringify(payload),
    });
    const body = await response.json().catch(() => ({}));
    if (!response.ok) {
        mcpError(body.error || 'לא הצלחנו ליצור מפתח');
        return;
    }
    document.getElementById('mcpKeyLabel').value = '';
    document.getElementById('mcpKeyAbsolute').value = '';
    document.getElementById('mcpKeyPermission').value = 'read';
    showMcpKeyOnce(body.token);
    await loadMcpKeys();
}

async function onMcpKeyListClick(event) {
    const button = event.target.closest('[data-mcp-revoke]');
    if (!button) {
        return;
    }
    const label = button.closest('tr')?.querySelector('td')?.textContent || '';
    if (!window.confirm(`לבטל את המפתח ${label}? אי אפשר לשחזר אותו.`)) {
        return;
    }
    mcpError('');
    const form = document.getElementById('mcpKeyForm');
    const response = await fetch(`/api/mcp-keys/${button.getAttribute('data-mcp-revoke')}`, {
        method: 'DELETE',
        headers: { 'X-CSRF-Token': form?.dataset.csrf || '' },
    });
    const body = await response.json().catch(() => ({}));
    if (!response.ok) {
        mcpError(body.error || 'לא הצלחנו לבטל');
        return;
    }
    await loadMcpKeys();
}

async function onMcpCopyClick(event) {
    const button = event.target.closest('[data-mcp-copy]');
    if (!button) {
        return;
    }
    const text = document.getElementById(button.getAttribute('data-mcp-copy'))?.textContent || '';
    try {
        await navigator.clipboard.writeText(text);
    } catch (error) {
        mcpError('לא הצלחנו להעתיק. סמנו את הטקסט והעתיקו ידנית.');
        return;
    }
    const status = document.getElementById('mcpCopyStatus');
    if (status) {
        status.hidden = false;
    }
}
