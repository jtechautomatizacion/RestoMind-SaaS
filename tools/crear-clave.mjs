/**
 * Genera LA clave con la que se firman todos los APK de producción.
 *
 *     node tools/crear-clave.mjs
 *
 * SE CORRE UNA SOLA VEZ EN LA VIDA DEL PROYECTO.
 *
 * Android solo acepta actualizar una app si el APK nuevo está firmado con la
 * MISMA clave que el que ya está instalado. Si esta clave se pierde:
 *
 *   - no se puede publicar ninguna actualización más de esta app, nunca;
 *   - cada restaurante tendría que DESINSTALAR (perdiendo su sesión y su
 *     impresora configurada) e instalar la app nueva como si fuera otra.
 *
 * No hay forma de recuperarla ni de pedirle a Google que la reemplace. Por eso
 * el archivo que genera va afuera del repositorio y hay que respaldarlo en
 * algún lugar que sobreviva a que se rompa esta computadora.
 */

import { spawnSync } from 'child_process';
import fs from 'fs';
import path from 'path';
import readline from 'readline';
import { fileURLToPath } from 'url';

const raiz = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const jks = path.join(raiz, 'android', 'restomind.jks');
const props = path.join(raiz, 'android', 'keystore.properties');

if (fs.existsSync(jks)) {
    console.log(`\nYa existe ${jks}`);
    console.log('NO se sobrescribe: generar otra clave dejaría sin actualizaciones a');
    console.log('todos los teléfonos que tienen la app instalada con la actual.');
    console.log('\nSi de verdad querés empezar de cero, movela a otro lado a mano primero.');
    process.exit(0);
}

const preguntar = (texto) => new Promise((resolver) => {
    const rl = readline.createInterface({ input: process.stdin, output: process.stdout });
    rl.question(texto, (r) => { rl.close(); resolver(r.trim()); });
});

const keytool = [
    process.env.JAVA_HOME && path.join(process.env.JAVA_HOME, 'bin', 'keytool'),
    'C:/Program Files/Android/Android Studio/jbr/bin/keytool.exe',
    '/Applications/Android Studio.app/Contents/jbr/Contents/Home/bin/keytool',
    'keytool',
].filter(Boolean).find(p => p === 'keytool' || fs.existsSync(p));

console.log('\n  CLAVE DE FIRMA DE RESTOMIND');
console.log('  Se genera una sola vez. Si se pierde, no hay más actualizaciones.\n');

const clave = await preguntar('  Contraseña para la clave (anotala donde no se pierda): ');
if (clave.length < 6) {
    console.error('\n  Tiene que tener al menos 6 caracteres.');
    process.exit(1);
}

const r = spawnSync(keytool, [
    '-genkeypair', '-v',
    '-keystore', jks,
    '-alias', 'restomind',
    '-keyalg', 'RSA',
    '-keysize', '2048',
    // 10000 días ≈ 27 años. Si el certificado vence, tampoco se puede volver
    // a firmar una actualización, así que se pone bien lejos a propósito.
    '-validity', '10000',
    '-storepass', clave,
    '-keypass', clave,
    '-dname', 'CN=RestoMind, OU=JTech, O=JTech Automatizacion, L=Lima, C=PE',
], { stdio: 'inherit' });

if (r.status !== 0) {
    console.error('\n  No se pudo generar la clave.');
    process.exit(1);
}

fs.writeFileSync(props, `# NO VERSIONAR. Con este archivo y el .jks, cualquiera puede publicar un APK
# que los telefonos aceptaran como actualizacion legitima de RestoMind.
storeFile=restomind.jks
storePassword=${clave}
keyAlias=restomind
keyPassword=${clave}
`, 'utf8');

console.log(`\n  Listo:`);
console.log(`    android/restomind.jks          la clave`);
console.log(`    android/keystore.properties    la contraseña`);
console.log('\n  RESPALDÁ LOS DOS en un lugar que sobreviva a esta computadora');
console.log('  (un disco externo, o tu gestor de contraseñas). No están en git,');
console.log('  y a propósito: si se filtran, alguien puede publicar una');
console.log('  actualización falsa de tu app.\n');
