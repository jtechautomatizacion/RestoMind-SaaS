/**
 * Vista unificada ("Todo en uno") — las tres etapas por las que pasa una
 * mesa, en una sola pantalla: tomar el pedido, cocinarlo y cobrarlo.
 *
 * Para quién es: el dueño que atiende solo. Con las pestañas separadas tiene
 * que saltar Mesas → Cocina → Mesas para cada cliente, y en cada salto pierde
 * de vista lo que estaba haciendo. Acá las tres columnas están siempre a la
 * vista y el trabajo fluye de izquierda a derecha.
 *
 * TRES DECISIONES QUE CONVIENE NO DESHACER SIN LEER ESTO:
 *
 * 1. Quién la ve sale de los ROLES que ya existen, no de una columna nueva
 *    en `clientes`. La condición es "esta cuenta ve Mesas Y ve Cocina"
 *    (`vistaUnificadaDisponible()`): un admin la cumple, y también una cuenta
 *    `mozo,jefe_cocina`. Un mozo puro no, y con razón — su columna de cocina
 *    estaría siempre vacía y cada consulta le devolvería un 403. Agregar un
 *    "modo de operación" en la base habría creado una segunda fuente de
 *    verdad sobre quién puede hacer qué, que tarde o temprano se contradice
 *    con los roles.
 *
 * 2. Es un INTERRUPTOR, no un reemplazo. La grilla de mesas de siempre queda
 *    intacta y a un toque de distancia (la preferencia se guarda por
 *    dispositivo). Si a mitad de un turno real esta vista no le acomoda, se
 *    vuelve sin perder nada.
 *
 * 3. Reusa los modales que ya existen (nuevo pedido, cuenta, cobro). Duplicar
 *    el carrito y el flujo de cobro sería duplicar la lógica de dinero —
 *    exactamente donde no se pueden tener dos versiones que se desincronicen.
 *    Esos modales YA son overlays semitransparentes (`.modal` en style.css usa
 *    rgba(10,10,10,.45)), así que el contexto de atrás se sigue viendo sin
 *    tener que construir nada nuevo.
 *
 * Lo que NO tiene, a propósito: Enter para confirmar. Cobrar mueve dinero y
 * libera la mesa; que se dispare con una tecla que se suele apretar sin mirar
 * es un cobro equivocado esperando a pasar. Los atajos de acá solo NAVEGAN.
 */

const VU_PREF_KEY = 'restomind_vista_unificada';
const VU_INTERVALO_MS = 5000;
// Ventana para juntar dígitos y poder tipear "12" en vez de saltar a la mesa 1.
const VU_TECLADO_MS = 700;

let vuActiva = false;
let vuIntervalo = null;
let vuEntregadas = [];   // comandas en 'entregado' → mesas listas para cobrar
let vuVentasHoy = null;  // solo admin (ver vuRefrescarDatos); null = no aplica
let vuTecladoBuffer = '';
let vuTecladoTimer = null;
let vuListenersPuestos = false;

function vistaUnificadaDisponible() {
    return typeof puedeVer === 'function' && puedeVer('mozo') && puedeVer('cocina');
}

function initVistaUnificada() {
    const sw = document.getElementById('vu-switch');
    if (!sw) return;

    if (!vistaUnificadaDisponible()) {
        sw.classList.add('hidden');
        return;
    }
    sw.classList.remove('hidden');

    // init() llega por dos caminos (sesión guardada o login recién hecho).
    // Sin esta guarda, un segundo paso dejaría dos listeners de teclado y un
    // intervalo huérfano consultando para siempre.
    if (!vuListenersPuestos) {
        vuListenersPuestos = true;
        document.querySelectorAll('#vu-tabs .vu-tab').forEach(btn => {
            btn.addEventListener('click', () => vuCambiarColumna(btn.dataset.col));
        });
        document.addEventListener('keydown', vuAtajosTeclado);
    }

    aplicarVistaUnificada(localStorage.getItem(VU_PREF_KEY) === '1');
}

function toggleVistaUnificada(activar) {
    aplicarVistaUnificada(typeof activar === 'boolean' ? activar : !vuActiva);
}

