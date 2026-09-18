/**
 * RestoMind - Aplicación Compartida
 * API client, estado global, navegación y utilidades.
 */

// En la web queda '/api' (mismo dominio). Empaquetada como APK, el frontend
// vive DENTRO de la app y el origen pasa a ser https://localhost: una ruta
// relativa apuntaría al propio teléfono, donde no hay ningún servidor. Por
// eso capacitor-init.js —que carga antes que este archivo— deja el dominio
// absoluto en RESTOMIND_API_BASE.
const API_BASE_URL = (window.RESTOMIND_API_BASE || '') + '/api';

// Filtra cualquier tecla que no sea dígito a medida que se escribe — más
// rápido de corregir para el usuario que dejarlo escribir letras/guiones
// y recién avisarle con un error al enviar el formulario.
function soloDigitos(event) {
    event.target.value = event.target.value.replace(/\D/g, '');
}

// Qué pestañas puede ver cada rol. Una cuenta de personal puede tener
// VARIOS roles a la vez (ej. cajero + jefe_cocina, cuando el restaurante
// tiene poco personal — ver backend/utils/roles.py) — estado.roles es
// siempre un array, y las pestañas visibles son la UNIÓN de las de todos
// sus roles (ver tabsPermitidas()). Sin login todavía, el rol se elige una
// vez por dispositivo (el celular del mozo, el de caja, etc.) con el
// selector manual — eso sigue siendo un solo rol a la vez, ver elegirRol().
const ROLES_PERMITIDOS = {
    admin: ['mozo', 'cocina', 'dashboard', 'admin'],
    mozo: ['mozo'],
    jefe_cocina: ['cocina'],
    cajero: ['mozo'],
    // Cubre las tres estaciones, SIN Dashboard ni Administración: es
    // personal de confianza que atiende solo, no el dueño. Los números del
    // negocio (ganancias, márgenes, gastos) y la configuración fiscal
    // siguen siendo del admin — ver backend/utils/roles.py.
    asistente: ['mozo', 'cocina'],
};

const ROL_LABELS = {
    admin: 'Admin',
    mozo: 'Mozo',
    jefe_cocina: 'Cocina',
    cajero: 'Cajero',
    asistente: 'Asistente',
};

// Quién opera en modo "Todo en uno" (Vista Unificada). Lista explícita, no
// una regla derivada de las pestañas: ver ROLES_VISTA_UNIFICADA en
// backend/utils/roles.py para el porqué. Los dos lados tienen que decir lo
// mismo, así que si cambia uno, cambia el otro.
const ROLES_VISTA_UNIFICADA = ['admin', 'asistente'];

function getRolesGuardados() {
    try {
        const guardado = JSON.parse(localStorage.getItem('restomind_roles') || 'null');
        if (Array.isArray(guardado) && guardado.length) return guardado;
    } catch (_) { /* localStorage corrupto o formato viejo — usar default */ }
    return ['admin'];
}

const estado = {
    clienteId: null, // Se completa en auth.js al validar la sesión
    usuario: null,   // { email, nombre, roles, cliente_id, cliente_nombre }
    roles: getRolesGuardados(),
    platos: [],
    mesas: [],
    // Lo que hay en cocina ahora mismo. Lo mantiene refreshCocina() (cocina.js)
    // y lo lee también la vista unificada, para no pedir dos veces lo mismo.
    comandasCocina: [],
    currentTab: 'mozo',
    cajaAbierta: null // null = aún no se consultó; ver refreshCajaGate()
};

// Unión de pestañas permitidas por TODOS los roles activos de la cuenta —
// no la primera que matchee. Con roles=['cajero','jefe_cocina'] esto
// devuelve ['mozo','cocina']: la persona ve Mesas (en modo cajero, sin
// poder agregar pedidos — ver mozo.js) Y Cocina, desde un solo dispositivo.
function tabsPermitidas() {
    const roles = estado.roles.length ? estado.roles : ['mozo'];
    const set = new Set();
    roles.forEach(r => (ROLES_PERMITIDOS[r] || []).forEach(t => set.add(t)));
    return [...set];
}

