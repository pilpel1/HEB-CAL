// מסך «עדכון גרסה» והנקודה על גלגל השיניים. הטקסט מהשרת נכנס כ-textContent.
(function () {
    var csrf = '';
    var latest = '';
    var pollTimer = 0;
    var sawRunning = false;

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
            sawRunning = false;
            window.setTimeout(function () {
                window.location.reload();
            }, 800);
        }
        return state === 'running';
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
        if (renderProgress(info.status || {})) {
            startPoll();
        }
    }

    function startPoll() {
        if (pollTimer) {
            return;
        }
        var misses = 0;

        async function tick() {
            try {
                var result = await api('/api/updates/status');
                misses = 0;
                if (!result.ok) {
                    setError((result.data && result.data.error) || 'לא הצלחנו לקרוא את מצב העדכון.');
                    pollTimer = 0;
                    return;
                }
                var running = renderProgress(result.data || {});
                if (!running) {
                    pollTimer = 0;
                    return;
                }
            } catch (error) {
                misses += 1;
                show(byId('updateProgress'), true);
                setText('updateProgressMessage', 'האפליקציה עולה מחדש…');
                if (misses > 80) {
                    setError('אין קשר לאפליקציה. אם היא לא עלתה, בדקו את הגיבוי בתיקיית backups.');
                    pollTimer = 0;
                    return;
                }
            }
            pollTimer = window.setTimeout(tick, 1500);
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
                show(byId('updateOffer'), false);
                show(byId('updateProgress'), true);
                setText('updateProgressMessage', (result.data && result.data.message) || 'העדכון התחיל');
                startPoll();
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
