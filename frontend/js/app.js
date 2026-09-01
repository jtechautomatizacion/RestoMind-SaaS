/**
 * RestoMind - Aplicación Compartida
 * API client, estado global, navegación y utilidades.
 */

const API_BASE_URL = '/api';

// Filtra cualquier tecla que no sea dígito a medida que se escribe — más
// rápido de corregir para el usuario que dejarlo escribir letras/guiones
// y recién avisarle con un error al enviar el formulario.
function soloDigitos(event) {
    event.target.value = event.target.value.replace(/\D/g, '');
}

// Qué pestañas puede ver cada rol. Sin login todavía, el rol se elige una
// vez por dispositivo (el celular del mozo, el de caja, etc.) y queda
// guardado en localStorage — cuando exista autenticación real, esto se
// reemplaza por el rol que devuelva el login, pero la lógica de abajo
// (aplicarPermisosRol) no cambia.
const ROLES_PERMITIDOS = {
    admin: ['mozo', 'cocina', 'dashboard', 'admin'],
    mozo: ['mozo'],
    jefe_cocina: ['cocina'],
    cajero: ['mozo'],
};

const ROL_LABELS = {
    admin: 'Admin',
    mozo: 'Mozo',
    jefe_cocina: 'Cocina',
    cajero: 'Cajero',
};

function getRolGuardado() {
    return localStorage.getItem('restomind_rol') || 'admin';
}

const estado = {
    clienteId: null, // Se completa en auth.js al validar la sesión
    usuario: null,   // { email, nombre, rol, cliente_id, cliente_nombre }
    rol: getRolGuardado(),
    platos: [],
    mesas: [],
    currentTab: 'mozo',
    cajaAbierta: null // null = aún no se consultó; ver refreshCajaGate()
};

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
            try {
                const body = await resp.json();
                detail = extraerMensajeError(body, detail);
            } catch (_) { /* respuesta sin JSON */ }
            throw new Error(detail);
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
            try {
                const body = await resp.json();
                detail = extraerMensajeError(body, detail);
            } catch (_) { /* respuesta sin JSON */ }
            throw new Error(detail);
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
    ['initMozo', 'initCocina', 'initDashboard', 'initAdmin'].forEach(fnName => {
        try {
            if (typeof window[fnName] === 'function') window[fnName]();
        } catch (err) {
            console.error(`Error iniciando ${fnName}:`, err);
        }
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
        if (btn) btn.classList.toggle('hidden', estado.rol !== 'admin');
    });
}

function irAAbrirCaja() {
    cambiarTab('admin');
    if (typeof cambiarAdminTab === 'function') cambiarAdminTab('caja');
}

// ============ ROLES ============

function aplicarPermisosRol() {
    const permitidas = ROLES_PERMITIDOS[estado.rol] || ROLES_PERMITIDOS.mozo;

    document.querySelectorAll('.nav-btn').forEach(btn => {
        btn.classList.toggle('hidden', !permitidas.includes(btn.dataset.tab));
    });

    const badge = document.getElementById('rol-badge');
    if (badge) badge.textContent = ROL_LABELS[estado.rol] || estado.rol;

    // Solo el Admin puede crear/editar/eliminar mesas — el mozo y el
    // cajero solo las usan.
    const btnGestionMesas = document.getElementById('btn-gestionar-mesas');
    if (btnGestionMesas) btnGestionMesas.classList.toggle('hidden', estado.rol !== 'admin');

    // Si la pestaña visible ya no está permitida para este rol, cambia a
    // la primera que sí lo esté (ej: cambio de Admin a Mozo estando en Cocina).
    if (!permitidas.includes(estado.currentTab)) {
        cambiarTab(permitidas[0]);
    }

    if (typeof renderMesas === 'function' && estado.currentTab === 'mozo') renderMesas();

    // Cocina es el único rol al que le sirve un aviso incluso con la app
    // minimizada (mozo/admin ya están mirando la pantalla al operar).
    if (estado.rol === 'jefe_cocina' && typeof activarNotificacionesCocina === 'function') {
        activarNotificacionesCocina();
    }
}

function abrirSelectorRol() {
    abrirModal('modal-rol');
}

function cerrarModalRol() {
    document.getElementById('modal-rol').classList.add('hidden');
}

function elegirRol(rol) {
    localStorage.setItem('restomind_rol', rol);
    estado.rol = rol;
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

function cerrarModalPlato() {
    document.getElementById('modal-plato').classList.add('hidden');
    document.getElementById('form-plato').reset();
}

function cerrarModalCompra() {
    document.getElementById('modal-compra').classList.add('hidden');
    document.getElementById('form-compra').reset();
    editingCompraId = null;
}

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
