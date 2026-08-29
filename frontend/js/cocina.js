/**
 * CU-03: Monitor de Cocina en Tiempo Real
 * El backend ya entrega minutos_transcurridos calculado, ordenado por
 * antigüedad (FIFO), para que el celular/tablet de cocina no tenga
 * que hacer ningún cálculo de fechas.
 */

const ALERTA_MINUTOS = 15;
let cocinaRefreshInterval = null;

function initCocina() {
    refreshCocina();
    cocinaRefreshInterval = setInterval(refreshCocina, 4000);
}

async function refreshCocina() {
    const container = document.getElementById('cocina-comandas');
    const emptyMsg = document.getElementById('cocina-empty');

    try {
        const comandas = await api.get('/monitor/cocina');

        if (!comandas || comandas.length === 0) {
            container.innerHTML = '';
            emptyMsg.classList.remove('hidden');
            return;
        }

        emptyMsg.classList.add('hidden');
        container.innerHTML = comandas.map(comanda => {
            const alerta = comanda.minutos_transcurridos > ALERTA_MINUTOS;
            const platosHtml = comanda.platos
                .map(p => `<div class="cocina-plato">${p.cantidad}x ${escapeHtml(p.nombre)}</div>`)
                .join('');

            return `
                <div class="cocina-tarjeta ${alerta ? 'alerta' : ''}" id="cocina-${comanda.id}">
                    <div class="cocina-tarjeta-top">
                        <div class="cocina-mesa">Mesa ${comanda.numero_mesa}</div>
                        <div class="cocina-tiempo ${alerta ? 'alerta' : ''}">${comanda.minutos_transcurridos} min</div>
                    </div>
                    <div class="cocina-platos">${platosHtml}</div>
                    <button class="btn-listo" onclick="marcarListo(${comanda.id})">✓ Listo</button>
                </div>
            `;
        }).join('');
    } catch (err) {
        console.error('Error cargando monitor de cocina:', err);
    }
}

async function marcarListo(comandaId) {
    try {
        await api.patch(`/comandas/${comandaId}/estado`, { estado: 'entregado' });

        const tarjeta = document.getElementById(`cocina-${comandaId}`);
        if (tarjeta) {
            tarjeta.style.transition = 'opacity 0.25s, transform 0.25s';
            tarjeta.style.opacity = '0';
            tarjeta.style.transform = 'scale(0.97)';
            setTimeout(() => {
                tarjeta.remove();
                if (document.getElementById('cocina-comandas').children.length === 0) {
                    document.getElementById('cocina-empty').classList.remove('hidden');
                }
            }, 250);
        }

        showToast('Comanda entregada', 'success');
        if (typeof refreshMozo === 'function') refreshMozo();
    } catch (err) {
        showToast(err.message || 'Error al marcar como listo', 'error');
    }
}

function stopCocinaRefresh() {
    if (cocinaRefreshInterval) clearInterval(cocinaRefreshInterval);
}
