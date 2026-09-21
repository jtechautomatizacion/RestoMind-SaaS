/**
 * CU-05: Dashboard Financiero
 * "Cómo viaja mi dinero": ventas vs gastos, ganancia y platos top.
 */

let dashboardPeriodo = 7;
let dashboardDesde = null;
let dashboardHasta = null;

function initDashboard() {
    const hoy = new Date();
    const desde = new Date(hoy);
    desde.setDate(desde.getDate() - 6);  // 7 días = hoy - 6 a hoy (7 fechas exactas)

    document.getElementById('dashboard-desde').value = formatDateInput(desde);
    document.getElementById('dashboard-hasta').value = formatDateInput(hoy);

    dashboardPeriodo = 7;
    document.querySelector('[data-dias="7"]').classList.add('active');

    document.getElementById('btn-aplicar-filtro').addEventListener('click', aplicarFiltroFechas);

    document.querySelectorAll('.periodo-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            document.querySelectorAll('.periodo-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            const dias = parseInt(btn.dataset.dias, 10);
            dashboardPeriodo = dias;
            dashboardDesde = null;
            dashboardHasta = null;

            const hoy = new Date();
            const desde = new Date(hoy);
            desde.setDate(desde.getDate() - (dias - 1));  // N días exactos = hoy - (N-1) a hoy
            document.getElementById('dashboard-desde').value = formatDateInput(desde);
            document.getElementById('dashboard-hasta').value = formatDateInput(hoy);

            refreshDashboard();
        });
    });
    refreshDashboard();
}

function aplicarFiltroFechas() {
    const desde = document.getElementById('dashboard-desde').value;
    const hasta = document.getElementById('dashboard-hasta').value;

    if (!desde || !hasta) {
        showToast('Selecciona ambas fechas', 'warning');
        return;
    }

    if (desde > hasta) {
        showToast('La fecha inicial no puede ser mayor a la final', 'warning');
        return;
    }

    // Mismo tope que el backend (MAX_DIAS_RANGO en routes/dashboard.py). Se
    // repite acá a propósito: el servidor es el que MANDA —sigue rechazando
    // igual si le llega de otro lado— pero avisar desde el teléfono evita
    // esperar un viaje de ida y vuelta para enterarse. Un rango de años
    // tampoco es un capricho de validación: son megabytes de respuesta y
    // segundos de un servidor que atiende a todo el restaurante.
    const MAX_DIAS = 366;
    const dias = Math.round((new Date(hasta) - new Date(desde)) / 86400000) + 1;
    if (dias > MAX_DIAS) {
        showToast(`El rango no puede superar ${MAX_DIAS} días (elegiste ${dias})`, 'warning');
        return;
    }

    dashboardDesde = desde;
    dashboardHasta = hasta;
    dashboardPeriodo = null;

    document.querySelectorAll('.periodo-btn').forEach(b => b.classList.remove('active'));
    refreshDashboard();
}

async function refreshDashboard() {
    try {
        let url = '/dashboard/resumen';
        if (dashboardDesde && dashboardHasta) {
            url += `?desde=${dashboardDesde}&hasta=${dashboardHasta}`;
        } else {
            url += `?dias=${dashboardPeriodo}`;
        }

        const data = await api.get(url);

        actualizarRangoLabel();
        renderStats(data.serie);
        renderBarChart(document.getElementById('chart-ventas-gastos'), data.serie);
        renderTablaDiaria(document.getElementById('dashboard-tabla-diaria'), data.serie);
        renderTopPlatos(document.getElementById('top-platos-list'), data.top_platos);
        renderTopGastos(document.getElementById('top-gastos-list'), data.top_gastos);
        renderVentasPorTipo(document.getElementById('ventas-por-tipo'), data.por_tipo_pedido);
        // Mismo componente de barras: son dos listas ordenadas con una
        // magnitud, y el dueño ya sabe leer ese formato.
        renderVentasPorTipo(
            document.getElementById('ventas-por-metodo'),
            data.por_metodo_pago,
            ETIQUETAS_METODO_PAGO
        );
    } catch (err) {
        console.error('Error cargando dashboard:', err);
        showToast('Error al cargar el dashboard', 'error');
    }
}

function actualizarRangoLabel() {
    const label = document.getElementById('dashboard-rango-label');
    if (dashboardDesde && dashboardHasta) {
        label.textContent = `${formatDate(dashboardDesde)} - ${formatDate(dashboardHasta)}`;
    } else {
        label.textContent = `Últimos ${dashboardPeriodo} días`;
    }
}

