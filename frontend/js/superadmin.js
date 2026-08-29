/**
 * Panel General (superadmin) — ve y administra TODOS los restaurantes.
 *
 * Deliberadamente independiente de app.js/auth.js: aquella lógica está
 * atada a la sesión de UN restaurante (estado.clienteId, manejarSesionExpirada,
 * etc.) y mezclarla acá abriría la puerta a confundir un token de
 * superadmin con uno de restaurante. Esta página es de un mundo aparte.
 */

const API_BASE_URL = '/api';
const SA_TOKEN_KEY = 'restomind_superadmin_token';

let clientesCache = [];
let clienteEnResetPassword = null;

// ============ UTILIDADES (copiadas de app.js: esta página no lo carga) ============

function escapeHtml(str) {
    const div = document.createElement('div');
    div.textContent = str == null ? '' : String(str);
    return div.innerHTML;
}

function formatCurrency(num) {
    return `S/ ${parseFloat(num || 0).toFixed(2)}`;
}

function formatDate(isoString) {
    const d = new Date(isoString);
    return d.toLocaleDateString('es-PE');
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

function abrirModal(id) {
    document.getElementById(id).classList.remove('hidden');
}

// ============ SESIÓN ============

function getSaToken() {
    return localStorage.getItem(SA_TOKEN_KEY);
}

async function saFetch(endpoint, options = {}) {
    const resp = await fetch(`${API_BASE_URL}${endpoint}`, {
        ...options,
        headers: {
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${getSaToken()}`,
            ...(options.headers || {}),
        },
    });
    if (resp.status === 401 || resp.status === 403) {
        cerrarSesionSuperadmin();
        throw new Error('Sesión inválida');
    }
    if (!resp.ok) {
        const body = await resp.json().catch(() => ({}));
        throw new Error(body.detail || `Error ${resp.status}`);
    }
    return resp.status === 204 ? null : resp.json();
}

function mostrarLoginSuperadmin(mensaje) {
    document.getElementById('login-screen').classList.remove('hidden');
    document.getElementById('app').classList.add('hidden');
    const error = document.getElementById('login-error');
    if (mensaje) {
        error.textContent = mensaje;
        error.classList.remove('hidden');
    } else {
        error.classList.add('hidden');
    }
}

function mostrarAppSuperadmin() {
    document.getElementById('login-screen').classList.add('hidden');
    document.getElementById('app').classList.remove('hidden');
}

function cerrarSesionSuperadmin() {
    localStorage.removeItem(SA_TOKEN_KEY);
    window.location.reload();
}

async function manejarLoginSuperadmin(event) {
    event.preventDefault();
    const email = document.getElementById('login-email').value.trim();
    const password = document.getElementById('login-password').value;
    const boton = document.getElementById('btn-login');

    boton.disabled = true;
    boton.textContent = 'Ingresando...';

    try {
        const resp = await fetch(`${API_BASE_URL}/superadmin/login`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ email, password }),
        });
        if (!resp.ok) {
            const body = await resp.json().catch(() => ({}));
            throw new Error(body.detail || 'No se pudo iniciar sesión');
        }
        const data = await resp.json();
        localStorage.setItem(SA_TOKEN_KEY, data.access_token);
        document.getElementById('nombre-superadmin-header').textContent = data.nombre;
        mostrarAppSuperadmin();
        await refreshClientes();
    } catch (err) {
        mostrarLoginSuperadmin(err.message);
    } finally {
        boton.disabled = false;
        boton.textContent = 'Ingresar';
    }
}

async function initSuperadmin() {
    document.getElementById('form-login').addEventListener('submit', manejarLoginSuperadmin);

    if (!getSaToken()) {
        mostrarLoginSuperadmin();
        return;
    }

    // Fetch directo (no saFetch): esta validación inicial maneja su propio
    // caso de "token vencido" mostrando un mensaje específico, en vez del
    // reload genérico que dispara saFetch para acciones dentro de la app.
    try {
        const resp = await fetch(`${API_BASE_URL}/superadmin/me`, {
            headers: { 'Authorization': `Bearer ${getSaToken()}` },
        });
        if (!resp.ok) throw new Error('Sesión inválida');

        const yo = await resp.json();
        document.getElementById('nombre-superadmin-header').textContent = yo.nombre;
        mostrarAppSuperadmin();
        await refreshClientes();
    } catch (_) {
        localStorage.removeItem(SA_TOKEN_KEY);
        mostrarLoginSuperadmin('Tu sesión expiró. Ingresa de nuevo.');
    }
}

// ============ LISTA DE CLIENTES ============

async function refreshClientes() {
    clientesCache = await saFetch('/superadmin/clientes');
    renderClientes();
}

function renderClientes() {
    const container = document.getElementById('clientes-list');

    if (clientesCache.length === 0) {
        container.innerHTML = '<p class="empty-hint">Aún no diste de alta ningún restaurante.</p>';
        return;
    }

    container.innerHTML = clientesCache.map(c => `
        <div class="cliente-card">
            <div class="cliente-card-header">
                <div>
                    <div class="cliente-card-nombre">${escapeHtml(c.nombre)}</div>
                    <div class="cliente-card-email">${escapeHtml(c.email)} · desde ${formatDate(c.creado_en)}</div>
                </div>
                <span class="cliente-estado-badge ${c.estado}">${c.estado}</span>
            </div>
            <div class="cliente-stats-row">
                <div class="cliente-stat"><div class="num">${c.num_usuarios}</div><div class="label">Usuarios</div></div>
                <div class="cliente-stat"><div class="num">${c.num_platos}</div><div class="label">Platos</div></div>
                <div class="cliente-stat"><div class="num">${c.num_mesas}</div><div class="label">Mesas</div></div>
                <div class="cliente-stat"><div class="num">${formatCurrency(c.ventas_mes_actual)}</div><div class="label">Este mes</div></div>
            </div>
            <div class="cliente-card-actions">
                ${c.estado === 'activo'
                    ? `<button class="btn btn-secondary" onclick="cambiarEstadoCliente('${c.id}', 'suspendido')">Suspender</button>`
                    : `<button class="btn btn-secondary" onclick="cambiarEstadoCliente('${c.id}', 'activo')">Reactivar</button>`}
                <button class="btn btn-secondary" onclick="abrirModalResetPassword('${c.id}', '${escapeHtml(c.nombre)}')">Resetear contraseña</button>
            </div>
        </div>
    `).join('');
}

async function cambiarEstadoCliente(clienteId, nuevoEstado) {
    const accion = nuevoEstado === 'suspendido' ? 'suspender' : 'reactivar';
    if (!confirm(`¿Seguro que quieres ${accion} este restaurante?`)) return;

    try {
        await saFetch(`/superadmin/clientes/${clienteId}/estado`, {
            method: 'PATCH',
            body: JSON.stringify({ estado: nuevoEstado }),
        });
        showToast(`Restaurante ${nuevoEstado === 'suspendido' ? 'suspendido' : 'reactivado'}`, 'success');
        await refreshClientes();
    } catch (err) {
        showToast(err.message || 'Error al cambiar el estado', 'error');
    }
}

// ============ NUEVO RESTAURANTE ============

function abrirModalNuevoCliente() {
    document.getElementById('form-nuevo-cliente').reset();
    document.getElementById('nc-mesas').value = 8;
    abrirModal('modal-nuevo-cliente');
}

function cerrarModalNuevoCliente() {
    document.getElementById('modal-nuevo-cliente').classList.add('hidden');
}

async function guardarNuevoCliente(event) {
    event.preventDefault();

    const payload = {
        nombre: document.getElementById('nc-nombre').value.trim(),
        email: document.getElementById('nc-email').value.trim(),
        telefono: document.getElementById('nc-telefono').value.trim() || null,
        num_mesas: parseInt(document.getElementById('nc-mesas').value, 10),
        admin_nombre: document.getElementById('nc-admin-nombre').value.trim(),
        admin_email: document.getElementById('nc-admin-email').value.trim(),
        admin_password: document.getElementById('nc-admin-password').value,
    };

    try {
        await saFetch('/superadmin/clientes', { method: 'POST', body: JSON.stringify(payload) });
        cerrarModalNuevoCliente();
        await refreshClientes();
        showToast('Restaurante creado', 'success');
    } catch (err) {
        showToast(err.message || 'Error al crear el restaurante', 'error');
    }
}

// ============ RESETEAR CONTRASEÑA ============

function abrirModalResetPassword(clienteId, nombreCliente) {
    clienteEnResetPassword = clienteId;
    document.getElementById('form-reset-password').reset();
    document.getElementById('reset-password-cliente-nombre').textContent = `Restaurante: ${nombreCliente}`;
    abrirModal('modal-reset-password');
}

function cerrarModalResetPassword() {
    document.getElementById('modal-reset-password').classList.add('hidden');
    clienteEnResetPassword = null;
}

async function confirmarResetPassword(event) {
    event.preventDefault();
    const nuevaPassword = document.getElementById('reset-nueva-password').value;

    try {
        const resultado = await saFetch(`/superadmin/clientes/${clienteEnResetPassword}/reset-password`, {
            method: 'PATCH',
            body: JSON.stringify({ nueva_password: nuevaPassword }),
        });
        cerrarModalResetPassword();
        showToast(`Contraseña actualizada para ${resultado.email}`, 'success');
    } catch (err) {
        showToast(err.message || 'Error al resetear la contraseña', 'error');
    }
}

// ============ MI PERFIL (SUPERADMIN) ============

async function abrirModalMiPerfil() {
    try {
        const resp = await fetch(`${API_BASE_URL}/superadmin/me`, {
            headers: { 'Authorization': `Bearer ${getSaToken()}` },
        });
        if (!resp.ok) throw new Error('No se pudo cargar el perfil');

        const perfil = await resp.json();
        document.getElementById('perfil-email').value = perfil.email;
        document.getElementById('perfil-nombre').value = perfil.nombre;
        document.getElementById('perfil-password-actual').value = '';
        document.getElementById('perfil-password-nueva').value = '';

        abrirModal('modal-mi-perfil');
    } catch (err) {
        showToast(err.message || 'Error al cargar el perfil', 'error');
    }
}

function cerrarModalMiPerfil() {
    document.getElementById('modal-mi-perfil').classList.add('hidden');
}

async function guardarMiPerfil() {
    const nombre = document.getElementById('perfil-nombre').value.trim();

    if (!nombre) {
        showToast('Ingresa tu nombre', 'error');
        return;
    }

    try {
        await saFetch('/superadmin/me', {
            method: 'PATCH',
            body: JSON.stringify({ nombre }),
        });
        showToast('Nombre actualizado', 'success');
    } catch (err) {
        showToast(err.message || 'Error al guardar el perfil', 'error');
    }
}

async function cambiarMiPassword() {
    const passwordActual = document.getElementById('perfil-password-actual').value;
    const nuevaPassword = document.getElementById('perfil-password-nueva').value;

    if (!passwordActual || !nuevaPassword) {
        showToast('Completa ambos campos', 'error');
        return;
    }

    if (nuevaPassword.length < 6) {
        showToast('La nueva contraseña debe tener al menos 6 caracteres', 'error');
        return;
    }

    try {
        await saFetch('/superadmin/me/password', {
            method: 'PATCH',
            body: JSON.stringify({ password_actual: passwordActual, nueva_password: nuevaPassword }),
        });
        document.getElementById('perfil-password-actual').value = '';
        document.getElementById('perfil-password-nueva').value = '';
        showToast('Contraseña actualizada exitosamente', 'success');
    } catch (err) {
        showToast(err.message || 'Error al cambiar la contraseña', 'error');
    }
}
