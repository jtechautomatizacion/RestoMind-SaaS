/**
 * Entrega una versión nueva del APK: sube el número, compila, la publica en
 * el VPS y hace que los teléfonos se enteren.
 *
 *     npm run version                  -> sube el PARCHE (1.3.2 -> 1.3.3)
 *     npm run version -- menor         -> 1.3.2 -> 1.4.0
 *     npm run version -- mayor         -> 1.3.2 -> 2.0.0
 *     npm run version -- --solo-numero -> solo toca version.json, no publica
 *     npm run version -- --dry-run     -> dice qué haría, sin tocar nada
 *
 * POR QUÉ EXISTE
 * --------------
 * Publicar una versión son TRES pasos, y hacer solo el primero es el error
 * fácil: el APK queda compilado en la PC y NADIE lo recibe.
 *
 *   1. Subir version.json y compilar.
 *   2. Copiar el APK a /home/restomind/descargas/ en el VPS.
 *   3. Actualizar APK_VERSION_CODE/APK_VERSION_NAME en el .env y reiniciar.
 *
 * Recién con el paso 3 el aviso de actualización le llega a los teléfonos:
 * `revisarActualizacion()` (capacitor-init.js) compara contra lo que dice
 * /api/app/version, que sale del .env — no del archivo que hay en disco.
 *
 * Ya se pagó: se entregó un APK con correcciones reales REUTILIZANDO el
 * versionCode 15 y sin hacer los pasos 2 y 3. Resultado: el enlace de
 * descarga seguía sirviendo el APK viejo, el aviso de actualización quedó
 * ciego (compara `<=`), y el teléfono del mozo se quedó semanas con la
 * versión anterior. El arreglo parecía no funcionar y la búsqueda se fue al
 * código, que estaba bien.
 *
 * POR QUÉ NO SE OMITE NINGÚN PASO AUNQUE "YA ESTÉ HECHO"
 * -----------------------------------------------------
 * Cada paso VERIFICA el anterior en vez de confiar: se compara el md5 de lo
 * que quedó publicado contra el del archivo local, y se relee
 * /api/app/version después de reiniciar. Un scp que copió a medias, o un
 * sed que no encontró la línea, no dan error por su cuenta.
 */

import { spawnSync } from 'child_process';
import fs from 'fs';
import crypto from 'crypto';
import path from 'path';
import { fileURLToPath } from 'url';

const raiz = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');

// --- Dónde vive producción -------------------------------------------------
// Se deja acá arriba y a la vista: si algún día cambia el VPS, se cambia en un
// solo lugar y no repartido por el archivo.
const VPS = 'root@167.148.33.5';
const LLAVE = path.join(process.env.HOME || process.env.USERPROFILE || '', '.ssh', 'restomind_vps');
const DIR_APP = '/home/restomind/app';
const DIR_DESCARGAS = '/home/restomind/descargas';
const URL_PUBLICA = 'https://app.jtechsolutiones.com';

const args = process.argv.slice(2);
const dryRun = args.includes('--dry-run');
const soloNumero = args.includes('--solo-numero');
const salto = args.find(a => ['parche', 'menor', 'mayor'].includes(a)) || 'parche';

const paso = (n, t) => console.log(`\n${'='.repeat(60)}\n  PASO ${n}: ${t}\n${'='.repeat(60)}`);
const ok = (t) => console.log(`  [OK] ${t}`);
const morir = (t, ayuda) => {
    console.error(`\n  [!] ${t}\n`);
    if (ayuda) console.error(`      ${ayuda}\n`);
    process.exit(1);
};

function correr(cmd, cmdArgs, opciones = {}) {
    const r = spawnSync(cmd, cmdArgs, { stdio: 'inherit', cwd: raiz, shell: process.platform === 'win32', ...opciones });
    return r.status === 0;
}

function capturar(cmd, cmdArgs) {
    const r = spawnSync(cmd, cmdArgs, { encoding: 'utf8', shell: process.platform === 'win32' });
    return { ok: r.status === 0, salida: (r.stdout || '') + (r.stderr || '') };
}

const ssh = (guion) => capturar('ssh', ['-i', `"${LLAVE}"`, VPS, `"${guion.replace(/"/g, '\\"')}"`]);