function aplicarVistaUnificada(activa) {
    vuActiva = !!activa && vistaUnificadaDisponible();
    localStorage.setItem(VU_PREF_KEY, vuActiva ? '1' : '0');

    // Una sola clase en el <section> gobierna todo el layout: qué se ve, qué
    // se esconde y dónde queda el botón flotante. Así el CSS no tiene que
    // adivinar el estado desde tres clases repartidas por el DOM.
    const tab = document.getElementById('mozo-tab');
    if (tab) tab.classList.toggle('vu-activa', vuActiva);

    document.querySelectorAll('#vu-switch .vu-switch-btn').forEach(b => {
        b.classList.toggle('active', (b.dataset.vista === 'unificada') === vuActiva);
        b.setAttribute('aria-pressed', String((b.dataset.vista === 'unificada') === vuActiva));
    });

    if (vuIntervalo) {
        clearInterval(vuIntervalo);
        vuIntervalo = null;
    }
    if (vuActiva) {
        vuRefrescarDatos();
        vuIntervalo = setInterval(vuRefrescarDatos, VU_INTERVALO_MS);
    }
}

function vuCambiarColumna(col) {
    const panel = document.getElementById('vu-panel');
    if (!panel) return;
    panel.dataset.col = col;
    document.querySelectorAll('#vu-tabs .vu-tab').forEach(b => {
        b.classList.toggle('active', b.dataset.col === col);
    });
}

// ============ DATOS ============

/**
 * Las comandas en cocina NO se piden acá: las trae cocina.js, que ya las
 * consulta cada 4s para su propia pestaña y las deja en `estado.comandasCocina`
 * (avisando por `onCocinaActualizada`). Pedirlas de nuevo sería el mismo dato
 * viajando dos veces por una conexión que en un restaurante suele ser el wifi
 * del local.
 */
async function vuRefrescarDatos() {
    if (!vuActiva) return;
    try {
        estado.mesas = await api.get('/mesas');
    } catch (err) {
        // Sin señal se sigue pintando con lo último conocido: una pantalla
        // desactualizada es más útil que una en blanco a media atención.
        console.warn('Vista unificada: no se pudieron refrescar las mesas', err);
    }
    if (typeof renderMesas === 'function') renderMesas();
    await vuSincronizar();
}

/**
 * Refresca solo lo propio de esta vista y repinta. Se llama por separado de
 * vuRefrescarDatos() para los momentos en que quien llama YA trajo las mesas
 * frescas (refreshMozo, después de enviar una comanda o de cobrar): volver a
 * pedirlas ahí sería una consulta al pedo por cada acción del usuario.
 */
async function vuSincronizar() {
    if (!vuActiva) return;

    try {
        vuEntregadas = await api.get('/comandas?estado=entregado');
    } catch (err) {
        console.warn('Vista unificada: no se pudo refrescar lo cobrable', err);
    }

    // El total vendido es admin-only (/caja/estado). Una cuenta
    // `mozo,jefe_cocina` también puede usar esta vista, y para ella el pie
    // simplemente no muestra ese dato — pedirlo igual sería un 403 en cada
    // vuelta del intervalo.
    if (estado.roles.includes('admin')) {
        try {
            const caja = await api.get('/caja/estado');
            vuVentasHoy = caja ? caja.ventas_hasta_ahora : null;
        } catch (_) {
            vuVentasHoy = null;
        }
    }

    renderUnificado();
}

// Hook que dispara cocina.js cuando refresca su monitor.
function onCocinaActualizada() {
    if (vuActiva) renderUnificado();
}

// ============ ESTADO DERIVADO ============

function vuMesasEnCocina() {
    return new Set((estado.comandasCocina || []).map(c => c.numero_mesa));
}

/**
 * Tres estados visuales, no dos. Una mesa `ocupada` puede estar esperando la
 * comida o esperando que le cobren, y son dos cosas muy distintas para quien
 * atiende: en la primera no hay nada que hacer todavía, en la segunda hay
 * plata sobre la mesa.
 */
function vuEstadoMesa(mesa, enCocina) {
    if (mesa.estado !== 'ocupada') return 'libre';
    return enCocina.has(mesa.numero) ? 'cocinando' : 'por-cobrar';
}

/**
 * Mesas listas para cobrar: las que tienen comandas entregadas y NINGUNA
 * todavía en cocina.
 *
 * El filtro por cocina no es cosmético. `POST /mesas/{id}/cobrar` rechaza con
 * 400 si queda alguna comanda en 'cocina' (no se cobra comida que el cliente
 * no recibió, ver CLAUDE.md). Sin este filtro, una mesa que pidió postre
 * después aparecería acá con su botón Cobrar y el botón fallaría siempre.
 */
