/**
 * El pulso que mantiene viva la pantalla de Mesas.
 *
 * POR QUÉ EXISTE ESTE ARCHIVO
 * ---------------------------
 * Durante meses, Mesas fue la ÚNICA pantalla sin un reloj de fondo: Cocina
 * refrescaba cada 4s y la vista unificada cada 5s, pero la grilla de mesas
 * solo se repintaba cuando el propio mozo tocaba algo. Un pedido cargado
 * desde otro teléfono no llegaba nunca — la pantalla mostraba el mundo tal
 * como estaba la última vez que ESE mozo hizo algo.
 *
 * El síntoma engaña, y por eso hace falta un test y no una prueba a mano:
 * "no se actualiza en tiempo real" se ve EXACTAMENTE IGUAL cuando el reloj
 * no existe, cuando existe pero un guardia lo frena de más, y cuando el
 * teléfono tiene un APK viejo sin este código adentro. Tres causas muy
 * distintas, un solo síntoma. Este archivo descarta las dos primeras para
 * que, cuando vuelva a pasar, la sospecha caiga donde corresponde.
 *
 *     node --test tests/frontend/
 */

import { test, describe, beforeEach } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import path from 'node:path';
import { parseHTML } from 'linkedom';

const raiz = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', '..');
const leer = (p) => readFileSync(path.join(raiz, p), 'utf8');

// ---- Entorno mínimo de navegador ---------------------------------------

function mesa(numero, extra = {}) {
    return { id: numero, numero, capacidad: 4, ubicacion: null, estado: 'disponible', cuenta_actual: 0, ...extra };
}

/**
 * Carga mozo.js con los globales que toca, y devuelve un puñado de mandos
 * para manejar el tiempo y la red a voluntad.
 *
 * El reloj es FALSO a propósito: un test que esperara 5 segundos de verdad
 * tardaría más que toda la suite junta, y sería inestable en una máquina
 * cargada. Acá `tic()` avanza el tiempo a mano.
 */
function cargarMozo({ mesas = [mesa(1), mesa(2)], roles = ['mozo'] } = {}) {
    const { document } = parseHTML(`<html><body>
        <div id="mozo-mesas"></div>
    </body></html>`);

    const estado = { mesas, roles, currentTab: 'mozo', platos: [], comandasCocina: [] };

    const llamadas = [];           // qué pidió a la red, en orden
    let respuestaMesas = mesas;    // lo que el servidor contesta ahora
    let fallarRed = false;

    const api = {
        async get(ruta) {
            llamadas.push(ruta);
            if (fallarRed) throw new Error('sin señal');
            if (ruta === '/mesas') return respuestaMesas;
            if (ruta === '/platos') return [];
            return [];
        },
        async post() { return {}; },
    };

    // Reloj falso: guardamos el callback en vez de dejar que corra solo.
    let tick = null;
    const setIntervalFalso = (fn) => { tick = fn; return 1; };
    const clearIntervalFalso = () => { tick = null; };

    const ctx = {
        document,
        estado,
        api,
        setInterval: setIntervalFalso,
        clearInterval: clearIntervalFalso,
        console,
        showToast: () => {},
        formatCurrency: (n) => `S/ ${Number(n).toFixed(2)}`,
        escapeHtml: (s) => String(s),
        puedeVer: () => true,
        abrirModal: () => {},
        cerrarModal: () => {},
        NetworkError: class NetworkError extends Error {},
    };

    const nombres = Object.keys(ctx);
    const fn = new Function(...nombres, leer('frontend/js/mozo.js') + '\n; return { initMozo, refreshMozo, renderMesas };');
    const exportado = fn(...nombres.map((n) => ctx[n]));

    return {
        ...exportado,
        document,
        estado,
        llamadas,
        // Avanza una vuelta del reloj y espera a que termine el trabajo async.
        async tic() {
            if (!tick) throw new Error('No hay ningún intervalo andando');
            await tick();
        },
        hayIntervalo: () => tick !== null,
        servidorDevuelve(nuevas) { respuestaMesas = nuevas; },
        cortarRed(v = true) { fallarRed = v; },
        pintado: () => document.getElementById('mozo-mesas').innerHTML,
    };
}

// ---- Los tests ----------------------------------------------------------

describe('El reloj existe y pide mesas', () => {
    test('initMozo deja un intervalo andando', () => {
        const m = cargarMozo();
        assert.equal(m.hayIntervalo(), false, 'no debería haber reloj antes de initMozo');
        m.initMozo();
        assert.equal(m.hayIntervalo(), true,
            'EL BUG ORIGINAL: initMozo pintaba una vez y no dejaba ningún reloj');
    });

    test('cada vuelta le pregunta al servidor por las mesas', async () => {
        const m = cargarMozo();
        m.initMozo();
        m.llamadas.length = 0;

        await m.tic();

        assert.ok(m.llamadas.includes('/mesas'),
            `esperaba una consulta a /mesas, hubo: ${JSON.stringify(m.llamadas)}`);
    });
});

