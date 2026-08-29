/**
 * CU-03: Monitor de Cocina en Tiempo Real
 * Pantalla de cocina para visualizar y marcar comandas como listas
 */

let cocinaRefreshInterval = null;

function initCocina() {
    refreshCocina();
    // Refresh every 2 seconds
    cocinaRefreshInterval = setInterval(refreshCocina, 2000);
}

function refreshCocina() {
    renderComandas();
}

async function renderComandas() {
    const container = document.getElementById('cocina-comandas');
    const emptyMsg = document.getElementById('cocina-empty');

    try {
        const comandas = await api.get('/monitor/cocina');

        if (!comandas || comandas.length === 0) {
            container.innerHTML = '';
            emptyMsg.style.display = 'block';
            return;
        }

        emptyMsg.style.display = 'none';
        container.innerHTML = '';

        comandas.forEach(comanda => {
            const minutosTranscurridos = calcularMinutosTranscurridos(comanda.creado_en);
            const alertaEstilo = minutosTranscurridos > 15 ? 'alerta' : '';

            const tarjeta = document.createElement('div');
            tarjeta.className = 'cocina-tarjeta';
            tarjeta.id = `cocina-${comanda.id}`;

            let platosHtml = '';
            comanda.platos.forEach(p => {
                platosHtml += `<div class="cocina-plato">• ${p.nombre} (x${p.cantidad})</div>`;
            });

            tarjeta.innerHTML = `
                <div class="cocina-mesa">MESA ${comanda.numero_mesa}</div>
                <div class="cocina-tiempo ${alertaEstilo}">⏱️ ${minutosTranscurridos} min</div>
                <div class="cocina-platos">
                    ${platosHtml}
                </div>
                <button class="btn-listo" onclick="marcarListo(${comanda.id})">
                    ✓ LISTO
                </button>
            `;

            container.appendChild(tarjeta);
        });
    } catch (err) {
        console.error('Error renderizando comandas:', err);
    }
}

function calcularMinutosTranscurridos(fecha) {
    const ahora = new Date();
    const fechaComanda = new Date(fecha);
    const minutos = Math.floor((ahora - fechaComanda) / 60000);
    return minutos;
}

async function marcarListo(comandaId) {
    try {
        await api.patch(`/comandas/${comandaId}/estado`, { estado: 'entregado' });
        console.log(`Comanda ${comandaId} marcada como entregada`);

        // Smooth removal animation
        const tarjeta = document.getElementById(`cocina-${comandaId}`);
        if (tarjeta) {
            tarjeta.style.opacity = '0';
            tarjeta.style.transition = 'opacity 0.3s';
            setTimeout(() => {
                tarjeta.remove();
                // Check if all done
                if (document.getElementById('cocina-comandas').children.length === 0) {
                    document.getElementById('cocina-empty').style.display = 'block';
                }
            }, 300);
        }

        showToast('✓ Comanda lista', 'success');

        // Refresh mozo display if open
        if (typeof refreshMozo === 'function') {
            refreshMozo();
        }
    } catch (err) {
        showToast('Error al marcar como listo: ' + err.message, 'error');
    }
}

// Cleanup on tab change
function stopCocinaRefresh() {
    if (cocinaRefreshInterval) {
        clearInterval(cocinaRefreshInterval);
    }
}