function vuMesasPorCobrar() {
    const enCocina = vuMesasEnCocina();
    const porMesa = new Map();

    vuEntregadas.forEach(c => {
        if (enCocina.has(c.numero_mesa)) return;
        const g = porMesa.get(c.numero_mesa) || {
            numero: c.numero_mesa, total: 0, comandas: 0, desde: c.creado_en,
        };
        g.total += c.total_cuenta;
        g.comandas += 1;
        if (c.creado_en < g.desde) g.desde = c.creado_en;
        porMesa.set(c.numero_mesa, g);
    });

    // La que espera hace más rato, primero: es la que más riesgo tiene de
    // que el cliente se canse de esperar la cuenta.
    return [...porMesa.values()].sort((a, b) => (a.desde < b.desde ? -1 : 1));
}

// ============ RENDER ============

function renderUnificado() {
    if (!vuActiva) return;
    const enCocina = vuMesasEnCocina();
    const porCobrar = vuMesasPorCobrar();

    vuRenderMesas(enCocina);
    vuRenderCocina();
    vuRenderPorCobrar(porCobrar);
    vuRenderPie(enCocina, porCobrar);
}

function vuRenderMesas(enCocina) {
    const cont = document.getElementById('vu-mesas');
    if (!cont) return;

    if (!estado.mesas.length) {
        cont.innerHTML = '<p class="vu-vacio">Aún no hay mesas configuradas.</p>';
        vuBadge('mesas', 0);
        return;
    }

    let ocupadas = 0;
    cont.innerHTML = estado.mesas.map((mesa, idx) => {
        const est = vuEstadoMesa(mesa, enCocina);
        if (est !== 'libre') ocupadas++;
        const detalle = est === 'libre'
            ? `${mesa.capacidad}p`
            : formatCurrency(mesa.cuenta_actual);
        return `
            <button type="button" class="vu-mesa ${est}" data-idx="${idx}" onclick="vuAbrirMesa(${idx})">
                <span class="vu-mesa-num">${mesa.numero}</span>
                <span class="vu-mesa-detalle">${detalle}</span>
            </button>
        `;
    }).join('');

    vuBadge('mesas', ocupadas);
}

function vuRenderCocina() {
    const cont = document.getElementById('vu-cocina');
    if (!cont) return;

    const comandas = estado.comandasCocina || [];
    vuBadge('cocina', comandas.length);

    if (!comandas.length) {
        cont.innerHTML = '<p class="vu-vacio">Nada en cocina ahora mismo.</p>';
        return;
    }

    cont.innerHTML = comandas.map(c => {
        const tarde = c.minutos_transcurridos > 15;
        const platos = c.platos
            .map(p => `<li>${p.cantidad}× ${escapeHtml(p.nombre)}</li>`)
            .join('');
        return `
            <article class="vu-card ${tarde ? 'tarde' : ''}" id="vu-cocina-${c.id}">
                <header class="vu-card-top">
                    <span class="vu-card-mesa">Mesa ${c.numero_mesa}</span>
                    <span class="vu-card-tiempo ${tarde ? 'tarde' : ''}">${c.minutos_transcurridos} min</span>
                </header>
                <ul class="vu-card-platos">${platos}</ul>
                <button type="button" class="vu-btn-listo" onclick="vuMarcarListo(${c.id})">✓ Está listo</button>
            </article>
        `;
    }).join('');
}

function vuRenderPorCobrar(porCobrar) {
    const cont = document.getElementById('vu-cobro');
    if (!cont) return;

    vuBadge('cobro', porCobrar.length);

    if (!porCobrar.length) {
        cont.innerHTML = '<p class="vu-vacio">Ninguna mesa espera la cuenta.</p>';
        return;
    }

    cont.innerHTML = porCobrar.map(g => `
        <article class="vu-card cobro">
            <header class="vu-card-top">
                <span class="vu-card-mesa">Mesa ${g.numero}</span>
                <span class="vu-card-total">${formatCurrency(g.total)}</span>
            </header>
            <p class="vu-card-nota">${g.comandas} ${g.comandas === 1 ? 'pedido entregado' : 'pedidos entregados'}</p>
            <button type="button" class="vu-btn-cobrar" onclick="vuCobrarMesa(${g.numero})">Cobrar</button>
        </article>
    `).join('');
}

