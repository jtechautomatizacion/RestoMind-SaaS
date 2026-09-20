/**
 * Compila el APK del entorno que se le pida y lo deja en la raíz, con un
 * nombre que dice qué es.
 *
 *     node tools/compilar.mjs testing      -> RestoMind-pruebas.apk
 *     node tools/compilar.mjs produccion   -> RestoMind.apk
 *
 * POR QUÉ NO SE LLAMA A GRADLE DIRECTO
 * ------------------------------------
 * Porque el APK queda enterrado en
 * `android/app/build/outputs/apk/<flavor>/<tipo>/app-<flavor>-<tipo>.apk`, y
 * los dos entornos generan archivos de nombre parecido. Mandarle al cliente
 * el de pruebas —que apunta a una PC que no existe para él— es un error que
 * se comete una sola vez, pero se paga caro. Acá salen con nombres que no se
 * confunden, y el de producción además se verifica antes de entregarlo.
 */

import { spawnSync } from 'child_process';
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const raiz = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const entorno = process.argv[2];

const ENTORNOS = {
    testing: { flavor: 'pruebas', tarea: 'assemblePruebasDebug', tipo: 'debug', salida: 'RestoMind-pruebas.apk' },
    produccion: { flavor: 'produccion', tarea: 'assembleProduccionRelease', tipo: 'release', salida: 'RestoMind.apk' },
};

const cfg = ENTORNOS[entorno];
if (!cfg) {
    console.error(`Entorno desconocido: "${entorno}". Usá: testing | produccion`);
    process.exit(1);
}

/**
 * NO COMPILAR CON EL FRONTEND VIEJO ADENTRO.
 *
 * Gradle empaqueta `android/app/src/main/assets/public/`, que es una COPIA que
 * deja `cap sync`. Este script es el ÚLTIMO de cuatro pasos (ver `npm run
 * apk`); llamado solo, compila contra la copia anterior y dice BUILD
 * SUCCESSFUL igual.
 *
 * Eso ya costó una sesión entera de depuración: se arregló un bug de
 * impresión, se compiló así, se instaló, y el teléfono siguió fallando
 * exactamente igual porque adentro tenía el código de antes. Desde afuera es
 * indistinguible de "el arreglo no sirvió", y lleva a seguir cambiando código
 * que ya estaba bien.
 *
 * Mismo principio que `codigo_desactualizado` en /health y que la copia
 * generada de ImpresoraTermica.java: cuando hay una copia que se puede
 * quedar atrás, lo que falla en silencio hay que volverlo ruidoso.
 */
// Se compara CADA archivo contra su copia, y no todo contra una fecha de
// corte: `preparar-apk.mjs` copia preservando la fecha de modificación, así
// que un archivo recién sincronizado tiene la MISMA fecha que su fuente y
// cualquier corte único da falsos positivos. Archivo contra archivo, una
// copia al día empata y una copia vieja pierde.
function desincronizados(origen, copia, aca = []) {
    if (!fs.existsSync(origen)) return aca;
    for (const e of fs.readdirSync(origen, { withFileTypes: true })) {
        const o = path.join(origen, e.name);
        const c = path.join(copia, e.name);
        if (e.isDirectory()) {
            desincronizados(o, c, aca);
        } else if (fs.existsSync(c)) {
            // Solo lo que SÍ viaja en el APK. Lo que `preparar-apk.mjs`
            // excluye a propósito (fotos de los platos, el service worker)
            // no existe en la copia y no es motivo para frenar nada.
            if (fs.statSync(o).mtimeMs > fs.statSync(c).mtimeMs + 1000) {
                aca.push(path.relative(raiz, o));
            }
        }
    }
    return aca;
}

const empaquetado = path.join(raiz, 'android', 'app', 'src', 'main', 'assets', 'public');
if (!fs.existsSync(empaquetado)) {
    console.error('\nNo hay nada sincronizado todavía en android/app/src/main/assets/public/.');
    console.error(`Compilá con la cadena completa:  npm run ${entorno === 'produccion' ? 'apk' : 'apk:testing'}`);
    process.exit(1);
}