// ¿Este usuario puede ver esta pestaña? Se usa para NO llamar a endpoints
// que su rol tiene prohibidos: el backend responde 403 (correctamente),
// pero pedirlos igual llena la consola de errores y confunde al depurar un
// problema real. La seguridad la pone el backend; esto solo evita el ruido.
function puedeVer(tab) {
    return tabsPermitidas().includes(tab);
}

// ============ AVISO DE SERVIDOR DESACTUALIZADO ============

/**
 * Avisa cuando el backend está sirviendo código más viejo que el que hay
 * en el disco.
 *
 * Existe por un problema que ya costó días tres veces: `uvicorn --reload`
 * detecta el cambio, imprime "Reloading..." y el proceso nuevo nunca
 * levanta (verificado en Windows con cero clientes conectados, puerto
 * limpio y los dos vigilantes de archivos — StatReload y WatchFiles). El
 * servidor viejo sigue respondiendo como si nada, así que desde el
 * navegador se ve un bug imposible: una ruta nueva que da 404, un rol
 * nuevo que da 422, un campo que "no se guarda".
 *
 * El backend ya sabe la respuesta (`/health` compara la hora de arranque
 * contra la fecha de los .py en disco). Lo único que faltaba era mostrarla
 * donde se está mirando cuando aparece el síntoma.
 *
 * En producción `codigo_desactualizado` es SIEMPRE false —los archivos no
 * cambian entre despliegues— así que este aviso no existe para el
 * restaurante: es invisible salvo que de verdad haya un servidor viejo.
 *
 * Se consulta al ARRANCAR y nada más. Ese es justo el momento en que uno
 * recarga la página para probar un cambio, y consultarlo en un intervalo
 * sería gastar red del local para siempre por un problema de desarrollo.
 */
async function avisarSiElServidorEstaDesactualizado() {
    try {
        // Con la ruta relativa, dentro del APK esto le preguntaba al PROPIO
        // teléfono: devolvía index.html, el .json() fallaba y la comprobación
        // no servía para nada — en silencio, porque el catch de abajo se la
        // come. Ver js/destino-api.js.
        const resp = await fetch(`${window.RESTOMIND_API_BASE || ''}/health`, { cache: 'no-store' });
        if (!resp.ok) return;
        const salud = await resp.json();
        if (!salud.codigo_desactualizado) return;

        const banner = document.getElementById('offline-banner');
        if (!banner) return;
        banner.className = 'offline-banner servidor-viejo';
        banner.textContent = 'El servidor está corriendo código viejo. Reinícialo: los cambios no están aplicados.';
        banner.classList.remove('hidden');
    } catch (_) {
        // Sin red o /health caído: el banner de offline ya cubre ese caso.
    }
}

// Aviso de versión nueva del APK.
//
// El que detecta es capacitor-init.js —es quien puede preguntarle a lo nativo
// qué versión está instalada— y avisa por un evento. Pintarlo es trabajo de
// acá: así ese archivo no necesita saber nada de la interfaz, y este no
// necesita saber nada de Capacitor.
//
// Reusa el banner que ya existe en vez de inventar un cartel nuevo: es el
// lugar donde el usuario ya está acostumbrado a que la app le hable.
window.addEventListener('restomind:actualizacion', function (evento) {
    const datos = evento.detail || {};
    const banner = document.getElementById('offline-banner');
    if (!banner) return;
    banner.className = 'offline-banner servidor-viejo';
    banner.textContent = `Hay una versión nueva de RestoMind (${datos.versionNueva}). `
        + 'Descargala cuando puedas — no corre apuro, podés seguir trabajando.';
    banner.classList.remove('hidden');
});

// ============ API CLIENT ============

// Minutos que hay que sumarle a la hora local para obtener UTC (Perú = 300).
// La BD guarda todo en UTC; el backend usa esto para que "hoy" signifique el
// día del restaurante y no el de Greenwich.
function tzOffsetMinutos() {
    return String(new Date().getTimezoneOffset());
}

