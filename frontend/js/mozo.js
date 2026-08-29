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

    estado.mesas.forEach(mesa => {
        const btn = document.createElement('button');
        btn.className = `mesa-btn ${mesa.estado}`;
        const cuentaHtml = mesa.estado === 'ocupada'
            ? `<div class="mesa-cuenta">${formatCurrency(mesa.cuenta_actual)}</div>`
            : '';
        btn.innerHTML = `
            <span class="mesa-estado-dot"></span>
            <span class="mesa-numero">${mesa.numero}</span>
            ${cuentaHtml}
        `;
        btn.onclick = () => abrirMesa(mesa);
        container.appendChild(btn);
    });
}

function abrirMesa(mesa) {
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

    platos.forEach(plato => {
        const div = document.createElement('div');
        div.className = 'plato-item';
        const descripcion = plato.descripcion
            ? `<div class="plato-descripcion">${escapeHtml(plato.descripcion)}</div>`
            : '';
        const thumb = plato.imagen_url
            ? `<img class="item-thumb" src="${escapeHtml(plato.imagen_url)}" alt="">`
            : '<div class="item-thumb-placeholder"><svg viewBox="0 0 24 24"><rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="8.5" cy="8.5" r="1.5"/><path d="M21 15l-5-5L5 21"/></svg></div>';
        div.innerHTML = `
            ${thumb}
            <div class="plato-info">
                <div class="plato-nombre">${escapeHtml(plato.nombre)}</div>
                ${descripcion}
                <div class="plato-precio">${formatCurrency(plato.precio_venta)}</div>
            </div>
            <button class="plato-btn-add" type="button">+</button>
        `;
        div.querySelector('.plato-btn-add').onclick = () => agregarACarrito(plato.id, plato.nombre, plato.precio_venta);
        container.appendChild(div);
    });
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
        await api.post('/comandas', data);

        showToast('Comanda enviada a cocina', 'success');
        cerrarModal();
        await refreshMozo();
        if (typeof refreshCocina === 'function') refreshCocina();
    } catch (err) {
        showToast(err.message || 'Error al enviar comanda', 'error');
    }
}

// ============ CUENTA DE MESA / COBRO ============

async function abrirCuentaMesa(mesa) {
    mesaActual = mesa;
    document.getElementById('modal-cuenta-title').textContent = `Mesa ${mesa.numero}`;

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
