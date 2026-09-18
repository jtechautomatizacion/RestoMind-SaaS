/**
 * Integra lo propio de RestoMind en el proyecto Android que genera Capacitor.
 *
 * `npx cap add android` crea un proyecto limpio, y `npx cap sync` puede
 * volver a tocarlo. Los tres cambios de acá se perderían cada vez que eso
 * pase, así que NO se hacen a mano: un paso manual que hay que recordar en
 * cada sync es un paso que algún día no se hace, y el síntoma sería "la app
 * compila pero no imprime" — sin ningún error que lo explique.
 *
 *    node tools/integrar-android.mjs      (o: npm run integrar-android)
 *
 * Es idempotente: correrlo dos veces no duplica nada.
 */

import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const raiz = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const paquete = path.join(raiz, 'android', 'app', 'src', 'main', 'java', 'com', 'restomind', 'pos');
const manifiesto = path.join(raiz, 'android', 'app', 'src', 'main', 'AndroidManifest.xml');

if (!fs.existsSync(paquete)) {
    console.error('No encuentro el proyecto Android. Corré antes:  npx cap add android');
    process.exit(1);
}

// --- 0. Guarda: push sin Firebase = la app no abre --------------------------
//
// @capacitor/push-notifications arrastra el SDK nativo de Firebase, que se
// engancha en el ARRANQUE de la aplicación. Sin app/google-services.json, el
// APK compila perfecto, instala perfecto, y al abrirlo Android muestra
// "la app continúa fallando" — sin ninguna pista de por qué.
//
// Ya pasó una vez y costó un rato encontrarlo: el error aparece en el
// dispositivo, no en el build, así que nada en la consola lo delata. Por eso
// se frena ACÁ, con el mensaje puesto, en vez de dejar salir un APK que se
// sabe que va a crashear.
const tienePush = fs.existsSync(path.join(raiz, 'node_modules', '@capacitor', 'push-notifications'));
const tieneFirebase = fs.existsSync(path.join(raiz, 'android', 'app', 'google-services.json'));

if (tienePush && !tieneFirebase) {
    console.error(`
[!] @capacitor/push-notifications está instalado pero falta
    android/app/google-services.json

    Ese plugin trae el SDK de Firebase, que se inicializa al arrancar la
    app. Sin ese archivo el APK compila e instala, pero CRASHEA al abrir.

    Dos caminos:

      a) Ya tenés el proyecto Firebase:
         poné google-services.json en android/app/ y volvé a correr esto.
         Además hay que activar el plugin de Gradle — ver docs/APK_ANDROID.md

      b) Todavía no lo tenés:
         npm uninstall @capacitor/push-notifications && npm run apk
         (la app funciona igual; solo no llegan avisos a cocina)
`);
    process.exit(1);
}

if (!tienePush) {
    console.log('  sin push: la app no va a recibir avisos de comandas (ver docs/APK_ANDROID.md)');
}

// --- 0b. local.properties: dónde está el SDK de Android ---------------------
//
// Gradle no compila sin este archivo, pero NO se versiona: la ruta del SDK es
// distinta en cada computadora, así que commitearla rompe el proyecto en la
// siguiente. La salida cuando falta tampoco ayuda ("SDK location not found"),
// porque no dice que el archivo se genera solo.
//
// Por eso se busca el SDK en las rutas donde Android Studio lo instala y se
// escribe acá. Un clon nuevo del repo compila sin ningún paso manual.
const localProps = path.join(raiz, 'android', 'local.properties');
if (!fs.existsSync(localProps)) {
    const candidatos = [
        process.env.ANDROID_HOME,
        process.env.ANDROID_SDK_ROOT,
        process.env.LOCALAPPDATA && path.join(process.env.LOCALAPPDATA, 'Android', 'Sdk'),
        process.env.HOME && path.join(process.env.HOME, 'Library', 'Android', 'sdk'),
        process.env.HOME && path.join(process.env.HOME, 'Android', 'Sdk'),
    ].filter(Boolean);

    const sdk = candidatos.find(p => fs.existsSync(p));
    if (!sdk) {
        console.error(`
[!] No encuentro el SDK de Android.

    Buscado en:
${candidatos.map(c => '      ' + c).join('\n')}

    Si lo tenés en otro lado, creá android/local.properties con:
      sdk.dir=C\\:\\\\ruta\\\\al\\\\Sdk
`);
        process.exit(1);
    }
    // En Windows gradle exige las barras y los dos puntos escapados: es un
    // archivo .properties de Java, no una ruta cualquiera.
    fs.writeFileSync(localProps, `# GENERADO - no versionar. Ver tools/integrar-android.mjs\nsdk.dir=${sdk.replace(/([\\:])/g, '\\$1')}\n`, 'utf8');
    console.log(`  local.properties generado (SDK en ${sdk})`);
}

