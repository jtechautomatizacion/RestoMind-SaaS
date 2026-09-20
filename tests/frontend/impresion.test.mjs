/**
 * Lo que sale por la impresora térmica, probado SIN impresora.
 *
 * POR QUÉ EXISTE ESTE ARCHIVO
 * ---------------------------
 * El conversor de tickets es lógica pura —entra HTML, salen bytes— pero vive
 * en el navegador, así que hasta ahora la única forma de verificarlo era
 * imprimir y mirar el papel. Eso costó una sesión entera: se arreglaba algo,
 * se compilaba, se instalaba, se imprimía, y recién ahí se veía el resultado.
 * Cada vuelta eran minutos, y varios "arreglos" resultaron no estar siquiera
 * dentro del APK.
 *
 * Todos los tests de acá cubren un bug REAL que ya pasó en producción. No son
 * hipótesis: son las frases que tienen que seguir siendo verdad para que el
 * papel salga bien.
 *
 *     node --test tests/frontend/
 *
 * CÓMO CORRE CÓDIGO DEL NAVEGADOR EN NODE
 * ---------------------------------------
 * `impresora-termica.js` y `print.js` son scripts clásicos (sin `import`/
 * `export`, a propósito — ver la cabecera de capacitor-init.js). Se cargan
 * con `new Function(...)` y se les da el puñado de globales del navegador que
 * tocan: DOMParser (vía linkedom), document y localStorage. Nada más hace
 * falta, y esa es justamente la señal de que el conversor está bien aislado.
 */

import { test, describe } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import path from 'node:path';
import { parseHTML } from 'linkedom';

const raiz = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', '..');
const leer = (p) => readFileSync(path.join(raiz, p), 'utf8');

// ---- El entorno mínimo de navegador -----------------------------------

function cargarConversor({ lenguaje = 'tspl' } = {}) {
    const { DOMParser, document } = parseHTML('<html><body></body></html>');
    const almacen = new Map([[
        'restomind_impresora',
        JSON.stringify({ tipo: 'bluetooth', destino: 'AA:BB', lenguaje, ancho: '80' }),
    ]]);

    const ventana = {};
    ventana.window = ventana;
    ventana.DOMParser = DOMParser;
    ventana.document = document;
    ventana.localStorage = {
        getItem: (k) => (almacen.has(k) ? almacen.get(k) : null),
        setItem: (k, v) => almacen.set(k, String(v)),
        removeItem: (k) => almacen.delete(k),
    };
    document.addEventListener = () => {};

    // `with` para que el script vea estos globales sin ensuciar los de Node:
    // dos tests con configuraciones distintas no pueden pisarse entre sí.
    const fn = new Function('entorno', `with (entorno) { ${leer('frontend/js/impresora-termica.js')} }`);
    fn(ventana);
    return ventana.ImpresoraTermica;
}

/** El ticket tal como sale, en texto: sirve para TSPL (que ya es texto) y,
 *  en ESC/POS, después de quitarle las secuencias de control. */
function aTexto(bytes) {
    return Buffer.from(bytes).toString('latin1');
}

function papelEscPos(bytes) {
    return aTexto(bytes)
        .replace(/\x1B@/g, '')
        .replace(/\x1B[aE!]./g, '')
        .replace(/\x1D!./g, '')
        .replace(/\x1Bd./g, '')
        .replace(/\x1DV../g, '');
}

const TICKET_CON_TOTALES = `<!DOCTYPE html><html><body>
    <div class="ticket-header"><h1>RESTOMIND</h1></div>
    <table>
      <tr><td class="cant">1x</td><td class="nombre">Ceviche</td><td class="precio">12.00</td></tr>
    </table>
    <div class="totales">
        <div><span>Sub-Total:</span><span>S/ 10.17</span></div>
        <div><span>IGV (18%):</span><span>S/ 1.83</span></div>
        <div class="total"><span>Total Venta:</span><span>S/ 12.00</span></div>
    </div>
</body></html>`;

