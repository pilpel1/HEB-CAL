/* מעטפת PWA בסיסית: HTML + CSS/JS מקומי. לא שומר /api ולא משאבי CDN. */
const CACHE_NAME = 'heb-cal-shell-v1';

const SHELL = [
    '/',
    '/static/css/style.css',
    '/static/css/components/variables.css',
    '/static/css/components/calendar.css',
    '/static/css/components/events-table.css',
    '/static/css/components/forms.css',
    '/static/css/components/dark-theme.css',
    '/static/js/theme.js',
    '/static/js/script.js',
    '/static/manifest.webmanifest',
];

function isShellRequest(url) {
    if (url.origin !== self.location.origin) {
        return false;
    }
    if (url.pathname.startsWith('/api/')) {
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

self.addEventListener('fetch', (event) => {
    if (event.request.method !== 'GET') {
        return;
    }
    let url;
    try {
        url = new URL(event.request.url);
    } catch (err) {
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
