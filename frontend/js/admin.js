/**
 * CU-01 y CU-04: Panel de Administración
 * - CU-01: Gestión de la Carta (crear/editar/desactivar platos)
 * - CU-04: Control de Compras y Caja Chica
 */

let editingPlatoId = null;
let editingCompraId = null;
let adminCompras = [];
let adminCategorias = [];
let archivoImagenPendiente = null; // Blob ya comprimido, listo para subir tras guardar
let platoImagenActualUrl = null;   // imagen_url ya guardada en el server (si se está editando)

const ICON_EDIT = '<svg viewBox="0 0 24 24"><path d="M12 20h9"/><path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z"/></svg>';
const ICON_CANCEL = '<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg>';
const ICON_RESTORE = '<svg viewBox="0 0 24 24"><polyline points="1 4 1 10 7 10"/><path d="M3.51 15a9 9 0 1 0 2.13-9.36L1 10"/></svg>';
const ICON_DELETE = '<svg viewBox="0 0 24 24"><polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/><path d="M10 11v6"/><path d="M14 11v6"/><path d="M9 6V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2"/></svg>';
const ICON_PHOTO_PLACEHOLDER = '<div class="item-thumb-placeholder"><svg viewBox="0 0 24 24"><rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="8.5" cy="8.5" r="1.5"/><path d="M21 15l-5-5L5 21"/></svg></div>';

function _thumbHtml(imagenUrl) {
    if (imagenUrl) {
        return `<img class="item-thumb" src="${escapeHtml(imagenUrl)}" alt="">`;
    }
    return ICON_PHOTO_PLACEHOLDER;
}

function initAdmin() {
    document.getElementById('compra-fecha').value = formatDateInput(new Date());
    _setupIconoPicker();
    refreshAdmin();
}

