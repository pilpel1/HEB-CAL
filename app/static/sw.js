/* מעטפת PWA בסיסית: HTML + CSS/JS מקומי. לא שומר /api ולא משאבי CDN. */
/* __HEB_CAL_VERSION__ מוחלף בזמן הגשת /sw.js */
const CACHE_VERSION = '__HEB_CAL_VERSION__';
const CACHE_NAME = 'heb-cal-shell-' + CACHE_VERSION;

const SHELL = [
    '/',
    '/static/css/style.css?v=' + CACHE_VERSION,
    '/static/css/components/variables.css?v=' + CACHE_VERSION,
    '/static/css/components/calendar.css?v=' + CACHE_VERSION,
    '/static/css/components/events-table.css?v=' + CACHE_VERSION,
    '/static/css/components/forms.css?v=' + CACHE_VERSION,
    '/static/css/components/dark-theme.css?v=' + CACHE_VERSION,
    '/static/js/theme.js?v=' + CACHE_VERSION,
    '/static/js/script.js?v=' + CACHE_VERSION,
    '/static/manifest.webmanifest?v=' + CACHE_VERSION,
];

function isShellRequest(url) {
    if (url.origin !== self.location.origin) {
        return false;
    }
    if (url.pathname.startsWith('/api/')) {
        return false;
    }
    if (url.pathname === '/api/events/stream' || url.pathname.startsWith('/api/events/stream')) {
        return false;
    }
    if (url.pathname === '/sw.js') {
        return false;
    }
    return (
        url.pathname === '/' ||
        url.pathname === '/events_list' ||
        url.pathname === '/settings' ||
        url.pathname.startsWith('/static/')
    );
}

self.addEventListener('install', (event) => {
    event.waitUntil(
        caches.open(CACHE_NAME).then((cache) => cache.addAll(SHELL)).then(() => self.skipWaiting())
    );
});

self.addEventListener('activate', (event) => {
    event.waitUntil(
        caches.keys().then((keys) =>
            Promise.all(keys.filter((key) => key !== CACHE_NAME).map((key) => caches.delete(key)))
        ).then(() => self.clients.claim())
    );
});

self.addEventListener('message', (event) => {
    if (event.data && event.data.type === 'SKIP_WAITING') {
        self.skipWaiting();
    }
});

self.addEventListener('fetch', (event) => {
    if (event.request.method !== 'GET') {
        return;
    }
    const mode = event.request.cache;
    if (mode === 'no-store' || mode === 'reload' || mode === 'no-cache') {
        return;
    }
    let url;
    try {
        url = new URL(event.request.url);
    } catch (err) {
        return;
    }
    const accept = event.request.headers.get('Accept') || '';
    if (
        url.pathname === '/api/events/stream'
        || url.pathname.startsWith('/api/events/stream')
        || accept.includes('text/event-stream')
    ) {
        return;
    }
    if (!isShellRequest(url)) {
        return;
    }

    event.respondWith(
        fetch(event.request)
            .then((response) => {
                if (response && response.ok) {
                    const copy = response.clone();
                    caches.open(CACHE_NAME).then((cache) => cache.put(event.request, copy));
                }
                return response;
            })
            .catch(() => caches.match(event.request))
    );
});