// FastAPI manda el detalle de un error de validación (422) como una lista
// de objetos, no como texto ({"detail": [{"msg": "Value error, ...", ...}]}).
// Sin esto, el toast le mostraría al usuario ese JSON crudo en vez de un
// mensaje legible como "El celular debe tener 9 dígitos y empezar con 9".
function extraerMensajeError(body, statusFallback) {
    if (!body || !body.detail) return statusFallback;
    if (typeof body.detail === 'string') return body.detail;
    if (Array.isArray(body.detail) && body.detail.length > 0) {
        const msg = body.detail[0].msg || statusFallback;
        return msg.replace(/^Value error,\s*/, '');
    }
    // POST /facturas/generar (y /reintentar) mandan detail como objeto
    // {"mensaje": "...", "factura": {...}} en vez de texto plano, para que
    // el cliente pueda leer también el estado de la Factura ya guardada
    // (ver backend/routes/facturas.py) — no perder ese 'mensaje' acá.
    if (typeof body.detail === 'object' && body.detail.mensaje) {
        return body.detail.mensaje;
    }
    return statusFallback;
}

// Distingue "no hay señal" (fetch ni siquiera llegó a un servidor) de un
// error real del backend (400, 404, 500...). Solo el primero tiene sentido
// reintentarlo solo cuando vuelva la conexión — ver frontend/js/offline.js.
class NetworkError extends Error {}