describe('Lo que cambia en OTRO dispositivo aparece acá', () => {
    test('una mesa que se ocupó desde otro teléfono se pinta sola', async () => {
        // Este es EXACTAMENTE el caso reportado: el admin carga un pedido en
        // la mesa 4 desde su teléfono, y el del mozo tiene que enterarse sin
        // que el mozo toque nada.
        const m = cargarMozo({ mesas: [mesa(1), mesa(4)] });
        m.initMozo();
        await m.tic();
        assert.ok(!m.pintado().includes('S/ 8.00'), 'la mesa 4 todavía no tenía cuenta');

        m.servidorDevuelve([mesa(1), mesa(4, { estado: 'ocupada', cuenta_actual: 8 })]);
        await m.tic();

        assert.ok(m.pintado().includes('S/ 8.00'),
            'la mesa ocupada desde otro dispositivo tiene que aparecer sin intervención');
        assert.ok(m.pintado().includes('ocupada'), 'y con su clase de ocupada');
    });

    test('una mesa NUEVA que creó el admin aparece sola', async () => {
        const m = cargarMozo({ mesas: [mesa(1)] });
        m.initMozo();
        await m.tic();

        m.servidorDevuelve([mesa(1), mesa(2), mesa(3)]);
        await m.tic();

        const html = m.pintado();
        assert.ok(html.includes('>2<') && html.includes('>3<'),
            'las mesas agregadas por el admin tienen que aparecer sin recargar la app');
    });
});

describe('Los guardias frenan lo justo, ni de más ni de menos', () => {
    test('con un modal abierto NO se repinta (el dedo está eligiendo platos)', async () => {
        const m = cargarMozo({ mesas: [mesa(1)] });
        m.initMozo();
        await m.tic();
        const antes = m.pintado();

        // Aparece un modal abierto, como al armar un pedido.
        const modal = m.document.createElement('div');
        modal.className = 'modal';
        m.document.body.appendChild(modal);

        m.servidorDevuelve([mesa(1, { estado: 'ocupada', cuenta_actual: 99 })]);
        await m.tic();

        assert.equal(m.pintado(), antes,
            'repintar con un modal abierto mueve la grilla bajo el dedo: un plato equivocado');
    });

    test('un modal CERRADO no frena nada', async () => {
        const m = cargarMozo({ mesas: [mesa(1)] });
        m.initMozo();
        await m.tic();

        const modal = m.document.createElement('div');
        modal.className = 'modal hidden';   // cerrado
        m.document.body.appendChild(modal);

        m.servidorDevuelve([mesa(1, { estado: 'ocupada', cuenta_actual: 99 })]);
        await m.tic();

        assert.ok(m.pintado().includes('S/ 99.00'),
            'un modal oculto no debería congelar la pantalla');
    });

    test('en otra pestaña no se gasta red', async () => {
        const m = cargarMozo();
        m.initMozo();
        m.estado.currentTab = 'admin';
        m.llamadas.length = 0;

        await m.tic();

        assert.equal(m.llamadas.length, 0, 'no hay para qué pedir mesas que nadie está mirando');
    });

    test('si nada cambió, no se reconstruye la grilla', async () => {
        // Un innerHTML cada 5s reinicia las transiciones de CSS y hace
        // parpadear la pantalla aunque no haya ninguna novedad.
        const m = cargarMozo({ mesas: [mesa(1)] });
        m.initMozo();
        await m.tic();

        const nodoAntes = m.document.getElementById('mozo-mesas').firstChild;
        await m.tic();   // misma respuesta del servidor
        const nodoDespues = m.document.getElementById('mozo-mesas').firstChild;

        assert.equal(nodoAntes, nodoDespues, 'sin cambios no debería tocarse el DOM');
    });
});

describe('Sin señal', () => {
    test('se sigue mostrando lo último conocido, no una pantalla en blanco', async () => {
        const m = cargarMozo({ mesas: [mesa(1, { estado: 'ocupada', cuenta_actual: 25 })] });
        m.initMozo();
        await m.tic();
        assert.ok(m.pintado().includes('S/ 25.00'));

        m.cortarRed();
        await m.tic();

        assert.ok(m.pintado().includes('S/ 25.00'),
            'una pantalla desactualizada es más útil que una vacía a media atención');
    });

    test('al volver la señal se vuelve a actualizar solo', async () => {
        const m = cargarMozo({ mesas: [mesa(1)] });
        m.initMozo();
        await m.tic();

        m.cortarRed();
        await m.tic();

        m.cortarRed(false);
        m.servidorDevuelve([mesa(1, { estado: 'ocupada', cuenta_actual: 42 })]);
        await m.tic();

        assert.ok(m.pintado().includes('S/ 42.00'),
            'el reloj no puede quedarse muerto después de un corte de señal');
    });
});
