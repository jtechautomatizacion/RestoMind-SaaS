/**
 * CU-02: Registro y Envío de Comandas Express + Cobro de Mesa
 * Interfaz del Mozo: tocar una mesa disponible abre un pedido nuevo;
 * tocar una mesa ocupada abre su cuenta (agregar pedido o cobrar).
 */

let carrito = [];
let mesaActual = null;

function initMozo() {
    renderMesas();
}

async function refreshMozo() {
    try {
        estado.mesas = await api.get('/mesas');
    } catch (err) {
        console.error('Error cargando mesas:', err);
    }
    renderMesas();
}

function renderMesas() {
    const container = document.getElementById('mozo-mesas');
    container.innerHTML = '';

    if (estado.mesas.length === 0) {
        container.innerHTML = '<p class="empty-hint">Aún no hay mesas configuradas.</p>';
        return;
    }

    // El cajero solo cobra: las mesas libres no le sirven de nada, así que
    // se muestran apagadas y sin acción (evita toques accidentales que
    // confundan "cobrar" con "tomar pedido").
    const esCajero = estado.rol === 'cajero';

    estado.mesas.forEach(mesa => {
        const btn = document.createElement('button');
        const deshabilitada = esCajero && mesa.estado !== 'ocupada';
        btn.className = `mesa-btn ${mesa.estado} ${deshabilitada ? 'mesa-btn-inactiva' : ''}`;

        const detalleHtml = mesa.estado === 'ocupada'
            ? `<div class="mesa-cuenta">${formatCurrency(mesa.cuenta_actual)}</div>`
            : `<div class="mesa-capacidad">${mesa.capacidad}p</div>`;
        const ubicacionHtml = mesa.ubicacion
            ? `<div class="mesa-ubicacion">${escapeHtml(mesa.ubicacion)}</div>`
            : '';

        const ocupada = mesa.estado === 'ocupada';
        const gradTop = ocupada ? 'url(#mesaTopOcupada)' : 'url(#mesaTopLibre)';
        const gradSilla = ocupada ? 'url(#sillaOcupada)' : 'url(#sillaLibre)';

        // Ícono 3D: disco con gradiente radial (relieve), sombra elíptica
        // "en el piso" para dar sensación de profundidad, brillo especular
        // arriba-izquierda (glossy) y sillas con degradé propio — todo con
        // formas planas (sin filter/blur), mismo costo que un ícono plano.
        btn.innerHTML = `
            <svg class="mesa-icono" viewBox="0 0 24 24">
                <ellipse class="mesa-icono-sombra" cx="12" cy="21.1" rx="6.6" ry="1.35"/>
                <circle class="mesa-icono-silla" fill="${gradSilla}" cx="12" cy="2.6" r="1.65"/>
                <circle class="mesa-icono-silla" fill="${gradSilla}" cx="12" cy="19.3" r="1.65"/>
                <circle class="mesa-icono-silla" fill="${gradSilla}" cx="2.6" cy="11" r="1.65"/>
                <circle class="mesa-icono-silla" fill="${gradSilla}" cx="21.4" cy="11" r="1.65"/>
                <circle class="mesa-icono-mesa" fill="${gradTop}" cx="12" cy="11" r="6"/>
                <ellipse class="mesa-icono-brillo" cx="9.4" cy="8.3" rx="2.5" ry="1.3"/>
            </svg>
            <span class="mesa-numero">${mesa.numero}</span>
            ${ubicacionHtml}
            ${detalleHtml}
            <span class="mesa-estado-dot"></span>
        `;
        if (!deshabilitada) {
            btn.onclick = () => abrirMesa(mesa);
        }
        container.appendChild(btn);
    });
}

function abrirMesa(mesa) {
    if (estado.rol === 'cajero') {
        // El cajero nunca toma pedidos, solo abre la cuenta para cobrar.
        if (mesa.estado === 'ocupada') abrirCuentaMesa(mesa);
        return;
    }

    if (mesa.estado === 'ocupada') {
        abrirCuentaMesa(mesa);
    } else {
        abrirNuevoPedido(mesa);
    }
}

// ============ NUEVO PEDIDO ============

