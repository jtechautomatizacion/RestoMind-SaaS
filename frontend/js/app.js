/**
 * RestoMind - Aplicación Compartida
 * API client, estado global, navegación y utilidades.
 */

const API_BASE_URL = '/api';

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
    currentTab: 'mozo'
};

// ============ API CLIENT ============

// Minutos que hay que sumarle a la hora local para obtener UTC (Perú = 300).
// La BD guarda todo en UTC; el backend usa esto para que "hoy" signifique el
// día del restaurante y no el de Greenwich.
function tzOffsetMinutos() {
    return String(new Date().getTimezoneOffset());
}

const api = {
    async _fetch(endpoint, options = {}) {
        const resp = await fetch(`${API_BASE_URL}${endpoint}`, {
            ...options,
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${getToken()}`,
                'X-TZ-Offset': tzOffsetMinutos(),
                ...(options.headers || {}),
            },
        });
        if (resp.status === 401) {
            manejarSesionExpirada();
            throw new Error('Sesión expirada');
        }
        if (!resp.ok) {
            let detail = `Error ${resp.status}`;
            try {
                const body = await resp.json();
                if (body.detail) detail = typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail);
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

    delete(endpoint) {
        return this._fetch(endpoint, { method: 'DELETE' });
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
                if (body.detail) detail = typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail);
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
}

async function refreshCatalogo() {
    const [platos, mesas] = await Promise.all([
        api.get('/platos'),
        api.get('/mesas'),
    ]);
    estado.platos = platos;
    estado.mesas = mesas;
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
