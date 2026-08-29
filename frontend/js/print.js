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

async function imprimirComandaCocinaYMozo(comanda) {
    try {
        const ticketCocina = _ticketHTML('COCINA', comanda, { conPrecios: false });
        const ticketMozo = _ticketHTML('COMANDA · COPIA MOZO', comanda, { conPrecios: true });

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
