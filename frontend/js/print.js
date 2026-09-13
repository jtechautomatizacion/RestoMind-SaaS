/**
 * Impresión de comandas.
 *
 * Al enviar un pedido a cocina se necesitan dos papeles físicos, no uno:
 * uno para cocina (qué preparar, sin precios) y otro para el mozo (su
 * propio comprobante con precios, para reclamos de mesa o cuadre de caja
 * al cerrar turno). En un restaurante real cada ticket normalmente va a
 * una impresora distinta (la de cocina suele estar en la cocina misma; la
 * del mozo, en la caja/POS), así que se imprimen uno tras otro —no en
 * paralelo— para que el diálogo de impresión del sistema permita elegir
 * una impresora diferente para cada uno.
 */

function _ticketHTML(titulo, comanda, { conPrecios }) {
    const fecha = new Date(comanda.creado_en);
    const horaStr = fecha.toLocaleTimeString('es-PE', { hour: '2-digit', minute: '2-digit' });
    const fechaStr = fecha.toLocaleDateString('es-PE');

    const filas = comanda.platos.map(p => `
        <tr>
            <td class="cant">${p.cantidad}x</td>
            <td class="nombre">${escapeHtml(p.nombre)}</td>
            ${conPrecios ? `<td class="precio">${formatCurrency(p.subtotal)}</td>` : ''}
        </tr>
    `).join('');

    return `<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<style>
    @page { size: 80mm auto; margin: 4mm; }
    * { box-sizing: border-box; }
    body { font-family: 'Courier New', Courier, monospace; margin: 0; padding: 0; color: #000; }
    .ticket-header { text-align: center; margin-bottom: 8px; }
    .ticket-header h1 { font-size: 15px; margin: 0; letter-spacing: 0.05em; }
    .ticket-mesa { font-size: 30px; font-weight: 900; margin: 6px 0; }
    .ticket-meta { font-size: 11px; text-align: center; margin-bottom: 8px; border-bottom: 1px dashed #000; padding-bottom: 6px; }
    table { width: 100%; border-collapse: collapse; font-size: 14px; }
    td { padding: 4px 0; vertical-align: top; }
    .cant { width: 34px; font-weight: 700; }
    .precio { text-align: right; white-space: nowrap; }
    .ticket-total { margin-top: 8px; border-top: 1px dashed #000; padding-top: 6px; display: flex; justify-content: space-between; font-weight: 900; font-size: 16px; }
</style>
</head>
<body>
    <div class="ticket-header">
        <h1>${titulo}</h1>
        <div class="ticket-mesa">MESA ${comanda.numero_mesa}</div>
    </div>
    <div class="ticket-meta">${fechaStr} &middot; ${horaStr}</div>
    <table>${filas}</table>
    ${conPrecios ? `<div class="ticket-total"><span>TOTAL</span><span>${formatCurrency(comanda.total_cuenta)}</span></div>` : ''}
</body>
</html>`;
}

/**
 * Pre-cuenta ("copia mozo") — formato calcado del ticket de referencia:
 * datos del negocio, PRE-CUENTA/NO FISCAL, mesa/mozo/cliente, detalle con
 * precio unitario, y al final RUC/RAZÓN SOCIAL/DIRECCIÓN en blanco para
 * que el cliente los complete a mano si va a pedir la boleta con sus
 * datos. Sin palotes — es HTML plano, la contraparte de _ticketBoletaHTML
 * (que se imprime recién al cobrar, con el número de boleta ya emitido).
 *
 * `negocio` sale de estado.usuario (ver frontend/js/auth.js), completado
 * en el login desde Cliente — no pide nada al backend en el momento de
 * imprimir.
 */
