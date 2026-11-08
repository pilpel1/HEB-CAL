// עמוד ההגדרות: לקוחות OAuth וחיבורים. הסוד מוצג פעם אחת.

let oauthOverviewPayload = null;

function initOauthSettings() {
    const form = document.getElementById('oauthClientForm');
    if (!form) {
        return;
    }
    form.addEventListener('submit', createOauthClient);
    document.getElementById('oauthClientList')?.addEventListener('click', onOauthClientListClick);
    document.getElementById('oauthConnectionList')?.addEventListener('click', onOauthConnectionListClick);
    document.getElementById('oauthCopyMcpUrl')?.addEventListener('click', copyOauthMcpUrl);
    document.getElementById('oauthCopySecret')?.addEventListener('click', copyOauthSecret);
    document.getElementById('settings-oauth')?.addEventListener('settings-section-toggle', (event) => {
        if (!event.detail || !event.detail.open) {
            return;
        }
        window.requestAnimationFrame(() => loadOauthOverview());
    });
    loadOauthOverview();
}

function oauthAdminError(message) {
    const el = document.getElementById('oauthAdminError');
    if (!el) {
        return;
    }
    el.hidden = !message;
    el.textContent = message || '';
}

async function loadOauthOverview() {
    const response = await fetch('/api/oauth/overview');
    const body = await response.json().catch(() => ({}));
    oauthOverviewPayload = body;
    const form = document.getElementById('oauthClientForm');
    if (form) {
        form.dataset.csrf = body.csrf_token || '';
    }
    const originMissing = document.getElementById('oauthOriginMissing');
    if (originMissing) {
        originMissing.hidden = Boolean(body.public_origin);
    }
    const urlEl = document.getElementById('oauthMcpUrl');
    if (urlEl) {
        urlEl.textContent = body.mcp_url || '—';
    }
    paintOauthClients(body.clients || []);
    paintOauthConnections(body.connections || []);
}

function paintOauthClients(clients) {
    const root = document.getElementById('oauthClientList');
    if (!root) {
        return;
    }
    if (!clients.length) {
        root.textContent = 'אין לקוחות רשומים.';
        return;
    }
    const rows = clients.map((client) => {
        const status = client.status === 'revoked' ? 'מבוטל' : 'פעיל';
        const revoke = client.status === 'revoked'
            ? ''
            : `<button type="button" class="btn btn-sm btn-outline-danger" data-oauth-revoke-client="${client.client_id}">ביטול</button>`;
        return `<tr><td>${escapeOauth(client.name)}</td><td dir="ltr">${escapeOauth(client.client_id)}</td><td>${status}</td><td>${revoke}</td></tr>`;
    }).join('');
    root.innerHTML = `<table class="table table-sm"><thead><tr><th>שם</th><th>Client ID</th><th>מצב</th><th></th></tr></thead><tbody>${rows}</tbody></table>`;
}

function oauthScopeLabel(scopes) {
    const parts = String(scopes || '').split(/\s+/).filter(Boolean);
    if (parts.includes('hebcal:write')) {
        return 'קריאה וכתיבה';
    }
    if (parts.includes('hebcal:read')) {
        return 'קריאה';
    }
    return scopes || '';
}

function paintOauthConnections(items) {
    const root = document.getElementById('oauthConnectionList');
    if (!root) {
        return;
    }
    const active = items.filter((item) => item.status === 'active');
    if (!active.length) {
        root.textContent = 'אין חיבורים פעילים.';
        return;
    }
    const rows = active.map((item) => {
        return `<tr><td>${escapeOauth(item.user_name)}</td><td>${escapeOauth(item.client_name)}</td><td>${escapeOauth(oauthScopeLabel(item.scopes))}</td><td><button type="button" class="btn btn-sm btn-outline-danger" data-oauth-revoke-grant="${item.id}">ניתוק</button></td></tr>`;
    }).join('');
    root.innerHTML = `<table class="table table-sm"><thead><tr><th>משתמש</th><th>לקוח</th><th>הרשאות</th><th></th></tr></thead><tbody>${rows}</tbody></table>`;
}

function escapeOauth(value) {
    return String(value || '')
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;');
}

async function createOauthClient(event) {
    event.preventDefault();
    oauthAdminError('');
    const name = document.getElementById('oauthClientName')?.value || '';
    const raw = document.getElementById('oauthClientRedirects')?.value || '';
    const redirects = raw.split(/\s+/).filter(Boolean);
    const form = document.getElementById('oauthClientForm');
    const response = await fetch('/api/oauth/clients', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-CSRF-Token': form?.dataset.csrf || '',
        },
        body: JSON.stringify({ name: name, redirect_uris: redirects }),
    });
    const body = await response.json().catch(() => ({}));
    if (!response.ok) {
        oauthAdminError(body.error || 'לא הצלחנו ליצור לקוח');
        return;
    }
    document.getElementById('oauthClientName').value = '';
    document.getElementById('oauthClientRedirects').value = '';
    const box = document.getElementById('oauthClientOnce');
    if (box) {
        box.hidden = false;
        document.getElementById('oauthOnceId').textContent = body.client_id || '';
        document.getElementById('oauthOnceSecret').textContent = body.client_secret || '';
    }
    await loadOauthOverview();
}

async function onOauthClientListClick(event) {
    const button = event.target.closest('[data-oauth-revoke-client]');
    if (!button) {
        return;
    }
    if (!window.confirm('לבטל את הלקוח? החיבורים שלו ינותקו.')) {
        return;
    }
    const form = document.getElementById('oauthClientForm');
    const response = await fetch(`/api/oauth/clients/${encodeURIComponent(button.getAttribute('data-oauth-revoke-client'))}`, {
        method: 'DELETE',
        headers: { 'X-CSRF-Token': form?.dataset.csrf || '' },
    });
    if (!response.ok) {
        oauthAdminError('לא הצלחנו לבטל את הלקוח');
        return;
    }
    await loadOauthOverview();
}

async function onOauthConnectionListClick(event) {
    const button = event.target.closest('[data-oauth-revoke-grant]');
    if (!button) {
        return;
    }
    if (!window.confirm('לנתק את החיבור הזה?')) {
        return;
    }
    const form = document.getElementById('oauthClientForm');
    const response = await fetch(`/api/oauth/connections/${button.getAttribute('data-oauth-revoke-grant')}`, {
        method: 'DELETE',
        headers: { 'X-CSRF-Token': form?.dataset.csrf || '' },
    });
    if (!response.ok) {
        oauthAdminError('לא הצלחנו לנתק');
        return;
    }
    await loadOauthOverview();
}

async function copyOauthMcpUrl() {
    const text = document.getElementById('oauthMcpUrl')?.textContent || '';
    try {
        await navigator.clipboard.writeText(text);
    } catch (error) {
        oauthAdminError('לא הצלחנו להעתיק');
    }
}

async function copyOauthSecret() {
    const text = document.getElementById('oauthOnceSecret')?.textContent || '';
    try {
        await navigator.clipboard.writeText(text);
    } catch (error) {
        oauthAdminError('לא הצלחנו להעתיק');
    }
}
