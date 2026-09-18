/**
 * Renderiza en consola cómo saldría un ticket por la térmica, en los dos
 * anchos de papel. Sirve para ver el formato sin tener la impresora.
 *
 *     npm run probar-termica
 */

import { parseHTML } from 'linkedom';
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const raiz = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const { DOMParser, document } = parseHTML('<html><body></body></html>');

const ventana = {};
const src = fs.readFileSync(path.join(raiz, 'frontend/js/impresora-termica.js'), 'utf8');
new Function('window', 'DOMParser', 'document', 'localStorage', 'btoa', 'console', src)(
    ventana, DOMParser, document,
    { getItem: () => null, setItem: () => {} },
    (s) => Buffer.from(s, 'binary').toString('base64'),
    console
);

const ticket = `<!DOCTYPE html><html><body>
  <div class="ticket-header"><h1>COCINA</h1><div class="ticket-mesa">MESA 5</div></div>
  <div class="ticket-meta">16/09/2026 &middot; 14:32</div>
  <table>
    <tr><td class="cant">2x</td><td class="nombre">Ceviche Clasico Mixto Especial de la Casa</td><td class="precio">S/ 90.00</td></tr>
    <tr><td class="cant">1x</td><td class="nombre">Jugo de Naranja grande</td><td class="precio">S/ 5.00</td></tr>
  </table>
  <div class="ticket-total"><span>TOTAL</span><span>S/ 95.00</span></div>
</body></html>`;

// Los bytes de comando ESC/POS no se imprimen en papel; acá se descartan
// para ver solo lo que el cajero va a leer.
function comoSeVe(bytes) {
    const lineas = [];
    let actual = '';
    for (let i = 0; i < bytes.length; i++) {
        const b = bytes[i];
        if (b === 0x1B) { i += (bytes[i + 1] === 0x40 ? 1 : 2); continue; }  // ESC
        if (b === 0x1D) { i += (bytes[i + 1] === 0x56 ? 3 : 2); continue; }  // GS
        if (b === 0x0A) { lineas.push(actual); actual = ''; continue; }
        if (b >= 0x20 && b <= 0x7E) actual += String.fromCharCode(b);
    }
    if (actual) lineas.push(actual);
    return lineas;
}

// Calcado de _ticketPreventaHTML() en frontend/js/print.js
const preventa = `<!DOCTYPE html><html><body>
  <div class="centro datos-negocio">
    <div class="comercial">Cevicheria El Puerto de Susy</div>
    <div>Av. Los Pescadores 123</div>
    <div>RUC: 10410827803</div>
    <div class="tipo">PRE-VENTA</div>
    <div class="aviso">NO ES COMPROBANTE DE PAGO</div>
  </div>
  <div class="linea"></div>
  <div class="campos"><span>MESA: 5</span><span>N&ordm; 13</span></div>
  <div class="campos"><span>16/09/2026 22:41</span><span>Joseph</span></div>
  <div class="linea"></div>
  <table>
    <thead><tr><th>Articulo</th><th class="num">Cant</th><th class="num">Importe</th></tr></thead>
    <tbody>
      <tr><td class="nombre">Ceviche Clasico Mixto Especial de la Casa</td><td class="cant">2</td><td class="precio">90.00</td></tr>
      <tr><td class="nombre">Jugo de Naranja</td><td class="cant">1</td><td class="precio">5.00</td></tr>
    </tbody>
  </table>
  <div class="total-caja"><div class="rotulo">TOTAL A PAGAR</div><div class="monto">S/ 95.00</div></div>
  <div class="instruccion">ENTREGUE ESTA HOJA EN CAJA</div>
  <div class="pie">GRACIAS POR SU PREFERENCIA</div>
</body></html>`;

for (const [etiqueta, doc] of [['COCINA', ticket], ['PRE-VENTA', preventa]]) {
    for (const [mm, cols] of [['80', 48]]) {
        const bytes = ventana.ImpresoraTermica._convertir(doc, cols, 'escpos');
        console.log(`
${etiqueta} — ${mm} mm — ${cols} col — ${bytes.length} bytes`);
        console.log('+' + '-'.repeat(cols) + '+');
        for (const l of comoSeVe(bytes)) console.log('|' + l.padEnd(cols).slice(0, cols) + '|');
        console.log('+' + '-'.repeat(cols) + '+');
    }
}

