/**
 * CU-01 y CU-04: Panel de Administración
 * - CU-01: Gestión de la Carta (crear/editar/desactivar platos)
 * - CU-04: Control de Compras y Caja Chica
 */

let editingPlatoId = null;
let adminCompras = [];

const ICON_EDIT = '<svg viewBox="0 0 24 24"><path d="M12 20h9"/><path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z"/></svg>';
const ICON_TOGGLE = '<svg viewBox="0 0 24 24"><path d="M18.36 6.64a9 9 0 1 1-12.73 0"/><line x1="12" y1="2" x2="12" y2="12"/></svg>';
const ICON_CANCEL = '<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg>';
const ICON_RESTORE = '<svg viewBox="0 0 24 24"><polyline points="1 4 1 10 7 10"/><path d="M3.51 15a9 9 0 1 0 2.13-9.36L1 10"/></svg>';

function initAdmin() {
    document.getElementById('compra-fecha').value = formatDateInput(new Date());
    refreshAdmin();
}

async function refreshAdmin() {
    try {
        const [platos, compras] = await Promise.all([
            api.get('/platos?incluir_inactivos=true'),
            api.get('/compras'),
        ]);
        estado.platos = platos;
        adminCompras = compras;
    } catch (err) {
        console.error('Error cargando datos de administración:', err);
    }
    renderPlatosAdmin();
    renderCompras();
}

// ============ CU-01: PLATOS ============

function renderPlatosAdmin() {
    const container = document.getElementById('admin-platos-list');

    if (estado.platos.length === 0) {
        container.innerHTML = '<p class="empty-hint">Aún no registras platos en tu carta.</p>';
        return;
    }

    container.innerHTML = estado.platos.map(plato => `
        <div class="admin-item ${plato.estado === 'inactivo' ? 'inactivo' : ''}">
            <div class="admin-item-info">
                <h3>${escapeHtml(plato.nombre)}</h3>
                <p>${escapeHtml(plato.categoria)} · ${formatCurrency(plato.precio_venta)}</p>
            </div>
            <div class="admin-item-actions">
                <button class="icon-btn" title="Editar" onclick="editarPlato(${plato.id})">${ICON_EDIT}</button>
                <button class="icon-btn ${plato.estado === 'activo' ? '' : 'danger'}" title="Activar/Desactivar" onclick="desactivarPlato(${plato.id})">${ICON_TOGGLE}</button>
            </div>
        </div>
    `).join('');
}

function abrirModalNuevoPlato() {
    editingPlatoId = null;
    document.getElementById('modal-plato-title').textContent = 'Nuevo Plato';
    document.getElementById('form-plato').reset();
    abrirModal('modal-plato');
}

function editarPlato(platoId) {
    const plato = estado.platos.find(p => p.id === platoId);
    if (!plato) return;

    editingPlatoId = platoId;
    document.getElementById('modal-plato-title').textContent = 'Editar Plato';
    document.getElementById('plato-nombre').value = plato.nombre;
    document.getElementById('plato-categoria').value = plato.categoria;
    document.getElementById('plato-precio').value = plato.precio_venta;
    document.getElementById('plato-descripcion').value = plato.descripcion || '';
    abrirModal('modal-plato');
}

async function guardarPlato(event) {
    event.preventDefault();

    const data = {
        nombre: document.getElementById('plato-nombre').value.trim(),
        categoria: document.getElementById('plato-categoria').value.trim(),
        precio_venta: parseFloat(document.getElementById('plato-precio').value),
        descripcion: document.getElementById('plato-descripcion').value.trim() || null,
    };

    try {
        if (editingPlatoId) {
            await api.patch(`/platos/${editingPlatoId}`, data);
            showToast('Plato actualizado', 'success');
        } else {
            await api.post('/platos', data);
            showToast('Plato creado', 'success');
        }
        cerrarModalPlato();
        await refreshAdmin();
        await refreshCatalogo();
        if (typeof refreshMozo === 'function') refreshMozo();
    } catch (err) {
        showToast(err.message || 'Error al guardar el plato', 'error');
    }
}

async function desactivarPlato(platoId) {
    const plato = estado.platos.find(p => p.id === platoId);
    const nuevoEstado = plato.estado === 'activo' ? 'inactivo' : 'activo';

    try {
        await api.patch(`/platos/${platoId}/estado`, { estado: nuevoEstado });
        await refreshAdmin();
        await refreshCatalogo();
        showToast(`Plato ${nuevoEstado === 'activo' ? 'activado' : 'desactivado'}`, 'success');
    } catch (err) {
        showToast(err.message || 'Error al cambiar estado', 'error');
    }
}

// ============ CU-04: COMPRAS ============

function renderCompras() {
    const container = document.getElementById('admin-compras-list');

    if (adminCompras.length === 0) {
        container.innerHTML = '<p class="empty-hint">Aún no registras gastos.</p>';
        return;
    }

    const porFecha = {};
    adminCompras.forEach(compra => {
        (porFecha[compra.fecha] = porFecha[compra.fecha] || []).push(compra);
    });

    const fechas = Object.keys(porFecha).sort().reverse();

    container.innerHTML = fechas.map(fecha => {
        const compras = porFecha[fecha];
        const totalDia = compras.reduce((sum, c) => sum + (c.estado === 'registrado' ? c.monto : 0), 0);

        const itemsHtml = compras.map(compra => `
            <div class="admin-item ${compra.estado === 'cancelado' ? 'inactivo' : ''}">
                <div class="admin-item-info">
                    <h4>${escapeHtml(compra.descripcion)}</h4>
                    <p>${escapeHtml(compra.categoria || 'Sin categoría')} · ${formatCurrency(compra.monto)}</p>
                </div>
                <div class="admin-item-actions">
                    <button class="icon-btn ${compra.estado === 'registrado' ? 'danger' : ''}" title="Cancelar/Restaurar" onclick="cancelarCompra(${compra.id})">
                        ${compra.estado === 'registrado' ? ICON_CANCEL : ICON_RESTORE}
                    </button>
                </div>
            </div>
        `).join('');

        return `
            <div class="day-group-title"><span>${formatDate(fecha)}</span><span>${formatCurrency(totalDia)}</span></div>
            ${itemsHtml}
        `;
    }).join('');
}

function abrirModalNuevaCompra() {
    document.getElementById('form-compra').reset();
    document.getElementById('compra-fecha').value = formatDateInput(new Date());
    abrirModal('modal-compra');
}

async function guardarCompra(event) {
    event.preventDefault();

    const data = {
        descripcion: document.getElementById('compra-descripcion').value.trim(),
        categoria: document.getElementById('compra-categoria').value || null,
        monto: parseFloat(document.getElementById('compra-monto').value),
        fecha: document.getElementById('compra-fecha').value,
    };

    try {
        await api.post('/compras', data);
        showToast('Gasto registrado', 'success');
        cerrarModalCompra();
        await refreshAdmin();
        if (typeof refreshDashboard === 'function') refreshDashboard();
    } catch (err) {
        showToast(err.message || 'Error al registrar el gasto', 'error');
    }
}

async function cancelarCompra(compraId) {
    const compra = adminCompras.find(c => c.id === compraId);
    const nuevoEstado = compra.estado === 'registrado' ? 'cancelado' : 'registrado';

    try {
        await api.patch(`/compras/${compraId}/estado`, { estado: nuevoEstado });
        await refreshAdmin();
        if (typeof refreshDashboard === 'function') refreshDashboard();
        showToast(`Gasto ${nuevoEstado}`, 'success');
    } catch (err) {
        showToast(err.message || 'Error al cambiar estado', 'error');
    }
}
