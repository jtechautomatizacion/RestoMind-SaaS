/**
 * Impresión de Cierre de Caja — plantilla visual similar a boleta electrónica.
 *
 * Diseño:
 * - Logo del restaurante (si existe)
 * - Resultado prominente (✅ CUADRA / ⚠️ REVISAR) en GRANDE
 * - Números principales (esperado vs real) en GRANDE
 * - Diferencia muy visible
 * - Detalles secundarios pequeños
 * - ID de transacción como texto (sin QR: dependía de una API externa
 *   —qrserver.com— que no siempre carga, dejando un ícono roto en el
 *   reporte impreso; el ID solo ya sirve para buscar el registro en el
 *   historial si hace falta).
 * - Respirable, no agobiante de números
 */

function generarReporteCierreCaja(cierre, negocio) {
    const {
        saldo_inicial,
        ventas_cobradas,
        gastos_efectivo,
        retiros_personales,
        saldo_esperado,
        saldo_contado,
        diferencia,
        variacion_pct,
        razon_discrepancia,
        cerrado_en,
        cerrado_por,
        fecha,
    } = cierre;

    // Determinar estado visual
    const esCuadrado = Math.abs(diferencia) < 0.01;
    const esDiscrepanciaLeve = Math.abs(diferencia) <= 5 && !esCuadrado;
    const esDiscrepanciaGrave = Math.abs(diferencia) > 5;

    let estadoEmoji, estadoTexto, claseFondo, colorTexto;
    if (esCuadrado) {
        estadoEmoji = "✅";
        estadoTexto = "CAJA CUADRA PERFECTAMENTE";
        claseFondo = "cuadrado";
        colorTexto = "#16A34A"; // Verde
    } else if (esDiscrepanciaLeve) {
        estadoEmoji = "⚠️";
        estadoTexto = "DISCREPANCIA MENOR";
        claseFondo = "discrepancia-leve";
        colorTexto = "#F59E0B"; // Naranja
    } else {
        estadoEmoji = "❌";
        estadoTexto = "DISCREPANCIA GRAVE";
        claseFondo = "discrepancia-grave";
        colorTexto = "#DC2626"; // Rojo
    }

    const fechaFormato = new Date(fecha).toLocaleDateString('es-PE', {
        weekday: 'long', year: 'numeric', month: 'long', day: 'numeric'
    });

    const horaFormato = new Date(cerrado_en).toLocaleTimeString('es-PE', {
        hour: '2-digit', minute: '2-digit'
    });

    const idTransaccion = `CIERRE-${fecha}-${Math.random().toString(36).substr(2, 9).toUpperCase()}`;

    return `<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
    @page {
        size: A4;
        margin: 12mm;
    }
    @media print {
        body { margin: 0; padding: 0; }
        .no-print { display: none; }
    }

    * {
        box-sizing: border-box;
        margin: 0;
        padding: 0;
    }

    body {
        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
        background: #f5f5f5;
        color: #333;
        line-height: 1.6;
        padding: 20px;
    }

    .container {
        background: white;
        max-width: 600px;
        margin: 0 auto;
        border-radius: 12px;
        box-shadow: 0 4px 12px rgba(0,0,0,0.1);
        overflow: hidden;
    }

    /* HEADER CON LOGO */
    .header {
        background: linear-gradient(135deg, #0E7C7B 0%, #0A4C4B 100%);
        color: white;
        padding: 20px;
        text-align: center;
    }

    .logo-restaurante {
        width: 60px;
        height: 60px;
        margin: 0 auto 12px;
        border-radius: 50%;
        background: rgba(255,255,255,0.2);
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 32px;
    }

    .nombre-restaurante {
        font-size: 22px;
        font-weight: 900;
        letter-spacing: 0.02em;
        margin-bottom: 4px;
    }

    .fecha-hora {
        font-size: 12px;
        opacity: 0.9;
    }

    /* RESULTADO GRANDE */
    .resultado {
        padding: 32px 20px;
        text-align: center;
        border-bottom: 3px solid #e5e7eb;
    }

    .resultado.cuadrado {
        background: linear-gradient(135deg, #f0fdf4 0%, #dcfce7 100%);
    }
    .resultado.discrepancia-leve {
        background: linear-gradient(135deg, #fefce8 0%, #fef3c7 100%);
    }
    .resultado.discrepancia-grave {
        background: linear-gradient(135deg, #fef2f2 0%, #fee7e7 100%);
    }

    .resultado-emoji {
        font-size: 56px;
        margin-bottom: 12px;
    }

    .resultado-texto {
        font-size: 24px;
        font-weight: 900;
        letter-spacing: 0.03em;
        margin-bottom: 8px;
        color: currentColor;
    }

    .resultado-variacion {
        font-size: 14px;
        opacity: 0.8;
    }

    /* NÚMEROS PRINCIPALES */
    .numeros-principales {
        display: grid;
        grid-template-columns: 1fr 1fr;
        gap: 20px;
        padding: 24px;
        background: #fafafa;
        border-bottom: 2px solid #e5e7eb;
    }

    .numero-card {
        text-align: center;
        padding: 16px;
        background: white;
        border-radius: 8px;
        border: 1px solid #e5e7eb;
    }

    .numero-card-label {
        font-size: 11px;
        text-transform: uppercase;
        letter-spacing: 0.04em;
        color: #6b7280;
        margin-bottom: 6px;
        font-weight: 700;
    }

    .numero-card-valor {
        font-size: 28px;
        font-weight: 900;
        color: #1a1a1a;
        font-variant-numeric: tabular-nums;
    }

    /* DIFERENCIA DESTACADA */
    .diferencia-section {
        padding: 24px;
        text-align: center;
        background: white;
        border-bottom: 2px solid #e5e7eb;
    }

    .diferencia-label {
        font-size: 12px;
        text-transform: uppercase;
        letter-spacing: 0.04em;
        color: #6b7280;
        margin-bottom: 8px;
    }

    .diferencia-valor {
        font-size: 32px;
        font-weight: 900;
        font-variant-numeric: tabular-nums;
        margin-bottom: 4px;
    }

    .diferencia-valor.positiva { color: #DC2626; }
    .diferencia-valor.neutra { color: #16A34A; }

    /* DETALLES SECUNDARIOS */
    .detalles {
        padding: 24px;
        background: #f9fafb;
    }

    .detalles-row {
        display: flex;
        justify-content: space-between;
        align-items: center;
        padding: 12px 0;
        border-bottom: 1px solid #e5e7eb;
        font-size: 14px;
    }

    .detalles-row:last-child {
        border-bottom: none;
    }

    .detalles-label {
        color: #6b7280;
        font-weight: 600;
    }

    .detalles-valor {
        font-weight: 700;
        font-variant-numeric: tabular-nums;
        color: #1a1a1a;
    }

    /* RAZÓN DE DISCREPANCIA */
    .razon-discrepancia {
        margin-top: 16px;
        padding: 12px;
        background: #fef3c7;
        border-left: 4px solid #f59e0b;
        border-radius: 4px;
    }

    .razon-discrepancia-label {
        font-size: 11px;
        text-transform: uppercase;
        letter-spacing: 0.04em;
        color: #92400e;
        margin-bottom: 4px;
    }

    .razon-discrepancia-texto {
        font-size: 13px;
        color: #78350f;
    }

    /* FIRMAS */
    .firmas {
        display: grid;
        grid-template-columns: 1fr 1fr;
        gap: 24px;
        padding: 24px;
        background: white;
        border-bottom: 2px solid #e5e7eb;
    }

    .firma-block {
        text-align: center;
    }

    .firma-linea {
        border-top: 1px solid #1a1a1a;
        height: 40px;
        margin-bottom: 4px;
    }

    .firma-nombre {
        font-size: 11px;
        color: #6b7280;
        font-weight: 600;
    }

    /* VERIFICACIÓN */
    .verificacion {
        padding: 24px;
        text-align: center;
        background: #f9fafb;
    }

    .verificacion-texto {
        font-size: 11px;
        color: #6b7280;
    }

    /* FOOTER */
    .footer {
        padding: 16px;
        text-align: center;
        font-size: 10px;
        color: #9ca3af;
        background: #f3f4f6;
    }

    /* RESPONSIVE */
    @media (max-width: 480px) {
        .numeros-principales {
            grid-template-columns: 1fr;
        }
        .firmas {
            grid-template-columns: 1fr;
        }
        .nombre-restaurante {
            font-size: 18px;
        }
        .resultado-emoji {
            font-size: 48px;
        }
        .resultado-texto {
            font-size: 20px;
        }
    }
</style>
</head>
<body>
    <div class="container">
        <!-- HEADER -->
        <div class="header">
            <div class="logo-restaurante">🍽️</div>
            <div class="nombre-restaurante">${escapeHtml(negocio?.nombre || 'Mi Restaurante')}</div>
            <div class="fecha-hora">${fechaFormato} • ${horaFormato}</div>
        </div>

        <!-- RESULTADO GRANDE -->
        <div class="resultado ${claseFondo}">
            <div class="resultado-emoji">${estadoEmoji}</div>
            <div class="resultado-texto" style="color: ${colorTexto};">${estadoTexto}</div>
            <div class="resultado-variacion">Variación: ${variacion_pct.toFixed(2)}%</div>
        </div>

        <!-- NÚMEROS PRINCIPALES -->
        <div class="numeros-principales">
            <div class="numero-card">
                <div class="numero-card-label">Esperado</div>
                <div class="numero-card-valor">${formatCurrency(saldo_esperado)}</div>
            </div>
            <div class="numero-card">
                <div class="numero-card-label">Contado</div>
                <div class="numero-card-valor">${formatCurrency(saldo_contado)}</div>
            </div>
        </div>

        <!-- DIFERENCIA DESTACADA -->
        <div class="diferencia-section">
            <div class="diferencia-label">Diferencia</div>
            <div class="diferencia-valor ${Math.abs(diferencia) < 0.01 ? 'neutra' : 'positiva'}">
                ${diferencia >= 0 ? '+' : ''}${formatCurrency(diferencia)}
            </div>
        </div>

        <!-- DETALLES SECUNDARIOS -->
        <div class="detalles">
            <div class="detalles-row">
                <span class="detalles-label">Saldo inicial</span>
                <span class="detalles-valor">${formatCurrency(saldo_inicial)}</span>
            </div>
            <div class="detalles-row">
                <span class="detalles-label">Ventas del día</span>
                <span class="detalles-valor">${formatCurrency(ventas_cobradas)}</span>
            </div>
            <div class="detalles-row">
                <span class="detalles-label">Gastos en efectivo</span>
                <span class="detalles-valor">${formatCurrency(gastos_efectivo)}</span>
            </div>
            <div class="detalles-row">
                <span class="detalles-label">Retiros personales</span>
                <span class="detalles-valor">${formatCurrency(retiros_personales)}</span>
            </div>

            ${razon_discrepancia ? `
            <div class="razon-discrepancia">
                <div class="razon-discrepancia-label">Razón de discrepancia</div>
                <div class="razon-discrepancia-texto">${escapeHtml(razon_discrepancia)}</div>
            </div>
            ` : ''}
        </div>

        <!-- FIRMAS -->
        <div class="firmas">
            <div class="firma-block">
                <div class="firma-linea"></div>
                <div class="firma-nombre">Cerrado por:<br>${escapeHtml(cerrado_por || 'N/A')}</div>
            </div>
            <div class="firma-block">
                <div class="firma-linea"></div>
                <div class="firma-nombre">Revisado por<br>(si requiere)</div>
            </div>
        </div>

        <!-- VERIFICACIÓN -->
        <div class="verificacion">
            <div class="verificacion-texto">
                Transacción: ${idTransaccion}
            </div>
        </div>

        <!-- FOOTER -->
        <div class="footer">
            RestoMind v2.5 • Cierre de Caja • ${new Date().toLocaleString('es-PE')}
        </div>
    </div>

    <!-- BOTONES DE IMPRESIÓN (Solo web, no en PDF) -->
    <div class="no-print" style="margin-top: 20px; text-align: center;">
        <button onclick="window.print()" style="
            padding: 12px 24px;
            background: #0E7C7B;
            color: white;
            border: none;
            border-radius: 8px;
            font-size: 14px;
            font-weight: 600;
            cursor: pointer;
            margin: 8px;
        ">🖨️ Imprimir</button>
        <button onclick="window.close()" style="
            padding: 12px 24px;
            background: #e5e7eb;
            color: #333;
            border: none;
            border-radius: 8px;
            font-size: 14px;
            font-weight: 600;
            cursor: pointer;
            margin: 8px;
        ">❌ Cerrar</button>
    </div>
</body>
</html>`;
}

/**
 * Abre el reporte en una pestaña nueva para imprimir/descargar como PDF.
 */
function abrirReporteCierreCaja(cierre, negocio) {
    const html = generarReporteCierreCaja(cierre, negocio);
    const ventana = window.open();
    ventana.document.write(html);
    ventana.document.close();
}