// El mismo ticket en su variante PARA LLEVAR: ya esta pagado, asi que no
// puede decir "TOTAL A PAGAR" ni mandar al cliente a la caja.
const paraLlevar = preventa
    .replace('<div class="tipo">PRE-VENTA</div>', '<div class="tipo">PARA LLEVAR</div>')
    .replace('<div class="rotulo">TOTAL A PAGAR</div>', '<div class="rotulo">TOTAL PAGADO</div>')
    .replace('<div class="instruccion">ENTREGUE ESTA HOJA EN CAJA</div>',
             '<div class="instruccion">SU PEDIDO: N° 63</div>')
    .replace('<span>MESA: 5</span>', '<span>PARA LLEVAR</span>');

const bytesLlevar = ventana.ImpresoraTermica._convertir(paraLlevar, 48, 'escpos');
console.log('\nPARA LLEVAR (ESC/POS) - lo que lee el cliente');
console.log('+' + '-'.repeat(48) + '+');
for (const l of comoSeVe(bytesLlevar)) console.log('|' + l.padEnd(48).slice(0, 48) + '|');
console.log('+' + '-'.repeat(48) + '+');

const tspl = ventana.ImpresoraTermica._convertir(preventa, 48, 'tspl');
console.log('');
console.log('TSPL (impresora de etiquetas) - ' + tspl.length + ' bytes');
console.log(Buffer.from(tspl).toString('ascii').trim());

/**
 * Dibuja el TSPL, en vez de listarlo.
 *
 * Leer "TEXT 477,422" no dice si el importe se encima con la cantidad ni si
 * el recuadro encierra lo que tiene que encerrar — y esos son justamente los
 * defectos que aparecen en el papel. Revisar coordenadas a ojo ya dejo pasar
 * un texto superpuesto y un recuadro descentrado. Esto los muestra.
 *
 * Es una maqueta a escala, no el resultado real: la impresora dibuja las
 * fuentes con su propio ancho, que es la razon por la que existe HOLGURA.
 * Sirve para ver la COMPOSICION —que nada choque, que todo cierre— no para
 * medir milimetros.
 */
