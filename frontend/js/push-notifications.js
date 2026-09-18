/**
 * Notificaciones push (Firebase Cloud Messaging) — avisan de una comanda
 * nueva incluso con la app minimizada (para restaurantes sin impresora de
 * cocina). Ver backend/utils/push_notifications.py.
 *
 * HOY NO LLEGA NADA POR ESTA VÍA, y conviene saberlo antes de tocar este
 * archivo: el APK no trae @capacitor/push-notifications ni
 * google-services.json, así que en el teléfono esto no puede recibir un
 * push. Queda para el día que exista el proyecto Firebase de los cuatro
 * pasos de abajo.
 *
 * El aviso que SÍ funciona hoy —sonido y vibración con la app abierta— vive
 * en cocina.js (sonarAvisoCocina). El switch de Admin > Personal controla
 * ese, no este: antes encendía el push y por eso fallaba siempre, con un
 * mensaje que mandaba a revisar el permiso del navegador cuando el permiso
 * no tenía nada que ver.
 *
 * Se activa solo al entrar con rol jefe_cocina (app.js: aplicarPermisosRol →
 * activarNotificacionesCocina()), sin switch — es la razón de ser del
 * feature, no algo que el cocinero deba configurar.
 *
 * REQUIERE CONFIGURACIÓN (no funciona "de fábrica"):
 * 1. Crear un proyecto en https://console.firebase.google.com (gratis)
 * 2. Configuración del proyecto > General > "Tus apps" > Agregar app Web
 *    → copiar el objeto firebaseConfig y pegarlo abajo en FIREBASE_CONFIG
 * 3. Configuración del proyecto > Cloud Messaging > Certificados push web
 *    → "Generar par de claves" → la clave pública ya la sirve el backend
 *    en GET /api/push/vapid-key (configurar FIREBASE_VAPID_KEY en el .env)
 * 4. Configuración del proyecto > Cuentas de servicio > "Generar nueva
 *    clave privada" → guardar el .json y apuntar FIREBASE_CREDENTIALS_JSON
 *    del backend (.env) a esa ruta
 *
 * Sin esos pasos, activarNotificacionesCocina() falla en silencio (log, sin
 * toast molesto) y el resto de la app sigue funcionando exactamente igual.
 */

// TODO: pegar acá el firebaseConfig real de tu proyecto (paso 2 de arriba).
// Los valores de ejemplo NO son reales — con ellos, Firebase rechaza la
// inicialización y las funciones de abajo simplemente no hacen nada.
const FIREBASE_CONFIG = {
    apiKey: "TODO_PEGAR_API_KEY",
    authDomain: "TODO_PEGAR_PROYECTO.firebaseapp.com",
    projectId: "TODO_PEGAR_PROYECTO",
    storageBucket: "TODO_PEGAR_PROYECTO.appspot.com",
    messagingSenderId: "TODO_PEGAR_SENDER_ID",
    appId: "TODO_PEGAR_APP_ID",
};

const PUSH_TOKEN_KEY = 'restomind_push_token';
// Preferencia SOLO del admin (opt-in) — jefe_cocina no tiene esta llave
// porque para ese rol la activación no es una preferencia, es obligatoria.

function _firebaseConfigurado() {
    return FIREBASE_CONFIG.apiKey && !FIREBASE_CONFIG.apiKey.startsWith('TODO_');
}

/** Devuelve la instancia de messaging, o null si este navegador no puede
 * usarla. NUNCA lanza: firebase.messaging() tira excepción en navegadores
 * sin soporte (iOS Safari viejo, HTTP sin TLS, algunos modos privados), y
 * dejar que esa excepción escape convertía a activarNotificacionesCocina()
 * en una promesa rechazada sin catch. */
function _getMessaging() {
    if (!_firebaseConfigurado() || typeof firebase === 'undefined') return null;
    try {
        if (!firebase.apps.length) firebase.initializeApp(FIREBASE_CONFIG);
        return firebase.messaging();
    } catch (err) {
        console.warn('[Push] Este navegador no soporta notificaciones push:', err);
        return null;
    }
}

