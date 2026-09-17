/**
 * Prepara lo que va DENTRO del APK.
 *
 * Capacitor copia `webDir` entero, y `frontend/` tiene cosas que no son la
 * app sino datos del restaurante. La más pesada: las fotos de los platos.
 * Hoy son 1 MB de los 1,6 MB de la carpeta — el 64% del bundle— y el número
 * SUBE cada vez que un admin carga una foto. Sin este paso, el APK engorda
 * solo, y encima cada instalación se llevaría las fotos de UN restaurante a
 * los celulares de todos.
 *
 * Las fotos ya se sirven desde el servidor en tiempo de ejecución; el APK no
 * las necesita.
 *
 *    node tools/preparar-apk.mjs      (o: npm run preparar-apk)
 */

import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const raiz = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const origen = path.join(raiz, 'frontend');
const destino = path.join(raiz, 'dist-apk');

// Rutas (relativas a frontend/) que NO viajan dentro del APK.
const EXCLUIR = [
    // Fotos subidas por cada restaurante. Datos de instancia, no de la app.
    'assets/platos',
    // El Service Worker no se registra en nativo (ver index.html): sus
    // archivos ya viven dentro del APK, y su caché sobreviviría a la
    // actualización sirviendo JS viejo.
    'sw.js',
];

function excluido(relativo) {
    const norm = relativo.split(path.sep).join('/');
    return EXCLUIR.some(e => norm === e || norm.startsWith(e + '/'));
}

function copiar(dirOrigen, dirDestino, base = '') {
    fs.mkdirSync(dirDestino, { recursive: true });
    let bytes = 0;
    for (const entrada of fs.readdirSync(dirOrigen, { withFileTypes: true })) {
        const rel = base ? path.join(base, entrada.name) : entrada.name;
        if (excluido(rel)) continue;

        const desde = path.join(dirOrigen, entrada.name);
        const hasta = path.join(dirDestino, entrada.name);
        if (entrada.isDirectory()) {
            bytes += copiar(desde, hasta, rel);
        } else {
            fs.copyFileSync(desde, hasta);
            bytes += fs.statSync(desde).size;
        }
    }
    return bytes;
}

function pesar(dir) {
    let total = 0;
    for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
        const p = path.join(dir, e.name);
        total += e.isDirectory() ? pesar(p) : fs.statSync(p).size;
    }
    return total;
}

if (!fs.existsSync(origen)) {
    console.error('No encuentro frontend/. Corré esto desde la raíz del proyecto.');
    process.exit(1);
}

fs.rmSync(destino, { recursive: true, force: true });
const copiados = copiar(origen, destino);
const original = pesar(origen);

const mb = (n) => (n / 1024 / 1024).toFixed(2) + ' MB';
console.log(`frontend/  ${mb(original)}`);
console.log(`dist-apk/  ${mb(copiados)}   (${mb(original - copiados)} fuera del APK)`);
console.log('\nListo. Ahora: npx cap sync android');
