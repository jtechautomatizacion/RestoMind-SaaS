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
if (xml.includes('BLUETOOTH_SCAN')) {
    console.log('  permisos ya estaban');
} else if (xml.includes('BLUETOOTH_CONNECT')) {
    // Proyecto de una versión anterior: se reescribe el bloque entero.
    xml = xml.replace(/\n?    <uses-permission android:name="android\.permission\.(ACCESS_NETWORK_STATE|POST_NOTIFICATIONS|BLUETOOTH[A-Z_]*)"[^>]*\/>/g, '');
    fs.writeFileSync(manifiesto, xml, 'utf8');
    xml = fs.readFileSync(manifiesto, 'utf8');
    console.log('  permisos viejos removidos, se reescriben');
}

if (!xml.includes('BLUETOOTH_SCAN')) {
    const original = '    <uses-permission android:name="android.permission.INTERNET" />';
    const bloque = `    <uses-permission android:name="android.permission.INTERNET" />
    <uses-permission android:name="android.permission.ACCESS_NETWORK_STATE" />
    <uses-permission android:name="android.permission.POST_NOTIFICATIONS" />

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

console.log('\nListo. Ahora:  cd android && ./gradlew assembleDebug');
