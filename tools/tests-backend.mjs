/**
 * Corre la suite de pytest usando el Python del entorno virtual.
 *
 * POR QUÉ NO VA DIRECTO EN package.json
 * -------------------------------------
 * El intérprete del venv está en rutas distintas según el sistema
 * (`.venv/Scripts/python.exe` en Windows, `.venv/bin/python` en Linux y Mac),
 * y npm ejecuta los scripts con `cmd` en Windows, que interpreta una ruta con
 * barras normales al principio del comando como si fueran opciones:
 *
 *     ".venv" no se reconoce como un comando interno o externo
 *
 * Poner la ruta de Windows con barras invertidas arreglaría eso y rompería el
 * despliegue, que es Linux. Un `python` a secas tampoco sirve: el venv no
 * está activado, así que agarraría el Python del sistema, sin las
 * dependencias — y fallaría con un ImportError que no menciona el venv por
 * ningún lado.
 *
 * Mismo criterio que tools/compilar.mjs con gradlew: donde el comando cambia
 * según el sistema, decide un script y no el package.json.
 */

import { spawnSync } from 'child_process';
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const raiz = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const esWindows = process.platform === 'win32';

const python = [
    path.join(raiz, '.venv', esWindows ? 'Scripts' : 'bin', esWindows ? 'python.exe' : 'python'),
    // `venv/` sin punto: este repo tuvo las dos formas conviviendo y la
    // documentación llegó a mencionar ambas.
    path.join(raiz, 'venv', esWindows ? 'Scripts' : 'bin', esWindows ? 'python.exe' : 'python'),
].find(p => fs.existsSync(p));

if (!python) {
    console.error('\nNo se encontró el entorno virtual (.venv/ ni venv/).');
    console.error('Creálo con:  python -m venv .venv  &&  pip install -r requirements.txt\n');
    process.exit(1);
}

const r = spawnSync(
    esWindows ? `"${python}"` : python,
    ['-m', 'pytest', '-q', ...process.argv.slice(2)],
    { cwd: raiz, stdio: 'inherit', shell: esWindows },
);

process.exit(r.status ?? 1);