function renderStats(serie) {
    const container = document.getElementById('dashboard-stats');
    container.innerHTML = '';

    const totalVentas = serie.reduce((sum, d) => sum + d.ventas, 0);
    const totalGastos = serie.reduce((sum, d) => sum + d.gastos, 0);
    const totalGanancia = totalVentas - totalGastos;

    container.appendChild(buildStatTile('Ventas', totalVentas, null, 'money'));
    container.appendChild(buildStatTile('Gastos', totalGastos, null, 'expense'));
    container.appendChild(buildStatTile('Ganancia', totalGanancia, null, 'profit'));
}

function buildStatTile(label, valor, valorAnterior, tipo) {
    const div = document.createElement('div');
    div.className = 'stat-tile';

    let deltaHtml = '';
    if (valorAnterior !== null && valorAnterior !== 0) {
        const delta = ((valor - valorAnterior) / Math.abs(valorAnterior)) * 100;
        const signo = delta >= 0 ? '+' : '';
        const clase = delta >= 0 ? 'up' : 'down';
        deltaHtml = `<div class="delta ${clase}">${signo}${delta.toFixed(0)}%</div>`;
    }

    div.innerHTML = `
        <div class="label">${label}</div>
        <div class="value ${tipo}">${formatCurrency(valor)}</div>
        ${deltaHtml}
    `;
    return div;
}

// Etiqueta de barra: sin símbolo de moneda (no entra a este tamaño de
// fuente), y en 'k' desde 1000 para no desbordar el ancho de la barra.
// IMPORTANTE: nunca redondear con Math.round() acá — un monto como 122.50
// se mostraba como "123", una cifra que no coincide con NINGÚN número real
// (ni el total exacto ni la tabla de abajo, que sí usa 2 decimales). Se
// muestra el monto exacto, recortando ".00" solo cuando no hay céntimos.
function formatCompacto(num) {
    if (num >= 1000) return `${(num / 1000).toFixed(1).replace('.0', '')}k`;
    const conDecimales = num.toFixed(2);
    return conDecimales.endsWith('.00') ? conDecimales.slice(0, -3) : conDecimales;
}

function renderBarChart(container, serie) {
    if (!serie || serie.length === 0) {
        container.innerHTML = '<p class="empty-hint">Sin datos para mostrar.</p>';
        return;
    }

    const maxValor = Math.max(...serie.map(d => Math.max(d.ventas, d.gastos))) || 100;
    const alto = 200;
    const ancho = serie.length > 0 ? Math.max(300, serie.length * 45) : 300;
    const padding = 40;

    let svg = `<svg viewBox="0 0 ${ancho} ${alto}" style="width:100%;height:auto;overflow-x:auto;display:block;">`;

    const step = (ancho - padding * 2) / Math.max(serie.length - 1, 1);

    const diasSemana = ['Dom', 'Lun', 'Mar', 'Mié', 'Jue', 'Vie', 'Sáb'];

    serie.forEach((d, i) => {
        const x = padding + i * step;
        // Interpretar la fecha en zona horaria LOCAL del navegador, no UTC
        const fecha = new Date(d.fecha + 'T00:00:00');
        const diaSemana = diasSemana[fecha.getDay()];

        const alturaVentas = (d.ventas / maxValor) * (alto - padding - 20);
        const alturaGastos = (d.gastos / maxValor) * (alto - padding - 20);

        const baseY = alto - 20;

        // Solo el número total de cada barra, sin "S/" ni decimales: a este
        // tamaño de fuente el símbolo de moneda no cabe sin encimarse.
        // Mismos colores que los stat-tiles de arriba (Ventas=--money,
        // Gastos=--danger): antes el gráfico usaba naranja/gris propios,
        // sin relación con el resto del dashboard — dos lenguajes de color
        // distintos para el mismo dato. var() además se resuelve solo en
        // dark mode, sin recalcular nada acá.
        const labelVentas = d.ventas > 0 && alturaVentas > 12
            ? `<text x="${x - 8}" y="${baseY - alturaVentas - 4}" font-size="9" text-anchor="middle" fill="var(--money)" font-weight="700">${formatCompacto(d.ventas)}</text>`
            : '';
        const labelGastos = d.gastos > 0 && alturaGastos > 12
            ? `<text x="${x + 10}" y="${baseY - alturaGastos - 4}" font-size="9" text-anchor="middle" fill="var(--danger)" font-weight="700">${formatCompacto(d.gastos)}</text>`
            : '';

        svg += `
            <g>
                <rect x="${x - 14}" y="${baseY - alturaVentas}" width="12" height="${alturaVentas}" fill="var(--money)" rx="2"/>
                <rect x="${x + 4}" y="${baseY - alturaGastos}" width="12" height="${alturaGastos}" fill="var(--danger)" rx="2"/>
                ${labelVentas}
                ${labelGastos}
                <text x="${x}" y="${alto - 2}" font-size="11" text-anchor="middle" fill="var(--text-muted)" font-weight="600">${diaSemana}</text>
            </g>
        `;
    });

    svg += '</svg>';
    container.innerHTML = svg;
}

