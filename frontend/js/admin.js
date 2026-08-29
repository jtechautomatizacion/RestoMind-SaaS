/**
 * CU-01 y CU-04: Panel de Administración
 * - CU-01: Gestión de la Carta (crear/editar/desactivar platos)
 * - CU-04: Control de Compras y Caja Chica
 */

let editingPlatoId = null;
let adminCompras = [];
let archivoImagenPendiente = null; // Blob ya comprimido, listo para subir tras guardar
let platoImagenActualUrl = null;   // imagen_url ya guardada en el server (si se está editando)

const ICON_EDIT = '<svg viewBox="0 0 24 24"><path d="M12 20h9"/><path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z"/></svg>';
const ICON_TOGGLE = '<svg viewBox="0 0 24 24"><path d="M18.36 6.64a9 9 0 1 1-12.73 0"/><line x1="12" y1="2" x2="12" y2="12"/></svg>';
const ICON_CANCEL = '<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg>';
const ICON_RESTORE = '<svg viewBox="0 0 24 24"><polyline points="1 4 1 10 7 10"/><path d="M3.51 15a9 9 0 1 0 2.13-9.36L1 10"/></svg>';
const ICON_PHOTO_PLACEHOLDER = '<div class="item-thumb-placeholder"><svg viewBox="0 0 24 24"><rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="8.5" cy="8.5" r="1.5"/><path d="M21 15l-5-5L5 21"/></svg></div>';

function _thumbHtml(imagenUrl) {
    if (imagenUrl) {
        return `<img class="item-thumb" src="${escapeHtml(imagenUrl)}" alt="">`;
    }
    return ICON_PHOTO_PLACEHOLDER;
}

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
            <div class="admin-item-main">
                ${_thumbHtml(plato.imagen_url)}
                <div class="admin-item-info">
                    <h3>${escapeHtml(plato.nombre)}</h3>
                    <p>${escapeHtml(plato.categoria)} · ${formatCurrency(plato.precio_venta)}</p>
                </div>
            </div>
            <div class="admin-item-actions">
                <button class="icon-btn" title="Editar" onclick="editarPlato(${plato.id})">${ICON_EDIT}</button>
                <button class="icon-btn ${plato.estado === 'activo' ? '' : 'danger'}" title="Activar/Desactivar" onclick="desactivarPlato(${plato.id})">${ICON_TOGGLE}</button>
            </div>
        </div>
    `).join('');
}

function resetFormImagen() {
    archivoImagenPendiente = null;
    platoImagenActualUrl = null;
    document.getElementById('plato-imagen-input').value = '';
    document.getElementById('imagen-preview').classList.add('hidden');
    document.getElementById('imagen-placeholder').classList.remove('hidden');
    document.getElementById('btn-quitar-imagen').classList.add('hidden');
}

function abrirModalNuevoPlato() {
    editingPlatoId = null;
    document.getElementById('modal-plato-title').textContent = 'Nuevo Plato';
    document.getElementById('form-plato').reset();
    resetFormImagen();
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

    resetFormImagen();
    if (plato.imagen_url) {
        platoImagenActualUrl = plato.imagen_url;
        document.getElementById('imagen-preview').src = plato.imagen_url;
        document.getElementById('imagen-preview').classList.remove('hidden');
        document.getElementById('imagen-placeholder').classList.add('hidden');
        document.getElementById('btn-quitar-imagen').classList.remove('hidden');
    }

    abrirModal('modal-plato');
}

/**
 * Redimensiona y comprime la foto en el navegador antes de subirla (máx
 * 800px de lado, JPEG calidad 0.8). Una foto de celular sin comprimir puede
 * pesar 4-8MB; en una conexión de restaurante o un plan de datos limitado
 * eso es carga eterna. Esto la deja típicamente por debajo de 150-300KB.
 */
function comprimirImagen(file, maxDim = 800, calidad = 0.8) {
    return new Promise((resolve, reject) => {
        const img = new Image();
        const objectUrl = URL.createObjectURL(file);

        img.onload = () => {
            let { width, height } = img;
            if (width > maxDim || height > maxDim) {
                if (width > height) {
                    height = Math.round(height * (maxDim / width));
                    width = maxDim;
                } else {
                    width = Math.round(width * (maxDim / height));
                    height = maxDim;
                }
            }

            const canvas = document.createElement('canvas');
            canvas.width = width;
            canvas.height = height;
            canvas.getContext('2d').drawImage(img, 0, 0, width, height);

            canvas.toBlob(blob => {
                URL.revokeObjectURL(objectUrl);
                if (blob) resolve(blob); else reject(new Error('No se pudo procesar la imagen'));
            }, 'image/jpeg', calidad);
        };

        img.onerror = () => {
            URL.revokeObjectURL(objectUrl);
            reject(new Error('Archivo de imagen inválido'));
        };

        img.src = objectUrl;
    });
}

async function previsualizarImagen(event) {
    const file = event.target.files[0];
    if (!file) return;

    if (!file.type.startsWith('image/')) {
        showToast('Selecciona un archivo de imagen', 'warning');
        event.target.value = '';
        return;
    }

    try {
        const blob = await comprimirImagen(file);
        archivoImagenPendiente = blob;

        const preview = document.getElementById('imagen-preview');
        preview.src = URL.createObjectURL(blob);
        preview.classList.remove('hidden');
        document.getElementById('imagen-placeholder').classList.add('hidden');
        document.getElementById('btn-quitar-imagen').classList.remove('hidden');
    } catch (err) {
        showToast('No se pudo procesar la imagen', 'error');
    }
}

async function quitarImagenPlato() {
    archivoImagenPendiente = null;

    if (editingPlatoId && platoImagenActualUrl) {
        try {
            await api.delete(`/platos/${editingPlatoId}/imagen`);
            platoImagenActualUrl = null;
            showToast('Foto eliminada', 'success');
            await refreshCatalogo();
            if (typeof refreshMozo === 'function') refreshMozo();
        } catch (err) {
            showToast(err.message || 'No se pudo eliminar la foto', 'error');
        }
    }

    document.getElementById('plato-imagen-input').value = '';
    document.getElementById('imagen-preview').classList.add('hidden');
    document.getElementById('imagen-placeholder').classList.remove('hidden');
    document.getElementById('btn-quitar-imagen').classList.add('hidden');
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
        let plato;
        if (editingPlatoId) {
            plato = await api.patch(`/platos/${editingPlatoId}`, data);
        } else {
            plato = await api.post('/platos', data);
        }

        if (archivoImagenPendiente) {
            const formData = new FormData();
            formData.append('archivo', archivoImagenPendiente, 'foto.jpg');
            await api.postFile(`/platos/${plato.id}/imagen`, formData);
        }

        showToast(editingPlatoId ? 'Plato actualizado' : 'Plato creado', 'success');
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
