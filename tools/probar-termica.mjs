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
    <div>BALBIN LEIVA CONSUELO SUSY</div>
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

const tspl = ventana.ImpresoraTermica._convertir(preventa, 48, 'tspl');
console.log('');
console.log('TSPL (impresora de etiquetas) - ' + tspl.length + ' bytes');
console.log(Buffer.from(tspl).toString('ascii').trim());
