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
 *    node tools/preparar-apk.mjs                    -> producción
 *    node tools/preparar-apk.mjs http://IP:8000     -> ese backend
 *
 * EL DESTINO DEL BACKEND
 * ----------------------
 * El segundo trabajo de este script es decidir contra qué servidor habla el
 * APK, sobrescribiendo `js/destino-api.js` EN LA COPIA. Nunca en `frontend/`:
 * si tocara el original, el árbol de trabajo quedaría apuntando a la PC de
 * quien compiló y eso terminaría commiteado, que es exactamente el problema
 * que esto viene a resolver.
 */

import fs from 'fs';
import os from 'os';
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

// --- El destino del backend -------------------------------------------------
//
// "local" se resuelve a la IP de esta PC en el wifi, EN CADA COMPILACION.
// Escribirla a mano una vez no sirve: el router la reparte por DHCP y cambia
// sola cada tantos días. Cuando eso pasa, el APK deja de conectar y en
// pantalla dice "Sin conexión" — que manda a revisar el wifi del local en vez
// del número que quedó viejo adentro del APK.
function ipDeEstaPC() {
    const candidatas = [];
    for (const [nombre, entradas] of Object.entries(os.networkInterfaces())) {
        for (const e of entradas || []) {
            if (e.family !== 'IPv4' || e.internal) continue;
            // Las interfaces virtuales (WSL, Docker, VirtualBox) tienen IP
            // propia y NO son alcanzables desde el celular. Elegir una de esas
            // da el mismo "Sin conexión" sin ninguna pista.
            if (/wsl|virtual|docker|vmware|loopback/i.test(nombre)) continue;
            candidatas.push({ nombre, ip: e.address });
        }
    }
    if (!candidatas.length) return null;
    // Se prefiere la del wifi: es la red donde va a estar el celular.
    const wifi = candidatas.find(c => /wi-?fi|wlan|inalámbric/i.test(c.nombre));
    return (wifi || candidatas[0]).ip;
}

let apiDestino = process.argv[2];
if (apiDestino === 'local') {
    const ip = ipDeEstaPC();
    if (!ip) {
        console.error('No pude encontrar la IP de esta PC en la red.\n'
            + 'Pasala a mano:  node tools/preparar-apk.mjs http://192.168.1.40:8000');
        process.exit(1);
    }
    apiDestino = `http://${ip}:8000`;
}

if (apiDestino) {
    if (!/^https?:\/\/[^\s/]+/.test(apiDestino)) {
        console.error(`Destino inválido: "${apiDestino}"\nEsperaba algo como http://192.168.1.40:8000`);
        process.exit(1);
    }
    const archivo = path.join(destino, 'js', 'destino-api.js');
    fs.writeFileSync(archivo, `// GENERADO AL COMPILAR — no editar. Ver tools/preparar-apk.mjs
window.RESTOMIND_API_DESTINO = ${JSON.stringify(apiDestino)};
`, 'utf8');
}

// Se lee del archivo que quedó en la copia, no de la variable: así lo que se
// anuncia es lo que de verdad va adentro del APK. Si el reemplazo fallara en
// silencio, el mensaje lo delataría en vez de confirmar algo que no pasó.
const destinoReal = (fs.readFileSync(path.join(destino, 'js', 'destino-api.js'), 'utf8')
    .match(/RESTOMIND_API_DESTINO\s*=\s*['"]([^'"]+)['"]/) || [])[1] || '(no encontrado)';

const mb = (n) => (n / 1024 / 1024).toFixed(2) + ' MB';
console.log(`frontend/  ${mb(original)}`);
console.log(`dist-apk/  ${mb(copiados)}   (${mb(original - copiados)} fuera del APK)`);
console.log(`\nEl APK va a hablar con:  ${destinoReal}`);
if (/^http:\/\//.test(destinoReal)) {
    console.log('  (texto plano: es un APK de PRUEBAS, no lo distribuyas)');
}
console.log('\nListo. Ahora: npx cap sync android');