const MESES_ABREV = ['ene', 'feb', 'mar', 'abr', 'may', 'jun', 'jul', 'ago', 'sep', 'oct', 'nov', 'dic'];
const DIAS_SEMANA_ABREV = ['Dom', 'Lun', 'Mar', 'Mié', 'Jue', 'Vie', 'Sáb'];

function formatFechaTabla(fechaStr) {
    // Interpretar la fecha en zona horaria LOCAL del navegador, no UTC —
    // mismo criterio que renderBarChart, para no desfasar el día mostrado.
    const fecha = new Date(fechaStr + 'T00:00:00');
    const diaSemana = DIAS_SEMANA_ABREV[fecha.getDay()];
    const dia = fecha.getDate();
    const mes = MESES_ABREV[fecha.getMonth()];
    return `${diaSemana} ${dia} ${mes}`;
}

/**
 * Tabla de ganancias por día — complementa el gráfico de barras con cifras
 * exactas (el gráfico da la tendencia visual, esta tabla da el número
 * preciso para reconciliar contra el POS o la caja física).
 */
function renderTablaDiaria(container, serie) {
    if (!serie || serie.length === 0) {
        container.innerHTML = '<p class="empty-hint">Sin datos para mostrar.</p>';
        return;
    }

    // Más reciente arriba: la serie del backend viene ASC por fecha.
    const filas = [...serie].reverse().map(d => {
        const ganancia = d.ventas - d.gastos;
        const margen = d.ventas > 0 ? (ganancia / d.ventas) * 100 : null;
        let claseFila = 'fila-neutro';
        if (ganancia > 0) claseFila = 'fila-positiva';
        else if (ganancia < 0) claseFila = 'fila-negativa';

        return `
            <tr class="${claseFila}">
                <td class="td-fecha">${formatFechaTabla(d.fecha)}</td>
                <td class="td-num">${formatCurrency(d.ventas)}</td>
                <td class="td-num">${formatCurrency(d.gastos)}</td>
                <td class="td-num td-ganancia">${formatCurrency(ganancia)}</td>
                <td class="td-num td-margen">${margen === null ? '—' : `${margen.toFixed(0)}%`}</td>
            </tr>
        `;
    }).join('');

    container.innerHTML = `
        <table class="tabla-diaria">
            <thead>
                <tr>
                    <th class="th-fecha">Fecha</th>
                    <th class="th-num">Ventas</th>
                    <th class="th-num th-oculto-movil">Gastos</th>
                    <th class="th-num">Ganancia</th>
                    <th class="th-num th-oculto-movil">Margen</th>
                </tr>
            </thead>
            <tbody>${filas}</tbody>
        </table>
    `;
}

function renderTopPlatos(container, topPlatos) {
    container.innerHTML = '';

    if (!topPlatos || topPlatos.length === 0) {
        container.innerHTML = '<p class="empty-hint">Sin ventas en este período.</p>';
        return;
    }

    const maxIngresos = topPlatos[0]?.ingresos || 1;

    topPlatos.slice(0, 5).forEach((plato, idx) => {
        const porcentaje = (plato.ingresos / maxIngresos) * 100;
        const div = document.createElement('div');
        div.className = 'top-plato-item';

        div.innerHTML = `
            <div class="top-plato-num">${idx + 1}</div>
            <div class="top-plato-info">
                <div class="top-plato-nombre">${escapeHtml(plato.nombre)}</div>
                <div class="top-plato-detalle">
                    <span class="cantidad-badge">${plato.cantidad}u</span>
                    <span class="top-plato-monto">${formatCurrency(plato.ingresos)}</span>
                </div>
            </div>
            <div class="top-plato-bar-wrapper">
                <div class="top-plato-bar" style="width: ${porcentaje}%"></div>
            </div>
        `;
        container.appendChild(div);
    });
}

