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
        <div class="ticket-mesa">${comanda.numero_mesa ? `MESA ${comanda.numero_mesa}` : `PARA LLEVAR N${String.fromCharCode(176)} ${comanda.id || ''}`}</div>
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
        <div>${rotuloPedido(comanda)}</div>
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

/**
 * HOJA DE PRE-VENTA — el único papel del modo sin SUNAT.
 *
 * En ese modo no hay comprobante electrónico, así que el flujo real del
 * local es otro: esta hoja se le entrega AL COMENSAL, él la lleva a la
 * caja, y el cajero cobra contra ella. Por eso acá manda el TOTAL: es el
 * número que dos personas distintas van a leer y comparar en un mostrador,
 * a veces de pie y con poca luz. Va en cuerpo grande y con su propio
 * recuadro, no perdido al final de una columna de importes.
 *
 * Es UNA sola impresión, a diferencia del modo con SUNAT (que imprime el
 * papel de cocina y la pre-cuenta por separado). Un restaurante que
 * trabaja sin facturación electrónica suele ser el dueño solo o con una
 * persona: ahí el pedido se ve en la pantalla de Cocina, y el segundo
 * papel era papel tirado.
 *
 * Lo que NO dice, y es deliberado: en ninguna parte se parece a una boleta.
 * "PRE-VENTA", "NO ES COMPROBANTE DE PAGO" y la instrucción de llevarla a
 * caja están puestas para que nadie —ni el comensal ni un fiscalizador—
 * pueda confundirla con un comprobante. Entregar algo con aspecto de
 * boleta sin serlo es un problema mucho más caro que imprimir de más.
 */
/**
 * Cómo se identifica un pedido en el papel.
 *
 * `numero_mesa` vale 0 en un pedido para llevar, así que sin esto los tres
 * tickets imprimirían "MESA: 0" — un número de mesa que no existe, que manda
 * a buscar una mesa por todo el local. Para llevar se identifica por su
 * número de pedido, que es lo que se canta en el mostrador.
 */
function rotuloPedido(comanda) {
    return comanda && comanda.numero_mesa
        ? `MESA: ${comanda.numero_mesa}`
        : `PARA LLEVAR  N${String.fromCharCode(176)} ${(comanda && comanda.id) || ''}`.trim();
}

