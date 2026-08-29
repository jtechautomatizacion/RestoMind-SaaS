/**
 * RestoMind - Aplicación Compartida
 * API client, estado global, navegación y utilidades.
 */

const API_BASE_URL = '/api';

const estado = {
    clienteId: 'rest-001', // TODO: vendrá del login cuando exista auth
    platos: [],
    mesas: [],
    currentTab: 'mozo'
};

// ============ API CLIENT ============

const api = {
    async _fetch(endpoint, options = {}) {
        const resp = await fetch(`${API_BASE_URL}${endpoint}`, {
            ...options,
            headers: {
                'Content-Type': 'application/json',
                'X-Cliente-Id': estado.clienteId,
                ...(options.headers || {}),
            },
        });
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
};

// ============ INIT ============

async function init() {
    setupBottomNav();
    setupAdminTabs();

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