const api = {
    async _fetch(endpoint, options = {}) {
        let resp;
        try {
            resp = await fetch(`${API_BASE_URL}${endpoint}`, {
                ...options,
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${getToken()}`,
                    'X-TZ-Offset': tzOffsetMinutos(),
                    ...(options.headers || {}),
                },
            });
        } catch (err) {
            throw new NetworkError('Sin conexión');
        }
        if (resp.status === 401) {
            manejarSesionExpirada();
            throw new Error('Sesión expirada');
        }
        if (!resp.ok) {
            let detail = `Error ${resp.status}`;
            let codigo = null;
            let factura = null;
            try {
                const body = await resp.json();
                detail = extraerMensajeError(body, detail);
                // Algunos errores traen un CÓDIGO estable además del texto
                // (ej. IDENTIFICAR_COMPRADOR en /facturas/generar). Se
                // conserva para que quien llama pueda distinguir ESE caso
                // sin tener que buscar palabras dentro del mensaje —
                // frágil, y encima se rompe al reescribir el texto.
                if (body && body.detail && typeof body.detail === 'object') {
                    codigo = body.detail.codigo || null;
                    // /facturas/generar devuelve la Factura YA GUARDADA
                    // dentro del error (502). Se conserva para poder
                    // imprimir el comprobante de contingencia sin volver a
                    // pedirle nada al servidor — que es justo lo que puede
                    // estar caído.
                    factura = body.detail.factura || null;
                }
            } catch (_) { /* respuesta sin JSON */ }
            const error = new Error(detail);
            error.status = resp.status;
            if (codigo) error.codigoNegocio = codigo;
            if (factura) error.factura = factura;
            throw error;
        }
        if (resp.status === 204) return null;
        return resp.json();
    },

    get(endpoint) {
        return this._fetch(endpoint);
    },

    post(endpoint, data) {
        return this._fetch(endpoint, { method: 'POST', body: JSON.stringify(data || {}) });
    },

    patch(endpoint, data) {
        return this._fetch(endpoint, { method: 'PATCH', body: JSON.stringify(data || {}) });
    },

    delete(endpoint, data) {
        const options = { method: 'DELETE' };
        if (data !== undefined) options.body = JSON.stringify(data);
        return this._fetch(endpoint, options);
    },

    // Multipart, sin el header Content-Type: json de _fetch (el navegador
    // arma el boundary correcto solo si no lo tocamos).
    async postFile(endpoint, formData) {
        const resp = await fetch(`${API_BASE_URL}${endpoint}`, {
            method: 'POST',
            headers: { 'Authorization': `Bearer ${getToken()}`, 'X-TZ-Offset': tzOffsetMinutos() },
            body: formData,
        });
        if (resp.status === 401) {
            manejarSesionExpirada();
            throw new Error('Sesión expirada');
        }
        if (!resp.ok) {
            let detail = `Error ${resp.status}`;
            let codigo = null;
            let factura = null;
            try {
                const body = await resp.json();
                detail = extraerMensajeError(body, detail);
                // Algunos errores traen un CÓDIGO estable además del texto
                // (ej. IDENTIFICAR_COMPRADOR en /facturas/generar). Se
                // conserva para que quien llama pueda distinguir ESE caso
                // sin tener que buscar palabras dentro del mensaje —
                // frágil, y encima se rompe al reescribir el texto.
                if (body && body.detail && typeof body.detail === 'object') {
                    codigo = body.detail.codigo || null;
                    // /facturas/generar devuelve la Factura YA GUARDADA
                    // dentro del error (502). Se conserva para poder
                    // imprimir el comprobante de contingencia sin volver a
                    // pedirle nada al servidor — que es justo lo que puede
                    // estar caído.
                    factura = body.detail.factura || null;
                }
            } catch (_) { /* respuesta sin JSON */ }
            const error = new Error(detail);
            error.status = resp.status;
            if (codigo) error.codigoNegocio = codigo;
            if (factura) error.factura = factura;
            throw error;
        }
        return resp.json();
    },
};

// ============ INIT ============

async function init() {
    setupBottomNav();
    setupAdminTabs();
    aplicarPermisosRol();

    try {
        await refreshCatalogo();
    } catch (err) {
        showToast('No se pudo conectar con el servidor', 'error');
        console.error(err);
    }

    if (typeof initOffline === 'function') initOffline();

    // Cada módulo se inicializa de forma aislada: si uno falla, no debe
    // dejar a los demás sin arrancar (pasó con un bug de CSS que dejaba
    // pestañas invisibles; un módulo roto no debería repetir ese efecto).
    //
    // Solo se arrancan los módulos cuya pestaña este rol puede ver:
    // initDashboard e initAdmin piden datos a endpoints admin-only nada más
    // arrancar, así que con un mozo el backend devolvía 403 —correcto— pero
    // la consola quedaba llena de errores rojos en cada carga, tapando
    // cualquier problema de verdad.
    const MODULOS = {
        mozo: 'initMozo',
        cocina: 'initCocina',
        dashboard: 'initDashboard',
        admin: 'initAdmin',
    };
    Object.entries(MODULOS).forEach(([tab, fnName]) => {
        if (!puedeVer(tab)) return;
        try {
            if (typeof window[fnName] === 'function') window[fnName]();
        } catch (err) {
            console.error(`Error iniciando ${fnName}:`, err);
        }
    });

    // Después de los módulos: decide si mostrar el interruptor "Todo en uno"
    // y, si quedó activado en este dispositivo, arranca esa vista. Necesita
    // que initMozo/initCocina ya hayan corrido.
    if (typeof initVistaUnificada === 'function') {
        try {
            initVistaUnificada();
        } catch (err) {
            console.error('Error iniciando la vista unificada:', err);
        }
    }

    // Escape cierra el modal que esté abierto. Antes no había forma de salir
    // con el teclado, y en una laptop (donde el dueño suele tener la app
    // abierta todo el turno) el reflejo es apretar Esc, no buscar la ✕.
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') cerrarModalConEscape();
    });

    // Gate de caja: se revisa al arrancar y cada 20s en segundo plano — así
    // si el admin abre/cierra caja desde otro dispositivo, un mozo con la
    // app ya abierta se desbloquea/bloquea solo, sin tener que recargar.
    if (typeof refreshCajaGate === 'function') {
        refreshCajaGate();
        setInterval(refreshCajaGate, 20000);
    }
}

const CACHE_PLATOS_KEY = 'restomind_cache_platos';
const CACHE_MESAS_KEY = 'restomind_cache_mesas';

async function refreshCatalogo() {
    try {
        const [platos, mesas] = await Promise.all([
            api.get('/platos'),
            api.get('/mesas'),
        ]);
        estado.platos = platos;
        estado.mesas = mesas;
        localStorage.setItem(CACHE_PLATOS_KEY, JSON.stringify(platos));
        localStorage.setItem(CACHE_MESAS_KEY, JSON.stringify(mesas));
    } catch (err) {
        // Sin señal: se usa la última carta/mesas conocida en vez de dejar
        // la pantalla en blanco. Puede estar desactualizada (alguien pudo
        // haber ocupado una mesa desde otro dispositivo mientras tanto),
        // pero es preferible a que el mozo no pueda ni ver el menú.
        if (err instanceof NetworkError) {
            const platosCache = JSON.parse(localStorage.getItem(CACHE_PLATOS_KEY) || '[]');
            const mesasCache = JSON.parse(localStorage.getItem(CACHE_MESAS_KEY) || '[]');
            if (platosCache.length > 0 || mesasCache.length > 0) {
                estado.platos = platosCache;
                estado.mesas = mesasCache;
                return;
            }
        }
        throw err;
    }
}

// ============ NAVEGACIÓN ============

function setupBottomNav() {
    document.querySelectorAll('.nav-btn').forEach(btn => {
        btn.addEventListener('click', () => cambiarTab(btn.dataset.tab));
    });
}

function cambiarTab(tabName) {
    estado.currentTab = tabName;

    document.querySelectorAll('.nav-btn').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.tab === tabName);
        if (btn.dataset.tab === tabName) {
            document.getElementById('page-title').textContent = btn.dataset.title;
        }
    });

    document.querySelectorAll('.tab-content').forEach(tab => {
        tab.classList.toggle('active', tab.id === `${tabName}-tab`);
    });

    if (tabName === 'cocina' && typeof refreshCocina === 'function') refreshCocina();
    if (tabName === 'mozo' && typeof refreshMozo === 'function') refreshMozo();
    if (tabName === 'dashboard' && typeof refreshDashboard === 'function') refreshDashboard();
    if (tabName === 'admin' && typeof refreshAdmin === 'function') refreshAdmin();

    // Mesas/Cocina dependen de si hay caja abierta hoy — al entrar a
    // cualquiera de las dos se revisa fresco, no se confía en el último
    // valor cacheado (pudo abrirse/cerrarse desde otro dispositivo).
    if ((tabName === 'mozo' || tabName === 'cocina') && typeof refreshCajaGate === 'function') {
        refreshCajaGate();
    }
}

// ============ GATE DE CAJA (Mesas/Cocina exigen caja abierta) ============

/**
 * Semáforo que bloquea Mesas y Cocina sin caja abierta hoy: sin esto, el
 * dinero que entra por esas pantallas no tiene ancla contra la cual
 * reconciliar al cerrar (ver "Validador de Caja" en CLAUDE.md) — un mozo
 * podría cobrar toda una jornada sin que exista un saldo_inicial declarado.
 * Consulta GET /caja/gate, que NO expone montos (cualquier rol puede
 * llamarlo, no solo admin) y de paso dispara el auto-cierre de una caja
 * vencida de un día anterior (ver backend/routes/caja.py).
 */
async function refreshCajaGate() {
    try {
        const { hay_caja_abierta } = await api.get('/caja/gate');
        estado.cajaAbierta = hay_caja_abierta;
    } catch (err) {
        // Sin señal o error: no se sabe con certeza -> no bloquear por un
        // problema de red (sería peor que dejar operar sin caja un rato).
        if (estado.cajaAbierta === null) return;
    }
    aplicarGateCaja();
}

function aplicarGateCaja() {
    const bloqueado = estado.cajaAbierta === false;

    ['mozo-tab', 'cocina-tab'].forEach(id => {
        const tab = document.getElementById(id);
        if (tab) tab.classList.toggle('caja-bloqueada', bloqueado);
    });

    // El botón "Ir a Caja" solo tiene sentido para quien puede abrirla.
    ['btn-ir-abrir-caja-mozo', 'btn-ir-abrir-caja-cocina'].forEach(id => {
        const btn = document.getElementById(id);
        if (btn) btn.classList.toggle('hidden', !estado.roles.includes('admin'));
    });
}

function irAAbrirCaja() {
    cambiarTab('admin');
    if (typeof cambiarAdminTab === 'function') cambiarAdminTab('caja');
}

// ============ ROLES ============

function aplicarPermisosRol() {
    const permitidas = tabsPermitidas();

    document.querySelectorAll('.nav-btn').forEach(btn => {
        btn.classList.toggle('hidden', !permitidas.includes(btn.dataset.tab));
    });

    const badge = document.getElementById('rol-badge');
    if (badge) badge.textContent = estado.roles.map(r => ROL_LABELS[r] || r).join(' + ');

    // Solo el Admin puede crear/editar/eliminar mesas — el mozo y el
    // cajero solo las usan.
    const btnGestionMesas = document.getElementById('btn-gestionar-mesas');
    if (btnGestionMesas) btnGestionMesas.classList.toggle('hidden', !estado.roles.includes('admin'));

    // Si la pestaña visible ya no está permitida para ninguno de los roles
    // activos, cambia a la primera que sí lo esté (ej: cambio de Admin a
    // Mozo estando en Cocina).
    if (!permitidas.includes(estado.currentTab)) {
        cambiarTab(permitidas[0]);
    }

    if (typeof renderMesas === 'function' && estado.currentTab === 'mozo') renderMesas();

    // Cocina es el único rol al que le sirve un aviso incluso con la app
    // minimizada (mozo/admin ya están mirando la pantalla al operar). Se
    // activa si jefe_cocina está entre los roles de la cuenta, aunque no
    // sea el único (ej. cajero + jefe_cocina).
    if (estado.roles.includes('jefe_cocina') && typeof activarNotificacionesCocina === 'function') {
        activarNotificacionesCocina();
    }
}

function abrirSelectorRol() {
    abrirModal('modal-rol');
}

function cerrarModalRol() {
    document.getElementById('modal-rol').classList.add('hidden');
}

// Selector manual de dispositivo compartido (sin login individual) — a
// diferencia de una cuenta real, acá se elige UN solo rol a la vez: es el
// "modo" en el que opera este celular ahora mismo, no el conjunto de
// permisos de una persona.
function elegirRol(rol) {
    localStorage.setItem('restomind_roles', JSON.stringify([rol]));
    estado.roles = [rol];
    aplicarPermisosRol();
    cerrarModalRol();
    showToast(`Dispositivo configurado como ${ROL_LABELS[rol]}`, 'success');
}

function setupAdminTabs() {
    document.querySelectorAll('.admin-tab-btn').forEach(btn => {
        btn.addEventListener('click', () => cambiarAdminTab(btn.dataset.adminTab));
    });
}

function cambiarAdminTab(tabName) {
    document.querySelectorAll('.admin-tab-btn').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.adminTab === tabName);
    });
    document.querySelectorAll('.admin-section').forEach(sec => {
        sec.classList.toggle('active', sec.id === `admin-${tabName}`);
    });

    // Boletas se carga al entrar, no al arrancar la app: es la única
    // pestaña cuyo contenido cambia solo por fallas (no por lo que el admin
    // hace ahí), así que mostrarla desactualizada sería engañoso.
    if (tabName === 'boletas' && typeof refreshBoletasPendientes === 'function') {
        refreshBoletasPendientes();
    }

    // Caja también depende de lo que pasó desde la última visita (ventas
    // cobradas mientras el admin estaba en otra pestaña) — recargar en
    // vivo al entrar, igual que boletas.
    if (tabName === 'caja' && typeof refreshCaja === 'function') {
        refreshCaja();
    }
}

// ============ MODALES ============

function abrirModal(id) {
    document.getElementById(id).classList.remove('hidden');
}

function cerrarModal() {
    document.getElementById('modal-comanda').classList.add('hidden');
}

/**
 * Cierra el modal visible que esté más arriba (Escape).
 *
 * No esconde el modal a mano: le hace click a su propia ✕, para que corra la
 * función de cierre que ese modal ya tiene. Varias hacen limpieza además de
 * ocultar (resetean el formulario, vacían el carrito), y saltárselas dejaría
 * datos del cliente anterior cargados en el siguiente uso.
 */
function cerrarModalConEscape() {
    const abiertos = [...document.querySelectorAll('.modal:not(.hidden)')];
    if (!abiertos.length) return false;

    const modal = abiertos[abiertos.length - 1];
    const btnCerrar = modal.querySelector('.btn-close');
    if (btnCerrar) btnCerrar.click();
    else modal.classList.add('hidden');
    return true;
}

function cerrarModalPlato() {
    document.getElementById('modal-plato').classList.add('hidden');
    document.getElementById('form-plato').reset();
}

function cerrarModalCompra() {
    document.getElementById('modal-compra').classList.add('hidden');
    document.getElementById('form-compra').reset();
    editingCompraId = null;
}

// ============ TEMA (oscuro / claro) ============
//
// El tema YA quedó aplicado por el script inline del <head>, antes del
// primer pintado. Lo de acá NO vuelve a decidirlo: sincroniza lo que aquel
// script no podía tocar (la barra de estado y el botón, que todavía no
// existían) y mantiene la app pegada al sistema operativo mientras el
// usuario no haya elegido a mano.

const TEMA_KEY = 'restomind-theme';

// Mismos valores que --bg de cada tema en style.css. Es lo que pinta la
// barra de estado de Android con la app instalada: sin actualizarlo, al
// cambiar de tema queda una franja del color anterior arriba de todo, que
// es exactamente el detalle que delata a una web empaquetada como APK.
const TEMA_BARRA = { dark: '#0F1317', light: '#F4F6F8' };

function temaActual() {
    return document.documentElement.getAttribute('data-theme') === 'light' ? 'light' : 'dark';
}

function applyTheme(tema) {
    // Cualquier valor raro cae en 'dark', que es el default de la app: un
    // localStorage manipulado no puede dejarla sin tema.
    const valido = tema === 'light' ? 'light' : 'dark';
    document.documentElement.setAttribute('data-theme', valido);

    const meta = document.querySelector('meta[name="theme-color"]');
    if (meta) meta.setAttribute('content', TEMA_BARRA[valido]);

    const btn = document.getElementById('themeToggle');
    if (btn) {
        // El ícono lo cambia el CSS; acá solo el texto para lector de
        // pantalla, que sí tiene que decir qué va a PASAR al tocarlo.
        const rotulo = valido === 'dark' ? 'Cambiar a tema claro' : 'Cambiar a tema oscuro';
        btn.setAttribute('title', rotulo);
        btn.setAttribute('aria-label', rotulo);
    }
}

function toggleTheme() {
    const nuevo = temaActual() === 'dark' ? 'light' : 'dark';
    applyTheme(nuevo);
    try {
        localStorage.setItem(TEMA_KEY, nuevo);
    } catch (e) {
        // Modo privado o almacenamiento bloqueado: el cambio vale para esta
        // sesión y se pierde al recargar. Preferible a romper el botón.
    }
}

function initTheme() {
    applyTheme(temaActual());

    // Mientras no haya elección manual, seguir al sistema EN VIVO: si el
    // celular pasa a oscuro al anochecer, la app acompaña sin recargar.
    // Una vez que el usuario tocó el botón, su elección manda y esto deja
    // de intervenir.
    try {
        const consulta = window.matchMedia('(prefers-color-scheme: light)');
        const alCambiarElSistema = (evento) => {
            let guardado = null;
            try { guardado = localStorage.getItem(TEMA_KEY); } catch (_) { /* ignorar */ }
            if (guardado === 'light' || guardado === 'dark') return;
            applyTheme(evento.matches ? 'light' : 'dark');
        };
        if (consulta.addEventListener) consulta.addEventListener('change', alCambiarElSistema);
        else if (consulta.addListener) consulta.addListener(alCambiarElSistema);  // Safari viejo
    } catch (e) { /* matchMedia ausente: queda el tema ya aplicado */ }
}

document.addEventListener('DOMContentLoaded', initTheme);


// ============ UTILIDADES ============

function formatCurrency(num) {
    return `S/ ${parseFloat(num || 0).toFixed(2)}`;
}

function formatDate(dateStr) {
    const [y, m, d] = dateStr.split('-');
    return `${d}/${m}/${y}`;
}

function formatDateInput(date) {
    const year = date.getFullYear();
    const month = String(date.getMonth() + 1).padStart(2, '0');
    const day = String(date.getDate()).padStart(2, '0');
    return `${year}-${month}-${day}`;
}

function escapeHtml(str) {
    const div = document.createElement('div');
    div.textContent = str == null ? '' : String(str);
    return div.innerHTML;
}

let toastTimer = null;

function showToast(message, type = 'info') {
    const container = document.getElementById('toast-container');
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.textContent = message;
    container.appendChild(toast);

    setTimeout(() => {
        toast.style.transition = 'opacity 0.25s';
        toast.style.opacity = '0';
        setTimeout(() => toast.remove(), 250);
    }, 2600);
}
