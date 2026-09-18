/**
 * CU-01 y CU-04: Panel de Administración
 * - CU-01: Gestión de la Carta (crear/editar/desactivar platos)
 * - CU-04: Control de Compras y Caja Chica
 */

let editingPlatoId = null;
let editingCompraId = null;
let editingUsuarioId = null;
let editingInsumoId = null;
let usuarioEnResetPassword = null;
let adminCompras = [];
let adminCategorias = [];
let adminPersonal = [];
let adminInsumos = [];
let adminFiltroCategoria = null; // null = "Todas"; si no, nombre exacto de la categoría
let archivoImagenPendiente = null; // Blob ya comprimido, listo para subir tras guardar
let platoImagenActualUrl = null;   // imagen_url ya guardada en el server (si se está editando)

const ICON_EDIT = '<svg viewBox="0 0 24 24"><path d="M12 20h9"/><path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z"/></svg>';
const ICON_CANCEL = '<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg>';
const ICON_RESTORE = '<svg viewBox="0 0 24 24"><polyline points="1 4 1 10 7 10"/><path d="M3.51 15a9 9 0 1 0 2.13-9.36L1 10"/></svg>';
const ICON_DELETE = '<svg viewBox="0 0 24 24"><polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/><path d="M10 11v6"/><path d="M14 11v6"/><path d="M9 6V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2"/></svg>';
const ICON_PHOTO_PLACEHOLDER = '<div class="item-thumb-placeholder"><svg viewBox="0 0 24 24"><rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="8.5" cy="8.5" r="1.5"/><path d="M21 15l-5-5L5 21"/></svg></div>';
const ICON_ENTRADA = '<svg viewBox="0 0 24 24"><line x1="12" y1="19" x2="12" y2="5"/><polyline points="5 12 12 5 19 12"/></svg>';
const ICON_SALIDA = '<svg viewBox="0 0 24 24"><line x1="12" y1="5" x2="12" y2="19"/><polyline points="19 12 12 19 5 12"/></svg>';
const ICON_HISTORIAL = '<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="9"/><polyline points="12 7 12 12 15 14"/></svg>';
const ICON_UNDO = '<svg viewBox="0 0 24 24"><polyline points="9 14 4 9 9 4"/><path d="M20 20v-7a4 4 0 0 0-4-4H4"/></svg>';

// Se muestran en el historial, no los valores crudos que guarda la BD.
const MOVIMIENTO_RAZON_LABEL = {
    compra: 'Llegó mercadería',
    uso: 'Se usó en cocina',
    merma: 'Se echó a perder',
    ajuste: 'Ajuste por conteo',
    reversion: 'Deshecho',
    otro: 'Otro',
};

function _thumbHtml(imagenUrl) {
    if (imagenUrl) {
        return `<img class="item-thumb" src="${escapeHtml(imagenUrl)}" alt="">`;
    }
    return ICON_PHOTO_PLACEHOLDER;
}

function initAdmin() {
    document.getElementById('compra-fecha').value = formatDateInput(new Date());
    _setupIconoPicker();
    _initSwitchNotificacionesAdmin();
    _initSwitchesDeRol();
    refreshAdmin();
}

// Los switches de rol viven en el HTML estático, así que se enganchan una
// sola vez al arrancar — no en cada apertura del modal, que dejaría un
// listener nuevo pegado por cada vez que se abre.
function _initSwitchesDeRol() {
    ROLES_STAFF_UI.forEach(r => {
        document.getElementById(`rol-check-${r}`)
            ?.addEventListener('change', aplicarExclusividadRoles);
    });
}

/**
 * Switch del aviso de comanda nueva, en ESTE dispositivo.
 *
 * ANTES PROMETIA ALGO QUE LA APP NO PODIA HACER. Encendía notificaciones
 * push de Firebase, que necesitan un proyecto creado a mano y un
 * google-services.json que el APK no tiene. Resultado: el switch fallaba
 * SIEMPRE, con un "revisá el permiso de notificaciones del navegador" que
 * mandaba a buscar el problema al lugar equivocado — el permiso estaba bien,
 * lo que faltaba era Firebase.
 *
 * Ahora controla el aviso que sí existe y sí funciona: el sonido y la
 * vibración cuando entra un pedido (ver cocina.js). Es por dispositivo y no
 * por cuenta, porque es una decisión sobre el parlante que uno tiene al lado.
 *
 * Cuando algún día haya proyecto Firebase, el push se suma acá — pero recién
 * cuando de verdad pueda llegar.
 */
function _initSwitchNotificacionesAdmin() {
    const input = document.getElementById('switch-notif-admin');
    if (!input || typeof avisoCocinaActivo !== 'function') return;
    input.checked = avisoCocinaActivo();
}

function onToggleNotificacionesAdmin(event) {
    const activar = event.target.checked;
    setAvisoCocinaActivo(activar);

    if (activar) {
        // Suena una vez al encenderlo. Es la única forma de saber que el
        // dispositivo no está en silencio, que es la causa más común de
        // "activé el aviso y no me llega nada".
        if (typeof sonarAvisoCocina === 'function') sonarAvisoCocina();
        showToast('Aviso activado en este dispositivo', 'success');
    } else {
        showToast('Aviso apagado en este dispositivo', 'success');
    }
}

async function refreshAdmin() {
    try {
        // Sin incluir_inactivos: un plato "eliminado" (aunque internamente se
        // haya archivado por tener historial de ventas) debe desaparecer de
        // la carta que ve el admin, igual que si de verdad se hubiera borrado.
        const [platos, compras, categorias, personal, insumos] = await Promise.all([
            api.get('/platos'),
            api.get('/compras'),
            api.get('/categorias'),
            api.get('/usuarios'),
            api.get('/insumos'),
        ]);
        estado.platos = platos;
        adminCompras = compras;
        adminCategorias = categorias;
        adminPersonal = personal;
        adminInsumos = insumos;
    } catch (err) {
        console.error('Error cargando datos de administración:', err);
    }
    renderPlatosAdmin();
    renderCompras();
    renderPersonal();
    renderInventario();
}

// ============ CU-01: PLATOS ============

/**
 * Chips de categoría para filtrar la carta del admin — mismo patrón que ya
 * usa el mozo (frontend/js/mozo.js) para elegir platos. Sin esto, un
 * restaurante con muchas categorías (Cebiches, Bebidas, Postres, Piqueos...)
 * y muchos platos obliga a scrollear una lista plana entera para encontrar
 * uno solo. "Todas" siempre va primero para no perder la vista general.
 */
