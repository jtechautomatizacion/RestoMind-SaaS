/**
 * Validador de Caja — apertura/cierre diario (solo admin).
 *
 * Tres estados posibles en pantalla (ver backend/routes/caja.py):
 *  1. Sin caja hoy           -> formulario "Abrir caja"
 *  2. Caja abierta           -> resumen en vivo + formulario "Cerrar caja"
 *     (puede ser de un día anterior sin cerrar: es_atrasada=true)
 *  3. Caja de hoy ya cerrada -> resultado + botón para reimprimir
 *
 * El backend es la única fuente de verdad de en qué estado está el flujo
 * (GET /caja/estado) — el frontend nunca infiere el estado localmente,
 * para no desincronizarse si dos pestañas del admin están abiertas.
 */

let cajaEstadoActual = null;
let cajaHistorialCache = [];

async function refreshCaja() {
    const contenedor = document.getElementById('caja-contenido');
    try {
        const estadoCaja = await api.get('/caja/estado');
        cajaEstadoActual = estadoCaja;
        renderCaja(estadoCaja);
    } catch (err) {
        contenedor.innerHTML = `<p class="empty-hint">No se pudo cargar: ${escapeHtml(err.message)}</p>`;
    }
    refreshHistorialCaja();
}

function _resumenEstadoCaja(estadoTexto) {
    if (estadoTexto === 'cuadrado') {
        return { icono: '✅', titulo: 'Caja cuadrada', clase: 'caja-banner-cuadrada' };
    }
    if (estadoTexto === 'discrepancia_leve') {
        return { icono: '⚠️', titulo: 'Discrepancia menor', clase: 'caja-banner-leve' };
    }
    return { icono: '❌', titulo: 'Discrepancia grave', clase: 'caja-banner-grave' };
}

function renderCaja(estadoCaja) {
    const contenedor = document.getElementById('caja-contenido');
    contenedor.innerHTML = '';

    if (estadoCaja.hay_caja_abierta) {
        const caja = estadoCaja.caja_abierta;
        const tpl = document.getElementById('tpl-caja-abierta');
        const nodo = tpl.content.cloneNode(true);

        const desde = new Date(caja.abierto_en).toLocaleString('es-PE', { dateStyle: 'medium', timeStyle: 'short' });
        nodo.querySelector('[data-slot="abierta-desde"]').textContent = `Desde ${desde}`;
        nodo.querySelector('[data-slot="ventas-ahora"]').textContent = formatCurrency(estadoCaja.ventas_hasta_ahora);
        nodo.querySelector('[data-slot="gastos-ahora"]').textContent = formatCurrency(estadoCaja.gastos_hasta_ahora);

        if (estadoCaja.es_atrasada) {
            nodo.querySelector('[data-slot="aviso-atrasada"]').classList.remove('hidden');
        }

        contenedor.appendChild(nodo);
        return;
    }

    if (estadoCaja.caja_cerrada_hoy) {
        const caja = estadoCaja.caja_cerrada_hoy;
        const tpl = document.getElementById('tpl-caja-ya-cerrada');
        const nodo = tpl.content.cloneNode(true);

        const { icono, titulo, clase } = _resumenEstadoCaja(caja.estado);
        nodo.querySelector('[data-slot="banner-clase"]').classList.add(clase);
        nodo.querySelector('[data-slot="banner-icono"]').textContent = icono;
        nodo.querySelector('[data-slot="banner-titulo"]').textContent = titulo;
        nodo.querySelector('[data-slot="hora-cierre"]').textContent = new Date(caja.cerrado_en)
            .toLocaleTimeString('es-PE', { hour: '2-digit', minute: '2-digit' });
        nodo.querySelector('[data-slot="esperado"]').textContent = formatCurrency(caja.saldo_esperado);
        nodo.querySelector('[data-slot="contado"]').textContent = formatCurrency(caja.saldo_contado);

        contenedor.appendChild(nodo);
        return;
    }

    const tpl = document.getElementById('tpl-caja-cerrada');
    contenedor.appendChild(tpl.content.cloneNode(true));
}

