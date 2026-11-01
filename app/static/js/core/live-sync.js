// סנכרון חי: SSE מ-/api/events/stream, רענון לוח/רשימה בלי לטעון את הדף מחדש.

const LIVE_SYNC_CLIENT_KEY = 'heb-cal-client';
const LIVE_SYNC_DEBOUNCE_MS = 400;

const liveSyncState = {
    clientId: '',
    source: null,
    opened: false,
    timer: null,
    refreshing: false,
    queued: false,
    origFetch: null,
};

function getLiveSyncClientId() {
    if (liveSyncState.clientId) {
        return liveSyncState.clientId;
    }
    let id = '';
    try {
        id = sessionStorage.getItem(LIVE_SYNC_CLIENT_KEY) || '';
    } catch (error) {
        id = '';
    }
    if (!id) {
        id = (typeof crypto !== 'undefined' && crypto.randomUUID)
            ? crypto.randomUUID()
            : `c${Date.now().toString(36)}${Math.random().toString(36).slice(2, 10)}`;
        try {
            sessionStorage.setItem(LIVE_SYNC_CLIENT_KEY, id);
        } catch (error) {
            // sessionStorage חסום — נשאר בזיכרון לטאב הזה
        }
    }
    liveSyncState.clientId = id;
    return id;
}

function wrapFetchWithLiveSyncClient() {
    if (liveSyncState.origFetch || typeof window.fetch !== 'function') {
        return;
    }
    liveSyncState.origFetch = window.fetch.bind(window);
    window.fetch = function (input, init) {
        const next = Object.assign({}, init);
        const headers = new Headers(
            next.headers || (input instanceof Request ? input.headers : undefined)
        );
        headers.set('X-Heb-Cal-Client', getLiveSyncClientId());
        next.headers = headers;
        return liveSyncState.origFetch(input, next);
    };
    // כל ה-fetch של האפליקציה הוא same-origin אל /api. EventSource לא עובר כאן.
}

function liveSyncModalIsOpen() {
    if (typeof isQuickEventModalOpen === 'function') {
        return isQuickEventModalOpen();
    }
    const el = document.getElementById('quickEventModal');
    return Boolean(el && el.classList.contains('show'));
}

function liveSyncOpenEventId() {
    if (typeof getOpenQuickEventId === 'function') {
        return getOpenQuickEventId();
    }
    const raw = document.getElementById('quick_event_id')?.value;
    const number = Number(raw);
    return Number.isInteger(number) && number > 0 ? number : null;
}

function showLiveSyncModalNotice(text) {
    const note = document.getElementById('quick_live_notice');
    if (!note || !text) {
        return;
    }
    note.textContent = text;
    note.hidden = false;
}

function hideLiveSyncModalNotice() {
    const note = document.getElementById('quick_live_notice');
    if (!note) {
        return;
    }
    note.hidden = true;
    note.textContent = '';
}

function noteOpenEventFromPayload(payload) {
    if (!liveSyncModalIsOpen()) {
        return;
    }
    const openId = liveSyncOpenEventId();
    if (!openId) {
        return;
    }
    const ids = Array.isArray(payload && payload.ids) ? payload.ids : [];
    const bulk = ids.length === 0;
    const hit = bulk || ids.some((item) => Number(item) === openId);
    if (!hit) {
        return;
    }
    if (payload && payload.action === 'deleted' && !bulk) {
        showLiveSyncModalNotice('האירוע נמחק במכשיר אחר');
        return;
    }
    showLiveSyncModalNotice(bulk ? 'היומן עודכן במכשיר אחר' : 'האירוע עודכן במכשיר אחר');
}

async function runLiveSyncRefresh() {
    if (liveSyncState.refreshing) {
        liveSyncState.queued = true;
        return;
    }
    liveSyncState.refreshing = true;
    try {
        if (typeof refreshEventsViews === 'function') {
            await refreshEventsViews();
        }
    } catch (error) {
        console.error('live sync refresh failed', error);
    } finally {
        liveSyncState.refreshing = false;
        if (liveSyncState.queued) {
            liveSyncState.queued = false;
            scheduleLiveSyncRefresh();
        }
    }
}

function scheduleLiveSyncRefresh() {
    if (liveSyncState.timer) {
        clearTimeout(liveSyncState.timer);
    }
    liveSyncState.timer = setTimeout(() => {
        liveSyncState.timer = null;
        runLiveSyncRefresh();
    }, LIVE_SYNC_DEBOUNCE_MS);
}

function handleLiveSyncMessage(payload) {
    if (!payload || payload.type !== 'changed') {
        return;
    }
    if (payload.origin && payload.origin === getLiveSyncClientId()) {
        return;
    }
    noteOpenEventFromPayload(payload);
    if (document.visibilityState === 'hidden') {
        liveSyncState.queued = true;
        return;
    }
    scheduleLiveSyncRefresh();
}

function parseLiveSyncEvent(raw) {
    if (!raw) {
        return null;
    }
    try {
        return JSON.parse(raw);
    } catch (error) {
        return null;
    }
}

function connectLiveSyncStream() {
    if (typeof EventSource === 'undefined') {
        return;
    }
    if (liveSyncState.source) {
        liveSyncState.source.close();
        liveSyncState.source = null;
    }
    const url = `/api/events/stream?client=${encodeURIComponent(getLiveSyncClientId())}`;
    const source = new EventSource(url);
    liveSyncState.source = source;
    source.addEventListener('hello', () => {});
    source.addEventListener('changed', (event) => {
        handleLiveSyncMessage(parseLiveSyncEvent(event.data));
    });
    source.onmessage = (event) => {
        handleLiveSyncMessage(parseLiveSyncEvent(event.data));
    };
    source.onopen = () => {
        if (liveSyncState.opened) {
            scheduleLiveSyncRefresh();
        }
        liveSyncState.opened = true;
    };
}

function initLiveSync() {
    wrapFetchWithLiveSyncClient();
    connectLiveSyncStream();
    document.addEventListener('visibilitychange', () => {
        if (document.visibilityState !== 'visible') {
            return;
        }
        scheduleLiveSyncRefresh();
    });
    window.addEventListener('pageshow', (event) => {
        if (event.persisted) {
            scheduleLiveSyncRefresh();
        }
    });
}
