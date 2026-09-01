/**
 * Notificaciones push (Firebase Cloud Messaging) — avisan de una comanda
 * nueva incluso con la app minimizada (para restaurantes sin impresora de
 * cocina). Ver backend/utils/push_notifications.py.
 *
 * Dos casos de uso distintos, mismo mecanismo de abajo:
 * - jefe_cocina: OBLIGATORIO. Se activa solo al elegir ese rol (app.js:
 *   aplicarPermisosRol → activarNotificacionesCocina()), sin switch — es
 *   la razón de ser del feature, no algo que el cocinero deba configurar.
 * - admin: OPCIONAL. El dueño puede o no querer que el celular le avise de
 *   cada comanda (ya lo ve todo desde el dashboard) — switch en Admin >
 *   Personal (ver toggleNotificacionesAdmin() más abajo).
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
 * Sin este paso, activarNotificacionesCocina()/toggleNotificacionesAdmin()
 * fallan en silencio (log, sin toast molesto) y el resto de la app sigue
 * funcionando exactamente igual.
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
const PUSH_ADMIN_ACTIVO_KEY = 'restomind_push_admin_activo';

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
async function _activarPush() {
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

/** Da de baja este dispositivo, tanto en el backend (deja de recibir
 * envíos) como en Firebase (invalida el token del lado del navegador).
 * Nunca lanza, por la misma razón que _activarPush().
 *
 * Si no hay token en localStorage (el navegador se limpió, o se usó el
 * botón ?reset de la app que hace localStorage.clear()) NO se sale sin
 * hacer nada: se manda la baja SIN token, que en el backend significa
 * "dar de baja todos mis dispositivos". Sin ese fallback, la fila quedaba
 * viva para siempre y el admin seguía recibiendo avisos sin ninguna forma
 * de apagarlos desde este navegador. */
async function _desactivarPush() {
    const token = localStorage.getItem(PUSH_TOKEN_KEY);

    try {
        await api.post('/push/desregistrar', token ? { token } : {});
    } catch (err) {
        console.error('[Push] No se pudo desregistrar el token en el servidor:', err);
    }

    try {
        const messaging = _getMessaging();
        if (messaging) await messaging.deleteToken();
    } catch (_) {
        // No crítico: aunque Firebase no invalide el token del lado del
        // navegador, ya se borró del backend — no van a llegar más envíos.
    }

    localStorage.removeItem(PUSH_TOKEN_KEY);
}

/**
 * jefe_cocina: activación OBLIGATORIA, sin switch. Se llama automáticamente
 * cuando el rol activo es jefe_cocina (ver app.js:aplicarPermisosRol).
 */
function activarNotificacionesCocina() {
    _activarPush();
}

/**
 * admin: activación OPCIONAL vía switch (Admin > Personal). Devuelve true
 * si quedó activado, false si no (para que el switch pueda revertirse solo
 * si algo falló, en vez de mostrar "activado" cuando en realidad no lo está).
 */
async function toggleNotificacionesAdmin(activar) {
    if (activar) {
        const token = await _activarPush();
        const exito = token !== null;
        localStorage.setItem(PUSH_ADMIN_ACTIVO_KEY, exito ? 'true' : 'false');
        return exito;
    }

    await _desactivarPush();
    localStorage.setItem(PUSH_ADMIN_ACTIVO_KEY, 'false');
    return false;
}

/** Estado guardado localmente — solo para pintar el switch de inmediato al
 * cargar la pantalla, sin esperar una llamada de red. NO es la fuente de
 * verdad (ver notificacionesAdminActivasEnServidor). */
function notificacionesAdminActivas() {
    return localStorage.getItem(PUSH_ADMIN_ACTIVO_KEY) === 'true';
}

/** Fuente de verdad real: ¿el servidor tiene algún dispositivo registrado
 * para este usuario? localStorage puede estar limpio (otro navegador, datos
 * borrados) aunque la fila exista — y en ese caso el switch tiene que
 * mostrarse ENCENDIDO, porque los avisos efectivamente están llegando.
 * Devuelve null si no se pudo consultar (sin red): el llamador conserva
 * entonces lo que ya mostraba en vez de inventar un estado. */
async function notificacionesAdminActivasEnServidor() {
    try {
        const { activo } = await api.get('/push/estado');
        localStorage.setItem(PUSH_ADMIN_ACTIVO_KEY, activo ? 'true' : 'false');
        return activo;
    } catch (err) {
        return null;
    }
}