// --- 1. El plugin de la impresora ------------------------------------------
fs.copyFileSync(
    path.join(raiz, 'plugin-impresora', 'ImpresoraTermica.java'),
    path.join(paquete, 'ImpresoraTermica.java')
);
console.log('  ImpresoraTermica.java copiado');

// --- 2. Registrarlo en MainActivity ----------------------------------------
// registerPlugin va ANTES de super.onCreate: después, el puente ya está
// armado y el plugin no aparece en Capacitor.Plugins. La app arranca bien y
// la impresión simplemente no encuentra el plugin.
const mainActivity = `package com.restomind.pos;

import android.os.Bundle;
import com.getcapacitor.BridgeActivity;

public class MainActivity extends BridgeActivity {

    @Override
    public void onCreate(Bundle savedInstanceState) {
        // ANTES de super.onCreate: después el puente ya se armó y el plugin
        // no aparece en Capacitor.Plugins.
        registerPlugin(ImpresoraTermica.class);
        super.onCreate(savedInstanceState);
    }
}
`;
fs.writeFileSync(path.join(paquete, 'MainActivity.java'), mainActivity, 'utf8');
console.log('  MainActivity.java con el plugin registrado');

// --- 3. Permisos ------------------------------------------------------------
let xml = fs.readFileSync(manifiesto, 'utf8');
// Se comprueba el permiso MÁS NUEVO, no el primero que se agregó: mirando
// BLUETOOTH_CONNECT, un proyecto de una versión anterior se daba por
// completo y nunca recibía BLUETOOTH_SCAN — la búsqueda de impresoras
// quedaba sin permiso, sin que nada lo avisara.
// "Completo" = tiene TODOS los permisos de la versión actual, no solo el
// primero que se agregó. Mirando uno solo, un proyecto de una versión anterior
// se daba por completo y nunca recibía los nuevos — el permiso quedaba sin
// pedir y nada lo avisaba.
//
// Se comprueba contra la misma lista que se escribe abajo, así agregar un
// permiso no obliga a acordarse de tocar también esta condición.
const REQUERIDOS = ['BLUETOOTH_SCAN', 'VIBRATE'];
const completo = REQUERIDOS.every(p => xml.includes(p));

if (completo) {
    console.log('  permisos ya estaban');
} else if (xml.includes('BLUETOOTH_CONNECT') || xml.includes('BLUETOOTH_SCAN')) {
    // Proyecto de una versión anterior: se borra el bloque entero y se
    // reescribe. Sin este borrado, insertar de nuevo DUPLICARÍA los permisos
    // que ya estaban.
    xml = xml.replace(/\n?    <uses-permission android:name="android\.permission\.(ACCESS_NETWORK_STATE|POST_NOTIFICATIONS|VIBRATE|BLUETOOTH[A-Z_]*)"[^>]*\/>/g, '');
    xml = xml.replace(/\n?    <!--[^]*?-->(?=\n    <uses-permission|\n\n    <application)/g, '');
    fs.writeFileSync(manifiesto, xml, 'utf8');
    xml = fs.readFileSync(manifiesto, 'utf8');
    console.log('  permisos viejos removidos, se reescriben');
}

if (!completo) {
    const original = '    <uses-permission android:name="android.permission.INTERNET" />';
    const bloque = `    <uses-permission android:name="android.permission.INTERNET" />
    <uses-permission android:name="android.permission.ACCESS_NETWORK_STATE" />
    <uses-permission android:name="android.permission.POST_NOTIFICATIONS" />

    <!-- Aviso de comanda nueva en cocina. Sin este permiso
         navigator.vibrate() no hace NADA y tampoco lanza error: el aviso
         simplemente no llega, y no hay forma de darse cuenta desde el codigo. -->
    <uses-permission android:name="android.permission.VIBRATE" />

    <!-- Impresora termica por Bluetooth Clasico (SPP).
         BLUETOOTH_CONNECT ademas hay que PEDIRLO en ejecucion en Android
         12+: sin el, getBondedDevices() devuelve una lista VACIA en vez de
         fallar, y parece que no hay ninguna impresora emparejada. -->
    <uses-permission android:name="android.permission.BLUETOOTH_CONNECT" />
    <!-- BUSCAR impresoras nuevas es un permiso DISTINTO de conectarse a las
         ya emparejadas. neverForLocation evita que Android ademas exija el
         permiso de UBICACION: sin esa bandera, buscar una impresora le pide
         al mozo acceso a su ubicacion, que no hace falta y asusta. -->
    <uses-permission android:name="android.permission.BLUETOOTH_SCAN"
        android:usesPermissionFlags="neverForLocation" />
    <uses-permission android:name="android.permission.BLUETOOTH"
        android:maxSdkVersion="30" />
    <uses-permission android:name="android.permission.BLUETOOTH_ADMIN"
        android:maxSdkVersion="30" />`;

    if (!xml.includes(original)) {
        console.error('  [!] No encontré el permiso INTERNET en el manifest: agregá los de Bluetooth a mano.');
        process.exit(1);
    }
    xml = xml.replace(original, bloque);
    fs.writeFileSync(manifiesto, xml, 'utf8');
    console.log('  permisos de Bluetooth y notificaciones agregados');
}