function md5(archivo) {
    return crypto.createHash('md5').update(fs.readFileSync(archivo)).digest('hex');
}

// --- 0. Chequeos previos ---------------------------------------------------
paso(0, 'Revisando que se pueda entregar');

if (!fs.existsSync(LLAVE) && !soloNumero && !dryRun) {
    morir(`No encuentro la llave del VPS en ${LLAVE}`, 'Sin eso no se puede publicar. Usá --solo-numero para solo subir el número.');
}

// Un árbol sucio significa que el APK va a llevar código que no está en
// ningún commit: si hay que volver atrás, no hay a qué volver.
const estado = capturar('git', ['status', '--porcelain']);
const sucio = estado.salida.split('\n').filter(l => l.trim() && !l.includes('version.json'));
if (sucio.length && !dryRun) {
    console.log('\n  [!] Hay cambios sin commitear:\n');
    for (const l of sucio.slice(0, 10)) console.log(`        ${l}`);
    console.log('\n      El APK llevaría código que no está en ningún commit, así que');
    console.log('      si hay que volver atrás no habría a qué volver.');
    console.log('      Commiteá primero, o usá --dry-run para ver qué haría.\n');
    process.exit(1);
}
ok('Árbol de git limpio');

// --- 1. Subir el número ----------------------------------------------------
paso(1, 'Subiendo la versión');

const rutaVersion = path.join(raiz, 'version.json');
const version = JSON.parse(fs.readFileSync(rutaVersion, 'utf8'));
const codigoViejo = version.versionCode;
const nombreViejo = version.versionName;

const [may, men, par] = nombreViejo.split('.').map(Number);
const nombreNuevo = salto === 'mayor' ? `${may + 1}.0.0`
    : salto === 'menor' ? `${may}.${men + 1}.0`
        : `${may}.${men}.${par + 1}`;
const codigoNuevo = codigoViejo + 1;

console.log(`  ${nombreViejo} (código ${codigoViejo})  ->  ${nombreNuevo} (código ${codigoNuevo})`);

// Contra lo que hay PUBLICADO, no contra lo que hay en el archivo: el archivo
// se puede haber subido antes sin llegar a publicarse.
let publicadaAntes = null;
try {
    const r = await fetch(`${URL_PUBLICA}/api/app/version`, { signal: AbortSignal.timeout(10000) });
    if (r.ok) publicadaAntes = await r.json();
} catch { /* sin internet: se sigue, el paso 4 vuelve a verificar */ }

if (publicadaAntes?.hay_publicada && codigoNuevo <= publicadaAntes.version_code) {
    morir(
        `El código ${codigoNuevo} no es mayor que el publicado (${publicadaAntes.version_code}).`,
        `Poné versionCode en ${publicadaAntes.version_code + 1} en version.json y volvé a correr esto.`,
    );
}

if (dryRun) {
    console.log('\n  --dry-run: hasta acá llega. No se tocó nada.\n');
    console.log(`  Haría: version.json -> ${codigoNuevo}, npm run apk, scp al VPS, .env + restart.\n`);
    process.exit(0);
}

version.versionCode = codigoNuevo;
version.versionName = nombreNuevo;
fs.writeFileSync(rutaVersion, JSON.stringify(version, null, 2) + '\n');
ok(`version.json actualizado`);

if (soloNumero) {
    console.log('\n  --solo-numero: listo. No se compiló ni se publicó nada.\n');
    process.exit(0);
}

// --- 2. Compilar -----------------------------------------------------------
paso(2, 'Compilando el APK de producción');

// La cadena COMPLETA, nunca compilar.mjs solo: Gradle empaqueta una copia que
// deja `cap sync`, así que saltarse los pasos previos compila el frontend
// anterior y dice BUILD SUCCESSFUL igual.
if (!correr('npm', ['run', 'apk'])) {
    // Si falló, el número ya quedó subido en el archivo. Se revierte para no
    // dejar version.json diciendo que hay una versión que nunca se compiló.
    version.versionCode = codigoViejo;
    version.versionName = nombreViejo;
    fs.writeFileSync(rutaVersion, JSON.stringify(version, null, 2) + '\n');
    morir('Falló la compilación. Se revirtió version.json.');
}