function renderFiltroCategoriasAdmin() {
    const contenedor = document.getElementById('admin-categorias-filtro');
    contenedor.innerHTML = '';

    // Categorías con al menos un plato, no solo las del catálogo de
    // /api/categorias — así un plato con una categoría ya borrada del
    // catálogo sigue teniendo un chip para encontrarlo.
    const nombresConPlatos = [...new Set(estado.platos.map(p => p.categoria))];
    if (nombresConPlatos.length <= 1) {
        // Con 0 o 1 categoría en uso, filtrar no ayuda a ubicar nada.
        return;
    }

    if (adminFiltroCategoria && !nombresConPlatos.includes(adminFiltroCategoria)) {
        adminFiltroCategoria = null;
    }

    const iconoDe = (nombre) => adminCategorias.find(c => c.nombre === nombre)?.icono || '🍽️';

    // Elementos creados con la API del DOM (no innerHTML con el nombre
    // interpolado) para que un nombre de categoría con comillas no rompa
    // el atributo onclick que se generaría al armarlo como string.
    const chips = [{ nombre: null, etiqueta: 'Todas', icono: '' }, ...nombresConPlatos.map(nombre => ({
        nombre, etiqueta: nombre, icono: iconoDe(nombre) + ' ',
    }))];

    chips.forEach(chip => {
        const btn = document.createElement('button');
        btn.type = 'button';
        btn.className = `categoria-btn ${adminFiltroCategoria === chip.nombre ? 'active' : ''}`;
        btn.textContent = `${chip.icono}${chip.etiqueta}`;
        btn.onclick = () => filtrarPlatosPorCategoria(chip.nombre);
        contenedor.appendChild(btn);
    });
}

function filtrarPlatosPorCategoria(nombreCategoria) {
    adminFiltroCategoria = nombreCategoria;
    renderPlatosAdmin();
}