// --- 4. Texto plano, SOLO si este build apunta a un backend http:// ---------
//
// Android 9+ bloquea http:// sin ningún error legible: la app simplemente
// dice "Sin conexión", y uno termina revisando el wifi en vez del esquema de
// la URL.
//
// El permiso se deriva del destino REAL que quedó en dist-apk/, no de una
// bandera aparte. Eso es lo que garantiza que un APK de producción (https) no
// pueda salir con texto plano habilitado aunque antes se haya compilado uno
// de pruebas en la misma carpeta: acá abajo, el caso https lo REMUEVE.
//
// Y cuando se habilita, se habilita para ESE host y nada más. Un
// `usesCleartextTraffic="true"` global abriría http hacia cualquier dominio.
const rutaXml = path.join(raiz, 'android', 'app', 'src', 'main', 'res', 'xml');
const archivoSeg = path.join(rutaXml, 'network_security_config.xml');
const ATRIBUTO = '\n        android:networkSecurityConfig="@xml/network_security_config"';

let destinoApk = '';
const archivoDestino = path.join(raiz, 'dist-apk', 'js', 'destino-api.js');
if (fs.existsSync(archivoDestino)) {
    const m = fs.readFileSync(archivoDestino, 'utf8')
        .match(/RESTOMIND_API_DESTINO\s*=\s*['"]([^'"]+)['"]/);
    destinoApk = m ? m[1] : '';
}

let man = fs.readFileSync(manifiesto, 'utf8');
man = man.replace(ATRIBUTO, '');   // se parte de limpio en los dos casos

const enTextoPlano = /^http:\/\//.test(destinoApk);
if (enTextoPlano) {
    const host = new URL(destinoApk).hostname;
    fs.mkdirSync(rutaXml, { recursive: true });
    fs.writeFileSync(archivoSeg, `<?xml version="1.0" encoding="utf-8"?>
<!-- GENERADO AL COMPILAR - no editar. Ver tools/integrar-android.mjs -->
<network-security-config>
    <!-- Texto plano permitido UNICAMENTE contra el backend de pruebas.
         El resto de la app sigue exigiendo HTTPS. -->
    <domain-config cleartextTrafficPermitted="true">
        <domain includeSubdomains="false">${host}</domain>
    </domain-config>
</network-security-config>
`, 'utf8');
    man = man.replace('    <application', '    <application' + ATRIBUTO);
    console.log(`  texto plano habilitado solo para ${host} (APK de pruebas)`);
} else {
    if (fs.existsSync(archivoSeg)) fs.rmSync(archivoSeg);
    console.log('  sin texto plano: todo el trafico va por HTTPS');
}
fs.writeFileSync(manifiesto, man, 'utf8');

// --- 5. Contenido mixto: son DOS permisos distintos, no uno ----------------
//
// El punto 4 convence a ANDROID de permitir http. Falta convencer al WEBVIEW,
// que es otra política y bloquea por su cuenta: la página se sirve desde
// https://localhost (androidScheme de Capacitor), así que pedirle algo a un
// http:// es "contenido mixto" y lo corta antes de que salga a la red.
//
// El síntoma engaña: el backend no registra NINGUNA petición, así que parece
// un problema de red o de firewall. Solo logcat lo dice, con todas las letras:
//   "Mixed Content: ... requested an insecure resource ... has been blocked"
//
// Se toca la copia que quedó en assets/ —que es la que lee la app— y no
// capacitor.config.json del repo, para que un APK de producción nunca salga
// con contenido mixto habilitado.
const cfgAssets = path.join(raiz, 'android', 'app', 'src', 'main', 'assets', 'capacitor.config.json');
if (fs.existsSync(cfgAssets)) {
    const cfg = JSON.parse(fs.readFileSync(cfgAssets, 'utf8'));
    cfg.android = cfg.android || {};
    cfg.android.allowMixedContent = enTextoPlano;
    fs.writeFileSync(cfgAssets, JSON.stringify(cfg, null, 2), 'utf8');
    console.log(`  contenido mixto: ${enTextoPlano ? 'permitido (solo pruebas)' : 'bloqueado'}`);
}

console.log(`\nEste APK habla con: ${destinoApk || '(no pude leerlo de dist-apk/)'}`);
console.log('Listo. Ahora:  cd android && ./gradlew assembleDebug');