// ============================================================
describe('TSPL — la impresora no se puede trabar con "no seam"', () => {

    test('no se manda ningun FEED despues del PRINT', () => {
        const IT = cargarConversor({ lenguaje: 'tspl' });
        const salida = aTexto(IT._convertir(TICKET_CON_TOTALES, 48, 'tspl'));

        // FEED mueve el papel DESPUES de que la etiqueta termino, y deja a la
        // impresora parada a mitad de etiqueta. El trabajo siguiente sale a
        // buscar la separacion, no la encuentra en papel continuo y se traba.
        assert.ok(
            !/^FEED /m.test(salida),
            'volvio el FEED despues del PRINT: el segundo ticket de cualquier tanda se va a trabar',
        );
    });

    test('PRINT es el ultimo comando del trabajo', () => {
        const IT = cargarConversor({ lenguaje: 'tspl' });
        const lineas = aTexto(IT._convertir(TICKET_CON_TOTALES, 48, 'tspl'))
            .split('\r\n').filter(Boolean);

        assert.equal(lineas[lineas.length - 1], 'PRINT 1,1');
    });

    test('la cola para romper el papel va sumada al alto de la etiqueta', () => {
        const IT = cargarConversor({ lenguaje: 'tspl' });
        const salida = aTexto(IT._convertir(TICKET_CON_TOTALES, 48, 'tspl'));

        const size = salida.match(/^SIZE \d+ mm,(\d+) mm/m);
        assert.ok(size, 'no se emitio el SIZE');
        const altoDeclarado = Number(size[1]);

        // La ultima coordenada dibujada, en milimetros (8 puntos por mm).
        const ys = [...salida.matchAll(/^(?:TEXT|BAR|BOX) \d+,(\d+)/gm)].map(m => Number(m[1]));
        const ultimoMm = Math.ceil(Math.max(...ys) / 8);

        // Sin la cola adentro del SIZE, la barra de corte —que esta ~12 mm mas
        // alla del cabezal— cae sobre el texto y la hoja se rompe encima.
        assert.ok(
            altoDeclarado - ultimoMm >= 12,
            `la etiqueta mide ${altoDeclarado} mm y el contenido llega a ${ultimoMm} mm: `
            + 'no queda cola suficiente para romper el papel',
        );
    });

    test('se apaga el modo tear, que es el que obliga a reposicionar', () => {
        const IT = cargarConversor({ lenguaje: 'tspl' });
        assert.match(aTexto(IT._convertir(TICKET_CON_TOTALES, 48, 'tspl')), /^SET TEAR OFF$/m);
    });

    test('el papel se declara CONTINUO, no etiquetas', () => {
        const IT = cargarConversor({ lenguaje: 'tspl' });
        // GAP distinto de 0 la manda a buscar una separacion que un rollo
        // continuo no tiene.
        assert.match(aTexto(IT._convertir(TICKET_CON_TOTALES, 48, 'tspl')), /^GAP 0,0$/m);
    });

    test('una comilla en el nombre de un plato no corta el comando', () => {
        const IT = cargarConversor({ lenguaje: 'tspl' });
        const html = '<!DOCTYPE html><html><body><div>Pollo "a la brasa"</div></body></html>';
        const salida = aTexto(IT._convertir(html, 48, 'tspl'));

        // Sin escapar, la comilla cierra el TEXT antes de tiempo y la etiqueta
        // sale vacia, sin ningun error que lo explique.
        assert.match(salida, /\\"a la brasa\\"/);
    });
});

// ============================================================
describe('ESC/POS — los importes van alineados a la derecha', () => {

    test('cada total va en UNA linea, con su importe a la derecha', () => {
        const IT = cargarConversor({ lenguaje: 'escpos' });
        const papel = papelEscPos(IT._convertir(TICKET_CON_TOTALES, 48, 'escpos'));
        const lineas = papel.split('\n');

        for (const [etiqueta, importe] of [
            ['Sub-Total:', 'S/ 10.17'],
            ['IGV (18%):', 'S/ 1.83'],
            ['Total Venta:', 'S/ 12.00'],
        ]) {
            const linea = lineas.find(l => l.includes(etiqueta));
            assert.ok(linea, `no aparece "${etiqueta}" en el papel`);
            // El bug real: cada <span> caia en su propio renglon, asi que el
            // importe quedaba DEBAJO de su etiqueta en vez de al lado.
            assert.ok(
                linea.includes(importe),
                `"${etiqueta}" y "${importe}" salieron en renglones distintos`,
            );
            assert.ok(
                linea.trimEnd().endsWith(importe),
                `"${importe}" no quedo pegado al margen derecho: "${linea}"`,
            );
        }
    });

    test('las lineas de totales no exceden el ancho del papel', () => {
        const IT = cargarConversor({ lenguaje: 'escpos' });
        const papel = papelEscPos(IT._convertir(TICKET_CON_TOTALES, 48, 'escpos'));

        for (const linea of papel.split('\n')) {
            assert.ok(
                linea.length <= 48,
                `linea de ${linea.length} columnas en un papel de 48: "${linea}"`,
            );
        }
    });

    test('el total NO va en doble ancho, porque desalinearia la columna', () => {
        const IT = cargarConversor({ lenguaje: 'escpos' });
        const bruto = aTexto(IT._convertir(TICKET_CON_TOTALES, 48, 'escpos'));

        // GS ! con el nibble alto distinto de 0 = doble ancho. Eso parte el
        // ancho util a la mitad y rompe el alineado a la derecha justo en la
        // linea que se quiere leer de un golpe.
        const lineaTotal = bruto.slice(0, bruto.indexOf('Total Venta:'));
        const ultimoGS = [...lineaTotal.matchAll(/\x1D!(.)/g)].pop();
        if (ultimoGS) {
            assert.equal(
                ultimoGS[1].charCodeAt(0) & 0xF0, 0,
                'el renglon del total quedo en doble ancho y desalinea el importe',
            );
        }
    });

    test('hay una separacion antes del bloque de totales', () => {
        const IT = cargarConversor({ lenguaje: 'escpos' });
        const lineas = papelEscPos(IT._convertir(TICKET_CON_TOTALES, 48, 'escpos')).split('\n');
        const i = lineas.findIndex(l => l.includes('Sub-Total:'));

        assert.ok(i > 0, 'no aparece el bloque de totales');
        // En TSPL esa separacion la daba el recuadro; en ESC/POS, que escribe
        // corrido, sin regla el importe queda pegado al ultimo plato.
        assert.match(lineas[i - 1], /^-+$/, 'falta la regla que despega los totales del detalle');
    });
});

