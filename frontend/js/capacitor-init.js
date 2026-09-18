/**
 * Puente con la app nativa (Capacitor).
 *
 * TIENE QUE CARGAR ANTES QUE app.js: define window.RESTOMIND_API_BASE, que
 * app.js lee al construir API_BASE_URL. Si cargara después, las primeras
 * llamadas saldrían con la URL equivocada.
 *
 * NO USA `import`, Y ES A PROPÓSITO
 * ---------------------------------
 * Todos los scripts de esta app se cargan como clásicos (`<script src=...>`,
 * sin type="module") y se comunican por funciones globales. Meter un solo
 * `import` acá obligaría a marcar este archivo como módulo, y entonces sus
 * funciones dejarían de ser globales — el resto de la app no las vería. Y un
 * `import` dentro de un script clásico directamente lanza
 * "Cannot use import statement outside a module" y mata la carga entera.
 *
 * Los plugins nativos se alcanzan por `window.Capacitor.Plugins`, que es
 * justamente la vía que existe para no necesitar un empaquetador.
 */

(function () {
    'use strict';

    // Dominio del backend cuando la app corre empaquetada. Al estar
    // embebida en el APK, el origen pasa a ser https://localhost, así que
    // una ruta relativa como "/api" apuntaría al propio teléfono. Tiene que
    // ser absoluta, sí o sí.
    //
    // El valor NO vive acá: lo pone js/destino-api.js, que se carga antes y
    // que la compilación reemplaza según se arme un APK de pruebas o uno de
    // producción. Ver ese archivo para el por qué.
    //
    // NO HAY RESPALDO A PRODUCCIÓN, y es deliberado. Poner
    // `|| 'https://app.jtechsolutiones.com'` parece prudente y es justo lo
    // contrario: si destino-api.js no cargara en un APK de PRUEBAS, ese
    // respaldo lo mandaría a escribir en la base del restaurante sin que nada
    // lo avisara — el mismo accidente que este archivo viene a evitar.
    // Quedarse sin destino es un error de compilación, y tiene que verse.
    const API_REMOTA = window.RESTOMIND_API_DESTINO || '';

    const esNativo = Boolean(
        window.Capacitor && typeof window.Capacitor.isNativePlatform === 'function'
            ? window.Capacitor.isNativePlatform()
            : false
    );

    window.RESTOMIND_ES_NATIVO = esNativo;
    // En la web queda vacío: la ruta relativa /api ya cae en el mismo
    // dominio, y así el mismo frontend sirve para desarrollo local, para el
    // VPS y para el APK sin condicionales repartidos por el código.
    window.RESTOMIND_API_BASE = esNativo ? API_REMOTA : '';

    if (!esNativo) return;

    // Empaquetado y sin destino = el APK se armó mal. Sin este aviso la app
    // arranca igual y falla mucho después, con un "Sin conexión" que manda a
    // revisar el wifi del local en vez de la compilación.
    if (!API_REMOTA) {
        console.error('[RestoMind] El APK no tiene backend configurado: falta js/destino-api.js. '
            + 'Recompilar con  npm run apk  o  npm run apk:testing');
    }

    // ---- Token de notificaciones -------------------------------------
    // Se expone con la MISMA forma que espera push-notifications.js
    // (window.RestoMindNativo.obtenerTokenFCM), así ese archivo no necesita
    // saber si abajo hay Capacitor, un WebView propio, o lo que venga
    // después. Un solo contrato, una sola cosa que mantener.
    let tokenPush = null;
    window.RestoMindNativo = {
        obtenerTokenFCM: function () { return tokenPush || ''; },
    };

    function plugin(nombre) {
        return (window.Capacitor && window.Capacitor.Plugins && window.Capacitor.Plugins[nombre]) || null;
    }

    async function iniciarPush() {
        const Push = plugin('PushNotifications');
        if (!Push) return;
        try {
            let permiso = await Push.checkPermissions();
            if (permiso.receive === 'prompt' || permiso.receive === 'prompt-with-rationale') {
                permiso = await Push.requestPermissions();
            }
            if (permiso.receive !== 'granted') return;

            // El token NO llega como respuesta de register(): llega por el
            // evento 'registration', posiblemente segundos después. Por eso
            // el listener se engancha ANTES de llamar a register.
            Push.addListener('registration', function (t) {
                tokenPush = t && t.value ? t.value : null;
                // Se avisa para que push-notifications.js lo registre contra
                // el backend con el JWT de la sesión. Si todavía no hay
                // sesión, la función se salta sola y se reintenta al entrar.
                if (tokenPush && typeof window.activarNotificacionesCocina === 'function') {
                    window.activarNotificacionesCocina();
                }
            });

            Push.addListener('registrationError', function (e) {
                console.warn('[Capacitor] FCM no pudo registrar el dispositivo:', e);
            });

            await Push.register();
        } catch (err) {
            console.warn('[Capacitor] Push no disponible:', err);
        }
    }

    async function iniciarRed() {
        const Network = plugin('Network');
        if (!Network) return;
        try {
            // navigator.onLine en Android miente seguido: dice "conectado"
            // con el wifi asociado pero sin salida a internet, que es
            // exactamente lo que pasa en un local con el router colgado. El
            // plugin consulta el estado real del sistema.
            const estadoRed = await Network.getStatus();
            aplicarEstadoRed(estadoRed.connected);

            Network.addListener('networkStatusChange', function (s) {
                aplicarEstadoRed(s.connected);
            });
        } catch (err) {
            console.warn('[Capacitor] Network no disponible:', err);
        }
    }

    function aplicarEstadoRed(conectado) {
        // Se reusa el mecanismo que ya existe (offline.js escucha los
        // eventos online/offline del navegador y decide qué encolar). Acá
        // NO se cambia qué se encola: esa política está razonada en
        // offline.js y encolar cobros a ciegas duplicaría cargos.
        window.dispatchEvent(new Event(conectado ? 'online' : 'offline'));
    }

    async function iniciarBotonAtras() {
        const App = plugin('App');
        if (!App) return;
        try {
            App.addListener('backButton', function (info) {
                // Si hay un modal abierto, el "atrás" lo cierra en vez de
                // navegar: salir de la app con un pedido a medio cargar
                // sería perderlo.
                if (typeof window.cerrarModalConEscape === 'function' && window.cerrarModalConEscape()) {
                    return;
                }
                if (info.canGoBack) {
                    window.history.back();
                } else {
                    App.exitApp();
                }
            });
        } catch (err) {
            console.warn('[Capacitor] App no disponible:', err);
        }
    }

    async function iniciarBarraEstado() {
        const StatusBar = plugin('StatusBar');
        if (!StatusBar) return;
        try {
            // Mismo color que --bg del tema oscuro. Sin esto queda una
            // franja del color por defecto arriba de todo, que es de lo
            // primero que delata a una web empaquetada.
            await StatusBar.setBackgroundColor({ color: '#0F1317' });
            await StatusBar.setStyle({ style: 'DARK' });
        } catch (err) {
            /* algunos dispositivos no lo permiten; no es crítico */
        }
    }

    /**
     * Hace visibles los errores de JavaScript dentro del APK.
     *
     * En el navegador uno abre la consola y los ve. En la app instalada no
     * hay consola: un error deja la pantalla a medias y el único dato que
     * llega es "no abre" o "sale un error", que no alcanza para arreglar
     * nada. Esto los muestra en pantalla, con el archivo y la línea.
     */
    function mostrarErroresEnPantalla() {
        let caja = null;

        function mostrar(texto) {
            if (!caja) {
                caja = document.createElement('div');
                caja.style.cssText =
                    'position:fixed;left:0;right:0;bottom:0;z-index:99999;max-height:45vh;' +
                    'overflow:auto;background:#3B0D12;color:#FFD9DD;font:12px/1.5 monospace;' +
                    'padding:12px 14px;border-top:3px solid #FB7185;white-space:pre-wrap';
                const cerrar = document.createElement('button');
                cerrar.textContent = 'Cerrar';
                cerrar.style.cssText =
                    'float:right;background:#FB7185;color:#3B0D12;border:0;border-radius:6px;' +
                    'padding:6px 12px;font-weight:700';
                cerrar.onclick = function () { caja.remove(); caja = null; };
                caja.appendChild(cerrar);
                document.body.appendChild(caja);
            }
            caja.appendChild(document.createTextNode(texto + '\n'));
        }

        window.addEventListener('error', function (e) {
            const donde = e.filename ? ' (' + String(e.filename).split('/').pop() + ':' + e.lineno + ')' : '';
            mostrar('ERROR: ' + (e.message || 'desconocido') + donde);
        });

        window.addEventListener('unhandledrejection', function (e) {
            const r = e.reason;
            mostrar('PROMESA RECHAZADA: ' + ((r && (r.message || r)) || 'sin detalle'));
        });
    }

    document.addEventListener('DOMContentLoaded', function () {
        mostrarErroresEnPantalla();
        iniciarBarraEstado();
        iniciarRed();
        iniciarBotonAtras();
        iniciarPush();
    });
})();
