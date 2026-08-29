/**
 * CU-02: Registro y Envío de Comandas Express
 * Interfaz del Mozo para crear comandas desde mesas
 */

let carrito = [];
let mesaActual = null;

function initMozo() {
    refreshMozo();
}

function refreshMozo() {
    renderMesas();
}

function renderMesas() {
    const container = document.getElementById('mozo-mesas');
    container.innerHTML = '';

    estado.mesas.forEach(mesa => {
        const btn = document.createElement('button');
        btn.className = `mesa-btn ${mesa.estado}`;
        btn.textContent = mesa.numero;
        btn.onclick = () => abrirComanda(mesa);
        container.appendChild(btn);
    });
}

function abrirComanda(mesa) {
    mesaActual = mesa;
    carrito = [];
    document.getElementById('modal-title').textContent = `Mesa ${mesa.numero}`;
    renderCategorias();
    renderPlatos();
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
}

function renderPlatos(categoria = null) {
    const container = document.getElementById('mozo-platos');
    container.innerHTML = '';

    let platos = estado.platos.filter(p => p.estado === 'activo');
    if (categoria) {
        platos = platos.filter(p => p.categoria === categoria);
    }

    platos.forEach(plato => {
        const div = document.createElement('div');
        div.className = 'plato-item';
        div.innerHTML = `
            <div class="plato-info">
                <div class="plato-nombre">${plato.nombre}</div>
                <div class="plato-precio">${formatCurrency(plato.precio_venta)}</div>
            </div>
            <button class="plato-btn-add" onclick="agregarACarrito(${plato.id}, '${plato.nombre}', ${plato.precio_venta})">
                ➕
            </button>
        `;
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
    container.innerHTML = '';

    let total = 0;

    carrito.forEach((item, idx) => {
        const subtotal = item.precio * item.cantidad;
        total += subtotal;

        const div = document.createElement('div');
        div.className = 'carrito-item';
        div.innerHTML = `
            <div class="carrito-item-info">
                <div class="carrito-item-nombre">${item.nombre}</div>
                <div class="carrito-item-cantidad">x${item.cantidad}</div>
            </div>
            <div class="carrito-item-precio">${formatCurrency(subtotal)}</div>
            <button class="carrito-item-remove" onclick="removerDelCarrito(${idx})">✕</button>
        `;
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
            platos: carrito.map(item => ({
                plato_id: item.platoId,
                cantidad: item.cantidad
            }))
        };

        const result = await api.post('/comandas', data);
        console.log('Comanda creada:', result);

        showToast('✅ Comanda enviada a cocina!', 'success');
        cerrarModal();
        refreshMozo();

        // Refresh cocina si está abierto
        if (typeof refreshCocina === 'function') {
            refreshCocina();
        }
    } catch (err) {
        showToast('Error al enviar comanda: ' + err.message, 'error');
    }
}
