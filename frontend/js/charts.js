/**
 * Charts - SVG generado a mano, sin dependencias externas.
 * Se evita deliberadamente cualquier librería (Chart.js, etc.) para
 * mantener el PWA liviano en celulares de gama media/baja y sin
 * depender de un CDN quer podría fallar offline.
 */

const DIAS_CORTOS = ['dom', 'lun', 'mar', 'mié', 'jue', 'vie', 'sáb'];

function _diaCorto(fechaIso) {
    const fecha = new Date(`${fechaIso}T00:00:00`);
    return DIAS_CORTOS[fecha.getDay()];
}

/**
 * Dibuja un gráfico de barras agrupadas (ventas vs gastos) por día.
 * @param {HTMLElement} container
 * @param {Array<{fecha:string, ventas:number, gastos:number}>} serie
 */
function renderBarChart(container, serie) {
    if (!serie || serie.length === 0) {
        container.innerHTML = '<p class="empty-hint">Sin datos en este periodo.</p>';
        return;
    }

    const width = Math.max(container.clientWidth || 320, 260);
    const height = 170;
    const padTop = 12;
    const padBottom = 22;
    const padSide = 6;
    const plotHeight = height - padTop - padBottom;

    const max = Math.max(1, ...serie.map(d => Math.max(d.ventas, d.gastos)));
    const groupWidth = (width - padSide * 2) / serie.length;
    const barWidth = Math.max(4, Math.min(16, groupWidth / 2 - 3));

    const mostrarEtiquetas = serie.length <= 14;

    let svg = '';
    serie.forEach((d, i) => {
        const cx = padSide + i * groupWidth + groupWidth / 2;
        const hVentas = (d.ventas / max) * plotHeight;
        const hGastos = (d.gastos / max) * plotHeight;
        const yVentas = height - padBottom - hVentas;
        const yGastos = height - padBottom - hGastos;

        svg += `<rect x="${(cx - barWidth - 2).toFixed(1)}" y="${yVentas.toFixed(1)}" width="${barWidth.toFixed(1)}" height="${Math.max(hVentas, 1).toFixed(1)}" rx="2.5" fill="#FF5A3C"/>`;
        svg += `<rect x="${(cx + 2).toFixed(1)}" y="${yGastos.toFixed(1)}" width="${barWidth.toFixed(1)}" height="${Math.max(hGastos, 1).toFixed(1)}" rx="2.5" fill="#94A3B8"/>`;

        if (mostrarEtiquetas) {
            svg += `<text x="${cx.toFixed(1)}" y="${height - 6}" font-size="9" text-anchor="middle" fill="#9CA3AF">${_diaCorto(d.fecha)}</text>`;
        }
    });

    container.innerHTML = `<svg viewBox="0 0 ${width} ${height}" width="100%" height="${height}" role="img" aria-label="Ventas y gastos por día" preserveAspectRatio="none">${svg}</svg>`;
}

/**
 * Renderiza el ranking de platos más vendidos como filas con barra proporcional.
 * @param {HTMLElement} container
 * @param {Array<{nombre:string, cantidad:number, revenue:number}>} items
 */
function renderTopPlatos(container, items) {
    if (!items || items.length === 0) {
        container.innerHTML = '<p class="empty-hint">Aún no hay ventas cobradas en este periodo.</p>';
        return;
    }

    const max = Math.max(...items.map(i => i.revenue), 1);

    container.innerHTML = items.map((item, idx) => `
        <div class="top-plato-row">
            <div class="top-plato-rank">${idx + 1}</div>
            <div class="top-plato-info">
                <div class="top-plato-nombre">${escapeHtml(item.nombre)} · ${item.cantidad}u</div>
                <div class="top-plato-bar-bg"><div class="top-plato-bar" style="width:${((item.revenue / max) * 100).toFixed(0)}%"></div></div>
            </div>
            <div class="top-plato-revenue">${formatCurrency(item.revenue)}</div>
        </div>
    `).join('');
}
