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
    // Las mesas que se acaban de traer son las mismas que pinta la vista
    // unificada, así que solo le falta refrescar lo suyo (lo cobrable y los
    // totales). Sin este aviso, después de enviar una comanda o de cobrar la
    // vista quedaría mostrando el estado anterior hasta la próxima vuelta del
    // intervalo. No hace nada si la vista está apagada.
    if (typeof vuSincronizar === 'function') vuSincronizar();
}

function renderMesas() {
    const container = document.getElementById('mozo-mesas');
    container.innerHTML = '';

    if (estado.mesas.length === 0) {
        container.innerHTML = '<p class="empty-hint">Aún no hay mesas configuradas.</p>';
        return;
    }

    // Restringido a "solo cobra" cuando la cuenta tiene cajero pero NO
    // mozo/admin entre sus roles — las mesas libres no le sirven de nada,
    // así que se muestran apagadas y sin acción (evita toques accidentales
    // que confundan "cobrar" con "tomar pedido"). Una cuenta con AMBOS
    // roles (cajero + mozo) sí puede tomar pedidos nuevos — el "solo cobra"
    // es una restricción de cajero en solitario, no de tener cajero.
    const soloCobra = estado.roles.includes('cajero')
        && !estado.roles.includes('mozo')
        && !estado.roles.includes('admin');

    estado.mesas.forEach(mesa => {
        const btn = document.createElement('button');
        const deshabilitada = soloCobra && mesa.estado !== 'ocupada';
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
    const soloCobra = estado.roles.includes('cajero')
        && !estado.roles.includes('mozo')
        && !estado.roles.includes('admin');
    if (soloCobra) {
        // Solo cajero (sin mozo/admin) nunca toma pedidos, solo abre la
        // cuenta para cobrar.
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

    const data = {
        numero_mesa: mesaActual.numero,
        platos: carrito.map(item => ({ plato_id: item.platoId, cantidad: item.cantidad })),
    };

    try {
        const comanda = await api.post('/comandas', data);

        showToast('Comanda enviada a cocina', 'success');
        cerrarModal();
        await refreshMozo();
        // Solo si este rol ve Cocina — mismo criterio que la línea de
        // refreshDashboard más abajo. El backend igual lo permitiría (el
        // monitor de cocina no es admin-only), pero para un mozo puro esa
        // pestaña ni existe en el DOM visible: es una llamada de red que
        // no sirve para nada.
        if (puedeVer('cocina') && typeof refreshCocina === 'function') refreshCocina();

        // Dos papeles, uno por impresora: cocina (qué preparar) y la copia
        // del mozo (con precios, para su propio registro).
        if (typeof imprimirComandaCocinaYMozo === 'function') {
            imprimirComandaCocinaYMozo(comanda);
        }
    } catch (err) {
        if (err instanceof NetworkError) {
            // Sin señal: el pedido no se pierde. Se guarda para reenviarlo
            // solo, y la mesa se marca ocupada localmente para que el mozo
            // pueda seguir trabajando sin esperar al servidor.
            const comandaLocal = construirComandaLocal(data, carrito);
            encolarComanda(data);
            marcarMesaOcupadaLocal(mesaActual.numero, comandaLocal.total_cuenta);

            showToast('Sin conexión: pedido guardado, se enviará solo al volver la señal', 'warning');
            cerrarModal();

            if (typeof imprimirComandaCocinaYMozo === 'function') {
                imprimirComandaCocinaYMozo(comandaLocal);
            }
            return;
        }
        showToast(err.message || 'Error al enviar comanda', 'error');
    }
}

// Construye un objeto con la forma de una Comanda del backend a partir del
// carrito local — para imprimir el ticket al toque aunque todavía no haya
// respuesta del servidor (ver enviarComanda, caso sin conexión).
function construirComandaLocal(data, carritoSnapshot) {
    return {
        creado_en: new Date().toISOString(),
        numero_mesa: data.numero_mesa,
        platos: carritoSnapshot.map(item => ({
            cantidad: item.cantidad,
            nombre: item.nombre,
            precio_unitario: item.precio,
            subtotal: item.precio * item.cantidad,
        })),
        total_cuenta: carritoSnapshot.reduce((sum, item) => sum + item.precio * item.cantidad, 0),
    };
}

// Actualiza la mesa en memoria sin esperar al servidor — se corrige solo
// en el próximo refreshMozo() ni bien vuelva la señal.
function marcarMesaOcupadaLocal(numeroMesa, montoAgregado) {
    const mesa = estado.mesas.find(m => m.numero === numeroMesa);
    if (!mesa) return;
    mesa.estado = 'ocupada';
    mesa.cuenta_actual = (mesa.cuenta_actual || 0) + montoAgregado;
    renderMesas();
}

// ============ CUENTA DE MESA / COBRO ============

async function abrirCuentaMesa(mesa) {
    mesaActual = mesa;
    document.getElementById('modal-cuenta-title').textContent = `Mesa ${mesa.numero}`;
    // Solo cajero (sin mozo/admin) cobra, no toma pedidos adicionales.
    const soloCobra = estado.roles.includes('cajero')
        && !estado.roles.includes('mozo')
        && !estado.roles.includes('admin');
    document.getElementById('btn-agregar-pedido').classList.toggle('hidden', soloCobra);
    try {
        const comandas = await api.get(`/comandas?numero_mesa=${mesa.numero}`);
        const activas = comandas.filter(c => c.estado === 'cocina' || c.estado === 'entregado');
        renderCuentaMesa(activas);
        // Las pestañas de cobro viven dentro de este modal: se dejan en
        // limpio acá, al abrir la mesa, y no en un paso aparte.
        prepararCobro();
        abrirModal('modal-cuenta');
    } catch (err) {
        showToast('No se pudo cargar la cuenta de la mesa', 'error');
    }
}

function renderCuentaMesa(comandas) {
    const container = document.getElementById('cuenta-comandas');
    // Sin pedidos no hay nada que cobrar: se ocultan las pestañas enteras en
    // vez de dejarlas visibles y muertas. Antes se deshabilitaba un botón
    // único; ahora el cobro son tres caminos y esconderlos es más honesto
    // que apagarlos uno por uno.
    const cobro = document.getElementById('cobro-bloque');

    if (comandas.length === 0) {
        container.innerHTML = '<p class="empty-hint">Esta mesa no tiene pedidos activos.</p>';
        document.getElementById('cuenta-total').textContent = formatCurrency(0);
        if (cobro) cobro.classList.add('hidden');
        return;
    }
    if (cobro) cobro.classList.remove('hidden');

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

    // No se cobra comida que el cliente todavía no recibió: POST
    // /mesas/{id}/cobrar rechaza con 400 si queda algo en cocina. Se bloquea
    // acá, con el motivo a la vista, en vez de dejar tocar un botón que va a
    // fallar.
    bloquearCobroPorCocina(hayEnCocina);
}


function bloquearCobroPorCocina(hayEnCocina) {
    const aviso = document.getElementById('cobro-espera-cocina');
    if (aviso) aviso.classList.toggle('hidden', !hayEnCocina);

    document.querySelectorAll('.cobro-tabs, .cobro-tab').forEach(el => {
        el.classList.toggle('hidden', hayEnCocina);
    });
    // La pestaña activa vuelve a mostrarse sola al desbloquear: el forEach de
    // arriba las oculta todas, así que hay que repintar cuál está activa.
    if (!hayEnCocina) cambiarTabCobro(cobroTabActiva);
}

function cerrarModalCuenta() {
    document.getElementById('modal-cuenta').classList.add('hidden');
}

function agregarPedidoAMesa() {
    cerrarModalCuenta();
    abrirNuevoPedido(mesaActual);
}

/**
 * Misma regla que valida el backend (schemas.py:validar_documento_comprador):
 * vacío, 8 dígitos (DNI), u 11 dígitos con prefijo válido y dígito
 * verificador correcto (RUC). Se repite acá a
 * propósito, y NO para reemplazar la del servidor —que sigue siendo la que
 * manda— sino por CUÁNDO corre: la boleta se emite después de cobrar, así
 * que sin este chequeo previo un tipeo dejaba la venta ya cobrada con la
 * boleta rechazada, y la recuperación desde Admin la emite como Público
 * General (pierde el documento que el cliente sí había pedido).
 *
 * Devuelve null si está bien, o el motivo del rechazo.
 */
// Prefijos de RUC que SUNAT usa de verdad. Antes acá decía solo (10|20), y
// eso rechazaba a los contribuyentes con RUC 15/16/17 (personas naturales
// con asignación antigua): son el 7,4% del padrón real, y al cajero le
// aparecía un error al tipear un RUC perfectamente válido.
// Espejo de PREFIJOS_VALIDOS en backend/utils/padron.py.
const PREFIJOS_RUC = /^(10|15|16|17|20)/;
const PESOS_RUC = [5, 4, 3, 2, 7, 6, 5, 4, 3, 2];

/**
 * Dígito verificador del RUC — la misma cuenta que hace el backend.
 *
 * Se repite acá a propósito: atrapar el número mal tipeado ANTES de mandar
 * nada le ahorra al cajero el viaje de ida y vuelta, y sobre todo evita
 * emitir una boleta a un RUC inexistente con la venta ya cobrada.
 */
function digitoRucValido(ruc) {
    if (!/^\d{11}$/.test(ruc)) return false;
    let suma = 0;
    for (let i = 0; i < 10; i++) suma += parseInt(ruc[i], 10) * PESOS_RUC[i];
    let d = 11 - (suma % 11);
    if (d === 10) d = 0;
    if (d === 11) d = 1;
    return d === parseInt(ruc[10], 10);
}

function validarDocumentoComprador(documento) {
    if (!documento) return null;  // vacío = Público General, válido
    if (!/^\d+$/.test(documento)) return 'El documento debe tener solo números';
    if (documento.length === 8) return null;
    if (documento.length === 11) {
        if (!PREFIJOS_RUC.test(documento)) {
            return 'Un RUC de 11 dígitos debe empezar en 10, 15, 16, 17 o 20';
        }
        if (!digitoRucValido(documento)) {
            return 'Ese RUC no existe. Revisá que los 11 dígitos estén bien copiados';
        }
        return null;
    }
    return 'El documento debe tener 8 dígitos (DNI) u 11 dígitos (RUC)';
}

// ============ BÚSQUEDA AUTOMÁTICA DE RAZÓN SOCIAL ============

let rucTimer = null;
let docUltimoBuscado = null;

/**
 * Ejecuta el cobro y, si corresponde, emite el comprobante.
 *
 * Es el ÚNICO lugar donde se cobra: tanto el campo de documento de la
 * cuenta como el modal de pestañas terminan acá. Duplicar este flujo sería
 * duplicar la lógica de dinero, que es donde no se pueden tener dos
 * versiones que se desincronicen.
 *
 * COBRAR Y FACTURAR SIGUEN SIENDO DOS PASOS, a propósito. Fundirlos en una
 * sola llamada haría que un rechazo de SUNAT tumbara el cobro — y la plata
 * ya cambió de mano. Así, el cobro entra siempre y el comprobante queda
 * recuperable desde Admin > Boletas si falla.
 */
async function ejecutarCobro(documento, nombreManual) {
    if (!mesaActual) return;

    // Antes de cobrar, no después: corregir un tipeo con la mesa todavía
    // abierta es trivial; con la venta ya cobrada, no.
    const errorDocumento = validarDocumentoComprador(documento);
    if (errorDocumento) {
        showToast(errorDocumento, 'error');
        return;
    }

    let resultado;
    try {
        resultado = await api.post(`/mesas/${mesaActual.id}/cobrar`);
    } catch (err) {
        showToast(err.message || 'No se pudo cobrar la mesa', 'error');
        return;
    }

    // A partir de acá el dinero YA se cobró y la mesa YA se liberó — nada
    // de lo que pase con la boleta debe deshacer eso ni bloquear al mozo.
    showToast(`Cobrado ${formatCurrency(resultado.total_cobrado)} · Mesa ${resultado.mesa_numero} libre`, 'success');
    cerrarModalCuenta();
    await refreshMozo();
    // Solo si este rol ve el Dashboard: un mozo/cajero cobrando dispararía
    // si no una llamada admin-only que el backend rechaza con 403.
    if (puedeVer('dashboard') && typeof refreshDashboard === 'function') refreshDashboard();

    // Solo si este restaurante emite boletas desde RestoMind. Antes se
    // intentaba SIEMPRE, así que uno que todavía no configuró SUNAT recibía
    // un toast rojo ("la boleta NO se emitió") en CADA cobro, y se le
    // llenaba Admin > Boletas de pendientes que nadie iba a emitir nunca.
    // Se vende desde el día uno; SUNAT se configura después.
    //
    // Sin await a propósito: la boleta se genera en paralelo, de fondo,
    // exactamente igual que el ticket de cocina en print.js no bloquea la
    // comanda. generarBoletaTrasCobro nunca deja escapar una excepción
    // (su propio try/catch resuelve todos los casos con un toast), así que
    // no dejar de esperarla acá no genera una promesa rechazada sin manejar.
    if (estado.usuario && estado.usuario.cliente_usar_sunat) {
        // El nombre escrito a mano viaja junto al documento: es lo que
        // permite emitir a un RUC que el padrón local todavía no tiene.
        generarBoletaTrasCobro(resultado, documento, nombreManual);
    }
}

// Best-effort: si el Facturador local no está configurado, la carpeta no
// existe, o Facturación.pe está caído, la venta YA quedó cobrada igual —
// solo se avisa que la boleta quedó pendiente/con error, reintentable
// después desde /api/facturas/{id}/reintentar (ver backend/routes/facturas.py).
async function generarBoletaTrasCobro(resultadoCobro, documento, nombreManual) {
    try {
        const factura = await api.post('/facturas/generar', {
            comanda_ids: resultadoCobro.comanda_ids,
            documento_comprador: documento || null,
            // Solo va cuando el cajero tuvo que escribirla: es la salida para
            // un RUC recién inscrito que el padrón local todavía no tiene.
            razon_social_manual: nombreManual || null,
        });
        showToast(`${factura.numero_boleta} generada`, 'success');

        // Un DNI escrito a mano se recuerda para este restaurante: la próxima
        // visita de esa persona el nombre aparece solo, sin volver a tipearlo
        // ni consultar un servicio de pago. Sin await ni manejo de error: si
        // falla, lo único que se pierde es la comodidad de la próxima vez.
        if (nombreManual && documento && documento.length === 8) {
            api.post(`/documento/${documento}`, { nombre: nombreManual }).catch(() => {});
        }

        // Recién acá existe un numero_boleta real (se reserva adentro del
        // endpoint) — no se puede imprimir antes sin arriesgarse a mostrar
        // un número que nunca se generó. No se espera el resultado: un
        // fallo de impresión no debe generar una segunda vuelta de nada.
        if (typeof imprimirBoletaVenta === 'function') imprimirBoletaVenta(factura);
    } catch (err) {
        // Caso SUNAT >= S/ 700 sin comprador identificado. El backend lo
        // manda con un código estable justamente para poder distinguirlo de
        // cualquier otro fallo y explicarlo bien, en vez de un error rojo
        // genérico que no dice qué hacer.
        if (err.codigoNegocio === 'IDENTIFICAR_COMPRADOR') {
            mostrarAvisoIdentificarComprador(err.message);
            return;
        }

        // El restaurante dejó de emitir mientras esta sesión seguía abierta
        // con el dato viejo. No es un fallo: la venta ya quedó en caja y
        // así fue la decisión del dueño. Se refresca la sesión para que el
        // resto de la pantalla (campo de documento, etiqueta del botón)
        // deje de ofrecer algo que ya no corre, y se avisa sin alarma.
        if (err.codigoNegocio === 'FACTURACION_DESACTIVADA') {
            // El servidor es la fuente de verdad del switch, así que se
            // relee de ahí en vez de parchear la copia local: el mismo
            // camino que ya se usa al activarlo (ver auth.js).
            if (typeof refrescarSesionDesdeServidor === 'function') {
                await refrescarSesionDesdeServidor();
            }
            if (typeof actualizarEtiquetaComprobante === 'function') actualizarEtiquetaComprobante();
            showToast('Venta registrada en caja. Este restaurante no emite comprobantes.', 'info');
            return;
        }

        // Caso con salida: el RUC no está en el padrón y falta la razón
        // social. No se manda al cajero a Admin — se le pide el dato ahí
        // mismo y se reintenta, que es el único momento en que el cliente
        // sigue enfrente para dictárselo.
        const faltaRazonSocial = !nombreManual
            && typeof err.message === 'string'
            && err.message.includes('razón social');

        if (faltaRazonSocial) {
            const nombre = prompt(
                `El RUC ${documento} no figura en el padrón de SUNAT.\n\n` +
                'Escribí la razón social tal como aparece en su ficha RUC:'
            );
            if (nombre && nombre.trim()) {
                return generarBoletaTrasCobro(resultadoCobro, documento, nombre.trim());
            }
            showToast('Comprobante pendiente. Emitilo desde Admin > Boletas.', 'warning');
            return;
        }

        // IMPRESIÓN DE CONTINGENCIA.
        //
        // El backend devuelve la Factura YA GUARDADA dentro del error, así
        // que hay con qué imprimir sin volver a pedirle nada al servidor —
        // que es justo lo que puede estar caído.
        //
        // No se hace esperar al comensal: la venta está cobrada y
        // registrada en la caja. El papel dice exactamente en qué estado
        // quedó el comprobante (ver _pieSegunEstado en print.js): "en
        // proceso de transmisión" si está pendiente, o "documento interno"
        // si SUNAT lo rechazó — porque un rechazado NO es una boleta y
        // decir lo contrario dejaría al cliente sin comprobante creyendo
        // que lo tiene.
        let impreso = false;
        if (err.factura && typeof imprimirBoletaContingencia === 'function') {
            impreso = await imprimirBoletaContingencia(err.factura);
        }

        // No se promete reintento automático: la cola offline
        // (frontend/js/offline.js) cubre SOLO comandas nuevas, no facturas.
        // Decir "se genera sola al volver la señal" sería mentirle al cajero
        // sobre un comprobante que nadie va a emitir.
        const detalle = err instanceof NetworkError
            ? 'se cortó la conexión'
            : err.message;
        showToast(
            impreso
                ? `Cobro OK. Ticket impreso; el comprobante quedó pendiente en Admin > Boletas (${detalle}).`
                : `Cobro OK, pero el comprobante NO se emitió (${detalle}). Emítelo desde Admin.`,
            impreso ? 'warning' : 'error'
        );
    }
}

/**
 * Aviso de la regla de los S/ 700.
 *
 * Va como panel y no como toast a propósito: un toast se va solo a los pocos
 * segundos, y esto el cajero TIENE que leerlo y accionarlo — la venta está
 * cobrada pero el comprobante quedó pendiente. Se cierra a mano.
 *
 * Lo primero que dice es que el cobro SÍ entró: esa es la duda inmediata de
 * alguien parado en la caja con el cliente enfrente.
 */
function mostrarAvisoIdentificarComprador(mensaje) {
    const panel = document.getElementById('aviso-sunat-700');
    const texto = document.getElementById('aviso-sunat-700-texto');
    if (!panel) {
        showToast(mensaje, 'warning');
        return;
    }
    if (texto && mensaje) texto.textContent = mensaje;
    panel.classList.remove('hidden');
}

function cerrarAvisoSunat700() {
    const panel = document.getElementById('aviso-sunat-700');
    if (panel) panel.classList.add('hidden');
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


/**
 * Qué comprobante va a salir, dicho ANTES de cobrar.
 *
 * Un RUC produce FACTURA... salvo en Nuevo RUS, que tiene PROHIBIDO
 * facturar: ahí el comensal recibe boleta con su RUC como documento del
 * adquiriente (el catálogo 06 de SUNAT lo admite). El régimen viaja en la
 * sesión porque quien cobra suele ser un mozo, y /configuracion es
 * admin-only.
 */
function actualizarEtiquetaComprobante(documento) {
    const el = document.getElementById('cuenta-tipo-comprobante');
    if (!el) return;

    const puedeFacturar = !!(estado.usuario && estado.usuario.cliente_emite_facturas);

    if (documento.length === 11) {
        if (puedeFacturar) {
            el.textContent = 'Factura · F001';
            el.className = 'comprobante-chip factura';
        } else {
            el.textContent = 'Boleta · RUC del comprador';
            el.className = 'comprobante-chip ruc-en-boleta';
        }
        return;
    }
    el.textContent = documento.length === 8 ? 'Boleta · DNI' : 'Boleta · B001';
    el.className = 'comprobante-chip';
}


// ============ MODAL DE COBRO: A NOMBRE DE QUIÉN VA EL COMPROBANTE ============
//
// Tres pestañas en vez de un solo campo donde el cajero tipea y el sistema
// adivina por la cantidad de dígitos. La diferencia práctica: el cajero
// ELIGE antes de tipear, así que ve de entrada qué comprobante va a salir en
// vez de descubrirlo cuando el número ya está puesto.
//
// NO reemplaza al modal de cuenta: ahí se revisa el detalle de lo consumido,
// acá se decide el comprobante. Y NO fusiona cobrar con facturar — siguen
// siendo dos llamadas, para que un rechazo de SUNAT no tumbe un cobro que ya
// ocurrió (ver ejecutarCobro).

let cobroTabActiva = 'sin-doc';
let cobroDocTimer = null;

/**
 * Prepara las pestañas de cobro. Se llama al ABRIR la cuenta, no en un paso
 * aparte: las pestañas viven dentro de ese mismo modal.
 */
function prepararCobro() {
    limpiarModalCobro();
    cambiarTabCobro('sin-doc');
}

function limpiarModalCobro() {
    clearTimeout(cobroDocTimer);
    ['cobro-ruc', 'cobro-dni', 'cobro-ruc-nombre', 'cobro-dni-nombre'].forEach(id => {
        const el = document.getElementById(id);
        if (el) { el.value = ''; el.readOnly = false; }
    });
    ['cobro-ruc-resultado', 'cobro-dni-resultado'].forEach(id => {
        document.getElementById(id).classList.add('hidden');
    });
    pintarDocInfo('ruc', '');
    pintarDocInfo('dni', '');

    // La pestaña "Sin documento" dice cosas distintas según si el
    // restaurante emite y según el monto. Se arma acá, con los datos de la
    // mesa que se está por cobrar.
    const emite = !!(estado.usuario && estado.usuario.cliente_usar_sunat);
    const total = mesaActual ? (mesaActual.cuenta_actual || 0) : 0;
    const ayuda = document.getElementById('cobro-sin-doc-ayuda');
    const tope = document.getElementById('cobro-sin-doc-tope');

    // "Sin documento" NO es "sin comprobante": un restaurante que emite
    // igual genera boleta, a nombre de Público General. Decir "sin boleta"
    // sería sugerir que se puede vender sin comprobante, que es justo lo
    // que SUNAT no permite.
    ayuda.textContent = emite
        ? 'Se emite boleta a Público General, sin identificar al cliente.'
        : 'Este restaurante no emite comprobantes electrónicos todavía.';

    // El tope de S/ 700 lo impone SUNAT, no la app. Avisarlo ACÁ —antes de
    // cobrar— le da al cajero la chance de pedir el documento con el cliente
    // todavía enfrente; descubrirlo después deja la venta sin comprobante.
    const superaTope = emite && total >= 700;
    tope.classList.toggle('hidden', !superaTope);
    if (superaTope) {
        tope.textContent = 'Desde S/ 700 SUNAT exige identificar al cliente. '
            + 'Pedile el DNI o el RUC en las otras pestañas.';
    }
    document.getElementById('btn-cobrar-sin-doc').disabled = superaTope;
}

function cambiarTabCobro(tab) {
    cobroTabActiva = tab;
    document.querySelectorAll('.cobro-tab-btn').forEach(b => {
        b.classList.toggle('active', b.dataset.tab === tab);
    });
    document.querySelectorAll('.cobro-tab').forEach(p => {
        p.classList.toggle('hidden', p.id !== `cobro-tab-${tab}`);
    });

    const foco = { 'con-ruc': 'cobro-ruc', 'con-dni': 'cobro-dni' }[tab];
    if (foco) document.getElementById(foco).focus();
}

/**
 * Valida y consulta mientras el cajero tipea.
 *
 * Se espera a que deje de escribir (350ms) en vez de consultar por tecla:
 * corregir un dígito dispararía una consulta por cada pulsación, y esa
 * consulta tiene cuota por IP en el backend.
 */
function onCobroDocInput(event, tipo) {
    soloDigitos(event);
    const largo = tipo === 'ruc' ? 11 : 8;
    const valor = event.target.value;

    clearTimeout(cobroDocTimer);
    document.getElementById(`cobro-${tipo}-resultado`).classList.add('hidden');

    if (valor.length !== largo) {
        pintarDocInfo(tipo, '');
        return;
    }
    // Un RUC mal tipeado se atrapa acá sin gastar consulta. Un DNI no tiene
    // dígito de control, así que solo se revisa el largo.
    if (tipo === 'ruc' && !digitoRucValido(valor)) {
        pintarDocInfo(tipo, 'Revisá el número, no parece un RUC válido', 'aviso');
        return;
    }

    pintarDocInfo(tipo, 'Buscando...', 'buscando');
    cobroDocTimer = setTimeout(() => consultarDocCobro(tipo, valor), 350);
}

async function consultarDocCobro(tipo, numero) {
    let datos = null;
    let sinPadron = false;
    try {
        datos = await api.get(`/documento/${numero}`);
    } catch (err) {
        // 503 = el padrón (1,6 GB) no está instalado en este servidor. NO
        // puede frenar un cobro, pero tampoco puede fallar en silencio: sin
        // explicación, el campo de nombre aparece vacío y parece un bug.
        sinPadron = err.status === 503;
        datos = null;
    }

    // Si el cajero siguió tipeando mientras la consulta viajaba, el
    // resultado ya no corresponde a lo que hay en pantalla.
    const actual = document.getElementById(`cobro-${tipo}`);
    if (!actual || actual.value !== numero) return;

    const campoNombre = document.getElementById(`cobro-${tipo}-nombre`);
    const encontrado = !!(datos && datos.encontrado);

    if (encontrado) {
        campoNombre.value = datos.nombre;
        // De solo lectura cuando el dato es oficial (padrón) o ya guardado:
        // si se viera editable, alguien intentaría corregirlo creyendo que
        // eso cambia algo.
        campoNombre.readOnly = tipo === 'ruc';
        pintarDocInfo(tipo, datos.advertencia || 'Verificado', datos.advertencia ? 'aviso' : 'ok');
    } else {
        campoNombre.value = '';
        campoNombre.readOnly = false;
        pintarDocInfo(
            tipo,
            sinPadron
                ? 'El padrón de SUNAT no está instalado. Escribí el nombre a mano.'
                : (tipo === 'ruc'
                    ? 'No figura en el padrón. Escribí la razón social.'
                    : 'No lo tenemos registrado. Escribí el nombre.'),
            'neutro'
        );
    }

    // El comprobante que va a salir, dicho ANTES de cobrar: un RUC produce
    // factura solo si el restaurante puede emitirlas (ver el régimen en
    // actualizarEtiquetaComprobante).
    if (tipo === 'ruc') actualizarEtiquetaComprobante(numero);
    document.getElementById(`cobro-${tipo}-resultado`).classList.remove('hidden');
    if (!encontrado || tipo === 'dni') campoNombre.focus();
}

function revisarDocumento(tipo) {
    const input = document.getElementById(`cobro-${tipo}`);
    input.value = '';
    input.readOnly = false;
    input.focus();
    document.getElementById(`cobro-${tipo}-resultado`).classList.add('hidden');
    pintarDocInfo(tipo, '');
}

function pintarDocInfo(tipo, texto, clase) {
    const el = document.getElementById(`cobro-${tipo}-info`);
    if (!el) return;
    el.textContent = texto || '';
    el.className = 'doc-info' + (texto ? ` ${clase}` : '');
}

/**
 * Punto de salida de las tres pestañas: arma (documento, nombre) y delega en
 * el MISMO ejecutor que usa el campo de la cuenta. La lógica de dinero vive
 * en un solo lugar.
 */
async function cobrarDesdeModal(tab) {
    let documento = '';
    let nombre = '';

    if (tab === 'con-ruc' || tab === 'con-dni') {
        const tipo = tab === 'con-ruc' ? 'ruc' : 'dni';
        documento = document.getElementById(`cobro-${tipo}`).value.trim();
        nombre = document.getElementById(`cobro-${tipo}-nombre`).value.trim();

        if (!documento) {
            showToast(tipo === 'ruc' ? 'Falta el RUC' : 'Falta el DNI', 'warning');
            return;
        }
        // Un RUC sin razón social no se puede facturar: SUNAT la exige. Con
        // DNI el nombre es opcional — una boleta es válida sin él.
        if (tipo === 'ruc' && !nombre) {
            showToast('Falta la razón social', 'warning');
            document.getElementById('cobro-ruc-nombre').focus();
            return;
        }
    }

    await ejecutarCobro(documento, nombre);
}
