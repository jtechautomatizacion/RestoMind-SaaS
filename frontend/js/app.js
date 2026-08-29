/**
 * RestoMind - Aplicación Compartida
 * API client, auth, utilidades globales
 */

const API_BASE_URL = 'http://localhost:8000/api';

// Estado global
const estado = {
    clienteId: 'rest-001', // TODO: obtener de login
    platos: [],
    mesas: [],
    comandas: [],
    compras: [],
    currentTab: 'mozo'
};

// API Client
const api = {
    async get(endpoint) {
        const resp = await fetch(`${API_BASE_URL}${endpoint}`);
        if (!resp.ok) throw new Error(`GET ${endpoint} failed`);
        return resp.json();
    },

    async post(endpoint, data) {
        const resp = await fetch(`${API_BASE_URL}${endpoint}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });
        if (!resp.ok) throw new Error(`POST ${endpoint} failed`);
        return resp.json();
    },

    async patch(endpoint, data) {
        const resp = await fetch(`${API_BASE_URL}${endpoint}`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });
        if (!resp.ok) throw new Error(`PATCH ${endpoint} failed`);
        return resp.json();
    }
};

// Initialize App
async function init() {
    console.log('RestoMind iniciándose...');

    // Load data
    try {
        estado.platos = await api.get('/platos');
        estado.mesas = await api.get('/mesas');
        estado.comandas = await api.get('/comandas');
        estado.compras = await api.get('/compras');
    } catch (err) {
        console.error('Error cargando datos:', err);
    }

    // Setup nav
    document.querySelectorAll('.nav-btn').forEach(btn => {
        btn.addEventListener('click', () => cambiarTab(btn.dataset.tab));
    });

    // Setup admin tabs
    document.querySelectorAll('.admin-tab-btn').forEach(btn => {
        btn.addEventListener('click', () => cambiarAdminTab(btn.dataset.adminTab));
    });

    // Initialize modules
    if (typeof initMozo === 'function') initMozo();
    if (typeof initCocina === 'function') initCocina();
    if (typeof initAdmin === 'function') initAdmin();

    console.log('RestoMind listo');
}

function cambiarTab(tabName) {
    estado.currentTab = tabName;

    // Update nav
    document.querySelectorAll('.nav-btn').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.tab === tabName);
    });

    // Update content
    document.querySelectorAll('.tab-content').forEach(tab => {
        tab.classList.toggle('active', tab.id === `${tabName}-tab`);
    });

    // Refresh data if needed
    if (tabName === 'cocina') refreshCocina();
    if (tabName === 'mozo') refreshMozo();
}

function cambiarAdminTab(tabName) {
    // Update buttons
    document.querySelectorAll('.admin-tab-btn').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.adminTab === tabName);
    });

    // Update sections
    document.querySelectorAll('.admin-section').forEach(sec => {
        sec.classList.toggle('active', sec.id === `admin-${tabName}`);
    });
}

// Modal utilities
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

// Utility functions
function formatCurrency(num) {
    return `S/ ${parseFloat(num).toFixed(2)}`;
}

function formatDate(dateStr) {
    const date = new Date(dateStr);
    return date.toLocaleDateString('es-PE');
}

function formatDateInput(dateStr) {
    const date = new Date(dateStr);
    const year = date.getFullYear();
    const month = String(date.getMonth() + 1).padStart(2, '0');
    const day = String(date.getDate()).padStart(2, '0');
    return `${year}-${month}-${day}`;
}

// Toast notifications (simple)
function showToast(message, type = 'info') {
    console.log(`[${type.toUpperCase()}] ${message}`);
    // TODO: Implementar UI toast
}