const pendientes = desincronizados(path.join(raiz, 'frontend'), empaquetado);
if (pendientes.length) {
    console.error('\n  [!] EL FRONTEND ESTÁ SIN SINCRONIZAR — no se compila.\n');
    console.error(`      ${pendientes.length} archivo(s) cambiaron después de la última copia:`);
    for (const f of pendientes.slice(0, 10)) console.error(`        ${f}`);
    if (pendientes.length > 10) console.error(`        ... y ${pendientes.length - 10} más`);
    console.error('\n      Si se compilara así, el APK saldría con el código ANTERIOR y');
    console.error('      Gradle diría BUILD SUCCESSFUL igual.\n');
    console.error(`      Compilá con la cadena completa:  npm run ${entorno === 'produccion' ? 'apk' : 'apk:testing'}\n`);
    process.exit(1);
}

// Gradle no arranca sin JAVA_HOME, y el mensaje que da ("JAVA_HOME is not
// set") no menciona que Android Studio ya trae un Java adentro. Se busca ahí
// antes de rendirse.
const env = { ...process.env };
if (!env.JAVA_HOME) {
    const jbr = [
        'C:/Program Files/Android/Android Studio/jbr',
        '/Applications/Android Studio.app/Contents/jbr/Contents/Home',
        process.env.HOME && path.join(process.env.HOME, 'android-studio', 'jbr'),
    ].filter(Boolean).find(p => fs.existsSync(p));
    if (jbr) env.JAVA_HOME = jbr;
}

// Ruta ABSOLUTA: en Windows el directorio actual no está en el PATH, así que
// un "gradlew.bat" a secas da "no se reconoce como un comando", que suena a
// que falta instalar algo cuando en realidad el archivo está ahí al lado.
const carpetaAndroid = path.join(raiz, 'android');
const gradlew = path.join(carpetaAndroid, process.platform === 'win32' ? 'gradlew.bat' : 'gradlew');

console.log(`\nCompilando ${entorno} (${cfg.tarea})...`);
// En Windows gradlew es un .bat y hay que pasarlo por cmd. `cmd.exe /d /s /c`
// invocado a mano rompe con rutas que tienen espacios (bug conocido de Node
// en Windows: https://github.com/nodejs/node/issues/38490 — el citado que
// arma Node para /S no sobrevive un cwd con espacios, ej. "D:\Cartera de
// proyectos\..."). `shell: true` sí cita bien el ejecutable; los argumentos
// no llevan entrada de nadie (cfg.tarea sale de ENTORNOS, fijo en este
// archivo), así que no hay riesgo de inyección pese al warning de Node.
const esWindows = process.platform === 'win32';
const r = spawnSync(
    esWindows ? `"${gradlew}"` : gradlew,
    [cfg.tarea],
    { cwd: carpetaAndroid, stdio: 'inherit', env, shell: esWindows },
);

if (r.status !== 0) process.exit(r.status ?? 1);

const carpeta = path.join(raiz, 'android', 'app', 'build', 'outputs', 'apk', cfg.flavor, cfg.tipo);
const generado = fs.existsSync(carpeta)
    ? fs.readdirSync(carpeta).find(f => f.endsWith('.apk'))
    : null;

if (!generado) {
    console.error(`\nGradle dijo que todo bien pero no hay ningún .apk en ${carpeta}`);
    process.exit(1);
}

const destino = path.join(raiz, cfg.salida);
fs.copyFileSync(path.join(carpeta, generado), destino);

const version = JSON.parse(fs.readFileSync(path.join(raiz, 'version.json'), 'utf8'));
const mb = (fs.statSync(destino).size / 1024 / 1024).toFixed(2);

console.log(`\n  ${cfg.salida}   ${mb} MB   v${version.versionName} (código ${version.versionCode})`);

if (entorno === 'produccion') {
    // Un APK de release SIN FIRMAR no se instala en ningún teléfono, y el
    // error que muestra Android ("no se pudo analizar el paquete") no dice
    // que el problema sea la firma. Mejor avisarlo acá.
    if (/unsigned/i.test(generado)) {
        console.log('\n  [!] Sin firmar: este APK NO se va a poder instalar.');
        console.log('      Generá la clave una sola vez:  node tools/crear-clave.mjs');
    } else {
        console.log('\n  Listo para entregar a los clientes.');
    }
} else {
    console.log('\n  Se instala AL LADO de la app real (id .pruebas), no la reemplaza.');
}