async function confirmarAbrirCaja() {
    const input = document.getElementById('caja-saldo-inicial');
    const saldo = parseFloat(input.value);

    if (isNaN(saldo) || saldo < 0) {
        showToast('Ingresa un saldo inicial válido', 'warning');
        return;
    }

    try {
        await api.post('/caja/abrir', { saldo_inicial: saldo });
        showToast('Caja abierta', 'success');
        await refreshCaja();
    } catch (err) {
        showToast(err.message || 'No se pudo abrir la caja', 'error');
    }
}

async function confirmarCerrarCaja() {
    const saldoContado = parseFloat(document.getElementById('caja-saldo-contado').value);
    const retiros = parseFloat(document.getElementById('caja-retiros').value) || 0;
    const razon = document.getElementById('caja-razon-discrepancia').value.trim();

    if (isNaN(saldoContado) || saldoContado < 0) {
        showToast('Ingresa cuánto dinero contaste en caja', 'warning');
        return;
    }

    // Cerrar caja es irreversible (congela ventas/gastos del día) — mismo
    // criterio que cobrar una mesa: confirmación explícita antes de una
    // acción que no tiene "deshacer".
    if (!confirm('¿Confirmas el cierre de caja? Esta acción no se puede deshacer.')) {
        return;
    }

    try {
        const cierre = await api.post('/caja/cerrar', {
            saldo_contado: saldoContado,
            retiros_personales: retiros,
            razon_discrepancia: razon || null,
        });
        showToast('Caja cerrada', 'success');
        await refreshCaja();

        // El dueño quiere ver el reporte apenas cierra, no ir a buscarlo
        // después en el historial.
        if (typeof abrirReporteCierreCaja === 'function') {
            abrirReporteCierreCaja(cierre, _datosNegocioParaReporte());
        }
    } catch (err) {
        showToast(err.message || 'No se pudo cerrar la caja', 'error');
    }
}

function _datosNegocioParaReporte() {
    return {
        nombre: (estado.usuario && estado.usuario.cliente_nombre) || 'Mi Restaurante',
    };
}

function reimprimirCierreCaja() {
    const caja = cajaEstadoActual && cajaEstadoActual.caja_cerrada_hoy;
    if (!caja) {
        showToast('No hay un cierre para mostrar', 'warning');
        return;
    }
    abrirReporteCierreCaja(caja, _datosNegocioParaReporte());
}

async function refreshHistorialCaja() {
    const container = document.getElementById('caja-historial-list');
    if (!container) return;

    try {
        cajaHistorialCache = await api.get('/caja/historial?limit=30');
        renderHistorialCaja(cajaHistorialCache);
    } catch (err) {
        container.innerHTML = '<p class="empty-hint">No se pudo cargar el historial</p>';
    }
}

function renderHistorialCaja(historial) {
    const container = document.getElementById('caja-historial-list');

    if (!historial || historial.length === 0) {
        container.innerHTML = '<p class="empty-hint">Sin cierres registrados todavía.</p>';
        return;
    }

    container.innerHTML = historial.map(c => {
        const { icono, titulo } = _resumenEstadoCaja(c.estado);
        const signo = c.diferencia >= 0 ? '+' : '';
        return `
            <div class="admin-item">
                <div class="admin-item-info">
                    <h4>${icono} ${formatDate(c.fecha)}</h4>
                    <p>${titulo} · Diferencia: ${signo}${formatCurrency(c.diferencia)}</p>
                </div>
                <div class="admin-item-actions">
                    <button class="icon-btn" title="Ver reporte" onclick="reimprimirCierreHistorial(${c.id})">${ICON_EDIT}</button>
                </div>
            </div>
        `;
    }).join('');
}

function reimprimirCierreHistorial(id) {
    const caja = cajaHistorialCache.find(c => c.id === id);
    if (!caja) return;
    abrirReporteCierreCaja(caja, _datosNegocioParaReporte());
}
