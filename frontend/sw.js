/**
 * Service Worker para PWA RestoMind
 * Network-first para HTML/CSS/JS: siempre se usa la versión más nueva
 * cuando hay conexión, y se cae al caché solo si el restaurante se
 * queda sin señal. Cache-first rompería el flujo de trabajo cada vez
 * que se publica una actualización (el navegador seguiría sirviendo
 * la versión vieja hasta cerrar todas las pestañas).
 */

const CACHE_NAME = 'restomind-v25';
const STATIC_ASSETS = [
    '/static/index.html',
    '/static/css/style.css',
    '/static/js/app.js',
    '/static/js/offline.js',
    '/static/js/auth.js',
    '/static/js/charts.js',
    '/static/js/print.js',
    '/static/js/mozo.js',
    '/static/js/cocina.js',
    '/static/js/dashboard.js',
    '/static/js/admin.js',
    '/static/js/caja.js',
    '/static/js/cierre-caja-print.js',
    '/static/manifest.json'
];

self.addEventListener('install', event => {
    event.waitUntil(
        caches.open(CACHE_NAME)
            .then(cache => cache.addAll(STATIC_ASSETS))
            .catch(err => console.log('SW: Cache error', err))
    );
    self.skipWaiting();
});

self.addEventListener('activate', event => {
    event.waitUntil(
        caches.keys().then(cacheNames => Promise.all(
            cacheNames
                .filter(name => name !== CACHE_NAME)
                .map(name => caches.delete(name))
        ))
    );
    self.clients.claim();
});

self.addEventListener('fetch', event => {
    const { request } = event;

    // API: siempre red, nunca cache (los datos deben ser frescos)
    if (request.url.includes('/api/')) {
        event.respondWith(
            fetch(request).catch(() => new Response(
                JSON.stringify({ detail: 'Sin conexión' }),
                { status: 503, headers: { 'Content-Type': 'application/json' } }
            ))
        );
        return;
    }

    // La extensión de DevTools/otras extensiones del navegador inyectan
    // requests con esquema chrome-extension:// que pasan por acá — la
    // Cache API los rechaza siempre ("Request scheme ... is unsupported").
    // Sin este filtro, cache.put() los intenta igual y explota en cada
    // fetch como promesa sin capturar (el error que se ve en consola).
    // Cache API tampoco acepta requests que no sean GET.
    const cacheable = request.method === 'GET' && request.url.startsWith(self.location.origin);

    // Estáticos: red primero, cache como respaldo offline
    event.respondWith(
        fetch(request)
            .then(response => {
                if (cacheable) {
                    const clone = response.clone();
                    caches.open(CACHE_NAME)
                        .then(cache => cache.put(request, clone))
                        .catch(() => { /* request no cacheable (extensión, esquema raro, etc.) — no es un error real */ });
                }
                return response;
            })
            .catch(() => caches.match(request).then(cached => cached || Response.error()))
    );
});
