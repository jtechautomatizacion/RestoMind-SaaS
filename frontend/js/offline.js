/**
 * Modo offline: cuando el mozo se queda sin señal a mitad de un servicio,
 * los pedidos no se pierden — se guardan localmente y se envían solos en
 * cuanto vuelve la conexión.
 *
 * Deliberadamente limitado a comandas nuevas (POST /comandas), no a
 * cualquier acción de la app: es la única operación donde el mozo tiene
 * toda la información necesaria sin depender del servidor (sabe qué mesa,
 * qué platos y cuántos). Cobrar una mesa, cambiar el estado en cocina o
 * editar la carta sí dependen de ver primero el estado real del servidor
 * — encolarlas a ciegas arriesgaría actuar sobre datos viejos.
 */

const OFFLINE_QUEUE_KEY = 'restomind_pendientes';
let sincronizandoPendientes = false;

function obtenerPendientes() {
    try {
        return JSON.parse(localStorage.getItem(OFFLINE_QUEUE_KEY) || '[]');
    } catch (_) {
        return [];
    }
}

function guardarPendientes(lista) {
    localStorage.setItem(OFFLINE_QUEUE_KEY, JSON.stringify(lista));
}

function encolarComanda(payload) {
    const lista = obtenerPendientes();
    lista.push({
        id: `pend-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
        payload,
        creadoEn: Date.now(),
    });
    guardarPendientes(lista);
    actualizarBannerOffline();
}

async function sincronizarPendientes() {
    if (sincronizandoPendientes || !navigator.onLine) return;

    let lista = obtenerPendientes();
    if (lista.length === 0) return;

    sincronizandoPendientes = true;
    actualizarBannerOffline();

    let algunaSincronizada = false;

    while (lista.length > 0) {
        const item = lista[0];
        try {
            await api.post('/comandas', item.payload);
            algunaSincronizada = true;
        } catch (err) {
            if (err instanceof NetworkError) {
                // Se cortó la señal de nuevo a mitad de la sincronización:
                // el resto de la cola queda intacto para el próximo intento.
                break;
            }
            // Error real del servidor (ej: esa mesa ya no existe) — reintentar
            // esto para siempre no tiene sentido, se descarta y se avisa.
            showToast(`No se pudo sincronizar un pedido pendiente: ${err.message}`, 'error');
        }
        lista = lista.slice(1);
        guardarPendientes(lista);
    }

    sincronizandoPendientes = false;
    actualizarBannerOffline();

    if (algunaSincronizada) {
        showToast('Pedidos pendientes sincronizados', 'success');
        if (typeof refreshMozo === 'function') refreshMozo();
        if (typeof puedeVer === 'function' && puedeVer('cocina') && typeof refreshCocina === 'function') refreshCocina();
    }
}

function actualizarBannerOffline() {
    const banner = document.getElementById('offline-banner');
    if (!banner) return;

    const pendientes = obtenerPendientes().length;
    const sinConexion = !navigator.onLine;

    if (!sinConexion && pendientes === 0 && !sincronizandoPendientes) {
        banner.classList.add('hidden');
        return;
    }

    banner.classList.remove('hidden');

    if (sincronizandoPendientes) {
        banner.textContent = `Sincronizando ${pendientes} pedido${pendientes === 1 ? '' : 's'} pendiente${pendientes === 1 ? '' : 's'}...`;
        banner.className = 'offline-banner syncing';
    } else if (sinConexion) {
        banner.textContent = pendientes > 0
            ? `Sin conexión · ${pendientes} pedido${pendientes === 1 ? '' : 's'} guardado${pendientes === 1 ? '' : 's'}, se enviará solo al volver la señal`
            : 'Sin conexión · los pedidos se guardan y se sincronizan solos';
        banner.className = 'offline-banner offline';
    } else {
        banner.classList.add('hidden');
    }
}

function initOffline() {
    actualizarBannerOffline();
    window.addEventListener('online', sincronizarPendientes);
    window.addEventListener('offline', actualizarBannerOffline);

    // Respaldo: el evento 'online' no siempre dispara de forma confiable en
    // redes inestables (wifi de restaurante que sube y baja de señal).
    // Reintentar cada 20s mientras quede algo pendiente cubre ese caso.
    setInterval(sincronizarPendientes, 20000);

    sincronizarPendientes();
}
