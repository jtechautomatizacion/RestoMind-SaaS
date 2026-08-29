/**
 * CU-01 y CU-04: Dashboard Administrador
 * - CU-01: Gestión de la Carta Inteligente
 * - CU-04: Control de Compras y Caja Chica
 */

function initAdmin() {
    refreshAdmin();
}

function refreshAdmin() {
    renderPlatos();
    renderCompras();
}

// ============ CU-01: PLATOS ============

function renderPlatos() {
    const container = document.getElementById('admin-platos-list');
    container.innerHTML = '';

    estado.platos.forEach(plato => {
        const div = document.createElement('div');
        div.className = 'admin-item';
        div.innerHTML = `
            <div class="admin-item-info">
                <h3>${plato.nombre}</h3>
                <p>${plato.categoria} • ${formatCurrency(plato.precio_venta)}</p>
                <p style="font-size: 12px; color: #999;">Estado: ${plato.estado}</p>
            </div>
            <div class="admin-item-actions">
                <button class="btn btn-secondary" onclick="editarPlato(${plato.id})">
                    ✏️ Editar
                </button>
                <button class="btn btn-danger" onclick="desactivarPlato(${plato.id})">
                    ${plato.estado === 'activo' ? '❌ Desactivar' : '✅ Activar'}
                </button>
            </div>
        `;
        container.appendChild(div);
    });
}

function abrirModalNuevoPlato() {
    document.getElementById('form-plato').reset();
    abrirModal('modal-plato');
}

async function guardarPlato(event) {
    event.preventDefault();

    const data = {
        nombre: document.getElementById('plato-nombre').value,
        categoria: document.getElementById('plato-categoria').value,
        precio_venta: parseFloat(document.getElementById('plato-precio').value),
        descripcion: document.getElementById('plato-descripcion').value || null
    };

    try {
        const result = await api.post('/platos', data);
        console.log('Plato creado:', result);
        estado.platos.push(result);
        renderPlatos();
        cerrarModalPlato();
        showToast('✅ Plato creado', 'success');
    } catch (err) {
        showToast('Error al crear plato: ' + err.message, 'error');
    }
}

async function editarPlato(platoId) {
    const plato = estado.platos.find(p => p.id === platoId);
    if (!plato) return;

    document.getElementById('plato-nombre').value = plato.nombre;
    document.getElementById('plato-categoria').value = plato.categoria;
    document.getElementById('plato-precio').value = plato.precio_venta;
    document.getElementById('plato-descripcion').value = plato.descripcion || '';

    // TODO: Cambiar form a PATCH mode
    abrirModal('modal-plato');
}

async function desactivarPlato(platoId) {
    const plato = estado.platos.find(p => p.id === platoId);
    const nuevoEstado = plato.estado === 'activo' ? 'inactivo' : 'activo';

    try {
        await api.patch(`/platos/${platoId}/estado`, { estado: nuevoEstado });
        plato.estado = nuevoEstado;
        renderPlatos();
        showToast(`✅ Plato ${nuevoEstado}`, 'success');
    } catch (err) {
        showToast('Error al cambiar estado: ' + err.message, 'error');
    }
}

// ============ CU-04: COMPRAS ============

function renderCompras() {
    const container = document.getElementById('admin-compras-list');
    container.innerHTML = '';

    // Agrupar por fecha
    const comprasPorFecha = {};
    estado.compras.forEach(compra => {
        if (!comprasPorFecha[compra.fecha]) {
            comprasPorFecha[compra.fecha] = [];
        }
        comprasPorFecha[compra.fecha].push(compra);
    });

    // Ordenar fechas descendente
    const fechas = Object.keys(comprasPorFecha).sort().reverse();

    fechas.forEach(fecha => {
        const comprasDelDia = comprasPorFecha[fecha];
        const totalDelDia = comprasDelDia.reduce((sum, c) => sum + c.monto, 0);

        const h3 = document.createElement('h3');
        h3.style.marginTop = '20px';
        h3.style.marginBottom = '10px';
        h3.textContent = `${formatDate(fecha)} - Total: ${formatCurrency(totalDelDia)}`;
        container.appendChild(h3);

        comprasDelDia.forEach(compra => {
            const div = document.createElement('div');
            div.className = 'admin-item';
            div.innerHTML = `
                <div class="admin-item-info">
                    <h4>${compra.descripcion}</h4>
                    <p>${compra.categoria || 'Sin categoría'} • ${formatCurrency(compra.monto)}</p>
                    <p style="font-size: 12px; color: #999;">Por: ${compra.creado_por || 'Admin'}</p>
                </div>
                <div class="admin-item-actions">
                    <button class="btn btn-danger" onclick="cancelarCompra(${compra.id})">
                        ${compra.estado === 'registrado' ? '❌ Cancelar' : '✅ Restaurar'}
                    </button>
                </div>
            `;
            container.appendChild(div);
        });
    });
}

function abrirModalNuevaCompra() {
    const hoy = formatDateInput(new Date());
    document.getElementById('compra-fecha').value = hoy;
    document.getElementById('form-compra').reset();
    abrirModal('modal-compra');
}

async function guardarCompra(event) {
    event.preventDefault();

    const data = {
        descripcion: document.getElementById('compra-descripcion').value,
        categoria: document.getElementById('compra-categoria').value || null,
        monto: parseFloat(document.getElementById('compra-monto').value),
        fecha: document.getElementById('compra-fecha').value
    };

    try {
        const result = await api.post('/compras', data);
        console.log('Compra creada:', result);
        estado.compras.push(result);
        renderCompras();
        cerrarModalCompra();
        showToast('✅ Gasto registrado', 'success');
    } catch (err) {
        showToast('Error al registrar gasto: ' + err.message, 'error');
    }
}

async function cancelarCompra(compraId) {
    const compra = estado.compras.find(c => c.id === compraId);
    const nuevoEstado = compra.estado === 'registrado' ? 'cancelado' : 'registrado';

    try {
        await api.patch(`/compras/${compraId}/estado`, { estado: nuevoEstado });
        compra.estado = nuevoEstado;
        renderCompras();
        showToast(`✅ Compra ${nuevoEstado}`, 'success');
    } catch (err) {
        showToast('Error al cambiar estado: ' + err.message, 'error');
    }
}
