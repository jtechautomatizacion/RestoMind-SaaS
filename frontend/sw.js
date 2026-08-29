/**
 * Service Worker para PWA RestoMind
 * Cache estático para assets, fallback offline básico
 */

const CACHE_NAME = 'restomind-v1';
const STATIC_ASSETS = [
    '/static/index.html',
    '/static/css/style.css',
    '/static/js/app.js',
    '/static/js/mozo.js',
    '/static/js/cocina.js',
    '/static/js/admin.js',
    '/static/manifest.json'
];

// Install event
self.addEventListener('install', event => {
    console.log('SW: Installing...');
    event.waitUntil(
        caches.open(CACHE_NAME).then(cache => {
            return cache.addAll(STATIC_ASSETS)
                .catch(err => console.log('SW: Cache error', err));
        })
    );
});

// Activate event
self.addEventListener('activate', event => {
    console.log('SW: Activating...');
    event.waitUntil(
        caches.keys().then(cacheNames => {
            return Promise.all(
                cacheNames.map(cacheName => {
                    if (cacheName !== CACHE_NAME) {
                        console.log('SW: Deleting old cache', cacheName);
                        return caches.delete(cacheName);
                    }
                })
            );
        })
    );
});

// Fetch event - Network first, fallback to cache
self.addEventListener('fetch', event => {
    const { request } = event;

    // API calls: network only
    if (request.url.includes('/api/')) {
        event.respondWith(
            fetch(request)
                .catch(() => new Response('{"error": "offline"}', {
                    status: 503,
                    headers: { 'Content-Type': 'application/json' }
                }))
        );
        return;
    }

    // Static assets: cache first
    event.respondWith(
        caches.match(request).then(response => {
            return response || fetch(request).then(response => {
                return caches.open(CACHE_NAME).then(cache => {
                    cache.put(request, response.clone());
                    return response;
                });
            }).catch(() => {
                // Fallback 404 page
                return new Response('Offline - archivo no en caché', {
                    status: 404,
                    headers: { 'Content-Type': 'text/plain' }
                });
            });
        })
    );
});
