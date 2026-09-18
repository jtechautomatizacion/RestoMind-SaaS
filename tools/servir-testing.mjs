/**
 * Levanta el backend de PRUEBAS: base propia, PUERTO propio, y escuchando en
 * toda la red.
 *
 *     npm run servir-testing
 *
 * TRES COSAS QUE NO SON OPCIONALES
 * --------------------------------
 * 1. `--host 0.0.0.0`. Por defecto uvicorn escucha solo en 127.0.0.1, o sea
 *    únicamente en esta PC. El celular nunca lo alcanza, y el síntoma en la
 *    app es "Sin conexión" — que manda a revisar el wifi en vez del comando.
 *
 * 2. Una base de datos APARTE (`restomind-testing.db`). Es el punto entero de
 *    esto: hasta ahora el APK de pruebas hablaba con producción, así que cada
 *    prueba de impresión creaba comandas reales en el restaurante.
 *
 * 3. Un PUERTO aparte (8010). El 8000 es el del servidor de desarrollo de
 *    siempre, que usa `restomind.db`. Compartiendo puerto, cuál de los dos
 *    contesta depende de cuál arrancó primero — y el celular terminaría
 *    escribiendo en una base u otra según el orden en que se prendieron las
 *    cosas. Eso es exactamente la confusión que este entorno viene a eliminar.
 *
 * NO usa --reload a propósito: en esta máquina el recargador de uvicorn
 * detecta el cambio y el proceso nuevo no levanta nunca (está documentado en
 * CLAUDE.md, sección "Troubleshooting"). Reiniciar a mano es un segundo y es
 * confiable.
 */

import { spawn } from 'child_process';
import fs from 'fs';
import os from 'os';
import path from 'path';
import { fileURLToPath } from 'url';

// 8010 y no 8000: el 8000 lo usa el servidor de desarrollo de siempre.
// Si se cambia acá, hay que cambiarlo también en tools/preparar-apk.mjs (el
// destino "local") y en la regla del firewall.
const PUERTO = 8010;

const raiz = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');

const python = ['.venv/Scripts/python.exe', '.venv/bin/python']
    .map(p => path.join(raiz, p))
    .find(p => fs.existsSync(p));

if (!python) {
    console.error('No encuentro el entorno virtual (.venv). Crealo antes de correr esto.');
    process.exit(1);
}

// Misma deteccion que preparar-apk.mjs, para poder ANUNCIAR la URL exacta que
// hay que tener adentro del APK. Si las dos no coinciden, no conecta — y es
// mucho mejor verlo acá, lado a lado, que descubrirlo en el celular.
function ipDeEstaPC() {
    for (const [nombre, entradas] of Object.entries(os.networkInterfaces())) {
        if (/wsl|virtual|docker|vmware|loopback/i.test(nombre)) continue;
        for (const e of entradas || []) {
            if (e.family === 'IPv4' && !e.internal) return e.address;
        }
    }
    return null;
}

const ip = ipDeEstaPC();
console.log('\n  BACKEND DE PRUEBAS');
console.log('  base de datos:  restomind-testing.db   (produccion NO se toca)');
console.log(`  el celular lo busca en:  http://${ip || '<ip-de-esta-pc>'}:8000\n`);
if (ip) {
    console.log('  Si el APK no conecta, casi siempre es el firewall de Windows:');
    console.log('  la primera vez pide permiso para python.exe y hay que darle');
    console.log('  acceso en REDES PRIVADAS.\n');
}

const proc = spawn(python, [
    '-m', 'uvicorn', 'backend.app:app',
    '--host', '0.0.0.0',
    '--port', String(PUERTO),
], {
    cwd: raiz,
    stdio: 'inherit',
    env: {
        ...process.env,
        // Pisa lo que diga el .env de desarrollo: esta base es solo de pruebas.
        DATABASE_URL: 'sqlite:///./restomind-testing.db',
        ENVIRONMENT: 'development',
    },
});

proc.on('exit', (codigo) => process.exit(codigo ?? 0));