async function refreshAdmin() {
    try {
        // Sin incluir_inactivos: un plato "eliminado" (aunque internamente se
        // haya archivado por tener historial de ventas) debe desaparecer de
        // la carta que ve el admin, igual que si de verdad se hubiera borrado.
        const [platos, compras, categorias] = await Promise.all([
            api.get('/platos'),
            api.get('/compras'),
            api.get('/categorias'),
        ]);
        estado.platos = platos;
        adminCompras = compras;
        adminCategorias = categorias;
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
        <div class="admin-item">
            <div class="admin-item-main">
                ${_thumbHtml(plato.imagen_url)}
                <div class="admin-item-info">
                    <h3>${escapeHtml(plato.nombre)}</h3>
                    <p>${escapeHtml(plato.categoria)} · ${formatCurrency(plato.precio_venta)}</p>
                </div>
            </div>
            <div class="admin-item-actions">
                <button class="icon-btn" title="Editar" onclick="editarPlato(${plato.id})">${ICON_EDIT}</button>
                <button class="icon-btn danger" title="Eliminar" onclick="eliminarPlato(${plato.id})">${ICON_DELETE}</button>
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

/**
 * La categoría es un select alimentado por /api/categorias, no texto libre:
 * evita que "Cebiches", "cebiches" y "Cebiche" convivan como categorías
 * distintas en la carta. Si el plato tiene una categoría que ya no existe
 * en el catálogo (se borró después de asignarla), se agrega igual como
 * opción para no perder el dato ni bloquear el guardado.
 */
function _poblarSelectCategorias(seleccionActual) {
    const select = document.getElementById('plato-categoria');
    const opciones = adminCategorias.map(c => ({ nombre: c.nombre, icono: c.icono }));
    if (seleccionActual && !opciones.some(o => o.nombre === seleccionActual)) {
        opciones.push({ nombre: seleccionActual, icono: '🍽️' });
    }

    if (opciones.length === 0) {
        select.innerHTML = '<option value="" disabled selected>Crea una categoría primero</option>';
        return;
    }

    select.innerHTML = opciones.map(o =>
        `<option value="${escapeHtml(o.nombre)}">${o.icono} ${escapeHtml(o.nombre)}</option>`
    ).join('');
    if (seleccionActual) select.value = seleccionActual;
}

function abrirModalNuevoPlato() {
    editingPlatoId = null;
    document.getElementById('modal-plato-title').textContent = 'Nuevo Plato';
    document.getElementById('form-plato').reset();
    _poblarSelectCategorias(null);
    resetFormImagen();
    abrirModal('modal-plato');
}

function editarPlato(platoId) {
    const plato = estado.platos.find(p => p.id === platoId);
    if (!plato) return;

    editingPlatoId = platoId;
    document.getElementById('modal-plato-title').textContent = 'Editar Plato';
    document.getElementById('plato-nombre').value = plato.nombre;
    _poblarSelectCategorias(plato.categoria);
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

async function eliminarPlato(platoId) {
    const plato = estado.platos.find(p => p.id === platoId);
    if (plato && !confirm(`¿Eliminar "${plato.nombre}" de la carta?`)) return;

    try {
        // Si el plato ya tiene ventas registradas, el backend no lo borra de
        // verdad (perdería historial del dashboard): lo archiva y avisa con
        // el mismo 'detail' que igual desaparece de la carta para el admin.
        const resultado = await api.delete(`/platos/${platoId}`);
        await refreshAdmin();
        await refreshCatalogo();
        if (typeof refreshMozo === 'function') refreshMozo();
        showToast(resultado.detail || 'Plato eliminado', 'success');
    } catch (err) {
        showToast(err.message || 'Error al eliminar el plato', 'error');
    }
}

// ============ CATEGORÍAS DE LA CARTA ============

function abrirModalCategorias() {
    renderGestionCategorias();
    resetIconoPicker();
    document.getElementById('form-categoria').reset();
    abrirModal('modal-categorias');
}

function cerrarModalCategorias() {
    document.getElementById('modal-categorias').classList.add('hidden');
}

// Icono = un emoji elegido de una paleta fija, no una foto: no hay que
// subir ni comprimir nada, cero costo de red o almacenamiento.
function resetIconoPicker() {
    const picker = document.getElementById('categoria-icono-picker');
    picker.querySelectorAll('.icono-opcion').forEach(btn => btn.classList.remove('selected'));
    picker.querySelector('.icono-opcion').classList.add('selected');
    document.getElementById('categoria-icono').value = picker.querySelector('.icono-opcion').dataset.icono;
}

function _setupIconoPicker() {
    const picker = document.getElementById('categoria-icono-picker');
    picker.querySelectorAll('.icono-opcion').forEach(btn => {
        btn.addEventListener('click', () => {
            picker.querySelectorAll('.icono-opcion').forEach(b => b.classList.remove('selected'));
            btn.classList.add('selected');
            document.getElementById('categoria-icono').value = btn.dataset.icono;
        });
    });
}

function renderGestionCategorias() {
    const container = document.getElementById('gestion-categorias-list');

    if (adminCategorias.length === 0) {
        container.innerHTML = '<p class="empty-hint">Aún no creas categorías. Agrega la primera arriba.</p>';
        return;
    }

    container.innerHTML = adminCategorias.map(cat => `
        <div class="admin-item">
            <div class="admin-item-info"><h4><span class="categoria-icono-chip">${cat.icono}</span>${escapeHtml(cat.nombre)}</h4></div>
            <div class="admin-item-actions">
                <button class="icon-btn danger" title="Eliminar" onclick="eliminarCategoria(${cat.id})">${ICON_DELETE}</button>
            </div>
        </div>
    `).join('');
}

async function guardarCategoria(event) {
    event.preventDefault();
    const nombre = document.getElementById('categoria-nombre').value.trim();
    const icono = document.getElementById('categoria-icono').value;

    try {
        await api.post('/categorias', { nombre, icono });
        document.getElementById('form-categoria').reset();
        resetIconoPicker();
        await refreshAdmin();
        renderGestionCategorias();
        showToast('Categoría creada', 'success');
    } catch (err) {
        showToast(err.message || 'Error al crear la categoría', 'error');
    }
}

async function eliminarCategoria(categoriaId) {
    try {
        await api.delete(`/categorias/${categoriaId}`);
        await refreshAdmin();
        renderGestionCategorias();
        showToast('Categoría eliminada', 'success');
    } catch (err) {
        showToast(err.message || 'No se pudo eliminar la categoría', 'error');
    }
}

// ============ CU-04: COMPRAS ============

function renderCompras() {
    const container = document.getElementById('admin-compras-list');

    if (adminCompras.length === 0) {
        container.innerHTML = '<p class="empty-hint">Aún no registras gastos.</p>';
        return;
    }

    const hoy = formatDateInput(new Date());
    const porFecha = {};
    adminCompras.forEach(compra => {
        (porFecha[compra.fecha] = porFecha[compra.fecha] || []).push(compra);
    });

    const fechas = Object.keys(porFecha).sort().reverse();

    container.innerHTML = fechas.map(fecha => {
        const compras = porFecha[fecha];
        const totalDia = compras.reduce((sum, c) => sum + (c.estado === 'registrado' ? c.monto : 0), 0);
        // Editar/eliminar solo aplica al día de hoy (igual que valida el backend);
        // un gasto de un día anterior solo se puede cancelar, para no borrar
        // historial financiero por accidente.
        const esHoy = fecha === hoy;

        const itemsHtml = compras.map(compra => `
            <div class="admin-item ${compra.estado === 'cancelado' ? 'inactivo' : ''}">
                <div class="admin-item-info">
                    <h4>${escapeHtml(compra.descripcion)}</h4>
                    <p>${escapeHtml(compra.categoria || 'Sin categoría')} · ${formatCurrency(compra.monto)}</p>
                </div>
                <div class="admin-item-actions">
                    ${esHoy && compra.estado === 'registrado' ? `
                        <button class="icon-btn" title="Editar" onclick="editarCompra(${compra.id})">${ICON_EDIT}</button>
                        <button class="icon-btn danger" title="Eliminar" onclick="eliminarCompra(${compra.id})">${ICON_DELETE}</button>
                    ` : ''}
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
    editingCompraId = null;
    document.getElementById('modal-compra-title').textContent = 'Registrar Gasto';
    document.getElementById('form-compra').reset();
    document.getElementById('compra-fecha').value = formatDateInput(new Date());
    abrirModal('modal-compra');
}

function editarCompra(compraId) {
    const compra = adminCompras.find(c => c.id === compraId);
    if (!compra) return;

    editingCompraId = compraId;
    document.getElementById('modal-compra-title').textContent = 'Editar Gasto';
    document.getElementById('compra-descripcion').value = compra.descripcion;
    document.getElementById('compra-categoria').value = compra.categoria || '';
    document.getElementById('compra-monto').value = compra.monto;
    document.getElementById('compra-fecha').value = compra.fecha;
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
        if (editingCompraId) {
            await api.patch(`/compras/${editingCompraId}`, data);
            showToast('Gasto actualizado', 'success');
        } else {
            await api.post('/compras', data);
            showToast('Gasto registrado', 'success');
        }
        cerrarModalCompra();
        await refreshAdmin();
        if (typeof refreshDashboard === 'function') refreshDashboard();
    } catch (err) {
        showToast(err.message || 'Error al guardar el gasto', 'error');
    }
}

async function eliminarCompra(compraId) {
    try {
        await api.delete(`/compras/${compraId}`);
        await refreshAdmin();
        if (typeof refreshDashboard === 'function') refreshDashboard();
        showToast('Gasto eliminado', 'success');
    } catch (err) {
        showToast(err.message || 'No se pudo eliminar el gasto', 'error');
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
