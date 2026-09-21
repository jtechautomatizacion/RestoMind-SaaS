/**
 * Validador de Caja — apertura/cierre por TURNO (solo admin).
 *
 * Un restaurante puede abrir y cerrar varias veces el mismo día (turno
 * mañana, turno tarde...) — la única regla es "no se puede abrir un turno
 * nuevo mientras haya uno abierto". Dos estados posibles en pantalla (ver
 * backend/routes/caja.py):
 *
 *  1. Hay un turno abierto -> resumen en vivo + formulario "Cerrar caja"
 *     (puede ser de un día anterior sin cerrar: es_atrasada=true)
 *  2. No hay turno abierto -> formulario "Abrir caja", SIEMPRE disponible
 *     (si hubo un turno cerrado hoy, su resultado se muestra arriba como
 *     confirmación rápida — nunca como excusa para bloquear abrir otro)
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
    // Textos en lenguaje simple a propósito: esta app la usa gente que
    // recién está aprendiendo a manejar un negocio, no contadores. "Caja
    // cuadrada" y "no cuadró" son las frases que cualquier persona que
    // maneja una caja ya usa todos los días — "discrepancia" es una
    // palabra de auditor que hay que pararse a pensar qué significa.
    if (estadoTexto === 'cuadrado') {
        return { icono: '✅', titulo: 'Caja cuadrada', clase: 'caja-banner-cuadrada' };
    }
    if (estadoTexto === 'discrepancia_leve') {
        return { icono: '⚠️', titulo: 'No cuadró (diferencia chica)', clase: 'caja-banner-leve' };
    }
    if (estadoTexto === 'cerrado_automatico') {
        // El admin nunca la cerró; el sistema la cerró solo al día siguiente
        // para no bloquear Mesas/Cocina indefinidamente (ver CLAUDE.md,
        // sección Validador de Caja). saldo_contado = saldo_esperado porque
        // no hubo conteo físico real — hay que revisarla a mano.
        return { icono: '⏰', titulo: 'Se cerró sola (falta contar el dinero)', clase: 'caja-banner-leve' };
    }
    return { icono: '❌', titulo: 'No cuadró (diferencia grande)', clase: 'caja-banner-grave' };
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
        // Con nombre, "Caja abierta" pasa a "Turno Mañana"; sin nombre,
        // queda el título genérico que ya trae la plantilla.
        if (caja.nombre_turno) {
            nodo.querySelector('[data-slot="banner-titulo-abierta"]').textContent = `Turno ${caja.nombre_turno}`;
        }
        nodo.querySelector('[data-slot="ventas-ahora"]').textContent = formatCurrency(estadoCaja.ventas_hasta_ahora);
        nodo.querySelector('[data-slot="gastos-ahora"]').textContent = formatCurrency(estadoCaja.gastos_hasta_ahora);
        // Desglose por método. Solo el efectivo se espera encontrar al contar;
        // el Yape se informa para que el total de arriba no parezca un error.
        nodo.querySelector('[data-slot="ventas-efectivo"]').textContent =
            formatCurrency(estadoCaja.ventas_efectivo_hasta_ahora || 0);
        nodo.querySelector('[data-slot="ventas-yape"]').textContent =
            formatCurrency(estadoCaja.ventas_yape_hasta_ahora || 0);

        if (estadoCaja.es_atrasada) {
            nodo.querySelector('[data-slot="aviso-atrasada"]').classList.remove('hidden');
        }

        contenedor.appendChild(nodo);
        return;
    }

    // Sin turno abierto: si hubo uno cerrado hoy, se muestra como
    // confirmación rápida — pero el formulario de abrir uno nuevo SIEMPRE
    // se agrega debajo, nunca se reemplaza por el resumen.
    if (estadoCaja.ultimo_cierre_hoy) {
        const caja = estadoCaja.ultimo_cierre_hoy;
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
        if (caja.nombre_turno || estadoCaja.turnos_hoy > 1) {
            // Con nombre, se prioriza sobre el conteo genérico: "Turno
            // Mañana" dice más que "Turno 1 de hoy".
            nodo.querySelector('[data-slot="turnos-hoy"]').textContent = caja.nombre_turno
                ? ` · Turno ${caja.nombre_turno}`
                : ` · Turno ${estadoCaja.turnos_hoy} de hoy`;
            nodo.querySelector('[data-slot="turnos-hoy"]').classList.remove('hidden');
        }

        contenedor.appendChild(nodo);
    }

    const tplAbrir = document.getElementById('tpl-caja-cerrada');
    contenedor.appendChild(tplAbrir.content.cloneNode(true));
}

async function confirmarAbrirCaja() {
    const input = document.getElementById('caja-saldo-inicial');
    const saldo = parseFloat(input.value);
    const nombreTurno = document.getElementById('caja-nombre-turno').value || null;

    if (isNaN(saldo) || saldo < 0) {
        showToast('Ingresa un saldo inicial válido', 'warning');
        return;
    }

    try {
        await api.post('/caja/abrir', { saldo_inicial: saldo, nombre_turno: nombreTurno });
        showToast('Caja abierta', 'success');
        await refreshCaja();
        // Desbloquea Mesas/Cocina de inmediato — sin esto el mozo vería el
        // banner de "caja cerrada" hasta el siguiente poll (hasta 20s).
        if (typeof refreshCajaGate === 'function') refreshCajaGate();
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
        if (typeof refreshCajaGate === 'function') refreshCajaGate();

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
    const caja = cajaEstadoActual && cajaEstadoActual.ultimo_cierre_hoy;
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
        // Hora de cierre, no solo fecha: con varios turnos el mismo día,
        // la fecha sola no alcanza para distinguir cuál es cuál.
        const hora = c.cerrado_en
            ? new Date(c.cerrado_en).toLocaleTimeString('es-PE', { hour: '2-digit', minute: '2-digit' })
            : '';
        const turno = c.nombre_turno ? ` · ${escapeHtml(c.nombre_turno)}` : '';
        return `
            <div class="admin-item">
                <div class="admin-item-info">
                    <h4>${icono} ${formatDate(c.fecha)}${hora ? ` · ${hora}` : ''}${turno}</h4>
                    <p>${titulo} · ${signo}${formatCurrency(c.diferencia)}</p>
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