const apkLocal = path.join(raiz, 'RestoMind.apk');
if (!fs.existsSync(apkLocal)) morir('Compiló pero no encuentro RestoMind.apk en la raíz.');

const md5Local = md5(apkLocal);
ok(`RestoMind.apk  ${(fs.statSync(apkLocal).size / 1024 / 1024).toFixed(2)} MB  md5 ${md5Local}`);

// --- 3. Publicar el archivo ------------------------------------------------
paso(3, 'Subiendo el APK al VPS');

// El anterior se conserva con su número: si la nueva sale con un problema,
// volver atrás es copiar un archivo, no recompilar una versión vieja.
const respaldo = `${DIR_DESCARGAS}/RestoMind-v${nombreViejo}-previo.apk`;
ssh(`test -f ${DIR_DESCARGAS}/RestoMind.apk && cp ${DIR_DESCARGAS}/RestoMind.apk ${respaldo} || true`);

const scp = capturar('scp', ['-i', `"${LLAVE}"`, `"${apkLocal}"`, `${VPS}:${DIR_DESCARGAS}/RestoMind.apk`]);
if (!scp.ok) morir(`No se pudo subir el APK:\n${scp.salida}`);
ssh(`chown restomind:restomind ${DIR_DESCARGAS}/RestoMind.apk`);

// VERIFICAR, no confiar: un scp cortado a la mitad deja un archivo truncado
// sin dar error, y el restaurante se baja un APK que no instala.
const remoto = ssh(`md5sum ${DIR_DESCARGAS}/RestoMind.apk`);
const md5Remoto = (remoto.salida.trim().split(/\s+/)[0] || '').toLowerCase();
if (md5Remoto !== md5Local) {
    morir(`El APK subido NO coincide.\n      local : ${md5Local}\n      remoto: ${md5Remoto || '(no se pudo leer)'}`);
}
ok(`Publicado y verificado (md5 coincide)`);

// --- 4. Avisarle a los teléfonos -------------------------------------------
paso(4, 'Actualizando la versión que anuncia el servidor');

// Esto es lo que de verdad dispara el aviso. Sin este paso el archivo nuevo
// está ahí pero nadie se entera: /api/app/version sale del .env.
const sed = ssh(
    `cd ${DIR_APP} && ` +
    `sed -i 's/^APK_VERSION_CODE=.*/APK_VERSION_CODE=${codigoNuevo}/' .env && ` +
    `sed -i 's/^APK_VERSION_NAME=.*/APK_VERSION_NAME=${nombreNuevo}/' .env && ` +
    `grep -E '^APK_VERSION' .env && systemctl restart restomind`,
);
if (!sed.ok) morir(`No se pudo actualizar el .env:\n${sed.salida}`);
console.log(sed.salida.trim().split('\n').map(l => `  ${l}`).join('\n'));

await new Promise(r => setTimeout(r, 4000));

let anunciada = null;
try {
    const r = await fetch(`${URL_PUBLICA}/api/app/version`, { signal: AbortSignal.timeout(15000) });
    if (r.ok) anunciada = await r.json();
} catch { /* se reporta abajo */ }

if (!anunciada || anunciada.version_code !== codigoNuevo) {
    morir(
        `El servidor NO está anunciando la versión ${codigoNuevo}.`,
        `Anuncia: ${JSON.stringify(anunciada)}\n      Revisá:  journalctl -u restomind -n 50 --no-pager`,
    );
}
ok(`El servidor anuncia v${anunciada.version_name} (código ${anunciada.version_code})`);

// --- Listo -----------------------------------------------------------------
console.log(`\n${'='.repeat(60)}`);
console.log(`  ENTREGADA  v${nombreNuevo}  (código ${codigoNuevo})`);
console.log('='.repeat(60));
console.log(`\n  Los teléfonos con una versión anterior van a ver el aviso al abrir`);
console.log(`  la app. También pueden bajarla de:\n`);
console.log(`      ${URL_PUBLICA}/descargar\n`);
console.log(`  El APK anterior quedó en el VPS como:`);
console.log(`      RestoMind-v${nombreViejo}-previo.apk\n`);
console.log(`  Falta commitear el cambio de version.json:`);
console.log(`      git add version.json && git commit -m "chore: v${nombreNuevo}"\n`);