function _ticketPrecuentaHTML(comanda, negocio, mozoNombre) {
    const fecha = new Date(comanda.creado_en);
    const fechaHoraStr = fecha.toLocaleString('es-PE', {
        day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit', second: '2-digit',
    });

    const filas = comanda.platos.map(p => `
        <tr>
            <td class="nombre">${escapeHtml(p.nombre)}</td>
            <td class="cant">${p.cantidad}</td>
            <td class="precio">${p.precio_unitario.toFixed(2)}</td>
            <td class="precio">${p.subtotal.toFixed(2)}</td>
        </tr>
    `).join('');

    // razon_social/direccion son opcionales (el dueño del sistema todavía
    // puede no haberlos cargado) — se omite la línea entera en vez de
    // imprimir "null" o un renglón vacío feo.
    const lineaTitular = negocio.razon_social ? `<div>${escapeHtml(negocio.razon_social)}</div>` : '';
    const lineaDireccion = negocio.direccion ? `<div>${escapeHtml(negocio.direccion)}</div>` : '';
    const lineaRuc = negocio.ruc ? `<div>RUC: ${escapeHtml(negocio.ruc)}</div>` : '';
    const lineaEmail = negocio.email ? `<div>Email: ${escapeHtml(negocio.email)}</div>` : '';

    return `<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<style>
    @page { size: 80mm auto; margin: 4mm; }
    * { box-sizing: border-box; }
    body { font-family: 'Courier New', Courier, monospace; margin: 0; padding: 0; color: #000; font-size: 12px; }
    .centro { text-align: center; }
    .linea { border-top: 1px dashed #000; margin: 6px 0; }
    .datos-negocio div { margin: 1px 0; }
    .datos-negocio .comercial { font-weight: 700; }
    .campos div { margin: 1px 0; }
    table { width: 100%; border-collapse: collapse; font-size: 11.5px; margin-top: 4px; }
    th { text-align: left; font-size: 10.5px; border-bottom: 1px solid #000; padding-bottom: 3px; }
    th.num, td.cant, td.precio { text-align: right; }
    td { padding: 3px 0; vertical-align: top; }
    .totales { margin-top: 4px; }
    .totales div { display: flex; justify-content: space-between; }
    .llenar { margin-top: 14px; font-size: 11px; }
    .llenar div { margin: 10px 0 0; border-bottom: 1px dotted #000; padding-bottom: 1px; }
    .gracias { margin-top: 14px; }
</style>
</head>
<body>
    <div class="centro datos-negocio">
        ${lineaTitular}
        <div class="comercial">${escapeHtml(negocio.nombre)}</div>
        ${lineaDireccion}
        ${lineaRuc}
        ${lineaEmail}
        <div>Comanda Nº ${comanda.id ?? 'pendiente'}</div>
        <div><strong>PRE-CUENTA</strong></div>
        <div>NO FISCAL / NO FISCAL</div>
    </div>
    <div class="campos">
        <div>MOZO: ${escapeHtml(mozoNombre || '-')}</div>
        <div>MESA: ${comanda.numero_mesa}</div>
        <div>CLIENTE: Publico General</div>
        <div>DOC: -</div>
    </div>
    <div class="linea"></div>
    <div class="centro">${fechaHoraStr}</div>
    <div class="linea"></div>
    <table>
        <thead><tr><th>Articulo</th><th class="num">Cant</th><th class="num">P.U.</th><th class="num">Importe</th></tr></thead>
        <tbody>${filas}</tbody>
    </table>
    <div class="totales">
        <div><span>Total Consumo:</span><span>S/ ${comanda.total_cuenta.toFixed(2)}</span></div>
        <div><span>Total a pagar:</span><span>S/ ${comanda.total_cuenta.toFixed(2)}</span></div>
    </div>
    <div class="llenar">
        <div>RUC:</div>
        <div>RAZON SOCIAL:</div>
        <div>DIRECCION:</div>
    </div>
    <div class="centro gracias">GRACIAS</div>
</body>
</html>`;
}

function _imprimirHTML(html) {
    return new Promise(resolve => {
        const iframe = document.createElement('iframe');
        iframe.style.cssText = 'position:fixed;right:0;bottom:0;width:0;height:0;border:0;';
        document.body.appendChild(iframe);

        const terminar = () => {
            if (document.body.contains(iframe)) document.body.removeChild(iframe);
            resolve();
        };

        // Si el usuario cancela el diálogo, algunos navegadores no disparan
        // onafterprint nunca: sin este límite el iframe quedaría pegado en
        // el DOM para siempre.
        const limite = setTimeout(terminar, 15000);

        const doc = iframe.contentWindow.document;
        doc.open();
        doc.write(html);
        doc.close();

        iframe.contentWindow.onafterprint = () => {
            clearTimeout(limite);
            terminar();
        };

        iframe.contentWindow.focus();
        iframe.contentWindow.print();
    });
}

/**
 * Boleta de venta (al cobrar) — texto plano/HTML legible para el cliente,
 * SIN palotes. Los palotes (|) son un formato interno aparte, solo para
 * el XML UBL que se firma y se envía a SUNAT — nunca llegan a este
 * archivo ni a papel.
 *
 * Usa exactamente los mismos fecha_emision_local/hora_emision_local que
 * quedaron congelados en la Factura, no `new Date()` — así el papel que recibe
 * el cliente coincide con el archivo que procesa el Facturador.
 *
 * Campos que el modelo de referencia trae y que a propósito NO están acá:
 *  - Nombre real del cliente por DNI/RUC: implicaría consultar RENIEC/SUNAT
 *    en el momento, justo lo que la regla de negocio evita (ver
 *    backend/routes/facturas.py:_resolver_comprador) — se imprime "-".
 *  - "Son: ... con 00/100 Soles" (monto en letras): conversor número→texto
 *    en español no implementado todavía.
 *  - Link de verificación del comprobante: pertenece a otro proveedor;
 *    no hay uno propio para inventar acá.
 */