function abrirNuevoPedido(mesa) {
    mesaActual = mesa;
    carrito = [];
    document.getElementById('modal-title').textContent = `Mesa ${mesa.numero} · Nuevo pedido`;
    renderCategorias();
    renderPlatos();
    renderCarrito();
    abrirModal('modal-comanda');
}

function renderCategorias() {
    const container = document.getElementById('mozo-categorias');
    container.innerHTML = '';

    const categorias = [...new Set(estado.platos.map(p => p.categoria))];

    categorias.forEach((cat, idx) => {
        const btn = document.createElement('button');
        btn.className = `categoria-btn ${idx === 0 ? 'active' : ''}`;
        btn.textContent = cat;
        btn.onclick = () => {
            document.querySelectorAll('.categoria-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            renderPlatos(cat);
        };
        container.appendChild(btn);
    });

    renderPlatos(categorias[0]);
}

function renderPlatos(categoria = null) {
    const container = document.getElementById('mozo-platos');
    container.innerHTML = '';

    let platos = estado.platos.filter(p => p.estado === 'activo');
    if (categoria) {
        platos = platos.filter(p => p.categoria === categoria);
    }

    if (platos.length === 0) {
        container.innerHTML = '<p class="empty-hint">No hay platos en esta categoría.</p>';
        return;
    }

    const grid = document.createElement('div');
    grid.className = 'platos-grid';

    platos.forEach(plato => {
        const card = document.createElement('button');
        card.className = 'plato-card';
        card.type = 'button';

        const thumb = plato.imagen_url
            ? `<img class="plato-card-imagen" src="${escapeHtml(plato.imagen_url)}" alt="">`
            : '<div class="plato-card-imagen plato-card-sin-imagen"><svg viewBox="0 0 24 24"><rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="8.5" cy="8.5" r="1.5"/><path d="M21 15l-5-5L5 21"/></svg></div>';

        const descripcion = plato.descripcion
            ? `<div class="plato-card-descripcion">${escapeHtml(plato.descripcion)}</div>`
            : '';

        card.innerHTML = `
            ${thumb}
            <div class="plato-card-contenido">
                <div class="plato-card-nombre">${escapeHtml(plato.nombre)}</div>
                ${descripcion}
                <div class="plato-card-footer">
                    <span class="plato-card-precio">${formatCurrency(plato.precio_venta)}</span>
                    <span class="plato-card-btn-add">+</span>
                </div>
            </div>
        `;
        card.onclick = () => agregarACarrito(plato.id, plato.nombre, plato.precio_venta);
        grid.appendChild(card);
    });

    container.appendChild(grid);
}

function agregarACarrito(platoId, nombre, precio) {
    const item = carrito.find(i => i.platoId === platoId);
    if (item) {
        item.cantidad++;
    } else {
        carrito.push({ platoId, nombre, precio, cantidad: 1 });
    }
    renderCarrito();
}

function renderCarrito() {
    const container = document.getElementById('mozo-carrito');

    if (carrito.length === 0) {
        container.innerHTML = '<p class="carrito-vacio">Toca un plato para agregarlo</p>';
        document.getElementById('mozo-total').textContent = formatCurrency(0);
        return;
    }

    let total = 0;
    container.innerHTML = '';

    carrito.forEach((item, idx) => {
        const subtotal = item.precio * item.cantidad;
        total += subtotal;

        const div = document.createElement('div');
        div.className = 'carrito-item';
        div.innerHTML = `
            <div>
                <div class="carrito-item-nombre">${escapeHtml(item.nombre)}</div>
                <div class="carrito-item-cantidad">x${item.cantidad}</div>
            </div>
            <div style="display:flex;align-items:center;">
                <span class="carrito-item-precio">${formatCurrency(subtotal)}</span>
                <button class="carrito-item-remove" type="button">✕</button>
            </div>
        `;
        div.querySelector('.carrito-item-remove').onclick = () => removerDelCarrito(idx);
        container.appendChild(div);
    });

    document.getElementById('mozo-total').textContent = formatCurrency(total);
}

function removerDelCarrito(idx) {
    const item = carrito[idx];
    if (item.cantidad > 1) {
        item.cantidad--;
    } else {
        carrito.splice(idx, 1);
    }
    renderCarrito();
}

async function enviarComanda() {
    if (carrito.length === 0) {
        showToast('Agrega al menos un plato', 'warning');
        return;
    }

    try {
        const data = {
            numero_mesa: mesaActual.numero,
            platos: carrito.map(item => ({ plato_id: item.platoId, cantidad: item.cantidad })),
        };
        const comanda = await api.post('/comandas', data);

        showToast('Comanda enviada a cocina', 'success');
        cerrarModal();
        await refreshMozo();
        if (typeof refreshCocina === 'function') refreshCocina();

        // Dos papeles, uno por impresora: cocina (qué preparar) y la copia
        // del mozo (con precios, para su propio registro).
        if (typeof imprimirComandaCocinaYMozo === 'function') {
            imprimirComandaCocinaYMozo(comanda);
        }
    } catch (err) {
        showToast(err.message || 'Error al enviar comanda', 'error');
    }
}

// ============ CUENTA DE MESA / COBRO ============

async function abrirCuentaMesa(mesa) {
    mesaActual = mesa;
    document.getElementById('modal-cuenta-title').textContent = `Mesa ${mesa.numero}`;
    // El cajero cobra, no toma pedidos adicionales.
    document.getElementById('btn-agregar-pedido').classList.toggle('hidden', estado.rol === 'cajero');

    try {
        const comandas = await api.get(`/comandas?numero_mesa=${mesa.numero}`);
        const activas = comandas.filter(c => c.estado === 'cocina' || c.estado === 'entregado');
        renderCuentaMesa(activas);
        abrirModal('modal-cuenta');
    } catch (err) {
        showToast('No se pudo cargar la cuenta de la mesa', 'error');
    }
}

function renderCuentaMesa(comandas) {
    const container = document.getElementById('cuenta-comandas');
    const btnCobrar = document.getElementById('btn-cobrar');

    if (comandas.length === 0) {
        container.innerHTML = '<p class="empty-hint">Esta mesa no tiene pedidos activos.</p>';
        document.getElementById('cuenta-total').textContent = formatCurrency(0);
        btnCobrar.disabled = true;
        btnCobrar.style.opacity = '0.5';
        return;
    }

    let total = 0;
    let hayEnCocina = false;

    container.innerHTML = comandas.map(c => {
        total += c.total_cuenta;
        if (c.estado === 'cocina') hayEnCocina = true;

        const badgeClase = c.estado === 'cocina' ? 'badge-cocina' : 'badge-entregado';
        const badgeTexto = c.estado === 'cocina' ? 'En cocina' : 'Entregado';

        const platosHtml = c.platos.map(p => `
            <div class="cuenta-plato-linea">
                <span>${p.cantidad}x ${escapeHtml(p.nombre)}</span>
                <span>${formatCurrency(p.subtotal)}</span>
            </div>
        `).join('');

        return `
            <div class="cuenta-comanda-bloque">
                <div class="cuenta-comanda-header">
                    <span class="badge ${badgeClase}">${badgeTexto}</span>
                    <strong>${formatCurrency(c.total_cuenta)}</strong>
                </div>
                ${platosHtml}
            </div>
        `;
    }).join('');

    document.getElementById('cuenta-total').textContent = formatCurrency(total);

    if (hayEnCocina) {
        btnCobrar.disabled = true;
        btnCobrar.style.opacity = '0.5';
        btnCobrar.textContent = 'Espera a que cocina entregue todo';
    } else {
        btnCobrar.disabled = false;
        btnCobrar.style.opacity = '1';
        btnCobrar.textContent = 'Cobrar y liberar mesa';
    }
}

function cerrarModalCuenta() {
    document.getElementById('modal-cuenta').classList.add('hidden');
}

function agregarPedidoAMesa() {
    cerrarModalCuenta();
    abrirNuevoPedido(mesaActual);
}

async function cobrarMesaActual() {
    if (!mesaActual) return;

    try {
        const resultado = await api.post(`/mesas/${mesaActual.id}/cobrar`);
        showToast(`Cobrado ${formatCurrency(resultado.total_cobrado)} · Mesa ${resultado.mesa_numero} libre`, 'success');
        cerrarModalCuenta();
        await refreshMozo();
        if (typeof refreshDashboard === 'function') refreshDashboard();
    } catch (err) {
        showToast(err.message || 'No se pudo cobrar la mesa', 'error');
    }
}

// ============ GESTIÓN DE MESAS (solo Admin) ============

let editingMesaId = null;

function abrirGestionMesas() {
    renderGestionMesas();
    abrirModal('modal-gestion-mesas');
}

function cerrarGestionMesas() {
    document.getElementById('modal-gestion-mesas').classList.add('hidden');
}

function renderGestionMesas() {
    const container = document.getElementById('gestion-mesas-list');

    if (estado.mesas.length === 0) {
        container.innerHTML = '<p class="empty-hint">Aún no hay mesas. Crea la primera.</p>';
        return;
    }

    const ICON_EDIT_MESA = '<svg viewBox="0 0 24 24"><path d="M12 20h9"/><path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z"/></svg>';
    const ICON_DELETE_MESA = '<svg viewBox="0 0 24 24"><polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/><path d="M10 11v6"/><path d="M14 11v6"/><path d="M9 6V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2"/></svg>';

    container.innerHTML = estado.mesas.map(mesa => {
        const ubicacion = mesa.ubicacion ? ` · ${escapeHtml(mesa.ubicacion)}` : '';
        return `
            <div class="admin-item">
                <div class="admin-item-info">
                    <h4>Mesa ${mesa.numero}</h4>
                    <p>${mesa.capacidad} personas${ubicacion} · ${mesa.estado}</p>
                </div>
                <div class="admin-item-actions">
                    <button class="icon-btn" title="Editar" onclick="abrirFormMesa(${mesa.id})">${ICON_EDIT_MESA}</button>
                    <button class="icon-btn danger" title="Eliminar" onclick="eliminarMesa(${mesa.id})">${ICON_DELETE_MESA}</button>
                </div>
            </div>
        `;
    }).join('');
}

function abrirFormMesa(mesaId = null) {
    editingMesaId = mesaId;
    document.getElementById('form-mesa').reset();

    if (mesaId) {
        const mesa = estado.mesas.find(m => m.id === mesaId);
        document.getElementById('modal-mesa-form-title').textContent = `Editar Mesa ${mesa.numero}`;
        document.getElementById('mesa-numero').value = mesa.numero;
        document.getElementById('mesa-capacidad').value = mesa.capacidad;
        document.getElementById('mesa-ubicacion').value = mesa.ubicacion || '';
    } else {
        document.getElementById('modal-mesa-form-title').textContent = 'Nueva mesa';
        document.getElementById('mesa-capacidad').value = 4;
    }

    abrirModal('modal-mesa-form');
}

function cerrarFormMesa() {
    document.getElementById('modal-mesa-form').classList.add('hidden');
}

async function guardarMesa(event) {
    event.preventDefault();

    const data = {
        numero: parseInt(document.getElementById('mesa-numero').value, 10),
        capacidad: parseInt(document.getElementById('mesa-capacidad').value, 10),
        ubicacion: document.getElementById('mesa-ubicacion').value.trim() || null,
    };

    try {
        if (editingMesaId) {
            await api.patch(`/mesas/${editingMesaId}`, data);
            showToast('Mesa actualizada', 'success');
        } else {
            await api.post('/mesas', data);
            showToast('Mesa creada', 'success');
        }
        cerrarFormMesa();
        await refreshMozo();
        renderGestionMesas();
    } catch (err) {
        showToast(err.message || 'Error al guardar la mesa', 'error');
    }
}

async function eliminarMesa(mesaId) {
    const mesa = estado.mesas.find(m => m.id === mesaId);
    if (!confirm(`¿Eliminar la Mesa ${mesa ? mesa.numero : ''}? No se puede deshacer.`)) return;

    try {
        await api.delete(`/mesas/${mesaId}`);
        showToast('Mesa eliminada', 'success');
        await refreshMozo();
        renderGestionMesas();
    } catch (err) {
        showToast(err.message || 'No se pudo eliminar la mesa', 'error');
    }
}
