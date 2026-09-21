/**
 * El lado del aparato de la cola de impresión.
 *
 * QUÉ PROBLEMA RESUELVE
 * ---------------------
 * La impresora térmica es Bluetooth y está emparejada a UN teléfono. Ningún
 * aparato puede escribirle a la impresora de otro, así que para que el ticket
 * salga en la COCINA, el aparato de la cocina tiene que ser el que imprime.
 * Antes imprimía el que hacía la acción —el mozo— y el ticket de cocina salía
 * en el mostrador, lejos de quien tenía que leerlo.
 *
 * Este archivo es el que va a buscar trabajo al servidor cada pocos segundos,
 * arma el papel con las plantillas de print.js y confirma si salió.
 *
 * POR QUÉ EL PAPEL SE ARMA ACÁ Y NO EN EL SERVIDOR
 * -----------------------------------------------
 * El servidor manda un PUNTERO ("ticket de cocina de la comanda 412"), no el
 * HTML. Las plantillas viven en print.js, ya están probadas y usan los datos
 * del negocio que este aparato tiene en sesión. Armarlas también en el backend
 * dejaría DOS versiones del mismo papel, y la diferencia entre las dos recién
 * se vería en el papel impreso, que es donde menos se mira.
 */

const COLA_INTERVALO_MS = 3000;

// Qué estaciones atiende ESTE aparato. Por aparato y no por cuenta, igual que
// la impresora misma: la misma persona puede pasar del tablet de la cocina al
// celular del mostrador, y lo que tiene que cambiar es lo que sale por cada
// impresora, no lo que hace esa persona.
const CLAVE_ESTACIONES = 'restomind_estaciones_impresion';

// Identifica al APARATO, no a la persona. Sirve para dos cosas: saber a qué
// impresora se mandó cada papel, y poder devolver a la cola lo que quedó
// colgado cuando un aparato no vuelve. No se manda nada más sobre el equipo.
const CLAVE_DEVICE_ID = 'restomind_device_id';

// Por defecto atiende LAS DOS. Es exactamente lo que hacía la app antes de que
// existiera la cola —el aparato que toma el pedido saca los dos papeles— así
// que ningún local se rompe sin que nadie toque nada. El que estrena impresora
// en la cocina configura: mozo -> mostrador, cocina -> cocina.
const ESTACIONES_POR_DEFECTO = ['cocina', 'mostrador'];

let colaIntervalo = null;
let colaTrabajando = false;

function _deviceId() {
    try {
        let id = localStorage.getItem(CLAVE_DEVICE_ID);
        if (!id) {
            id = 'dev-' + Math.random().toString(36).slice(2, 10) + Date.now().toString(36).slice(-4);
            localStorage.setItem(CLAVE_DEVICE_ID, id);
        }
        return id;
    } catch (_) {
        // Sin localStorage (modo privado) el id cambia en cada carga. Funciona
        // igual: lo único que se pierde es poder recuperar lo que este aparato
        // dejó a medias, y para eso ya está el vencimiento del reclamo.
        return 'dev-efimero-' + Date.now().toString(36);
    }
}

function estacionesDeEsteAparato() {
    try {
        const crudo = localStorage.getItem(CLAVE_ESTACIONES);
        if (!crudo) return [...ESTACIONES_POR_DEFECTO];
        const lista = JSON.parse(crudo);
        const validas = Array.isArray(lista)
            ? lista.filter(e => ESTACIONES_POR_DEFECTO.includes(e))
            : [];
        // Una lista vacía guardada significa "este aparato no imprime nada",
        // que es una elección legítima (el celular de un mozo sin impresora).
        return validas;
    } catch (_) {
        return [...ESTACIONES_POR_DEFECTO];
    }
}

function guardarEstacionesDeEsteAparato(estaciones) {
    try {
        localStorage.setItem(CLAVE_ESTACIONES, JSON.stringify(estaciones));
    } catch (_) { /* sin localStorage: vale para esta sesión nomás */ }
    reiniciarColaImpresion();
}

/**
 * Arma el papel de un trabajo. Devuelve null si no se puede armar, que es
 * distinto de "falló la impresión": sin los datos del pedido no hay nada que
 * mandarle a la impresora, y reintentarlo no va a cambiar eso.
 */
async function _armarDocumento(trabajo) {
    let comanda;
    try {
        comanda = await api.get(`/comandas/${trabajo.comanda_id}`);
    } catch (err) {
        console.warn('[Cola] no se pudo traer la comanda', trabajo.comanda_id, err);
        return null;
    }

    const negocio = {
        nombre: estado.usuario?.cliente_nombre || 'RestoMind',
        razon_social: estado.usuario?.cliente_razon_social || null,
        direccion: estado.usuario?.cliente_direccion || null,
        ruc: estado.usuario?.cliente_ruc || null,
        email: estado.usuario?.cliente_email || null,
    };
    const quien = estado.usuario?.nombre;

    if (trabajo.tipo_documento === 'cocina') {
        return _ticketHTML('COCINA', comanda, { conPrecios: false });
    }
    if (trabajo.tipo_documento === 'precuenta') {
        return _ticketPrecuentaHTML(comanda, negocio, quien);
    }
    return _ticketPreventaHTML(comanda, negocio, quien);
}

async function _confirmar(trabajo, salio, error) {
    try {
        await api.post(`/impresion/${trabajo.id}/resultado`, {
            device_id: _deviceId(), salio, error: error || null,
        });
    } catch (err) {
        // Un 404 acá casi siempre significa que el reclamo venció y otro
        // aparato se llevó el trabajo. No es algo que haya que mostrarle a
        // nadie: el papel ya está en manos de otra impresora.
        console.warn('[Cola] no se pudo confirmar el trabajo', trabajo.id, err);
    }
}

