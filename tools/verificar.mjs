/**
 * TODAS las verificaciones del repo, en orden, con un solo comando:
 *
 *     npm run verificar
 *
 * Se detiene en la primera que falla y dice cuál fue. Es lo que hay que correr
 * antes de cada commit: si esto pasa en verde, el commit no rompe nada que la
 * suite sepa ver.
 *
 *   1. Flutter: formato (sin cambios pendientes), analyze, pruebas
 *   2. web/ al día con flutter_app/ (la compilación publicada no quedó atrás)
 *   3. Frontend viejo (fuente del APK): pruebas de la impresora térmica
 *   4. Backend: pytest completo
 */

import { spawnSync } from 'child_process';
import path from 'path';
import { fileURLToPath } from 'url';

const raiz = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const app = path.join(raiz, 'flutter_app');
const win = process.platform === 'win32';
const flutterBin = process.env.FLUTTER_BIN || (win ? 'C:\\src\\flutter\\bin' : '');
const herramienta = (n) => (flutterBin ? path.join(flutterBin, win ? `${n}.bat` : n) : n);

const PASOS = [
    ['Flutter · formato', herramienta('dart'), ['format', '--output=none', '--set-exit-if-changed', 'lib', 'test'], app],
    ['Flutter · analyze', herramienta('flutter'), ['analyze'], app],
    ['Flutter · pruebas', herramienta('flutter'), ['test'], app],
    ['web/ al día', process.execPath, [path.join(raiz, 'tools', 'flutter-web.mjs'), '--check'], raiz],
    ['APK · impresora térmica', process.execPath, ['--test', 'tests/frontend/*.test.mjs'], raiz],
    ['Backend · pytest', process.execPath, [path.join(raiz, 'tools', 'tests-backend.mjs'), '-p', 'no:warnings'], raiz],
];

for (const [nombre, cmd, args, cwd] of PASOS) {
    console.log(`\n==> ${nombre}`);
    // Los .bat de Flutter en Windows solo corren a través de cmd.exe.
    const r = win && cmd.endsWith('.bat')
        ? spawnSync('cmd.exe', ['/d', '/c', cmd, ...args], { cwd, stdio: 'inherit' })
        : spawnSync(cmd, args, { cwd, stdio: 'inherit' });
    if (r.status !== 0) {
        console.error(`\n✗ Falló: ${nombre}`);
        process.exit(r.status || 1);
    }
}
console.log('\n✓ Todo en verde');