/** Un blob a base64 pelado (sin el prefijo "data:...;base64,"), que es lo que
 *  espera Filesystem.writeFile. */
function _blobABase64(blob) {
    return new Promise((resolve, reject) => {
        const lector = new FileReader();
        lector.onerror = () => reject(new Error('No se pudo leer el archivo generado'));
        lector.onload = () => {
            const s = String(lector.result || '');
            resolve(s.slice(s.indexOf(',') + 1));
        };
        lector.readAsDataURL(blob);
    });
}

/**
 * Guarda el reporte en el teléfono y abre el menú de compartir.
 *
 * Devuelve false si no estamos en la app instalada, para que el llamador caiga
 * al camino del navegador. Nunca lanza: si el guardado falla, se avisa y se
 * deja que el otro camino lo intente.
 *
 * POR QUÉ SE COMPARTE Y NO SE "DESCARGA"
 * --------------------------------------
 * Escribir en la carpeta de Descargas necesita permisos que cambian en cada
 * versión de Android, y si se conceden igual queda un archivo que el dueño
 * tiene que ir a buscar con un explorador. El menú de compartir resuelve las
 * dos cosas de una: desde ahí lo manda por WhatsApp a su contador, lo sube a
 * Drive o lo abre en Excel — que es lo que va a hacer con un reporte, no
 * dejarlo guardado en el teléfono.
 *
 * Se escribe en CACHE y no en Documentos por lo mismo: no pide permisos, y el
 * sistema la limpia solo. El archivo ya salió para donde tenía que ir.
 */
async function _guardarReporteEnNativo(blob, nombreArchivo) {
    const P = window.Capacitor && window.Capacitor.Plugins;
    const Filesystem = P && P.Filesystem;
    if (!Filesystem) return false;

    try {
        const escrito = await Filesystem.writeFile({
            path: nombreArchivo,
            data: await _blobABase64(blob),
            directory: 'CACHE',
            recursive: true,
        });

        const Share = P && P.Share;
        if (Share) {
            await Share.share({
                title: nombreArchivo,
                url: escrito.uri,
                dialogTitle: 'Guardar o enviar el reporte',
            });
        } else {
            showToast('Reporte guardado: ' + nombreArchivo, 'success');
        }
        return true;
    } catch (err) {
        // Cancelar el menú de compartir también llega acá, y NO es un error: el
        // archivo ya se escribió. Se distingue por el mensaje porque el plugin
        // no expone un código.
        const msg = String((err && err.message) || err);
        if (/cancel/i.test(msg)) return true;
        console.error('[Reporte] no se pudo guardar en el dispositivo:', err);
        showToast('No se pudo guardar el reporte en este dispositivo', 'error');
        return true;
    }
}

async function descargarReporteExcel() {
    const boton = document.getElementById('btn-descargar-reporte');
    const textoOriginal = boton.innerHTML;
    boton.disabled = true;
    boton.innerHTML = 'Generando...';

    try {
        let url = `${API_BASE_URL}/dashboard/reporte-excel`;
        url += (dashboardDesde && dashboardHasta)
            ? `?desde=${dashboardDesde}&hasta=${dashboardHasta}`
            : `?dias=${dashboardPeriodo}`;

        const resp = await fetch(url, {
            headers: { 'Authorization': `Bearer ${getToken()}`, 'X-TZ-Offset': tzOffsetMinutos() },
        });
        if (resp.status === 401) {
            manejarSesionExpirada();
            return;
        }
        if (!resp.ok) throw new Error('No se pudo generar el reporte');

        const blob = await resp.blob();
        const nombreArchivo = resp.headers.get('Content-Disposition')?.match(/filename="(.+)"/)?.[1] || 'reporte.xlsx';

        // DENTRO DEL APK EL CAMINO DE ABAJO NO SIRVE, Y FALLA EN SILENCIO.
        //
        // Un <a download> con href de blob: es inerte en un WebView de
        // Android: no hay gestor de descargas conectado a las URLs blob:, así
        // que el click no hace absolutamente nada y tampoco tira error. El
        // botón se veía funcionar —decía "Generando...", volvía a la normalidad—
        // y el archivo no aparecía en ninguna parte.
        if (await _guardarReporteEnNativo(blob, nombreArchivo)) return;

        // Truco estándar para forzar la descarga de un blob sin backend de
        // por medio en la navegación: un <a> invisible con href de blob.
        const enlace = document.createElement('a');
        enlace.href = URL.createObjectURL(blob);
        enlace.download = nombreArchivo;
        document.body.appendChild(enlace);
        enlace.click();
        document.body.removeChild(enlace);
        URL.revokeObjectURL(enlace.href);
    } catch (err) {
        showToast(err.message || 'Error al descargar el reporte', 'error');
    } finally {
        boton.disabled = false;
        boton.innerHTML = textoOriginal;
    }
}