async function _vueltaDeCola() {
    // Una vuelta por vez. Cada papel abre su propia conexión Bluetooth y tarda
    // segundos; si se encimaran dos vueltas, el mismo trabajo podría mandarse
    // dos veces a la impresora.
    if (colaTrabajando) return;
    if (!estado.usuario) return;

    const estaciones = estacionesDeEsteAparato();
    if (!estaciones.length) return;

    // Con la impresión apagada en este aparato NO se reclama nada. Reclamar y
    // no imprimir sería peor que no reclamar: el trabajo quedaría tomado por
    // un aparato que no va a sacarlo, y el que sí puede tendría que esperar a
    // que venza el reclamo.
    if (window.ImpresoraTermica && !window.ImpresoraTermica.impresionActiva()) return;

    colaTrabajando = true;
    try {
        let trabajos = [];
        try {
            trabajos = await api.post('/impresion/reclamar', {
                device_id: _deviceId(), estaciones, limite: 5,
            });
        } catch (err) {
            return;   // sin señal: la próxima vuelta reintenta
        }

        for (const trabajo of trabajos) {
            const html = await _armarDocumento(trabajo);
            if (!html) {
                await _confirmar(trabajo, false, 'No se pudieron leer los datos del pedido');
                continue;
            }

            try {
                // Entre papel y papel se respeta la misma pausa que usa
                // print.js: sin ella el segundo trabajo llega mientras la
                // impresora todavía está sacando el primero, y sale cortado.
                await _imprimirHTML(html);
                await _confirmar(trabajo, true);
            } catch (err) {
                await _confirmar(trabajo, false, String(err && err.message || err).slice(0, 300));
            }

            if (trabajos.indexOf(trabajo) < trabajos.length - 1) {
                await _esperar(PAUSA_ENTRE_PAPELES_MS);
            }
        }
    } finally {
        colaTrabajando = false;
    }
}

function iniciarColaImpresion() {
    if (colaIntervalo) clearInterval(colaIntervalo);
    colaIntervalo = setInterval(_vueltaDeCola, COLA_INTERVALO_MS);
    _vueltaDeCola();
}

function reiniciarColaImpresion() {
    iniciarColaImpresion();
}

// ============ PANTALLA (Admin -> Impresora) ============

/** Deja las casillas acordes con lo guardado en ESTE aparato. Se llama al
 *  abrir el modal, porque la configuración pudo cambiarse antes. */
function sincronizarEstaciones() {
    const actuales = estacionesDeEsteAparato();
    const cocina = document.getElementById('estacion-cocina');
    const mostrador = document.getElementById('estacion-mostrador');
    if (!cocina || !mostrador) return;

    cocina.checked = actuales.includes('cocina');
    mostrador.checked = actuales.includes('mostrador');
    _pintarAvisoEstaciones(actuales);
}

/** El aviso dice qué SIGNIFICA lo elegido, no lo repite.
 *
 *  Las dos situaciones que avisa son las que dejan a un local sin papeles sin
 *  que nadie se entere: nada marcado acá, o cocina marcada en dos aparatos
 *  (que saca el ticket por duplicado). */
function _pintarAvisoEstaciones(actuales) {
    const aviso = document.getElementById('estaciones-aviso');
    if (!aviso) return;

    if (!actuales.length) {
        aviso.textContent = 'Este aparato no va a imprimir nada. Asegurate de que otro esté sacando los papeles.';
        aviso.className = 'estaciones-aviso atencion';
        return;
    }
    if (actuales.length === 2) {
        aviso.textContent = 'Este aparato saca los dos papeles. Si la cocina tiene su propia impresora, destildá "Tickets de cocina" acá.';
        aviso.className = 'estaciones-aviso';
        return;
    }
    aviso.textContent = actuales[0] === 'cocina'
        ? 'Solo tickets de cocina. El papel del comensal lo tiene que sacar otro aparato.'
        : 'Solo el papel del comensal. Los tickets de cocina los tiene que sacar otro aparato.';
    aviso.className = 'estaciones-aviso';
}

function onCambiarEstaciones() {
    const elegidas = [];
    if (document.getElementById('estacion-cocina')?.checked) elegidas.push('cocina');
    if (document.getElementById('estacion-mostrador')?.checked) elegidas.push('mostrador');

    guardarEstacionesDeEsteAparato(elegidas);
    _pintarAvisoEstaciones(elegidas);
}

/**
 * Vuelve a pedir un papel de un pedido que ya existe.
 *
 * Cubre los tres casos que pasan de verdad en un turno: el aparato de la
 * cocina estaba apagado cuando entró el pedido, la impresora estaba trabada, o
 * el papel salió y se perdió entre el movimiento.
 *
 * NO imprime acá: encola. Así el papel sale por la impresora que corresponde
 * a esa estación, que puede no ser la de quien apretó el botón — es el mismo
 * motivo por el que existe la cola.
 */
async function pedirReimpresion(comandaId, tipoDocumento = 'cocina') {
    try {
        await api.post('/impresion/reimprimir', {
            comanda_id: comandaId, tipo_documento: tipoDocumento,
        });
        showToast('Pedido a la impresora', 'success');
        _vueltaDeCola();   // sin esperar la próxima vuelta
    } catch (err) {
        showToast(err.message || 'No se pudo pedir la reimpresión', 'error');
    }
}