// ============================================================
describe('Qué papeles salen AL PEDIR', () => {

    /*
     * OJO CON LA CUENTA TOTAL: acá se prueba lo que sale AL MANDAR EL PEDIDO.
     * La boleta electrónica no entra en esta tabla porque sale al COBRAR (ver
     * imprimirBoletaVenta), así que el total por mesa termina siendo:
     *
     *                    al pedir        al cobrar     TOTAL
     *   En equipo        2 (cocina+pre)  + boleta  ->  3 con SUNAT
     *   Atiendo solo     1 (pre)         + boleta  ->  2 con SUNAT
     *
     * que es la matriz que pidió el dueño. Sin SUNAT no hay boleta, así que
     * el total es el de esta tabla: 2 y 1.
     */

    // _papelesAlPedir vive en print.js, que ademas define plantillas y toca
    // muchos globales. Se lo carga solo para leer esa funcion: es la tabla que
    // el dueño pidio explicitamente y la que no puede cambiar sin querer.
    function cargarPapeles() {
        const ventana = {};
        ventana.window = ventana;
        ventana.document = { addEventListener: () => {}, getElementById: () => null };
        ventana.estado = { usuario: {} };
        ventana.escapeHtml = (s) => String(s ?? '');
        ventana.showToast = () => {};
        ventana.api = { get: async () => ({}) };
        const fn = new Function('entorno', `with (entorno) {
            ${leer('frontend/js/print.js')}
            entorno.__papeles = _papelesAlPedir;
        }`);
        fn(ventana);
        return ventana.__papeles;
    }

    const casos = [
        // [atiendeSolo, conSunat, papeles esperados]
        [false, false, ['cocina', 'preventa']],
        [false, true, ['cocina', 'precuenta']],
        [true, false, ['preventa']],
        [true, true, ['precuenta']],
    ];

    for (const [atiendeSolo, conSunat, esperado] of casos) {
        const modo = atiendeSolo ? 'atiendo solo' : 'en equipo';
        const sunat = conSunat ? 'con SUNAT' : 'sin SUNAT';
        test(`${modo} ${sunat} -> al pedir salen ${esperado.length}: ${esperado.join(' + ')}`, () => {
            const papelesAlPedir = cargarPapeles();
            assert.deepEqual(papelesAlPedir({ atiendeSolo, conSunat }), esperado);
        });
    }

    test('en equipo SIEMPRE sale el ticket de cocina', () => {
        const papelesAlPedir = cargarPapeles();
        // Si cocina deja de recibir su papel, el pedido no se prepara: es el
        // unico de los cuatro documentos cuya ausencia frena el servicio.
        for (const conSunat of [false, true]) {
            assert.ok(papelesAlPedir({ atiendeSolo: false, conSunat }).includes('cocina'));
        }
    });

    test('atendiendo solo NUNCA sale el ticket de cocina', () => {
        const papelesAlPedir = cargarPapeles();
        // Quien atiende solo ya vio el pedido al tomarlo y lo tiene en la
        // pantalla de Cocina: ese papel seria papel tirado.
        for (const conSunat of [false, true]) {
            assert.ok(!papelesAlPedir({ atiendeSolo: true, conSunat }).includes('cocina'));
        }
    });
});