/**
 * Pide permiso del navegador, obtiene el token FCM de este dispositivo y lo
 * registra en el backend. Devuelve el token si quedó activo, o null si no
 * (permiso denegado, Firebase sin configurar, navegador sin soporte, etc.)
 * — nunca lanza: cualquier fallo acá es "sin notificaciones", no un error
 * que deba interrumpir al usuario.
 */
/**
 * Token FCM cuando la app corre dentro del APK (WebView), o null si no.
 *
 * POR QUÉ HACE FALTA UN CAMINO APARTE
 * -----------------------------------
 * `android.webkit.WebView` NO implementa la Push API ni `Notification`. El
 * resto de esta función se apagaría en su primera línea y devolvería null
 * SIN ERROR: el cocinero abriría la app, no vería ninguna advertencia, y
 * simplemente no le llegarían las comandas. Es el fallo que se descubre
 * cuando ya se perdieron tres pedidos.
 *
 * Así que dentro del APK el token lo consigue la capa nativa (SDK de
 * Firebase para Android) y lo entrega por este puente. El registro contra
 * el backend lo sigue haciendo el lado web, que es quien tiene el JWT —
 * duplicar la sesión en Kotlin sería otra copia de la autenticación que
 * mantener sincronizada.
 *
 * Contrato con la app nativa (ver docs/APK_ANDROID.md):
 *   window.RestoMindNativo.obtenerTokenFCM() -> string  ('' si todavía no hay)
 */
function _tokenNativo() {
    try {
        const puente = window.RestoMindNativo;
        if (!puente || typeof puente.obtenerTokenFCM !== 'function') return null;
        const token = puente.obtenerTokenFCM();
        return token && token.length > 20 ? token : null;
    } catch (err) {
        console.warn('[Push] El puente nativo falló:', err);
        return null;
    }
}

/** ¿Estamos dentro del APK? Se pregunta por el puente y no por el
 *  user-agent: el UA se puede falsear y además cambia con cada versión de
 *  Android System WebView, mientras que el puente existe exactamente
 *  cuando la app nativa lo inyectó. */
function corriendoEnAPK() {
    return Boolean(window.RestoMindNativo);
}

async function _activarPush() {
    // Dentro del APK este es el ÚNICO camino que funciona, así que se
    // intenta antes que nada.
    const nativo = _tokenNativo();
    if (nativo) {
        try {
            if (localStorage.getItem(PUSH_TOKEN_KEY) !== nativo) {
                await api.post('/push/registrar', { token: nativo });
                localStorage.setItem(PUSH_TOKEN_KEY, nativo);
            }
            return nativo;
        } catch (err) {
            console.error('[Push] No se pudo registrar el token nativo:', err);
            return null;
        }
    }

    if (corriendoEnAPK()) {
        // El puente está, pero todavía no entregó token: FCM lo genera de
        // forma asíncrona al primer arranque. No es un error — en la
        // siguiente vuelta ya va a estar.
        console.warn('[Push] El puente nativo aún no tiene token FCM.');
        return null;
    }

    if (!('Notification' in window) || !('serviceWorker' in navigator)) return null;

    const messaging = _getMessaging();
    if (!messaging) {
        console.warn('[Push] Firebase no está configurado todavía (frontend/js/push-notifications.js).');
        return null;
    }

    try {
        const permiso = await Notification.requestPermission();
        if (permiso !== 'granted') return null;

        const { vapid_key } = await api.get('/push/vapid-key');
        if (!vapid_key) {
            console.warn('[Push] FIREBASE_VAPID_KEY no está configurado en el backend (.env).');
            return null;
        }

        const registration = await navigator.serviceWorker.ready;
        const token = await messaging.getToken({ vapidKey: vapid_key, serviceWorkerRegistration: registration });
        if (!token) return null;

        if (localStorage.getItem(PUSH_TOKEN_KEY) !== token) {
            await api.post('/push/registrar', { token });
            localStorage.setItem(PUSH_TOKEN_KEY, token);
        }
        return token;
    } catch (err) {
        console.error('[Push] No se pudo activar notificaciones:', err);
        return null;
    }
}

/**
 * jefe_cocina: activación OBLIGATORIA, sin switch. Se llama automáticamente
 * cuando el rol activo es jefe_cocina (ver app.js:aplicarPermisosRol).
 */
function activarNotificacionesCocina() {
    _activarPush();
}