function dibujar(bytes, anchoCabezal) {
    const texto = Buffer.from(bytes).toString('ascii');
    const PPC = 10;   // puntos por caracter, horizontal
    const PPF = 16;   // puntos por fila, vertical

    let anchoDeclarado = 640, altoPuntos = 800;
    const m = texto.match(/SIZE (\d+) mm,(\d+) mm/);
    if (m) { anchoDeclarado = +m[1] * 8; altoPuntos = +m[2] * 8; }

    // EL LIMITE ES EL CABEZAL, NO LO QUE DECLARA EL CODIGO.
    //
    // La primera version de esta comprobacion media contra el SIZE del propio
    // TSPL generado, y por eso no sirvio para nada: si el codigo se equivoca y
    // declara 80 mm donde el cabezal cubre 72, el dibujo se agranda con el
    // error y todo "entra" perfecto — mientras el papel sale partido. Una
    // prueba que se mide contra la afirmacion que quiere verificar siempre
    // pasa. El ancho del cabezal es un dato FISICO y entra desde afuera.
    const anchoPuntos = anchoCabezal;
    if (anchoDeclarado > anchoCabezal) {
        console.log(`\n[!] SIZE declara ${anchoDeclarado} puntos pero el cabezal cubre ${anchoCabezal}.`);
    }

    const cols = Math.ceil(anchoPuntos / PPC);
    const filas = Math.ceil(altoPuntos / PPF);
    const lienzo = Array.from({ length: filas }, () => new Array(cols).fill(' '));
    const desbordes = [];

    const poner = (fila, col, cadena, pasoPuntos) => {
        if (fila < 0 || fila >= filas) return;
        // `pasoPuntos` = cuanto avanza la impresora por caracter. Sin esto el
        // dibujo daria todas las fuentes del mismo ancho, y justo el renglon
        // mas ancho —el total, en fuente 4— es el que mas riesgo tiene de
        // chocar con lo de al lado. Un previsualizador que no ve ese choque
        // no sirve para lo unico que se le pide.
        const paso = (pasoPuntos || PPC) / PPC;
        for (let i = 0; i < cadena.length; i++) {
            const c = col + Math.round(i * paso);
            if (c < 0) continue;
            // Lo que cae fuera del cabezal NO se pierde: la impresora lo
            // envuelve al renglon siguiente y el ticket sale partido
            // ("Importe" -> "Impo"/"rte"). Antes esto se descartaba en
            // silencio, asi que el dibujo salia perfecto mientras el papel
            // salia roto. Ahora se cuenta y se denuncia.
            if (c >= cols) { desbordes.push(cadena.slice(i) + '  (de "' + cadena + '")'); return; }
            // Si ya hay algo distinto de un espacio, los dos textos se estan
            // pisando. Se marca con '#' para que salte a la vista.
            lienzo[fila][c] = lienzo[fila][c] === ' ' ? cadena[i] : '#';
        }
    };

    // Los mismos anchos que usa el emisor, con su misma holgura del 15%.
    const ANCHO_FUENTE = { '1': 8, '2': 12, '3': 16, '4': 24 };

    for (const linea of texto.split(/\r?\n/)) {
        let g;
        if ((g = linea.match(/^TEXT (\d+),(\d+),"(\d)",\d+,\d+,\d+,"(.*)"$/))) {
            poner(Math.round(+g[2] / PPF), Math.round(+g[1] / PPC), g[4],
                  (ANCHO_FUENTE[g[3]] || 12) * 1.15);
        } else if ((g = linea.match(/^BAR (\d+),(\d+),(\d+),(\d+)$/))) {
            poner(Math.round(+g[2] / PPF), Math.round(+g[1] / PPC),
                  '-'.repeat(Math.round(+g[3] / PPC)));
        } else if ((g = linea.match(/^BOX (\d+),(\d+),(\d+),(\d+),(\d+)$/))) {
            const [x1, y1, x2, y2] = [+g[1], +g[2], +g[3], +g[4]];
            const c1 = Math.round(x1 / PPC), c2 = Math.round(x2 / PPC);
            const f1 = Math.round(y1 / PPF), f2 = Math.round(y2 / PPF);
            poner(f1, c1, '+' + '-'.repeat(Math.max(0, c2 - c1 - 1)) + '+');
            poner(f2, c1, '+' + '-'.repeat(Math.max(0, c2 - c1 - 1)) + '+');
            for (let f = f1 + 1; f < f2; f++) { poner(f, c1, '|'); poner(f, c2, '|'); }
        }
    }

    console.log('\nASI QUEDA LA HOJA  (# = textos superpuestos)');
    console.log('.' + '.'.repeat(cols) + '.');
    for (const f of lienzo) console.log(':' + f.join('') + ':');
    console.log("'" + "'".repeat(cols) + "'");

    const choques = lienzo.filter(f => f.includes('#')).length;
    console.log(choques ? `\n[!] ${choques} fila(s) con texto superpuesto` : '\nSin superposiciones.');

    if (desbordes.length) {
        console.log(`[!] ${desbordes.length} texto(s) se salen del cabezal (${anchoPuntos} puntos).`);
        console.log('    La impresora los ENVUELVE al renglon siguiente:');
        for (const d of desbordes) console.log('      -> ' + d);
    } else {
        console.log(`Nada se sale del ancho imprimible (${anchoPuntos} puntos).`);
    }
}

// 576 puntos = 72 mm. Es el ancho REAL del cabezal en un rollo de 80 mm, y
// esta escrito aca —a mano, fuera del codigo que se quiere probar— justamente
// para que siga siendo un dato independiente. Medido sobre el papel: cuatro
// textos distintos cortaron entre el punto 574 y el 575.
dibujar(tspl, 576);
