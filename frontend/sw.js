/**
 * Service Worker para PWA RestoMind
 * Network-first para HTML/CSS/JS: siempre se usa la versión más nueva
 * cuando hay conexión, y se cae al caché solo si el restaurante se
 * queda sin señal. Cache-first rompería el flujo de trabajo cada vez
 * que se publica una actualización (el navegador seguiría sirviendo
 * la versión vieja hasta cerrar todas las pestañas).
 */

const CACHE_NAME = 'restomind-v30';
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
    '/static/js/push-notifications.js',
    '/static/manifest.json'
];

// Notificaciones push (Firebase Cloud Messaging) para jefe_cocina — este
// bloque solo hace algo si el proyecto tiene Firebase configurado (ver
// frontend/js/push-notifications.js). Si el SDK no carga (CDN caído,
// offline en el momento del install del SW) el resto del Service Worker
// sigue funcionando igual: no es una dependencia dura.
try {
    importScripts('https://www.gstatic.com/firebasejs/10.13.0/firebase-app-compat.js');
    importScripts('https://www.gstatic.com/firebasejs/10.13.0/firebase-messaging-compat.js');
} catch (err) {
    console.warn('SW: Firebase Messaging no disponible', err);
}

// El mismo objeto que frontend/js/push-notifications.js — si cambias uno,
// cambia el otro. No se puede compartir un archivo entre ambos contextos
// (Service Worker no puede leer /static/js/push-notifications.js sin
// duplicar el importScripts de arriba), así que queda intencionalmente
// repetido acá.
const FIREBASE_CONFIG_SW = {
    apiKey: "TODO_PEGAR_API_KEY",
    authDomain: "TODO_PEGAR_PROYECTO.firebaseapp.com",
    projectId: "TODO_PEGAR_PROYECTO",
    storageBucket: "TODO_PEGAR_PROYECTO.appspot.com",
    messagingSenderId: "TODO_PEGAR_SENDER_ID",
    appId: "TODO_PEGAR_APP_ID",
};

if (typeof firebase !== 'undefined' && FIREBASE_CONFIG_SW.apiKey && !FIREBASE_CONFIG_SW.apiKey.startsWith('TODO_')) {
    firebase.initializeApp(FIREBASE_CONFIG_SW);
    const messaging = firebase.messaging();

    // Notificación con la app minimizada o cerrada: Firebase entrega el
    // mensaje acá (no en el 'push' event handler de abajo) cuando se usa
    // el SDK compat de messaging.
    const ICONO_NOTIFICACION = "data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 192 192'><rect width='192' height='192' rx='38' fill='%23FF5A3C'/><text x='96' y='96' font-size='90' fill='%23fff' font-family='sans-serif' text-anchor='middle' dy='.32em' font-weight='800'>R</text></svg>";

    messaging.onBackgroundMessage((payload) => {
        const { title, body } = payload.notification || {};
        self.registration.showNotification(title || 'RestoMind', {
            body: body || 'Nueva comanda',
            icon: ICONO_NOTIFICACION,
            vibrate: [200, 100, 200],
            requireInteraction: true,
            tag: 'restomind-comanda',
        });
    });
}

self.addEventListener('notificationclick', (event) => {
    event.notification.close();
    event.waitUntil(
        clients.matchAll({ type: 'window', includeUncontrolled: true }).then((clientList) => {
            for (const client of clientList) {
                if ('focus' in client) return client.focus();
            }
            if (clients.openWindow) return clients.openWindow('/static/index.html');
        })
    );
});

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
