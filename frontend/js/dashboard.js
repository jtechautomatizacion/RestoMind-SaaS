/**
 * CU-05: Dashboard Financiero
 * "Cómo viaja mi dinero": ventas vs gastos, ganancia y platos top.
 */

let dashboardPeriodo = 7;

function initDashboard() {
    document.querySelectorAll('.periodo-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            document.querySelectorAll('.periodo-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            dashboardPeriodo = parseInt(btn.dataset.dias, 10);
            refreshDashboard();
        });
    });
    refreshDashboard();
}

async function refreshDashboard() {
    try {
        const data = await api.get(`/dashboard/resumen?dias=${dashboardPeriodo}`);
        renderStats(data.serie);
        renderBarChart(document.getElementById('chart-ventas-gastos'), data.serie);
        renderTopPlatos(document.getElementById('top-platos-list'), data.top_platos);
    } catch (err) {
        console.error('Error cargando dashboard:', err);
    }
}

function renderStats(serie) {
    const container = document.getElementById('dashboard-stats');
    container.innerHTML = '';

    const hoy = serie[serie.length - 1];
    const ayer = serie.length > 1 ? serie[serie.length - 2] : null;

    container.appendChild(buildStatTile('Ventas hoy', hoy.ventas, ayer ? ayer.ventas : null, 'money'));
    container.appendChild(buildStatTile('Gastos hoy', hoy.gastos, ayer ? ayer.gastos : null, 'expense'));
    container.appendChild(buildStatTile('Ganancia hoy', hoy.ganancia, ayer ? ayer.ganancia : null, 'profit'));
}

function buildStatTile(label, valor, valorAnterior, tipo) {
    const div = document.createElement('div');
    div.className = 'stat-tile';

    let deltaHtml = '';
    if (valorAnterior !== null && valorAnterior !== 0) {
        const delta = ((valor - valorAnterior) / Math.abs(valorAnterior)) * 100;
        const signo = delta >= 0 ? '+' : '';
        const clase = delta >= 0 ? 'up' : 'down';
        deltaHtml = `<div class="delta ${clase}">${signo}${delta.toFixed(0)}% vs ayer</div>`;
    }

    div.innerHTML = `
        <div class="label">${label}</div>
        <div class="value ${tipo}">${formatCurrency(valor)}</div>
        ${deltaHtml}
    `;
    return div;
}