function renderTopGastos(container, topGastos) {
    container.innerHTML = '';

    if (!topGastos || topGastos.length === 0) {
        container.innerHTML = '<p class="empty-hint">Sin gastos en este período.</p>';
        return;
    }

    const maxMonto = topGastos[0]?.monto || 1;

    topGastos.slice(0, 3).forEach((gasto, idx) => {
        const porcentaje = (gasto.monto / maxMonto) * 100;
        const div = document.createElement('div');
        div.className = 'top-plato-item top-gasto-item';

        div.innerHTML = `
            <div class="top-plato-num top-gasto-num">${idx + 1}</div>
            <div class="top-plato-info">
                <div class="top-plato-nombre">${escapeHtml(gasto.categoria)}</div>
                <div class="top-plato-detalle">
                    <span class="cantidad-badge cantidad-badge-gasto">${gasto.cantidad}${gasto.cantidad === 1 ? ' gasto' : ' gastos'}</span>
                    <span class="top-plato-monto top-gasto-monto">${formatCurrency(gasto.monto)}</span>
                </div>
            </div>
            <div class="top-plato-bar-wrapper">
                <div class="top-plato-bar top-gasto-bar" style="width: ${porcentaje}%"></div>
            </div>
        `;
        container.appendChild(div);
    });
}


/**
 * Salón contra mostrador: el reporte para decidir dónde poner esfuerzo.
 *
 * Reusa el mismo componente de barras que Top platos y Top gastos en vez de
 * inventar un gráfico nuevo — son tres listas ordenadas con una magnitud, y
 * el dueño ya sabe leer ese formato.
 *
 * Las DOS filas se muestran siempre, aunque una esté en cero: un restaurante
 * que todavía no vendió para llevar tiene que ver el renglón para enterarse
 * de que la función existe. Ocultarla haría que la pantalla dependiera de si
 * ya se usó, que es justo al revés de lo que hace falta.
 */
const ETIQUETAS_TIPO_PEDIDO = { mesa: 'En salón', llevar: 'Para llevar' };
const ETIQUETAS_METODO_PAGO = { efectivo: '💵 Efectivo', yape: '📱 Yape/Plin' };

function renderVentasPorTipo(container, porTipo, ETIQUETAS = ETIQUETAS_TIPO_PEDIDO) {
    if (!container) return;
    container.innerHTML = '';

    const filas = porTipo || [];
    const totalGeneral = filas.reduce((suma, f) => suma + f.total, 0);

    if (!filas.length || totalGeneral === 0) {
        container.innerHTML = '<p class="empty-hint">Sin ventas en este período.</p>';
        return;
    }

    const mayor = Math.max(...filas.map(f => f.total)) || 1;

    filas.forEach((fila, idx) => {
        // Sobre el TOTAL, no sobre la fila más grande: la pregunta real es
        // "de cada 100 soles, cuántos entran por mostrador", y contra el
        // máximo ese número no se puede leer.
        const parte = totalGeneral ? Math.round((fila.total / totalGeneral) * 100) : 0;
        const div = document.createElement('div');
        div.className = 'top-plato-item';
        div.innerHTML = `
            <div class="top-plato-num">${idx + 1}</div>
            <div class="top-plato-info">
                <div class="top-plato-nombre">${ETIQUETAS[fila.tipo] || escapeHtml(fila.tipo)}</div>
                <div class="top-plato-detalle">
                    <span class="cantidad-badge">${fila.pedidos}${fila.pedidos === 1 ? ' pedido' : ' pedidos'} &middot; ${parte}%</span>
                    <span class="top-plato-monto">${formatCurrency(fila.total)}</span>
                </div>
            </div>
            <div class="top-plato-bar-wrapper">
                <div class="top-plato-bar" style="width: ${(fila.total / mayor) * 100}%"></div>
            </div>
        `;
        container.appendChild(div);
    });
}
