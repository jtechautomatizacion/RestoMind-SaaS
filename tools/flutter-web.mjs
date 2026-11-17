/**
 * Compila la app web (flutter_app/) y la publica en web/, que es lo que sirve
 * FastAPI en "/".
 *
 *     node tools/flutter-web.mjs           compila y publica   (npm run web)
 *     node tools/flutter-web.mjs --check   falla si web/ quedó atrás del código
 *
 * POR QUÉ web/ VA EN EL REPO
 * --------------------------
 * Producción se actualiza con `git pull` (deploy/deploy.sh) y el VPS no tiene
 * el SDK de Flutter: compilar allá exigiría instalarlo, o una imagen de 2 GB en
 * un servidor de 4. Así que la compilación viaja en el commit, ya verificada.
 *
 * El riesgo de una copia en el repo es que se quede atrás de su fuente y nadie
 * lo note (ya pasó con el APK: ver tools/compilar.mjs). Por eso web/BUILD.json
 * guarda la huella SHA-256 de todo lo que entra a la compilación, y `--check`
 * —que corre dentro de `npm run verificar`— falla si no coincide.
 *
 * QUÉ SE PUBLICA
 * --------------
 * La compilación JS (no la WebAssembly) usa solo canvaskit/canvaskit.* y
 * canvaskit/chromium/canvaskit.*. El resto de canvaskit/ (skwasm, wimp,
 * webparagraph, los .symbols de depuración) son ~25 MB que nunca se cargan.
 */

import { spawnSync } from 'child_process';
import crypto from 'crypto';
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const raiz = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const app = path.join(raiz, 'flutter_app');
const destino = path.join(raiz, 'web');
const sello = path.join(destino, 'BUILD.json');

// Lo que entra a la compilación. Si cambia cualquiera de estos, web/ está vieja.
const FUENTES = ['lib', 'web', 'assets', 'pubspec.yaml', 'pubspec.lock'];

function archivos(dir) {
    if (!fs.existsSync(dir)) return [];
    if (fs.statSync(dir).isFile()) return [dir];
    return fs.readdirSync(dir, { withFileTypes: true }).flatMap((e) =>
        archivos(path.join(dir, e.name)),
    );
}

function huella() {
    const h = crypto.createHash('sha256');
    const lista = FUENTES.flatMap((f) => archivos(path.join(app, f)))
        .map((a) => path.relative(app, a).split(path.sep).join('/'))
        .sort();
    for (const rel of lista) {
        h.update(rel);
        // Fin de línea normalizado: un checkout en Linux y otro en Windows
        // tienen que dar la misma huella.
        const contenido = fs.readFileSync(path.join(app, rel));
        h.update(/\.(dart|yaml|lock|json|html|md|txt)$/.test(rel)
            ? Buffer.from(contenido.toString('utf8').replace(/\r\n/g, '\n'))
            : contenido);
    }
    return h.digest('hex');
}

function version() {
    const m = fs.readFileSync(path.join(app, 'pubspec.yaml'), 'utf8').match(/^version:\s*([^\s+]+)/m);
    return m ? m[1] : '0.0.0';
}

if (process.argv.includes('--check')) {
    const actual = huella();
    const publicado = fs.existsSync(sello) ? JSON.parse(fs.readFileSync(sello, 'utf8')) : null;
    if (!publicado || publicado.fuente_sha256 !== actual) {
        console.error('✗ web/ no corresponde al código de flutter_app/. Corra: npm run web');
        process.exit(1);
    }
    console.log(`✓ web/ al día con flutter_app/ (versión ${publicado.version})`);
    process.exit(0);
}

const flutter = process.env.FLUTTER
    || (process.platform === 'win32' ? 'C:\\src\\flutter\\bin\\flutter.bat' : 'flutter');
const v = version();
console.log(`==> Compilando RestoMind web ${v}`);
const args = [
    'build', 'web', '--release',
    '--no-web-resources-cdn', // CanvasKit y fuentes desde el propio servidor (CSP)
    '--csp',                  // sin eval ni new Function en el JS generado
    '--no-wasm-dry-run',
    `--dart-define=APP_VERSION=${v}`,
];
// En Windows flutter es un .bat, que Node solo ejecuta a través de cmd.exe.
const r = process.platform === 'win32'
    ? spawnSync('cmd.exe', ['/d', '/c', flutter, ...args], { cwd: app, stdio: 'inherit' })
    : spawnSync(flutter, args, { cwd: app, stdio: 'inherit' });
if (r.status !== 0) {
    console.error('✗ Falló la compilación');
    process.exit(r.status || 1);
}

const origen = path.join(app, 'build', 'web');
const NO_SE_USA = /^canvaskit\/(?!canvaskit\.(js|wasm)$|chromium\/canvaskit\.(js|wasm)$)|\.symbols$/;
fs.rmSync(destino, { recursive: true, force: true });
let total = 0;
for (const a of archivos(origen)) {
    const rel = path.relative(origen, a).split(path.sep).join('/');
    if (NO_SE_USA.test(rel)) continue;
    const salida = path.join(destino, rel);
    fs.mkdirSync(path.dirname(salida), { recursive: true });
    fs.copyFileSync(a, salida);
    total += fs.statSync(a).size;
}
fs.writeFileSync(sello, JSON.stringify({
    version: v,
    fuente_sha256: huella(),
    compilado_en: new Date().toISOString(),
}, null, 2) + '\n');
console.log(`✓ Publicada en web/ (${(total / 1048576).toFixed(1)} MB). Recuerde hacer commit de web/.`);