function _ticketBoletaHTML(factura, cajeroNombre, contingencia) {
    const filas = factura.detalles.map(item => `
        <tr>
            <td class="nombre">${escapeHtml(item.descripcion)}</td>
            <td class="cant">${item.cantidad}</td>
            <td class="precio">${item.precio_unitario.toFixed(2)}</td>
            <td class="precio">${item.subtotal.toFixed(2)}</td>
        </tr>
    `).join('');

    const tieneDocumento = factura.tipo_documento_comprador !== '0';
    const etiquetaDoc = factura.tipo_documento_comprador === '6' ? 'RUC' : 'DNI';
    // Sin nombre real (ver nota arriba): "-" cuando hay documento, igual que
    // queda guardado en Factura.nombre_comprador.
    const lineaCliente = tieneDocumento
        ? `<div>CLIENTE: -</div><div>${etiquetaDoc}: ${escapeHtml(factura.numero_documento_comprador)}</div>`
        : `<div>CLIENTE: Publico General</div>`;

    // Mismo encabezado que la pre-cuenta (titular / comercial / dirección) —
    // acá sale del backend (Factura sabe leer Cliente en el momento exacto
    // en que se emitió), no de estado.usuario cacheado en el login.
    const lineaTitular = factura.razon_social_emisor && factura.razon_social_emisor !== factura.nombre_emisor
        ? `<div>${escapeHtml(factura.razon_social_emisor)}</div>`
        : '';
    const lineaDireccionEmisor = factura.direccion_emisor ? `<div>${escapeHtml(factura.direccion_emisor)}</div>` : '';
    const lineaEmailEmisor = factura.email_emisor ? `<div>Email: ${escapeHtml(factura.email_emisor)}</div>` : '';

    return `<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<style>
    @page { size: 80mm auto; margin: 4mm; }
    * { box-sizing: border-box; }
    body { font-family: 'Courier New', Courier, monospace; margin: 0; padding: 0; color: #000; font-size: 12px; }
    .centro { text-align: center; }
    .linea { border-top: 1px dashed #000; margin: 6px 0; }
    .datos-negocio div { margin: 1px 0; }
    .datos-negocio .comercial { font-weight: 700; }
    .campos div { margin: 1px 0; }
    table { width: 100%; border-collapse: collapse; font-size: 11.5px; margin-top: 4px; }
    th { text-align: left; font-size: 10.5px; border-bottom: 1px solid #000; padding-bottom: 3px; }
    th.num, td.cant, td.precio { text-align: right; }
    td { padding: 3px 0; vertical-align: top; }
    .totales { margin-top: 4px; }
    .totales div { display: flex; justify-content: space-between; }
    .totales .total { font-weight: 900; }
    .footer { margin-top: 14px; font-size: 10.5px; text-align: center; }
    .footer div { margin: 2px 0; }
</style>
</head>
<body>
    <div class="centro datos-negocio">
        ${lineaTitular}
        <div class="comercial">${escapeHtml(factura.nombre_emisor)}</div>
        ${lineaDireccionEmisor}
        <div>RUC: ${escapeHtml(factura.ruc_emisor)}</div>
        ${lineaEmailEmisor}
        <div><strong>BOLETA DE VENTA ELECTRONICA</strong></div>
        <div>Numero: ${factura.numero_boleta}</div>
    </div>
    <div class="campos">
        <div>CAJERO: ${escapeHtml(cajeroNombre || '-')}</div>
        <div>MESA: ${factura.numero_mesa}</div>
        ${lineaCliente}
    </div>
    <div class="linea"></div>
    <div class="centro">${factura.fecha_emision_local} ${factura.hora_emision_local}</div>
    <div class="linea"></div>
    <table>
        <thead><tr><th>Articulo</th><th class="num">Cant</th><th class="num">P.U.</th><th class="num">Importe</th></tr></thead>
        <tbody>${filas}</tbody>
    </table>
    <div class="totales">
        <div><span>Sub-Total:</span><span>S/ ${factura.subtotal.toFixed(2)}</span></div>
        <div><span>IGV (18%):</span><span>S/ ${factura.igv.toFixed(2)}</span></div>
        <div class="total"><span>Total Venta:</span><span>S/ ${factura.total.toFixed(2)}</span></div>
    </div>
    <div class="footer">
        ${_pieSegunEstado(factura, contingencia)}
        <div>GRACIAS POR SU COMPRA Y PREFERENCIA</div>
        <div>NO SE ACEPTAN CAMBIOS NI DEVOLUCIONES</div>
    </div>
</body>
</html>`;
}

