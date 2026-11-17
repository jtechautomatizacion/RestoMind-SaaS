/**
 * Levanta RestoMind COMPLETO en esta PC, igual que corre en producción:
 *
 *     npm run local          arranca todo; Ctrl+C apaga el backend
 *     npm run local:parar    apaga también el contenedor SUNAT
 *
 * Qué hace, en orden:
 *   1. Revisa que el .env tenga lo que el backend exige (sin mostrar valores).
 *   2. Si Docker Desktop está apagado, lo prende y espera al motor.
 *   3. Levanta el contenedor de firma SUNAT (docker compose, modo beta).
 *   4. Si web/ quedó atrás de flutter_app/, la recompila (npm run web).
 *   5. Arranca uvicorn SIN --reload en 127.0.0.1:8000, en PRIMER PLANO: sus logs
 *      salen en esta misma terminal y Ctrl+C lo apaga. En esta máquina Windows
 *      --reload detecta el cambio y nunca levanta el proceso nuevo (CLAUDE.md,
 *      "--reload NO RECARGA"): después de un cambio, Ctrl+C y de nuevo.
 *   6. Espera /health y confirma que no está sirviendo código viejo.
 *
 * Mismo esquema que el VPS: uvicorn sirve la API y la app web desde el mismo
 * origen (lo exige la cookie de sesión SameSite=Strict), y el contenedor SUNAT
 * escucha solo en 127.0.0.1:8100.
 */

import { spawn, spawnSync } from 'child_process';
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const raiz = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const win = process.platform === 'win32';
const URL_APP = 'http://localhost:8000';

const paso = (t) => console.log(`\n==> ${t}`);
const falla = (t) => {
    console.error(`\n✗ ${t}`);
    process.exit(1);
};
const correr = (cmd, args, opciones = {}) =>
    spawnSync(cmd, args, { cwd: raiz, encoding: 'utf8', ...opciones });
const esperar = (ms) => new Promise((r) => setTimeout(r, ms));

if (process.argv.includes('--parar')) {
    paso('Apagando el contenedor SUNAT');
    correr('docker', ['compose', 'stop', 'sunat-service'], { stdio: 'inherit' });
    console.log('\n✓ Todo apagado');
    process.exit(0);
}

// 1. .env ----------------------------------------------------------------
paso('Revisando .env');
const env = fs.existsSync(path.join(raiz, '.env')) ? fs.readFileSync(path.join(raiz, '.env'), 'utf8') : '';
for (const clave of ['SECRET_KEY', 'SUNAT_SERVICE_URL', 'SUNAT_SERVICE_TOKEN']) {
    if (!new RegExp(`^${clave}=.+`, 'm').test(env)) {
        falla(`Falta ${clave} en .env (vea .env.example). No se pone un valor por defecto en el código a propósito.`);
    }
}
console.log('  .env completo');

// 2. Docker --------------------------------------------------------------
paso('Revisando Docker Desktop');
if (correr('docker', ['info'], { stdio: 'ignore' }).status !== 0) {
    const ejecutable = [
        path.join(process.env.LOCALAPPDATA || '', 'Programs', 'DockerDesktop', 'Docker Desktop.exe'),
        'C:\\Program Files\\Docker\\Docker\\Docker Desktop.exe',
    ].find((p) => fs.existsSync(p));
    if (!ejecutable) falla('Docker no responde y no se encontró Docker Desktop. Ábralo a mano y reintente.');
    console.log('  Docker está apagado: abriendo Docker Desktop…');
    spawn(ejecutable, [], { detached: true, stdio: 'ignore' }).unref();
    let listo = false;
    for (let i = 0; i < 60 && !listo; i++) {
        await esperar(3000);
        listo = correr('docker', ['info'], { stdio: 'ignore' }).status === 0;
    }
    if (!listo) falla('Docker Desktop no terminó de arrancar en 3 minutos.');
}
console.log('  Motor de Docker listo');

// 3. Contenedor SUNAT ----------------------------------------------------
paso('Levantando el contenedor SUNAT (beta)');
if (correr('docker', ['compose', 'up', '-d', '--build', 'sunat-service'], { stdio: 'inherit' }).status !== 0) {
    falla('docker compose no pudo levantar sunat-service.');
}
let sunatOk = false;
for (let i = 0; i < 20 && !sunatOk; i++) {
    try {
        sunatOk = (await fetch('http://127.0.0.1:8100/health')).ok;
    } catch { /* todavía arrancando */ }
    if (!sunatOk) await esperar(2000);
}
console.log(sunatOk ? '  SUNAT responde en 127.0.0.1:8100' : '  ⚠ SUNAT no respondió: la app arranca igual, pero no podrá emitir boletas');

// 4. App web -------------------------------------------------------------
paso('Revisando la compilación de la app web');
if (correr(process.execPath, ['tools/flutter-web.mjs', '--check'], { stdio: 'inherit' }).status !== 0) {
    if (correr(process.execPath, ['tools/flutter-web.mjs'], { stdio: 'inherit' }).status !== 0) {
        falla('No se pudo compilar la app web.');
    }
}

// 5. Backend, en primer plano -------------------------------------------
paso('Arrancando el backend');
const ocupado = await fetch('http://127.0.0.1:8000/health').then(() => true, () => false);
if (ocupado) falla('Ya hay algo escuchando en el puerto 8000. Ciérrelo (Ctrl+C en su terminal) y reintente.');
const python = path.join(raiz, '.venv', win ? 'Scripts' : 'bin', win ? 'python.exe' : 'python');
if (!fs.existsSync(python)) falla('No existe .venv. Créelo con: python -m venv .venv && pip install -r requirements.txt');
const backend = spawn(python, ['-m', 'uvicorn', 'backend.app:app', '--host', '127.0.0.1', '--port', '8000'], {
    cwd: raiz,
    stdio: 'inherit',
});
backend.on('exit', (codigo) => process.exit(codigo ?? 0));
process.on('SIGINT', () => backend.kill('SIGINT'));

// 6. Salud ---------------------------------------------------------------
let salud = null;
for (let i = 0; i < 40 && !salud; i++) {
    await esperar(1500);
    try {
        const r = await fetch('http://127.0.0.1:8000/health');
        if (r.ok) salud = await r.json();
    } catch { /* arrancando */ }
}
if (!salud) {
    backend.kill();
    falla('El backend no respondió. Revise los mensajes de arriba.');
}

console.log(`
✓ RestoMind corriendo en local

  App web (PWA):   ${URL_APP}
  Superadmin:      ${URL_APP}/static/superadmin.html
  Docs de la API:  ${URL_APP}/docs

  Ctrl+C apaga el backend. El contenedor SUNAT sigue arriba
  (npm run local:parar lo apaga).
`);