function renderPlatosAdmin() {
    renderFiltroCategoriasAdmin();

    const container = document.getElementById('admin-platos-list');

    if (estado.platos.length === 0) {
        container.innerHTML = '<p class="empty-hint">Aún no registras platos en tu carta.</p>';
        return;
    }

    const platosFiltrados = adminFiltroCategoria
        ? estado.platos.filter(p => p.categoria === adminFiltroCategoria)
        : estado.platos;

    if (platosFiltrados.length === 0) {
        container.innerHTML = '<p class="empty-hint">No hay platos en esta categoría.</p>';
        return;
    }

    container.innerHTML = platosFiltrados.map(plato => `
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
    document.getElementById('compra-monto').disabled = false;
    document.getElementById('compra-monto-hint').classList.add('hidden');
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
    document.getElementById('compra-monto').disabled = true;
    document.getElementById('compra-monto-hint').classList.remove('hidden');
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

// ============ INVENTARIO (stock de almacén) ============

/**
 * Vive dentro de Gastos, no en una pestaña propia: el admin ya entra ahí
 * cuando llega mercadería, así que el stock queda a mano sin sumar una
 * función más al menú. Arranca colapsado para no empujar la lista de
 * gastos fuera de la pantalla en un celular.
 */

const INSUMO_ESTADO_LABEL = { ok: 'OK', bajo: 'Bajo', critico: 'Crítico' };

function toggleInventario() {
    const panel = document.getElementById('insumo-panel');
    const toggle = document.getElementById('insumo-toggle');
    const abierto = panel.classList.toggle('hidden') === false;
    toggle.classList.toggle('abierto', abierto);
    toggle.setAttribute('aria-expanded', String(abierto));
}

function renderInventario() {
    renderResumenInsumos();
    renderAlertasInsumos();
    renderListaInsumos();
}

// Contador en la cabecera: es lo único visible con el panel colapsado, así
// que tiene que alcanzar para decidir si vale la pena abrirlo.
function renderResumenInsumos() {
    const resumen = document.getElementById('insumo-resumen');
    const criticos = adminInsumos.filter(i => i.estado === 'critico').length;
    const bajos = adminInsumos.filter(i => i.estado === 'bajo').length;

    if (criticos > 0) {
        resumen.textContent = `${criticos} crítico${criticos === 1 ? '' : 's'}`;
        resumen.className = 'insumo-resumen critico';
    } else if (bajos > 0) {
        resumen.textContent = `${bajos} bajo${bajos === 1 ? '' : 's'}`;
        resumen.className = 'insumo-resumen bajo';
    } else if (adminInsumos.length > 0) {
        resumen.textContent = 'Todo OK';
        resumen.className = 'insumo-resumen ok';
    } else {
        resumen.textContent = '';
        resumen.className = 'insumo-resumen';
    }
}

function renderAlertasInsumos() {
    const container = document.getElementById('insumo-alertas');
    const enAlerta = adminInsumos.filter(i => i.estado !== 'ok');

    if (enAlerta.length === 0) {
        container.innerHTML = '';
        return;
    }

    // Críticos primero: es el que puede faltar hoy mismo.
    const orden = { critico: 0, bajo: 1 };
    enAlerta.sort((a, b) => orden[a.estado] - orden[b.estado]);

    container.innerHTML = `
        <div class="insumo-alertas">
            ${enAlerta.map(i => `
                <div class="insumo-alerta-fila">
                    <span class="insumo-punto ${i.estado}"></span>
                    <strong>${escapeHtml(i.nombre)}</strong>
                    <span>${formatCantidad(i.cantidad_actual)} ${escapeHtml(i.unidad)} · mín ${formatCantidad(i.cantidad_minima)}</span>
                </div>
            `).join('')}
        </div>
    `;
}

function renderListaInsumos() {
    const container = document.getElementById('insumo-lista');

    if (adminInsumos.length === 0) {
        container.innerHTML = '<p class="empty-hint">Aún no registras insumos. Agrega los que más te importan (pescado, limón, ají...).</p>';
        return;
    }

    container.innerHTML = `
        <div class="insumo-tabla-wrap">
            <table class="insumo-tabla">
                <thead>
                    <tr>
                        <th>Insumo</th>
                        <th class="num">Stock</th>
                        <th class="num">Mín</th>
                        <th></th>
                    </tr>
                </thead>
                <tbody>
                    ${adminInsumos.map(i => `
                        <tr class="insumo-fila ${i.estado}">
                            <td>
                                <span class="insumo-punto ${i.estado}" title="${INSUMO_ESTADO_LABEL[i.estado]}"></span>
                                ${escapeHtml(i.nombre)}
                            </td>
                            <td class="num"><strong>${formatCantidad(i.cantidad_actual)}</strong> ${escapeHtml(i.unidad)}</td>
                            <td class="num">${formatCantidad(i.cantidad_minima)}</td>
                            <td class="insumo-acciones">
                                <button class="icon-btn entrada" title="Registrar entrada" onclick="abrirModalMovimiento(${i.id}, 'entrada')">${ICON_ENTRADA}</button>
                                <button class="icon-btn salida" title="Registrar salida" onclick="abrirModalMovimiento(${i.id}, 'salida')">${ICON_SALIDA}</button>
                                <button class="icon-btn" title="Ver movimientos" onclick="abrirHistorial(${i.id})">${ICON_HISTORIAL}</button>
                                <button class="icon-btn" title="Editar" onclick="abrirModalInsumo(${i.id})">${ICON_EDIT}</button>
                            </td>
                        </tr>
                    `).join('')}
                </tbody>
            </table>
        </div>
    `;
}

// Un stock rara vez es decimal exacto: 20 se muestra "20", no "20.00", pero
// 0.5 kg de ají sigue viéndose "0.5".
function formatCantidad(n) {
    const num = parseFloat(n || 0);
    return Number.isInteger(num) ? String(num) : String(parseFloat(num.toFixed(2)));
}

function abrirModalInsumo(insumoId = null) {
    editingInsumoId = insumoId;
    const form = document.getElementById('form-insumo');
    form.reset();

    const btnEliminar = document.getElementById('insumo-eliminar');

    if (insumoId) {
        const insumo = adminInsumos.find(i => i.id === insumoId);
        if (!insumo) return;
        document.getElementById('modal-insumo-title').textContent = 'Editar insumo';
        document.getElementById('insumo-nombre').value = insumo.nombre;
        document.getElementById('insumo-unidad').value = insumo.unidad;
        document.getElementById('insumo-cantidad').value = insumo.cantidad_actual;
        document.getElementById('insumo-minima').value = insumo.cantidad_minima;
        btnEliminar.classList.remove('hidden');
    } else {
        document.getElementById('modal-insumo-title').textContent = 'Nuevo insumo';
        btnEliminar.classList.add('hidden');
    }

    abrirModal('modal-insumo');
}

function cerrarModalInsumo() {
    document.getElementById('modal-insumo').classList.add('hidden');
    document.getElementById('form-insumo').reset();
    editingInsumoId = null;
}

async function guardarInsumo(event) {
    event.preventDefault();

    const data = {
        nombre: document.getElementById('insumo-nombre').value.trim(),
        unidad: document.getElementById('insumo-unidad').value,
        cantidad_actual: parseFloat(document.getElementById('insumo-cantidad').value),
        cantidad_minima: parseFloat(document.getElementById('insumo-minima').value),
    };

    try {
        if (editingInsumoId) {
            await api.patch(`/insumos/${editingInsumoId}`, data);
            showToast('Insumo actualizado', 'success');
        } else {
            await api.post('/insumos', data);
            showToast('Insumo agregado', 'success');
        }
        cerrarModalInsumo();
        await refreshAdmin();
    } catch (err) {
        showToast(err.message || 'Error al guardar el insumo', 'error');
    }
}

async function eliminarInsumo(insumoId) {
    const insumo = adminInsumos.find(i => i.id === insumoId);
    const nombre = insumo ? insumo.nombre : 'este insumo';
    // Avisa que se lleva el historial: es lo que el admin no espera, y sin
    // ese aviso descubre la pérdida cuando ya no puede recuperarla.
    if (!confirm(`¿Eliminar "${nombre}" del inventario?\n\nSe borran también todos sus movimientos registrados.`)) return;

    try {
        await api.delete(`/insumos/${insumoId}`);
        showToast('Insumo eliminado', 'success');
        cerrarModalInsumo();
        await refreshAdmin();
    } catch (err) {
        showToast(err.message || 'No se pudo eliminar el insumo', 'error');
    }
}

// ============ MOVIMIENTOS DE STOCK (entradas / salidas) ============

let movimientoInsumoId = null;
let movimientoTipo = null;
let historialInsumoId = null;

function abrirModalMovimiento(insumoId, tipo) {
    const insumo = adminInsumos.find(i => i.id === insumoId);
    if (!insumo) return;

    movimientoInsumoId = insumoId;
    movimientoTipo = tipo;

    const esEntrada = tipo === 'entrada';
    document.getElementById('modal-movimiento-title').textContent =
        esEntrada ? 'Registrar entrada' : 'Registrar salida';
    document.getElementById('movimiento-contexto').innerHTML =
        `<strong>${escapeHtml(insumo.nombre)}</strong> · quedan ${formatCantidad(insumo.cantidad_actual)} ${escapeHtml(insumo.unidad)}`;
    document.getElementById('movimiento-unidad').textContent = insumo.unidad;

    const form = document.getElementById('form-movimiento');
    form.reset();
    // El motivo más probable según el tipo: quien registra una entrada casi
    // siempre está anotando mercadería que acaba de llegar.
    document.getElementById('movimiento-razon').value = esEntrada ? 'compra' : 'uso';
    document.getElementById('movimiento-fecha').value = hoyLocalISO();

    const submit = document.getElementById('movimiento-submit');
    submit.textContent = esEntrada ? 'Registrar entrada' : 'Registrar salida';
    submit.classList.toggle('btn-salida', !esEntrada);

    abrirModal('modal-movimiento');
    document.getElementById('movimiento-cantidad').focus();
}

function cerrarModalMovimiento() {
    document.getElementById('modal-movimiento').classList.add('hidden');
    document.getElementById('form-movimiento').reset();
    movimientoInsumoId = null;
    movimientoTipo = null;
}

// El <input type="date"> espera fecha LOCAL. toISOString() devuelve UTC, que
// en Perú (UTC-5) da el día anterior en cualquier movimiento antes de las 7pm.
function hoyLocalISO() {
    const d = new Date();
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}

async function guardarMovimiento(event) {
    event.preventDefault();

    const insumoId = movimientoInsumoId;
    const insumo = adminInsumos.find(i => i.id === insumoId);
    const data = {
        tipo: movimientoTipo,
        cantidad: parseFloat(document.getElementById('movimiento-cantidad').value),
        razon: document.getElementById('movimiento-razon').value,
        fecha: document.getElementById('movimiento-fecha').value,
    };

    try {
        const mov = await api.post(`/insumos/${insumoId}/movimientos`, data);
        const signo = mov.tipo === 'entrada' ? '+' : '−';
        const unidad = insumo ? insumo.unidad : '';
        showToast(
            `${signo}${formatCantidad(mov.cantidad)} ${unidad} · quedan ${formatCantidad(mov.saldo_despues)} ${unidad}`,
            'success'
        );
        cerrarModalMovimiento();
        await refreshAdmin();
    } catch (err) {
        showToast(err.message || 'No se pudo registrar el movimiento', 'error');
    }
}

async function abrirHistorial(insumoId) {
    const insumo = adminInsumos.find(i => i.id === insumoId);
    if (!insumo) return;

    historialInsumoId = insumoId;
    document.getElementById('historial-titulo').textContent = insumo.nombre;
    document.getElementById('historial-subtitulo').textContent =
        `${formatCantidad(insumo.cantidad_actual)} ${insumo.unidad} en stock`;
    document.getElementById('historial-lista').innerHTML = '<p class="empty-hint">Cargando...</p>';

    document.getElementById('historial-overlay').classList.remove('hidden');
    const panel = document.getElementById('historial-panel');
    panel.classList.add('abierto');
    panel.setAttribute('aria-hidden', 'false');

    await cargarHistorial();
}

async function cargarHistorial() {
    const container = document.getElementById('historial-lista');
    try {
        const movimientos = await api.get(`/insumos/${historialInsumoId}/movimientos?limite=50`);
        renderHistorial(movimientos);
    } catch (err) {
        container.innerHTML = `<p class="empty-hint">${escapeHtml(err.message || 'No se pudo cargar el historial')}</p>`;
    }
}

function renderHistorial(movimientos) {
    const container = document.getElementById('historial-lista');

    if (movimientos.length === 0) {
        container.innerHTML = '<p class="empty-hint">Sin movimientos todavía. Las entradas y salidas que registres aparecen acá.</p>';
        return;
    }

    const insumo = adminInsumos.find(i => i.id === historialInsumoId);
    const unidad = insumo ? escapeHtml(insumo.unidad) : '';

    container.innerHTML = movimientos.map(m => {
        const esEntrada = m.tipo === 'entrada';
        const signo = esEntrada ? '+' : '−';
        // Una reversión ya no se puede deshacer, y un movimiento revertido
        // tampoco: ofrecer el botón sería prometer algo que da 400.
        const puedeDeshacer = !m.revertido && m.razon !== 'reversion';
        return `
            <div class="mov-fila ${m.revertido ? 'revertido' : ''}">
                <span class="mov-badge ${m.tipo}">${esEntrada ? ICON_ENTRADA : ICON_SALIDA}</span>
                <div class="mov-cuerpo">
                    <div class="mov-linea">
                        <strong class="mov-monto">${signo}${formatCantidad(m.cantidad)} ${unidad}</strong>
                        <span class="mov-saldo">→ ${formatCantidad(m.saldo_despues)} ${unidad}</span>
                    </div>
                    <div class="mov-meta">
                        ${escapeHtml(MOVIMIENTO_RAZON_LABEL[m.razon] || m.razon)}
                        · ${formatFechaCorta(m.fecha)}
                        ${m.usuario_nombre ? '· ' + escapeHtml(m.usuario_nombre) : ''}
                    </div>
                </div>
                ${puedeDeshacer
                    ? `<button class="icon-btn" title="Deshacer este movimiento" onclick="revertirMovimiento(${m.id})">${ICON_UNDO}</button>`
                    : ''}
            </div>
        `;
    }).join('');
}

function formatFechaCorta(iso) {
    const d = new Date(iso);
    if (isNaN(d)) return '';
    return d.toLocaleDateString('es-PE', { day: '2-digit', month: 'short' });
}

async function revertirMovimiento(movimientoId) {
    if (!confirm('¿Deshacer este movimiento?\n\nEl original queda registrado y se agrega uno que lo corrige.')) return;

    try {
        await api.delete(`/insumos/${historialInsumoId}/movimientos/${movimientoId}`);
        showToast('Movimiento deshecho', 'success');
        await refreshAdmin();
        // Después de refreshAdmin para que el encabezado del panel muestre
        // el stock ya corregido, no el de antes de deshacer.
        const insumo = adminInsumos.find(i => i.id === historialInsumoId);
        if (insumo) {
            document.getElementById('historial-subtitulo').textContent =
                `${formatCantidad(insumo.cantidad_actual)} ${insumo.unidad} en stock`;
        }
        await cargarHistorial();
    } catch (err) {
        showToast(err.message || 'No se pudo deshacer el movimiento', 'error');
    }
}

function cerrarHistorial() {
    document.getElementById('historial-overlay').classList.add('hidden');
    const panel = document.getElementById('historial-panel');
    panel.classList.remove('abierto');
    panel.setAttribute('aria-hidden', 'true');
    historialInsumoId = null;
}

// ============ PERSONAL (mozos, cajeros, cocina) ============

function renderPersonal() {
    const container = document.getElementById('admin-personal-list');

    if (adminPersonal.length === 0) {
        container.innerHTML = '<p class="empty-hint">Aún no registras personal.</p>';
        return;
    }

    const miEmail = estado.usuario ? estado.usuario.email : null;

    container.innerHTML = adminPersonal.map(u => {
        const esUnoMismo = u.email === miEmail;
        return `
        <div class="admin-item ${u.estado === 'inactivo' ? 'inactivo' : ''}">
            <div class="admin-item-info">
                <h4>${escapeHtml(u.nombre)} ${esUnoMismo ? '<span class="cantidad-badge">Tú</span>' : ''}</h4>
                <p>${escapeHtml(u.email || u.celular || '')} · ${(u.roles || [u.rol]).map(r => ROL_LABELS[r] || r).join(' + ')}</p>
            </div>
            <div class="admin-item-actions">
                <button class="icon-btn" title="Editar" onclick="abrirModalEditarUsuario('${u.id}')">${ICON_EDIT}</button>
                <button class="icon-btn" title="Resetear contraseña" onclick="abrirModalResetPasswordUsuario('${u.id}')">🔑</button>
                ${esUnoMismo ? '' : `<button class="icon-btn danger" title="Eliminar" onclick="eliminarUsuario('${u.id}')">${ICON_DELETE}</button>`}
            </div>
        </div>
    `;
    }).join('');
}

function abrirModalNuevoUsuario() {
    // Solo se crea personal (mozo/cajero/cocina) desde acá — con un código
    // de acceso que genera el backend, no un celular real. Un admin no
    // puede crear otro admin: ese lo da de alta el superadmin al registrar
    // el restaurante.
    editingUsuarioId = null;
    document.getElementById('modal-usuario-title').textContent = 'Nueva Cuenta';
    document.getElementById('form-usuario').reset();

    document.getElementById('usuario-codigo-nuevo-hint').classList.remove('hidden');
    document.getElementById('usuario-celular-group').classList.add('hidden');
    document.getElementById('usuario-email-fijo-group').classList.add('hidden');

    document.getElementById('usuario-password-group').classList.remove('hidden');
    document.getElementById('usuario-password').required = true;

    document.getElementById('usuario-rol-group').classList.remove('hidden');
    document.getElementById('usuario-rol-fijo-group').classList.add('hidden');
    // form.reset() desmarca los switches pero NO limpia el `disabled` que
    // pudo dejar una edición anterior de un asistente: sin esto, la
    // siguiente cuenta nueva abriría con roles bloqueados sin motivo.
    aplicarExclusividadRoles();

    abrirModal('modal-usuario');
}

function abrirModalEditarUsuario(usuarioId) {
    const usuario = adminPersonal.find(u => u.id === usuarioId);
    if (!usuario) return;

    editingUsuarioId = usuarioId;
    document.getElementById('modal-usuario-title').textContent = 'Editar Cuenta';
    document.getElementById('usuario-nombre').value = usuario.nombre;
    document.getElementById('usuario-codigo-nuevo-hint').classList.add('hidden');

    // La contraseña se cambia solo desde "Resetear contraseña", no mezclado
    // en este formulario (evita que quede en blanco por accidente y alguien
    // piense que la borró).
    document.getElementById('usuario-password-group').classList.add('hidden');
    document.getElementById('usuario-password').required = false;

    if (usuario.rol === 'admin') {
        // El admin (fila "Tú"): ni el email ni el rol se pueden tocar acá.
        document.getElementById('usuario-celular-group').classList.add('hidden');
        document.getElementById('usuario-email-fijo-group').classList.remove('hidden');
        document.getElementById('usuario-email-fijo').textContent = usuario.email;

        document.getElementById('usuario-rol-group').classList.add('hidden');
        document.getElementById('usuario-rol-fijo-group').classList.remove('hidden');
    } else {
        // Personal: el código de acceso es el identificador de login, ya
        // generado y no se puede cambiar (cambiarlo sería re-crear la
        // cuenta), pero los roles sí — puede tener varios a la vez (ej.
        // cocina Y caja, cuando el restaurante tiene poco personal).
        document.getElementById('usuario-celular-group').classList.remove('hidden');
        document.getElementById('usuario-celular').value = usuario.celular;
        document.getElementById('usuario-email-fijo-group').classList.add('hidden');

        document.getElementById('usuario-rol-group').classList.remove('hidden');
        document.getElementById('usuario-rol-fijo-group').classList.add('hidden');
        const rolesActuales = usuario.roles || [usuario.rol];
        ROLES_STAFF_UI.forEach(r => {
            document.getElementById(`rol-check-${r}`).checked = rolesActuales.includes(r);
        });
        aplicarExclusividadRoles();
    }

    abrirModal('modal-usuario');
}

function cerrarModalUsuario() {
    document.getElementById('modal-usuario').classList.add('hidden');
    document.getElementById('form-usuario').reset();
    editingUsuarioId = null;
}

// Los roles de staff que ofrece el modal, en el orden en que se ven. No
// incluye 'admin': ese lo asigna el superadmin al crear el restaurante y
// nunca se ofrece acá (ver abrirModalNuevoUsuario).
const ROLES_STAFF_UI = ['mozo', 'cajero', 'jefe_cocina', 'asistente'];

// 'asistente' ya cubre mesas + cocina + cobro, así que no se combina con
// ningún otro (ROLES_EXCLUSIVOS en backend/utils/roles.py). El backend lo
// rechaza con un 422, pero descubrirlo recién al guardar es una mala forma
// de enterarse: acá los switches incompatibles se apagan y se bloquean en
// el momento, así el estado imposible no llega a existir en pantalla.
const ROLES_EXCLUSIVOS_UI = ['asistente'];

function aplicarExclusividadRoles() {
    const marcados = _rolesMarcados();
    const hayExclusivo = marcados.some(r => ROLES_EXCLUSIVOS_UI.includes(r));
    ROLES_STAFF_UI.forEach(r => {
        const check = document.getElementById(`rol-check-${r}`);
        if (!check) return;
        const esExclusivo = ROLES_EXCLUSIVOS_UI.includes(r);
        // Con un exclusivo marcado se bloquea todo lo demás; con cualquier
        // rol normal marcado se bloquea el exclusivo.
        const bloquear = hayExclusivo ? !esExclusivo : (esExclusivo && marcados.length > 0);
        check.disabled = bloquear;
        if (bloquear) check.checked = false;
        check.closest('.rol-switch-row')?.classList.toggle('rol-switch-bloqueada', bloquear);
    });
}

function _rolesMarcados() {
    return ROLES_STAFF_UI.filter(
        r => document.getElementById(`rol-check-${r}`)?.checked
    );
}

async function guardarUsuario(event) {
    event.preventDefault();

    const nombre = document.getElementById('usuario-nombre').value.trim();

    try {
        if (editingUsuarioId) {
            const usuario = adminPersonal.find(u => u.id === editingUsuarioId);
            const datos = { nombre };
            // Los roles de un admin nunca se mandan: son fijos, y el
            // backend lo rechazaría igual si se intentara cambiar.
            if (usuario && usuario.rol !== 'admin') {
                const roles = _rolesMarcados();
                if (roles.length === 0) {
                    showToast('Marca al menos un rol', 'error');
                    return;
                }
                datos.roles = roles;
            }
            await api.patch(`/usuarios/${editingUsuarioId}`, datos);
            cerrarModalUsuario();
            await refreshAdmin();
            showToast('Cuenta actualizada', 'success');
        } else {
            const password = document.getElementById('usuario-password').value;
            const roles = _rolesMarcados();
            if (roles.length === 0) {
                showToast('Marca al menos un rol', 'error');
                return;
            }
            const creado = await api.post('/usuarios/staff', { nombre, password, roles });
            cerrarModalUsuario();
            await refreshAdmin();
            // El código lo genera el backend — sin esto, el admin no tiene
            // forma de saber qué código darle al empleado recién creado
            // (aunque también queda visible después en la lista de Personal).
            showToast(`Cuenta creada. Código de acceso: ${creado.celular}`, 'success');
        }
    } catch (err) {
        showToast(err.message || 'Error al guardar la cuenta', 'error');
    }
}

async function eliminarUsuario(usuarioId) {
    const usuario = adminPersonal.find(u => u.id === usuarioId);
    if (usuario && !confirm(`¿Eliminar la cuenta de "${usuario.nombre}"?`)) return;

    try {
        await api.delete(`/usuarios/${usuarioId}`);
        await refreshAdmin();
        showToast('Cuenta eliminada', 'success');
    } catch (err) {
        showToast(err.message || 'Error al eliminar la cuenta', 'error');
    }
}

function abrirModalResetPasswordUsuario(usuarioId) {
    const usuario = adminPersonal.find(u => u.id === usuarioId);
    if (!usuario) return;

    usuarioEnResetPassword = usuarioId;
    document.getElementById('form-reset-password-usuario').reset();
    document.getElementById('reset-usuario-nombre').textContent = `Cuenta: ${usuario.nombre} (${usuario.email || usuario.celular})`;
    abrirModal('modal-reset-password-usuario');
}

function cerrarModalResetPasswordUsuario() {
    document.getElementById('modal-reset-password-usuario').classList.add('hidden');
    usuarioEnResetPassword = null;
}

async function confirmarResetPasswordUsuario(event) {
    event.preventDefault();
    const nuevaPassword = document.getElementById('reset-usuario-password').value;

    try {
        await api.patch(`/usuarios/${usuarioEnResetPassword}/password`, { nueva_password: nuevaPassword });
        cerrarModalResetPasswordUsuario();
        showToast('Contraseña actualizada', 'success');
    } catch (err) {
        showToast(err.message || 'Error al resetear la contraseña', 'error');
    }
}

// ============ MI CUENTA (Usuario actual) ============

async function abrirModalMiCuenta() {
    try {
        const resp = await api.get('/usuarios/me');
        document.getElementById('cuenta-email').value = resp.email;
        document.getElementById('cuenta-nombre').textContent = resp.nombre;
        document.getElementById('cuenta-password-actual').value = '';
        document.getElementById('cuenta-password-nueva').value = '';
        abrirModal('modal-mi-cuenta');
    } catch (err) {
        showToast(err.message || 'Error al cargar mi cuenta', 'error');
    }
}

function cerrarModalMiCuenta() {
    document.getElementById('modal-mi-cuenta').classList.add('hidden');
}

async function cambiarMiCuenta() {
    const passwordActual = document.getElementById('cuenta-password-actual').value;
    const nuevaPassword = document.getElementById('cuenta-password-nueva').value;

    if (!passwordActual || !nuevaPassword) {
        showToast('Completa ambos campos', 'error');
        return;
    }

    if (nuevaPassword.length < 6) {
        showToast('La nueva contraseña debe tener al menos 6 caracteres', 'error');
        return;
    }

    try {
        await api.patch('/usuarios/me/password', {
            password_actual: passwordActual,
            nueva_password: nuevaPassword
        });
        document.getElementById('cuenta-password-actual').value = '';
        document.getElementById('cuenta-password-nueva').value = '';
        cerrarModalMiCuenta();
        showToast('Contraseña actualizada exitosamente', 'success');
    } catch (err) {
        showToast(err.message || 'Error al cambiar la contraseña', 'error');
    }
}

// ============ BOLETAS PENDIENTES ============
//
// Punto de recuperación cuando una boleta no llegó a emitirse. Dos casos,
// con arreglos distintos (ver GET /api/facturas/pendientes en el backend):
//   - facturas_con_error: la Factura existe y su correlativo ya está
//     reservado -> se reintenta, conservando ese mismo número.
//   - ventas_sin_boleta: nunca se creó la Factura -> se emite de cero.

async function refreshBoletasPendientes() {
    const container = document.getElementById('admin-boletas-list');
    if (!container) return;

    refreshSwitchUsarSunat();

    try {
        const data = await api.get('/facturas/pendientes');
        renderBoletasPendientes(data);
    } catch (err) {
        container.innerHTML = `<p class="empty-hint">No se pudo cargar: ${escapeHtml(err.message)}</p>`;
    }
}

/**
 * Estado del interruptor de facturación. La fuente de verdad es el
 * servidor, no la sesión guardada: el RUC lo carga el superadmin, así que
 * puede aparecer sin que este admin vuelva a loguearse.
 */
// ¿Este restaurante ya cargó su certificado? Lo dice el backend
// (datos_fiscales_bloqueados); mientras no responda, se asume que no —
// es el supuesto que lleva al camino seguro (abrir el formulario).
let sunatYaConfigurado = false;

async function refreshSwitchUsarSunat() {
    const check = document.getElementById('switch-usar-sunat');
    const hint = document.getElementById('sunat-switch-hint');
    if (!check) return;

    try {
        const cfg = await api.get('/configuracion');
        check.checked = cfg.usar_sunat;
        // `datos_fiscales_bloqueados` viene en true solo cuando la
        // facturación está activa, o sea cuando el certificado YA se cargó.
        // Es lo que distingue "prender de nuevo algo ya configurado" de
        // "configurarlo por primera vez".
        sunatYaConfigurado = !!cfg.datos_fiscales_bloqueados;
        // Sin RUC el interruptor no puede prenderse — se deshabilita y se
        // dice POR QUÉ, en vez de dejarlo muerto sin explicación.
        // Siempre habilitado si el servidor respondió: prenderlo sin
        // credenciales ya no es un callejón sin salida, abre el formulario
        // que sirve para cargarlas.
        check.disabled = false;
        if (!sunatYaConfigurado) {
            hint.textContent = 'Actívalo para vincular tu certificado digital y empezar a emitir.';
        } else if (cfg.usar_sunat) {
            hint.textContent = `Emitiendo con RUC ${cfg.ruc} · ${cfg.razon_social || ''}`.trim();
        } else {
            hint.textContent = 'Apagado: cobrás normal, sin emitir comprobantes ni pedir documento.';
        }
    } catch (_) {
        // Si no se pudo leer la configuración, el interruptor queda
        // DESHABILITADO y lo dice.
        //
        // Antes acá no se hacía nada, y el resultado era un interruptor que
        // se veía perfectamente usable pero no hacía nada: al tocarlo solo
        // salía un error, sin ninguna pista de por qué. Peor todavía,
        // mostraba "apagado" cuando en realidad NO SE SABE cómo está — y
        // apagado significa "este restaurante no emite boletas", que es una
        // afirmación fuerte para hacerla sin haber podido consultar nada.
        //
        // A diferencia del switch de notificaciones (que tiene respaldo en
        // localStorage), este estado vive solo en el servidor: sin
        // respuesta no hay nada que mostrar honestamente.
        check.disabled = true;
        hint.textContent = 'No se pudo leer la configuración. Revisa la conexión con el servidor y vuelve a entrar.';
    }
}

async function onToggleUsarSunat(event) {
    const activar = event.target.checked;

    // ENCENDER no es un PATCH: hace falta el certificado digital y las
    // credenciales SOL. Sin los tres archivos en el servidor, el restaurante
    // quedaría "activado" y fallando en cada cobro, que es justo lo que este
    // interruptor existe para evitar.
    //
    // Si ya está todo cargado (el admin lo apagó y lo vuelve a prender), el
    // PATCH alcanza: los archivos siguen donde estaban.
    if (activar && !sunatYaConfigurado) {
        event.target.checked = false;   // no mentir: todavía no está activo
        abrirActivacionSunat();
        return;
    }

    try {
        const cfg = await api.patch('/configuracion', { usar_sunat: activar });
        showToast(cfg.usar_sunat ? 'Boletas activadas' : 'Boletas desactivadas', 'success');
        // La sesión guardada lleva cliente_usar_sunat, y es lo que mira el
        // mozo al cobrar para decidir si emitir. Sin refrescarla, el cambio
        // no surte efecto hasta el próximo login.
        await refrescarSesionDesdeServidor();
        await refreshBoletasPendientes();
    } catch (err) {
        // Volver el switch a donde estaba: dejarlo mostrando "activado"
        // cuando el backend lo rechazó sería mentir sobre el estado real.
        event.target.checked = !activar;
        showToast(err.message || 'No se pudo cambiar', 'error');
    }
}

function renderBoletasPendientes({ facturas_con_error, ventas_sin_boleta }) {
    const container = document.getElementById('admin-boletas-list');

    if (facturas_con_error.length === 0 && ventas_sin_boleta.length === 0) {
        container.innerHTML = '<p class="empty-hint">Todas las ventas cobradas tienen su boleta emitida.</p>';
        return;
    }

    const bloqueErrores = facturas_con_error.map(f => `
        <div class="admin-item">
            <div class="admin-item-info">
                <h4>${escapeHtml(f.numero_boleta)}</h4>
                <p>Mesa ${f.numero_mesa} · ${formatCurrency(f.total)} · ${formatDate(f.creado_en)}</p>
                <p>${escapeHtml(f.error_mensaje || 'Sin detalle del error')}</p>
            </div>
            <div class="admin-item-actions">
                <button class="btn btn-secondary" onclick="reintentarBoleta(${f.id})">Reintentar</button>
            </div>
        </div>
    `).join('');

    const bloqueSinBoleta = ventas_sin_boleta.map(v => `
        <div class="admin-item">
            <div class="admin-item-info">
                <h4>Mesa ${v.numero_mesa}</h4>
                <p>${formatCurrency(v.total)} · ${formatDate(v.creado_en)}</p>
                <p>Cobrada, nunca se emitió boleta</p>
            </div>
            <div class="admin-item-actions">
                <button class="btn btn-secondary" onclick="emitirBoletaPendiente([${v.comanda_ids.join(',')}])">Emitir</button>
            </div>
        </div>
    `).join('');

    container.innerHTML = `
        ${facturas_con_error.length ? `<h3 class="section-title">Boletas con error (${facturas_con_error.length})</h3>${bloqueErrores}` : ''}
        ${ventas_sin_boleta.length ? `<h3 class="section-title">Ventas sin boleta (${ventas_sin_boleta.length})</h3>${bloqueSinBoleta}` : ''}
    `;
}

async function reintentarBoleta(facturaId) {
    try {
        const factura = await api.post(`/facturas/${facturaId}/reintentar`);
        showToast(`Boleta ${factura.numero_boleta} emitida`, 'success');
        if (typeof imprimirBoletaVenta === 'function') imprimirBoletaVenta(factura);
        await refreshBoletasPendientes();
    } catch (err) {
        // Mismo criterio que al cobrar: si el backend devolvió la Factura
        // dentro del error, hay con qué imprimir sin depender del servidor.
        // Acá el comensal ya se fue, pero el restaurante necesita el papel
        // para su propio control mientras regulariza.
        let impreso = false;
        if (err.factura && typeof imprimirBoletaContingencia === 'function') {
            impreso = await imprimirBoletaContingencia(err.factura);
        }
        showToast(
            impreso
                ? `Sigue pendiente (${err.message}). Se imprimió el comprobante de contingencia.`
                : (err.message || 'No se pudo emitir la boleta'),
            impreso ? 'warning' : 'error'
        );
        await refreshBoletasPendientes();
    }
}

async function emitirBoletaPendiente(comandaIds) {
    try {
        // Sin documento del comprador: se emite como Público General. Quien
        // pidió boleta con su DNI/RUC ya se fue — inventarle un documento
        // sería peor que emitirla a nombre de "CLIENTES VARIOS".
        const factura = await api.post('/facturas/generar', { comanda_ids: comandaIds });
        showToast(`Boleta ${factura.numero_boleta} emitida`, 'success');
        if (typeof imprimirBoletaVenta === 'function') imprimirBoletaVenta(factura);
        await refreshBoletasPendientes();
    } catch (err) {
        showToast(err.message || 'No se pudo emitir la boleta', 'error');
        await refreshBoletasPendientes();
    }
}


// ============ ACTIVACIÓN DE FACTURACIÓN ELECTRÓNICA ============
//
// Prender el interruptor no es un PATCH: hace falta el certificado digital y
// las credenciales SOL, porque sin los tres archivos el restaurante quedaría
// "activado" y fallando en CADA cobro. Por eso el switch abre este
// formulario en vez de mandar un cambio de estado que el backend rechazaría.
//
// Dos pasos porque el primero puede fallar solo (un RUC mal tipeado), y no
// tiene sentido pedirle el certificado a alguien cuyo RUC todavía no validó.

let sunatDatosFiscales = null;   // { ruc, razon_social, direccion_fiscal }
// Razón social que el superadmin ya cargó al dar de alta el restaurante. Si
// existe, el paso 1 no consulta el padrón: ese dato es más confiable y ya
// está en el servidor.
let sunatRazonSocialGuardada = '';

function abrirActivacionSunat() {
    const panel = document.getElementById('sunat-activacion');
    if (!panel) return;
    panel.classList.remove('hidden');
    volverAPaso1();

    // Si el restaurante ya tiene RUC cargado (lo puso el superadmin al darlo
    // de alta), se precarga: el admin no tiene por qué volver a tipearlo.
    api.get('/configuracion').then(cfg => {
        sunatRazonSocialGuardada = (cfg.razon_social || '').trim();
        if (cfg.direccion_fiscal) {
            document.getElementById('sunat-direccion').value = cfg.direccion_fiscal;
        }
        if (cfg.ruc) {
            document.getElementById('sunat-ruc').value = cfg.ruc;
            validarRucEmpresa();
        }
        // Restaurante de pruebas (RUC 20000000001): el ambiente BETA de SUNAT
        // exige unas credenciales fijas y PÚBLICAS, iguales para todos. Se
        // precargan para que nadie tenga que ir a buscarlas a la
        // documentación — y se avisa, bien visible, que ahí nada tiene
        // efecto tributario.
        if (cfg.es_ambiente_beta) {
            document.getElementById('sunat-sol-usuario').value = 'MODDATOS';
            document.getElementById('sunat-sol-clave').value = 'moddatos';
            const aviso = document.getElementById('sunat-aviso-beta');
            if (aviso) aviso.classList.remove('hidden');
        }
    }).catch(() => { /* que falle el precargado no impide tipearlo a mano */ });

    panel.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

function cerrarActivacionSunat() {
    const panel = document.getElementById('sunat-activacion');
    if (panel) panel.classList.add('hidden');
    sunatDatosFiscales = null;
    sunatRazonSocialGuardada = '';
    // Las claves NO se dejan en el DOM: si el admin cancela, no tiene por qué
    // quedar una contraseña escrita en un input de una pantalla abierta.
    ['sunat-cert-clave', 'sunat-sol-clave', 'sunat-cert'].forEach(id => {
        const el = document.getElementById(id);
        if (el) el.value = '';
    });
}

function volverAPaso1() {
    document.getElementById('sunat-paso-1').classList.remove('hidden');
    document.getElementById('sunat-paso-2').classList.add('hidden');
    document.getElementById('sunat-paso-1-chip').classList.add('activo');
    document.getElementById('sunat-paso-2-chip').classList.remove('activo');
}

// ---- Paso 1: validar el RUC contra el padrón ----

async function validarRucEmpresa() {
    const ruc = document.getElementById('sunat-ruc').value.trim();
    const info = document.getElementById('sunat-ruc-info');
    const encontrados = document.getElementById('sunat-datos-encontrados');
    const boton = document.getElementById('sunat-btn-validar');

    encontrados.classList.add('hidden');

    if (ruc.length !== 11) {
        pintar(info, 'El RUC tiene 11 dígitos.', 'aviso');
        return;
    }

    // Si el superadmin ya cargó la razón social al dar de alta el
    // restaurante, NO hace falta consultar nada: ese dato es más confiable
    // que el padrón y ya está en el servidor. Consultar igual ataría la
    // activación a 1,6 GB de padrón para averiguar algo que ya se sabe.
    if (sunatRazonSocialGuardada) {
        mostrarDatosFiscales(sunatRazonSocialGuardada, false);
        pintar(info, 'Datos fiscales ya registrados', 'ok');
        return;
    }

    boton.disabled = true;
    pintar(info, 'Buscando en SUNAT...', 'buscando');
    try {
        const datos = await api.get(`/documento/${ruc}`);

        if (datos.encontrado) {
            mostrarDatosFiscales(datos.nombre, false);
            pintar(
                info,
                datos.puede_facturarse === false
                    ? (datos.advertencia || 'Revisá el estado de tu RUC en SUNAT.')
                    : 'RUC verificado',
                datos.puede_facturarse === false ? 'aviso' : 'ok'
            );
            return;
        }

        // No está en el padrón. NO es un callejón sin salida: puede ser un
        // RUC recién inscrito, o el RUC 20000000001 del ambiente de pruebas,
        // que es ficticio y no va a figurar nunca. Se deja escribir la razón
        // social a mano y se sigue.
        mostrarDatosFiscales('', true);
        pintar(info, 'No figura en el padrón. Escribí la razón social a mano.', 'neutro');
    } catch (err) {
        // 503 = el padrón todavía no está construido (son 1,6 GB y varios
        // minutos). Eso NO puede impedir activar la facturación: es un dato
        // de comodidad, no un requisito. Mismo camino que "no encontrado".
        const sinPadron = err.status === 503;
        mostrarDatosFiscales('', true);
        pintar(
            info,
            sinPadron
                ? 'El padrón de SUNAT no está instalado en este servidor. Escribí la razón social a mano.'
                : (err.message || 'No se pudo consultar. Escribí la razón social a mano.'),
            'neutro'
        );
    } finally {
        boton.disabled = false;
    }
}

/**
 * Muestra los datos fiscales del paso 1.
 *
 * `editable` decide si la razón social se puede escribir: viene del padrón
 * (no editable, es el dato oficial) o la tiene que poner el admin (editable,
 * porque no hay de dónde sacarla). Un campo que se ve igual en los dos casos
 * haría que alguien intente corregir el oficial y no pase nada.
 */
function mostrarDatosFiscales(razonSocial, editable) {
    const campo = document.getElementById('sunat-razon-social');
    const encontrados = document.getElementById('sunat-datos-encontrados');

    campo.value = razonSocial || '';
    campo.readOnly = !editable;
    campo.placeholder = editable ? 'Tal como figura en tu ficha RUC' : '';
    encontrados.classList.remove('hidden');
    if (editable && !razonSocial) campo.focus();
}


function confirmarDatosFiscales() {
    const ruc = document.getElementById('sunat-ruc').value.trim();
    const razon = document.getElementById('sunat-razon-social').value.trim();
    const direccion = document.getElementById('sunat-direccion').value.trim();

    if (!razon) {
        showToast('Falta la razón social', 'warning');
        document.getElementById('sunat-razon-social').focus();
        return;
    }
    if (!direccion) {
        showToast('Falta la dirección fiscal', 'warning');
        document.getElementById('sunat-direccion').focus();
        return;
    }

    sunatDatosFiscales = { ruc, razon_social: razon, direccion_fiscal: direccion };

    document.getElementById('sunat-paso-1').classList.add('hidden');
    document.getElementById('sunat-paso-2').classList.remove('hidden');
    document.getElementById('sunat-paso-1-chip').classList.remove('activo');
    document.getElementById('sunat-paso-2-chip').classList.add('activo');
}

// ---- Paso 2: certificado y credenciales ----

function mostrarNombreCertificado(event) {
    const archivo = event.target.files && event.target.files[0];
    const el = document.getElementById('sunat-cert-nombre');
    el.textContent = archivo ? archivo.name : 'Ningún archivo elegido';
}

async function vincularConSunat() {
    const error = document.getElementById('sunat-activacion-error');
    const boton = document.getElementById('sunat-btn-vincular');
    error.classList.add('hidden');

    const archivo = document.getElementById('sunat-cert').files[0];
    const claveCert = document.getElementById('sunat-cert-clave').value;
    const solUsuario = document.getElementById('sunat-sol-usuario').value.trim();
    const solClave = document.getElementById('sunat-sol-clave').value;

    // Se revisa acá antes de subir: mandar un formulario incompleto gasta el
    // tiempo de subida del certificado para nada.
    const falta = !archivo ? 'el certificado (.pfx)'
        : !claveCert ? 'la clave del certificado'
        : !solUsuario ? 'el usuario SOL'
        : !solClave ? 'la clave SOL'
        : null;
    if (falta) {
        error.textContent = `Falta ${falta}.`;
        error.classList.remove('hidden');
        return;
    }

    const datos = new FormData();
    datos.append('ruc', sunatDatosFiscales.ruc);
    datos.append('file', archivo);
    datos.append('password', claveCert);
    datos.append('sol_usuario', solUsuario);
    datos.append('sol_clave', solClave);
    datos.append('direccion_fiscal', sunatDatosFiscales.direccion_fiscal);
    // Solo sirve cuando el padrón no pudo resolver el RUC (no instalado, o
    // un RUC que no figura — como el 20000000001 de pruebas). El backend la
    // ignora si ya tiene una guardada.
    datos.append('razon_social_manual', sunatDatosFiscales.razon_social);

    boton.disabled = true;
    boton.textContent = 'Vinculando...';
    try {
        // api.postFile no pone Content-Type a mano: el navegador tiene que
        // armar el boundary del multipart, y fijarlo nosotros rompe el parseo.
        await api.postFile('/configuracion/subir-certificado', datos);

        cerrarActivacionSunat();
        showToast('Listo: ya podés emitir comprobantes electrónicos', 'success');
        // El backend es la fuente de verdad del switch: se repinta con lo que
        // acaba de responder, no con una suposición del frontend.
        await refreshSwitchUsarSunat();
        // La sesión guardada lleva cliente_usar_sunat, y es lo que mira el
        // mozo al cobrar. Sin refrescarla, el cambio no surte efecto hasta el
        // próximo login.
        await refrescarSesionDesdeServidor();
        await refreshBoletasPendientes();
    } catch (err) {
        error.textContent = err.message || 'No se pudo vincular';
        error.classList.remove('hidden');
    } finally {
        boton.disabled = false;
        boton.textContent = 'Vincular con SUNAT';
    }
}

function pintar(el, texto, tipo) {
    if (!el) return;
    el.textContent = texto || '';
    el.className = 'doc-info' + (texto ? ` ${tipo}` : '');
}
