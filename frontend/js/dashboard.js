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
        renderTopPlatos(document.getElementById('top-platos-list'), data.top_platos);
        renderTopGastos(document.getElementById('top-gastos-list'), data.top_gastos);
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

// Etiqueta de barra: sin decimales ni símbolo de moneda (no entran a este
// tamaño de fuente), y en 'k' desde 1000 para no desbordar el ancho de la barra.
function formatCompacto(num) {
    if (num >= 1000) return `${(num / 1000).toFixed(1).replace('.0', '')}k`;
    return String(Math.round(num));
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
        const labelVentas = d.ventas > 0 && alturaVentas > 12
            ? `<text x="${x - 8}" y="${baseY - alturaVentas - 4}" font-size="9" text-anchor="middle" fill="#FF5A3C" font-weight="700">${formatCompacto(d.ventas)}</text>`
            : '';
        const labelGastos = d.gastos > 0 && alturaGastos > 12
            ? `<text x="${x + 10}" y="${baseY - alturaGastos - 4}" font-size="9" text-anchor="middle" fill="#94A3B8" font-weight="700">${formatCompacto(d.gastos)}</text>`
            : '';

        svg += `
            <g>
                <rect x="${x - 14}" y="${baseY - alturaVentas}" width="12" height="${alturaVentas}" fill="#FF5A3C" rx="2"/>
                <rect x="${x + 4}" y="${baseY - alturaGastos}" width="12" height="${alturaGastos}" fill="#94A3B8" rx="2"/>
                ${labelVentas}
                ${labelGastos}
                <text x="${x}" y="${alto - 2}" font-size="11" text-anchor="middle" fill="#6B7280" font-weight="600">${diaSemana}</text>
            </g>
        `;
    });

    svg += '</svg>';
    container.innerHTML = svg;
}

function renderTopPlatos(container, topPlatos) {
    container.innerHTML = '';

    if (!topPlatos || topPlatos.length === 0) {
        container.innerHTML = '<p class="empty-hint">Sin ventas en este período.</p>';
        return;
    }

    const maxIngresos = topPlatos[0]?.ingresos || 1;

    topPlatos.slice(0, 3).forEach((plato, idx) => {
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
