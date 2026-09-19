/**
 * CU-03: Monitor de Cocina en Tiempo Real
 * El backend ya entrega minutos_transcurridos calculado, ordenado por
 * antigüedad (FIFO), para que el celular/tablet de cocina no tenga
 * que hacer ningún cálculo de fechas.
 */

const ALERTA_MINUTOS = 15;
let cocinaRefreshInterval = null;

// IDs de comandas que cocina ya vio. Sirve para distinguir "hay 3 pedidos"
// de "ACABA de entrar un pedido" — sin esto no hay forma de saber cuál de las
// 15 vueltas por minuto trae algo nuevo.
let comandasVistas = null;

/**
 * Avisa que entró un pedido: sonido y vibración.
 *
 * POR QUÉ ESTO Y NO UNA NOTIFICACIÓN PUSH
 * ---------------------------------------
 * Cocina no tenía NINGÚN aviso: la pantalla se actualizaba sola cada 4s y el
 * cocinero se enteraba si estaba mirando. El único aviso que existía en el
 * código era por Firebase, que necesita un proyecto creado a mano y que hoy
 * no está en el APK — o sea que en la práctica no avisaba nada.
 *
 * Esto funciona SIEMPRE: en el navegador y en la app, sin configurar nada.
 * Cubre el caso real —el tablet prendido en la cocina, con la app abierta—
 * que es el 95% del tiempo. El push sigue siendo necesario solo para avisar
 * con la app CERRADA, y queda como un extra aparte.
 *
 * El sonido se sintetiza con WebAudio en vez de cargar un .mp3: son dos tonos
 * y no vale sumarle un archivo al APK, ni una petición de red que puede
 * fallar justo cuando hace falta el aviso.
 */
// Si ESTE dispositivo hace sonar el aviso. Por dispositivo y no por cuenta:
// es una decisión sobre el parlante que uno tiene al lado — el tablet de la
// cocina lo quiere encendido, el celular del dueño en una reunión no.
const AVISO_COCINA_KEY = 'restomind_aviso_cocina';

function avisoCocinaActivo() {
    try {
        // Encendido por defecto: si un local nunca toca el ajuste, tiene que
        // enterarse igual de que entró un pedido. Apagado por defecto haría
        // que el aviso pareciera roto.
        return localStorage.getItem(AVISO_COCINA_KEY) !== 'false';
    } catch (_) {
        return true;
    }
}

function setAvisoCocinaActivo(activo) {
    try {
        localStorage.setItem(AVISO_COCINA_KEY, activo ? 'true' : 'false');
    } catch (_) { /* almacenamiento bloqueado */ }
}

function sonarAvisoCocina() {
    if (!avisoCocinaActivo()) return;
    try {
        const Ctx = window.AudioContext || window.webkitAudioContext;
        if (Ctx) {
            const ctx = new Ctx();
            // El navegador arranca el audio SUSPENDIDO hasta que hubo un toque
            // del usuario. Si la sesión se restauró sola (token guardado),
            // puede no haber habido ninguno todavía y el aviso no sonaría, sin
            // error ni pista. Se reanuda antes de programar las notas — si no
            // se puede, queda la vibración.
            if (ctx.state === 'suspended' && ctx.resume) {
                ctx.resume().then(() => tocar(ctx)).catch(() => {});
            } else {
                tocar(ctx);
            }
            setTimeout(() => ctx.close().catch(() => {}), 1200);
        }
    } catch (_) {
        // Sin audio (permiso, política del navegador, dispositivo mudo) la
        // vibración de abajo sigue avisando. Nunca se corta el refresco.
    }

    try {
        if (navigator.vibrate) navigator.vibrate([120, 60, 120]);
    } catch (_) { /* el dispositivo no vibra */ }
}

/** Las dos notas del aviso. Separado porque puede sonar ya o después de que
 *  el navegador levante la suspensión del audio. */
function tocar(ctx) {
    try {
        // Dos notas cortas ascendentes: se distingue del ruido de un local
        // lleno mejor que un beep plano, y no suena a error.
        [[880, 0], [1320, 0.16]].forEach(([hz, cuando]) => {
            const osc = ctx.createOscillator();
            const vol = ctx.createGain();
            osc.type = 'sine';
            osc.frequency.value = hz;
            osc.connect(vol);
            vol.connect(ctx.destination);
            const t = ctx.currentTime + cuando;
            // Subida y bajada suaves: un corte seco produce un chasquido
            // audible en los parlantes chicos de un tablet.
            vol.gain.setValueAtTime(0.0001, t);
            vol.gain.exponentialRampToValueAtTime(0.35, t + 0.02);
            vol.gain.exponentialRampToValueAtTime(0.0001, t + 0.15);
            osc.start(t);
            osc.stop(t + 0.16);
        });
    } catch (_) { /* el contexto se cerró antes de tiempo */ }
}

function initCocina() {
    // Se arranca en null y no en un Set vacío para poder distinguir la PRIMERA
    // carga. Con un Set vacío, abrir la pantalla con 5 pedidos ya en cocina
    // sonaría 5 veces seguidas por pedidos viejos.
    comandasVistas = null;
    refreshCocina();
    cocinaRefreshInterval = setInterval(refreshCocina, 4000);
}

async function refreshCocina() {
    const container = document.getElementById('cocina-comandas');
    const emptyMsg = document.getElementById('cocina-empty');

    try {
        const comandas = await api.get('/monitor/cocina');

        // La vista unificada pinta estas mismas comandas en su columna del
        // medio. Se comparten desde acá en vez de que ella las vuelva a
        // pedir: es el mismo dato, y esta consulta ya corre cada 4s.
        estado.comandasCocina = comandas || [];
        if (typeof onCocinaActualizada === 'function') onCocinaActualizada();

        // ¿Entró alguno que no estaba la vuelta anterior?
        const ids = new Set((comandas || []).map(c => c.id));
        if (comandasVistas === null) {
            // Primera carga: se toma nota de lo que ya había, sin sonar. Lo
            // que está en cocina al abrir la pantalla no es novedad.
            comandasVistas = ids;
        } else {
            const nuevas = [...ids].filter(id => !comandasVistas.has(id));
            comandasVistas = ids;
            // Un solo aviso aunque entren tres pedidos juntos: tres sonidos
            // encimados se escuchan como ruido, no como tres pedidos.
            if (nuevas.length) sonarAvisoCocina();
        }

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
                        <div class="cocina-mesa">${rotuloComanda(comanda)}</div>
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