function vuRenderPie(enCocina, porCobrar) {
    const pie = document.getElementById('vu-pie');
    if (!pie) return;

    const totalPorCobrar = porCobrar.reduce((s, g) => s + g.total, 0);
    const hora = new Date().toLocaleTimeString('es-PE', { hour: '2-digit', minute: '2-digit' });

    const partes = [
        `<span class="vu-pie-item"><b>${enCocina.size}</b> en cocina</span>`,
        `<span class="vu-pie-item"><b>${formatCurrency(totalPorCobrar)}</b> por cobrar</span>`,
    ];
    if (vuVentasHoy !== null) {
        partes.push(`<span class="vu-pie-item vu-pie-fuerte"><b>${formatCurrency(vuVentasHoy)}</b> vendido</span>`);
    }
    partes.push(`<span class="vu-pie-item vu-pie-hora">${hora}</span>`);

    const cajaOk = estado.cajaAbierta !== false;
    partes.push(
        `<span class="vu-pie-caja ${cajaOk ? 'ok' : 'cerrada'}">${cajaOk ? 'Caja abierta' : 'Caja cerrada'}</span>`
    );

    pie.innerHTML = partes.join('');
}

function vuBadge(col, n) {
    const el = document.getElementById(`vu-badge-${col}`);
    if (!el) return;
    el.textContent = n;
    el.classList.toggle('cero', n === 0);
}

// ============ ACCIONES ============

// Se pasa el índice y no el número de mesa porque abrirMesa() necesita el
// objeto completo (id, estado, cuenta) y no solo su número.
function vuAbrirMesa(idx) {
    const mesa = estado.mesas[idx];
    if (mesa) abrirMesa(mesa);
}

async function vuMarcarListo(comandaId) {
    const card = document.getElementById(`vu-cocina-${comandaId}`);
    if (card) card.classList.add('saliendo');
    // marcarListo() (cocina.js) ya hace el PATCH, avisa y refresca las mesas;
    // duplicar esa llamada acá sería una segunda versión de la misma regla.
    await marcarListo(comandaId);
    // Se le vuelve a preguntar al servidor en vez de dar por hecho que salió
    // bien: marcarListo() atrapa sus propios errores, así que desde acá no hay
    // forma de distinguir éxito de fallo. Si falló, la tarjeta reaparece sola.
    // Además evita esperar hasta 4s (la vuelta del monitor de cocina) para ver
    // la mesa pasar a la columna de cobro, que es la acción más frecuente.
    if (typeof refreshCocina === 'function') await refreshCocina();
    await vuSincronizar();
}

function vuCobrarMesa(numeroMesa) {
    const mesa = estado.mesas.find(m => m.numero === numeroMesa);
    if (!mesa) {
        showToast(`No se encontró la mesa ${numeroMesa}`, 'warning');
        return;
    }
    // Abre la cuenta de siempre: muestra el detalle, el campo de DNI/RUC si
    // el restaurante emite boletas, y cobra con el mismo botón de siempre.
    abrirCuentaMesa(mesa);
}

// ============ TECLADO ============

function vuEsCampoDeTexto(el) {
    if (!el) return false;
    return el.tagName === 'INPUT' || el.tagName === 'TEXTAREA'
        || el.tagName === 'SELECT' || el.isContentEditable;
}

function vuAtajosTeclado(e) {
    if (e.ctrlKey || e.altKey || e.metaKey) return;
    // Escribiendo en un campo (buscando un plato, tipeando un DNI) las teclas
    // son texto, no atajos.
    if (vuEsCampoDeTexto(e.target)) return;
    if (!vuActiva) return;
    // Con un modal abierto la pantalla ya está en otra tarea; saltar a otra
    // mesa desde ahí perdería el pedido a medio armar.
    if (document.querySelector('.modal:not(.hidden)')) return;

    if (!/^[0-9]$/.test(e.key)) return;

    vuTecladoBuffer += e.key;
    clearTimeout(vuTecladoTimer);
    vuTecladoTimer = setTimeout(() => {
        const numero = parseInt(vuTecladoBuffer, 10);
        vuTecladoBuffer = '';
        const mesa = estado.mesas.find(m => m.numero === numero);
        if (!mesa) {
            showToast(`No hay mesa ${numero}`, 'warning');
            return;
        }
        abrirMesa(mesa);
    }, VU_TECLADO_MS);
}