function _ticketPreventaHTML(comanda, negocio, atendidoPor) {
    const fecha = new Date(comanda.creado_en || Date.now());
    const fechaHoraStr = fecha.toLocaleString('es-PE', {
        day: '2-digit', month: '2-digit', year: 'numeric',
        hour: '2-digit', minute: '2-digit',
    });

    const filas = comanda.platos.map(p => `
        <tr>
            <td class="nombre">${escapeHtml(p.nombre)}</td>
            <td class="cant">${p.cantidad}</td>
            <td class="precio">${p.subtotal.toFixed(2)}</td>
        </tr>
    `).join('');

    // La pre-venta se entrega EN MANO a alguien que ya está en el local, y
    // el papel térmico se paga por metro. Dirección y correo no le sirven a
    // nadie en ese momento —y de paso la acercan al aspecto de un
    // comprobante, que es justo lo que este ticket NO debe parecer— así que
    // no se imprimen. El RUC sí queda: identifica al negocio en una hoja que
    // el comensal puede llevarse.
    // La RAZON SOCIAL no se imprime. En un RUC de persona natural (prefijo
    // 10) es el nombre y apellido del titular — en esta hoja salia
    // "CONSUELO SUSY BALBIN LEIVA" arriba de todo, que no le dice nada al
    // comensal y expone el nombre de una persona en un papel que se entrega
    // en mano y despues se tira. El negocio ya queda identificado por su
    // nombre comercial y por el RUC, que es el dato que sirve si alguien
    // tiene que reclamar.
    const lineaRuc = negocio.ruc ? `<div>RUC: ${escapeHtml(negocio.ruc)}</div>` : '';

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
    .datos-negocio .comercial { font-weight: 700; font-size: 14px; }
    .tipo { margin-top: 6px; font-weight: 700; letter-spacing: 1px; }
    .aviso { font-size: 10px; }
    .campos { display: flex; justify-content: space-between; font-size: 11.5px; }
    table { width: 100%; border-collapse: collapse; font-size: 11.5px; margin-top: 4px; }
    th { text-align: left; font-size: 10.5px; border-bottom: 1px solid #000; padding-bottom: 3px; }
    th.num, td.cant, td.precio { text-align: right; }
    td { padding: 3px 0; vertical-align: top; }

    /* El total: lo único que se lee de lejos en este papel. */
    .total-caja {
        margin-top: 10px;
        border: 3px solid #000;
        padding: 8px 6px 10px;
        text-align: center;
    }
    .total-caja .rotulo { font-size: 11px; font-weight: 700; letter-spacing: 1px; }
    .total-caja .monto { font-size: 30px; font-weight: 900; line-height: 1.1; margin-top: 2px; }

    .instruccion {
        margin-top: 10px;
        text-align: center;
        font-size: 11.5px;
        font-weight: 700;
        border: 1px dashed #000;
        padding: 6px 4px;
    }
    .pie { margin-top: 12px; text-align: center; font-size: 10px; }
</style>
</head>
<body>
    <div class="centro datos-negocio">
        <div class="comercial">${escapeHtml(negocio.nombre)}</div>
        ${lineaRuc}
        <div class="tipo">PRE-VENTA</div>
        <div class="aviso">NO ES COMPROBANTE DE PAGO</div>
    </div>
    <div class="linea"></div>
    <div class="campos">
        <span>${rotuloPedido(comanda)}</span>
        <span>N&ordm; ${comanda.id ?? '-'}</span>
    </div>
    <div class="campos">
        <span>${fechaHoraStr}</span>
        <span>${escapeHtml(atendidoPor || '-')}</span>
    </div>
    <div class="linea"></div>
    <table>
        <thead><tr><th>Articulo</th><th class="num">Cant</th><th class="num">Importe</th></tr></thead>
        <tbody>${filas}</tbody>
    </table>
    <div class="total-caja">
        <div class="rotulo">TOTAL A PAGAR</div>
        <div class="monto">S/ ${comanda.total_cuenta.toFixed(2)}</div>
    </div>
    <div class="instruccion">ENTREGUE ESTA HOJA EN CAJA</div>
    <div class="pie">GRACIAS POR SU PREFERENCIA</div>
</body>
</html>`;
}

/**
 * Único punto de salida de TODOS los tickets de la app.
 *
 * Intenta primero la térmica por Bluetooth y, si no está disponible o
 * falla, cae al diálogo del navegador de siempre. El orden importa: dentro
 * del APK `window.print()` no hace nada —no existe ese diálogo en un
 * WebView— así que si la térmica no responde, el ticket simplemente no
 * sale. Por eso la ruta térmica avisa por toast cuando no puede, en vez de
 * fallar callada.
 */
async function _imprimirHTML(html) {
    if (window.ImpresoraTermica && window.ImpresoraTermica.disponible()) {
        const salio = await window.ImpresoraTermica.imprimirHTML(html);
        if (salio) return;
    }
    return _imprimirEnNavegador(html);
}

function _imprimirEnNavegador(html) {
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
 *  - Nombre real del titular de un DNI: RENIEC no es una fuente disponible
 *    acá, así que ahí sí se imprime "-". Para un RUC el nombre SÍ sale
 *    (razón social del padrón, resuelta en el backend al emitir).
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
    // El nombre viene del BACKEND (Factura.nombre_comprador: razón social
    // del padrón para un RUC, o lo que el cajero escribió a mano), nunca se
    // arma acá — el papel tiene que decir lo mismo que el XML que se le
    // mandó a SUNAT. "-" es el valor real cuando no se pudo conseguir
    // (un DNI, o un RUC que el padrón no tiene).
    const nombreComprador = (factura.nombre_comprador || '').trim();
    const lineaCliente = tieneDocumento
        ? `<div>CLIENTE: ${escapeHtml(nombreComprador || '-')}</div><div>${etiquetaDoc}: ${escapeHtml(factura.numero_documento_comprador)}</div>`
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
        <div>CAJERO: ${escapeHtml(factura.cajero_nombre || cajeroNombre || '-')}</div>
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

/**
 * Qué se imprime al mandar una comanda. Depende del MODO del restaurante.
 *
 *   CON SUNAT   -> dos papeles, uno por impresora: cocina (qué preparar,
 *                  sin precios) y la pre-cuenta con precios. Al cobrar se
 *                  suma la boleta electrónica. Este camino NO se toca.
 *
 *   SIN SUNAT   -> UNA hoja: la pre-venta para el comensal, con el total
 *                  en grande (ver _ticketPreventaHTML). Él la lleva a caja
 *                  y el cajero cobra contra ella, sin comprobante. El
 *                  pedido igual le llega a cocina por pantalla.
 *
 * El modo sale de `cliente_usar_sunat` en la sesión — el mismo dato que ya
 * decide si al cobrar se emite boleta y si se piden DNI/RUC (ver mozo.js).
 * Una sola fuente de verdad para las tres decisiones.
 */
async function imprimirComandaNueva(comanda) {
    try {
        const negocio = {
            nombre: estado.usuario?.cliente_nombre || 'RestoMind',
            razon_social: estado.usuario?.cliente_razon_social || null,
            direccion: estado.usuario?.cliente_direccion || null,
            ruc: estado.usuario?.cliente_ruc || null,
            email: estado.usuario?.cliente_email || null,
        };
        const quien = estado.usuario?.nombre;

        if (!estado.usuario?.cliente_usar_sunat) {
            await _imprimirHTML(_ticketPreventaHTML(comanda, negocio, quien));
            return;
        }

        const ticketCocina = _ticketHTML('COCINA', comanda, { conPrecios: false });
        const ticketMozo = _ticketPrecuentaHTML(comanda, negocio, quien);

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
