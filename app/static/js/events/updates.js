// מסך «עדכון גרסה» והנקודה על גלגל השיניים. הטקסט מהשרת נכנס כ-textContent.

function shouldHardReloadAfterUpdate(opts) {
    var version = (opts && opts.version) || '';
    var before = (opts && opts.before) || '';
    var target = (opts && opts.target) || '';
    var status = (opts && opts.status) || '';
    var watching = !!(opts && opts.watching);
    var sawDisconnect = !!(opts && opts.sawDisconnect);
    if (!watching || !version) {
        return false;
    }
    if (status === 'failed') {
        return false;
    }
    var isNew = (before && version !== before) || (target && version === target);
    if (!isNew) {
        return false;
    }
    if (sawDisconnect) {
        return true;
    }
    if (status === 'running') {
        return false;
    }
    return status === 'success' || status === 'idle';
}

(function () {
    var csrf = '';
    var latest = '';
    var pollTimer = 0;
    var sawRunning = false;
    var sawDisconnect = false;
    var beforeVersion = '';
    var targetVersion = '';
    var pollStartedAt = 0;
    var POLL_MS = 2000;
    var POLL_TIMEOUT_MS = 150000;

    function byId(id) {
        return document.getElementById(id);
    }

    function show(el, on) {
        if (!el) {
            return;
        }
        el.hidden = !on;
    }

    function setText(id, text) {
        var el = byId(id);
        if (el) {
            el.textContent = text || '';
        }
    }

    async function api(url, options) {
        var headers = {Accept: 'application/json'};
        if (options && options.body) {
            headers['Content-Type'] = 'application/json';
        }
        if (csrf) {
            headers['X-CSRF-Token'] = csrf;
        }
        var response = await fetch(url, {
            method: (options && options.method) || 'GET',
            headers: headers,
            body: options && options.body,
            credentials: 'same-origin',
            cache: 'no-store',
        });
        var data = {};
        try {
            data = await response.json();
        } catch (error) {
            data = {};
        }
        if (data && data.csrf_token) {
            csrf = data.csrf_token;
        }
        return {ok: response.ok, status: response.status, data: data};
    }

    function setError(text) {
        var el = byId('updateError');
        if (!el) {
            return;
        }
        el.textContent = text || '';
        show(el, !!text);
    }

    function fillList(id, lines) {
        var list = byId(id);
        if (!list) {
            return;
        }
        list.textContent = '';
        (lines || []).forEach(function (line) {
            var item = document.createElement('li');
            item.textContent = line;
            list.appendChild(item);
        });
    }

    function stateFromCache(cached) {
        if (!cached || cached.checked === false) {
            return (cached && cached.message) || 'עדיין לא נבדק.';
        }
        if (cached.available) {
            return cached.checked_label || '';
        }
        var parts = [];
        if (cached.message) {
            parts.push(cached.message);
        }
        if (cached.checked_label) {
            parts.push(cached.checked_label);
        }
        return parts.join(' ');
    }

    function renderOffer(source, info) {
        var current = (info && info.current) || '';
        var offered = (source && source.latest) || '';
        var available = !!(source && source.available && offered && offered !== current);
        show(byId('updateOffer'), available);
        if (!available) {
            return;
        }
        latest = offered;
        setText('updateLatest', latest);
        fillList('updateHighlights', source.highlights || []);
        show(byId('updateEmptyNotes'), !(source.highlights && source.highlights.length));
        var link = byId('updateReleaseLink');
        if (link) {
            link.textContent = '';
            if (source.url && source.url.indexOf('https://github.com/') === 0) {
                var anchor = document.createElement('a');
                anchor.href = source.url;
                anchor.target = '_blank';
                anchor.rel = 'noopener';
                anchor.textContent = 'לדף הגרסה';
                link.appendChild(anchor);
            }
        }
        show(byId('updateApplyBtn'), !!(info && info.can_apply));
    }

    function showDockerCommand(info) {
        var command = byId('updateDockerCommand');
        if (!command) {
            return;
        }
        command.textContent = (info && info.docker_command) || '';
        show(command, !!(info && info.docker_command));
    }

    function renderProgress(status) {
        var state = (status && status.state) || 'idle';
        var active = state === 'running' || state === 'failed' || state === 'success';
        show(byId('updateProgress'), active && state !== 'idle');
        setText('updateProgressMessage', (status && status.message) || '');
        fillList('updateProgressLines', (status && status.lines) || []);
        if (state === 'failed') {
            setError((status && (status.error || status.message)) || 'העדכון נכשל.');
            var applyFailed = byId('updateApplyBtn');
            if (applyFailed) {
                applyFailed.disabled = false;
            }
            if (latest) {
                show(byId('updateOffer'), true);
            }
        }
        if (state === 'running') {
            sawRunning = true;
            show(byId('updateOffer'), false);
            setText('updateState', '');
        }
        if (state === 'success' && sawRunning) {
            setError('');
        }
        return state;
    }

    async function pingHealth() {
        var url = '/api/updates/health?_=' + Date.now();
        var response = await fetch(url, {
            method: 'GET',
            headers: {Accept: 'application/json', 'Cache-Control': 'no-cache'},
            credentials: 'same-origin',
            cache: 'no-store',
        });
        if (!response.ok) {
            throw new Error('health');
        }
        var data = {};
        try {
            data = await response.json();
        } catch (error) {
            data = {};
        }
        return data;
    }

    function hardReload() {
        function go() {
            try {
                var url = new URL(window.location.href);
                url.searchParams.set('_upd', String(Date.now()));
                window.location.replace(url.href);
            } catch (error) {
                window.location.reload();
            }
        }
        var finish = function () {
            go();
        };
        if (!(navigator.serviceWorker && navigator.serviceWorker.getRegistrations)) {
            finish();
            return;
        }
        var clearCaches = function () {
            if (!window.caches || !caches.keys) {
                return Promise.resolve();
            }
            return caches.keys().then(function (keys) {
                return Promise.all(keys.map(function (key) {
                    return caches.delete(key);
                }));
            });
        };
        navigator.serviceWorker.getRegistrations().then(function (regs) {
            regs.forEach(function (reg) {
                if (reg.waiting) {
                    reg.waiting.postMessage({type: 'SKIP_WAITING'});
                }
                if (reg.active) {
                    reg.active.postMessage({type: 'SKIP_WAITING'});
                }
            });
            if (navigator.serviceWorker.controller) {
                navigator.serviceWorker.controller.postMessage({type: 'SKIP_WAITING'});
            }
            return clearCaches();
        }).then(finish, finish);
    }

    function showReloadPrompt() {
        show(byId('updateProgress'), true);
        setText('updateProgressMessage', 'העדכון כנראה הסתיים, אבל הדף לא התרענן לבד.');
        setText('updateReloadMessage', 'לחצו «רענן» כדי לטעון את הגרסה החדשה.');
        show(byId('updateReloadPrompt'), true);
    }

    function applySummary(info) {
        if (info.csrf_token) {
            csrf = info.csrf_token;
        }
        setText('updateCurrentVersion', info.current || '');
        setText('updateModeHint', info.instructions || info.hint || '');
        var state = stateFromCache(info.cached);
        if (info.block) {
            setText('updateState', info.block);
        } else {
            setText('updateState', state);
        }
        show(byId('updateCheckBtn'), true);
        showDockerCommand(info);
        renderOffer(info.cached, info);
        var status = info.status || {};
        renderProgress(status);
        if (status.state === 'running') {
            beforeVersion = beforeVersion || info.current || '';
            targetVersion = targetVersion || status.target || latest;
            startPoll();
        }
    }

    function startPoll() {
        if (pollTimer) {
            return;
        }
        pollStartedAt = Date.now();
        sawDisconnect = false;
        show(byId('updateReloadPrompt'), false);

        async function tick() {
            if (Date.now() - pollStartedAt > POLL_TIMEOUT_MS) {
                pollTimer = 0;
                showReloadPrompt();
                return;
            }
            var healthVersion = '';
            try {
                var health = await pingHealth();
                healthVersion = (health && health.version) || '';
            } catch (error) {
                sawDisconnect = true;
                show(byId('updateProgress'), true);
                setText('updateProgressMessage', 'האפליקציה עולה מחדש…');
                pollTimer = window.setTimeout(tick, POLL_MS);
                return;
            }
            var statusState = '';
            try {
                var result = await api('/api/updates/status?_=' + Date.now());
                if (result.ok) {
                    var status = result.data || {};
                    statusState = status.state || '';
                    if (statusState === 'running') {
                        sawRunning = true;
                    }
                    renderProgress(status);
                    if (statusState === 'failed') {
                        pollTimer = 0;
                        return;
                    }
                } else {
                    sawDisconnect = true;
                }
            } catch (error) {
                sawDisconnect = true;
            }
            if (shouldHardReloadAfterUpdate({
                before: beforeVersion,
                target: targetVersion,
                version: healthVersion,
                sawDisconnect: sawDisconnect,
                status: statusState,
                watching: true,
            })) {
                show(byId('updateProgress'), true);
                setText('updateProgressMessage', 'טוען מחדש…');
                hardReload();
                return;
            }
            pollTimer = window.setTimeout(tick, POLL_MS);
        }

        pollTimer = window.setTimeout(tick, 600);
    }

    async function refreshBadge() {
        var badge = byId('updateNavBadge');
        if (!badge) {
            return;
        }
        try {
            var result = await api('/api/updates/badge');
            var on = !!(result.data && result.data.available);
            show(badge, on);
            var link = badge.closest('a');
            if (link) {
                link.setAttribute('aria-label', on ? 'הגדרות, יש עדכון גרסה' : 'הגדרות');
            }
        } catch (error) {
            show(badge, false);
        }
    }

    function bind() {
        var check = byId('updateCheckBtn');
        if (check) {
            check.addEventListener('click', async function () {
                setError('');
                check.disabled = true;
                try {
                    var result = await api('/api/updates/check', {method: 'POST', body: '{}'});
                    if (!result.ok) {
                        setError((result.data && result.data.error) || 'לא הצלחנו לבדוק.');
                        return;
                    }
                    var info = await api('/api/updates');
                    applySummary(info.data || {});
                } finally {
                    check.disabled = false;
                }
            });
        }
        var apply = byId('updateApplyBtn');
        if (apply) {
            apply.addEventListener('click', async function () {
                var question = 'לעדכן עכשיו לגרסה ' + latest
                    + '? נשמר גיבוי. אם משהו נכשל נחזור אחורה, והאפליקציה תופעל מחדש.';
                if (!window.confirm(question)) {
                    return;
                }
                setError('');
                apply.disabled = true;
                var result = await api('/api/updates/apply', {
                    method: 'POST',
                    body: JSON.stringify({version: latest}),
                });
                if (!result.ok) {
                    setError((result.data && result.data.error) || 'העדכון לא התחיל.');
                    apply.disabled = false;
                    return;
                }
                beforeVersion = (byId('updateCurrentVersion') && byId('updateCurrentVersion').textContent.trim()) || '';
                targetVersion = latest;
                sawRunning = true;
                show(byId('updateOffer'), false);
                show(byId('updateProgress'), true);
                show(byId('updateReloadPrompt'), false);
                setText('updateProgressMessage', (result.data && result.data.message) || 'העדכון התחיל');
                startPoll();
            });
        }
        var reloadBtn = byId('updateReloadBtn');
        if (reloadBtn) {
            reloadBtn.addEventListener('click', function () {
                hardReload();
            });
        }
    }

    document.addEventListener('DOMContentLoaded', function () {
        bind();
        refreshBadge();
        if (byId('settingsUpdate')) {
            api('/api/updates').then(function (result) {
                applySummary(result.data || {});
            }).catch(function () {
                setError('לא הצלחנו לטעון את מצב העדכון.');
            });
        }
    });
})();