/**
 * El pie del tique dice LA VERDAD sobre el estado del comprobante.
 *
 * Son tres situaciones distintas y no se pueden imprimir igual:
 *
 *   1. ACEPTADO por SUNAT  -> es la representación impresa de una boleta.
 *   2. PENDIENTE de envío  -> el comprobante es válido, solo no llegó
 *      todavía (SUNAT caída, sin red). "En proceso de transmisión" es
 *      cierto, y esta impresión de contingencia es práctica estándar.
 *   3. RECHAZADO por SUNAT -> el comprobante NO EXISTE para SUNAT. Decirle
 *      al comensal "en proceso de transmisión" sería falso: no está en
 *      transmisión, fue rechazado y hay que corregirlo y reemitirlo.
 *      Entregarle un papel que se presenta como boleta cuando no lo es lo
 *      deja sin comprobante y creyendo que lo tiene.
 *
 * Por eso el caso 3 se imprime como comprobante INTERNO, no como boleta.
 * El comensal se lleva el detalle de lo que consumió y pagó — que es lo que
 * necesita para irse — sin que el papel afirme algo que no es cierto.
 */
function _pieSegunEstado(factura, contingencia) {
    if (!contingencia) {
        return '<div>Representación impresa de la boleta de venta electrónica</div>';
    }
    if (factura.estado === 'error') {
        return `
        <div style="font-weight:700">DOCUMENTO INTERNO - NO ES COMPROBANTE DE PAGO</div>
        <div>SUNAT observó el comprobante. Será corregido y reemitido.</div>
        <div>Consulte su boleta con el negocio.</div>`;
    }
    return `
        <div style="font-weight:700">Representación impresa de contingencia local</div>
        <div>Comprobante en proceso de transmisión a SUNAT</div>`;
}


/**
 * Imprime AL TOQUE aunque el comprobante no haya llegado a SUNAT.
 *
 * El comensal no tiene por qué esperar a que se resuelva un problema del
 * servidor o de SUNAT: la venta ya está cobrada y registrada en la caja.
 * Los datos salen de la Factura que el backend YA guardó y devolvió dentro
 * del error — no se le vuelve a pedir nada al servidor, que es justo lo que
 * puede estar caído.
 */
async function imprimirBoletaContingencia(factura) {
    if (!factura) return false;
    try {
        await _imprimirHTML(_ticketBoletaHTML(factura, estado.usuario?.nombre, true));
        return true;
    } catch (err) {
        console.error('Error al imprimir el comprobante de contingencia:', err);
        return false;
    }
}


async function imprimirBoletaVenta(factura) {
    try {
        // Quien cobra, no quien tomó el pedido — ya se identificó a ese
        // último en la pre-cuenta (MOZO) impresa al enviar la comanda.
        await _imprimirHTML(_ticketBoletaHTML(factura, estado.usuario?.nombre));
    } catch (err) {
        // La venta y la boleta YA se generaron en el backend — un fallo acá
        // es solo de impresión, no de la operación en sí.
        console.error('Error al imprimir boleta:', err);
        showToast('Boleta generada, pero no se pudo imprimir', 'warning');
    }
}

async function imprimirComandaCocinaYMozo(comanda) {
    try {
        const negocio = {
            nombre: estado.usuario?.cliente_nombre || 'RestoMind',
            razon_social: estado.usuario?.cliente_razon_social || null,
            direccion: estado.usuario?.cliente_direccion || null,
            ruc: estado.usuario?.cliente_ruc || null,
            email: estado.usuario?.cliente_email || null,
        };

        const ticketCocina = _ticketHTML('COCINA', comanda, { conPrecios: false });
        const ticketMozo = _ticketPrecuentaHTML(comanda, negocio, estado.usuario?.nombre);

        // Secuencial: dos print() al mismo tiempo se pisan entre sí, y en la
        // práctica cada uno necesita que el mozo elija una impresora distinta.
        await _imprimirHTML(ticketCocina);
        await _imprimirHTML(ticketMozo);
    } catch (err) {
        // Un fallo de impresión (sin impresora configurada, navegador que
        // bloquea el diálogo, etc.) no debe deshacer la comanda: el pedido
        // ya se guardó en el servidor y cocina ya lo puede ver en pantalla.
        console.error('Error al imprimir comanda:', err);
        showToast('Comanda guardada, pero no se pudo imprimir', 'warning');
    }
}
