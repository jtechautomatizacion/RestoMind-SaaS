# 📱 RestoMind como APK (Capacitor)

APK de distribución directa — no pasa por Play Store. El frontend viaja
**dentro** de la app; las llamadas van a `https://app.jtechsolutiones.com`.

---

## Por qué el frontend va empaquetado y no apuntando a la web

Capacitor admite las dos formas, y son excluyentes:

| | Empaquetado *(el que se usa)* | `server.url` apuntando a la web |
|---|---|---|
| Abre sin señal | ✅ la interfaz carga igual | ❌ pantalla en blanco |
| Actualizar | hay que instalar un APK nuevo | sale solo al subir al VPS |

Para un restaurante, que la app no abra porque se cayó el wifi es peor que
tener que instalar una actualización cada tanto. Por eso **no hay
`server.url`** en `capacitor.config.json`.

Tres consecuencias de esa decisión, ya resueltas, que conviene no deshacer:

1. **El origen pasa a ser `https://localhost`.** Por eso `API_BASE_URL` se
   arma con `window.RESTOMIND_API_BASE` (lo define `capacitor-init.js`, que
   carga **antes** que `app.js`). Una ruta relativa apuntaría al teléfono.
2. **El backend debe aceptar ese origen.** Está en `ORIGENES_APP_NATIVA`
   (`backend/app.py`), en el código y no en el `.env`: si dependiera del
   `.env`, olvidarlo en un servidor nuevo dejaría la app móvil muerta ahí
   con un síntoma de "sin conexión".
3. **Las rutas del frontend son relativas.** `js/app.js`, no
   `/static/js/app.js` — así sirven en la web y dentro del APK.

---

## 1. Compilar

```bash
npm install
npm run sync        # prepara dist-apk/ y sincroniza Android
npx cap open android
```

`npm run sync` corre `tools/preparar-apk.mjs`, que copia `frontend/` a
`dist-apk/` **sin las fotos de los platos**. No es cosmético: son 1 MB de
los 1,44 MB de la carpeta, crecen con cada foto que suba un admin, y
mandarían las fotos de un restaurante a los celulares de todos. Se sirven
desde el servidor en tiempo de ejecución.

## 2. El plugin de la impresora y los permisos

`npm run apk` ya deja todo integrado. Lo hace `tools/integrar-android.mjs`,
que copia el plugin, reescribe `MainActivity.java` registrándolo y agrega
los permisos al manifest.

**Va en un script y no en una lista de pasos manuales** porque `cap sync`
puede volver a tocar el proyecto Android: un paso que hay que recordar en
cada sync es un paso que algún día no se hace, y el síntoma sería *"la app
compila pero no imprime"*, sin ningún error que lo explique. Es idempotente:
correrlo dos veces no duplica nada.

Dos cosas que resuelve y conviene conocer por si algún día hay que tocarlas
a mano:

- **`registerPlugin()` va ANTES de `super.onCreate()`.** Después, el puente
  ya está armado y el plugin no aparece en `Capacitor.Plugins`: la app
  arranca perfecto y la impresión no encuentra nada.
- **`BLUETOOTH_CONNECT` hay que pedirlo en tiempo de ejecución** en Android
  12+. Sin él, `getBondedDevices()` devuelve una lista **vacía** en vez de
  fallar — parece que no hay ninguna impresora emparejada, y manda a revisar
  el Bluetooth del celular en vez del permiso.

> El plugin está en **Java**, no en Kotlin. Capacitor genera el proyecto
> Android solo con Java, y sumar Kotlin por un archivo arrastra su runtime
> al APK (~1,5 MB) — más peso que todo el frontend empaquetado.

## 3. Compilar el APK

```bash
cd android && ./gradlew assembleDebug
# -> android/app/build/outputs/apk/debug/app-debug.apk
```

La primera compilación tarda ~12 minutos (baja Gradle y las dependencias de
los 6 plugins); las siguientes, menos de un minuto.

## 4. Firmar para distribución directa

Sin Play Store, la firma solo tiene que ser estable: Android exige que las
actualizaciones estén firmadas con **la misma** clave que la instalación
original.

```bash
cd android/app
keytool -genkey -v -keystore restomind.jks -keyalg RSA -keysize 2048 \
        -validity 10000 -alias restomind
```

> **Guardá el `.jks` y su contraseña fuera de la máquina.** Si se pierden,
> no se puede volver a actualizar la app instalada: hay que desinstalar y
> reinstalar en cada local, perdiendo la sesión de cada dispositivo.

`android/key.properties` (va en `.gitignore`):

```properties
storeFile=restomind.jks
storePassword=...
keyAlias=restomind
keyPassword=...
```

En `android/app/build.gradle`, dentro de `android { }`:

```gradle
def keyProps = new Properties()
def keyFile = rootProject.file("key.properties")
if (keyFile.exists()) keyProps.load(new FileInputStream(keyFile))

signingConfigs {
    release {
        storeFile file(keyProps['storeFile'])
        storePassword keyProps['storePassword']
        keyAlias keyProps['keyAlias']
        keyPassword keyProps['keyPassword']
    }
}
buildTypes {
    release {
        signingConfig signingConfigs.release
        minifyEnabled true
        shrinkResources true
    }
}
```

`minifyEnabled` + `shrinkResources` recortan bastante el APK final.

```bash
cd android && ./gradlew assembleRelease
# -> app/build/outputs/apk/release/app-release.apk
```

---

## La impresora térmica

### Cómo está armado

```
print.js                arma el ticket en HTML  (uno solo, el de siempre)
    |
    v
impresora-termica.js    extrae las líneas de ese HTML y las emite
    |                   en ESC/POS  o  en TSPL, según la impresora
    v
ImpresoraTermica.java   las manda por socket Bluetooth SPP
```

El ticket **no** se escribe dos veces. Dos generadores del mismo documento
se desincronizan sin falta: alguien agrega una línea al ticket de cocina y
se acuerda de uno solo. El conversor recorre el HTML que `print.js` ya
produjo.

`_imprimirHTML()` intenta primero la térmica y, si no hay plugin o falla,
cae al diálogo del navegador. Ese orden importa: dentro del APK
`window.print()` **no hace nada** —no existe ese diálogo en un WebView— así
que la ruta térmica avisa por toast cuando no puede, en vez de fallar
callada.

### Dos lenguajes, porque son dos clases de impresora

No alcanza con hablar ESC/POS. Las que se consiguen en el mercado peruano
se parten en dos familias que **no se entienden entre sí**:

| | Lenguaje | Qué pasa si se le manda el otro |
|---|---|---|
| Impresora de **tickets** (rollo continuo) | ESC/POS | — |
| Impresora de **etiquetas** (papel con gaps) | TSPL | Saca garabatos, o `err: no seam!` |

`convertir()` despacha según `cfg.lenguaje`, que el admin elige en
**Admin → Impresora**. No se autodetecta: no hay forma confiable de
preguntarle a una térmica barata qué habla, y adivinar mal desperdicia un
rollo entero.

Del lado de TSPL hay tres valores que costaron papel averiguar:

- **`GAP 0,0`** y no `GAP 2 mm,0`. Declarar un gap que el papel no tiene
  hace que la impresora busque una separación inexistente, avance el rollo
  entero buscándola y termine en `err: no seam!` — que solo se limpia
  apagándola. `GAP 0,0` le dice "papel continuo", que es lo que hay.
- **`DIRECTION 0`** y no `1`. Con `1` el ticket sale invertido: se imprime
  de abajo hacia arriba, así que el cajero lee el total antes que el
  encabezado y el papel sigue saliendo de más.
- **`HOLGURA = 1.15`** al medir el ancho de un texto. Los anchos nominales
  de fuente que declara el manual no se cumplen; sin ese margen del 15% el
  precio se monta encima del nombre del plato.

### Por qué Bluetooth Clásico y no BLE

Estas térmicas hablan **Bluetooth Clásico (SPP)**, no Low Energy. Los
plugins de la comunidad (`bluetooth-le` y similares) solo manejan BLE: con
estas impresoras ni las encuentran. De ahí el código nativo.

### La configuración se guarda en DOS lados, y no es redundancia

`guardarConfiguracion()` escribe en `localStorage` **y** en Preferences
(SharedPreferences nativo). Cada uno cubre lo que el otro no:

- `localStorage` es **síncrono**, que es lo que hace falta en el momento de
  imprimir. Pero vive dentro del WebView: Android lo vacía al liberar
  espacio, y reinstalar el APK lo deja limpio.
- Preferences **sobrevive** a todo eso, pero es asíncrono.

De ahí la regla que **no conviene tocar**: `imprimirHTMLenTermica()` hace
`await asegurarConfiguracion()` antes de leer nada. Sin esa espera hay una
carrera con un síntoma engañoso — tras reinstalar, el primer cobro salía
antes de que la restauración terminara, `configuracion()` devolvía `null`,
caía en la autodetección y **se imprimía en el lenguaje equivocado**. No se
ve como un bug de configuración: se ve como si la impresora se hubiera
roto.

Por el mismo motivo la autodetección construye la configuración con
`lenguaje` **explícito** aunque sea el valor por defecto. Omitirlo dejaba
`cfg.lenguaje` en `undefined`, y `convertir()` caía a ESC/POS en silencio.

### Detalles que hacen que funcione de verdad

- **Plan B al conectar.** `createRfcommSocketToServiceRecord` es la vía
  documentada, pero muchas térmicas económicas no publican bien su registro
  SDP y devuelven `read failed, socket might closed`. El método oculto
  `createRfcommSocket` va directo al canal 1 y con esas sí funciona.
- **Envío en trozos de 180 bytes con pausa.** El búfer de estas impresoras
  es chico: un volcado de una sola vez se pierde por la mitad.
- **Pausa antes de cerrar.** Sin ella, cerrar el socket corta el envío a
  mitad de camino y el ticket sale por la mitad.
- **`cancelDiscovery()` antes de conectar.** Una búsqueda en curso y una
  conexión saliente compiten por la radio.
- **Todo fuera del hilo principal.** El I/O de Bluetooth bloquea; en el hilo
  principal congela la interfaz y, con la impresora apagada, Android muestra
  "la aplicación no responde" justo mientras el cajero cobra.
- **Acentos transliterados** (`CLÁSICO` → `CLASICO`). Las térmicas chinas
  declaran CP850 y muchas no la implementan igual: el papel sale con
  `CL├üSICO`. Un ticket sin tildes se lee perfecto; uno con basura, no.
- **`BLUETOOTH_CONNECT` se pide en ejecución**, no solo en el manifiesto.
  En Android 12+, sin ese permiso concedido `getBondedDevices()` devuelve
  una lista **vacía** en vez de fallar — así que parece que no hay ninguna
  impresora emparejada, sin ningún error que lo explique.

### Probar el conversor sin impresora

```bash
npm run probar-termica
```

Imprime en consola cómo quedaría el papel a 48 columnas.

### Si no imprime

**Empezá por el botón `Estado`** (Admin → Impresora). Pregunta y no gasta
papel, y separa en un toque las causas que desde afuera se ven idénticas:

| Lo que dice | Qué pasa |
|---|---|
| `Lista para imprimir` | La impresora está bien: el problema está en la app o en el lenguaje |
| `La impresora no tiene papel` / `cabezal abierto` / `atascado` | Falla física, con el motivo puesto |
| `La impresora está trabada. Apagala y prendela de nuevo.` | El firmware se declaró en error y descarta todo lo que le llega |
| `Conectada, pero este modelo no informa su estado` | Ese modelo no contesta la consulta: si no sale papel, apagala y prendela |
| `No se pudo conectar con la impresora` | Ni se llegó al enlace: apagada, lejos, o desemparejada |

Después, si sigue sin salir:

1. ¿Está **emparejada** en Ajustes → Bluetooth? La app puede buscar y
   emparejar desde Admin → Impresora, pero el emparejamiento tiene que
   existir antes de imprimir.
2. ¿Se aceptaron los permisos de Bluetooth?
3. ¿El **lenguaje** elegido es el correcto? Si el papel sale con garabatos
   o la impresora tira `err: no seam!`, es esto: probá el otro.
4. Con **más de una** impresora emparejada, la app no adivina: hay que
   elegirla. Mandar la comanda a la equivocada es peor que no imprimir.

#### Por qué existe la consulta de estado

Un `write()` sobre el socket SPP tiene éxito mientras el enlace RFCOMM esté
vivo, y eso **no** significa que el firmware procesó nada: una impresora
trabada mantiene el enlace abierto y tira los bytes. Medido: cuatro trabajos
seguidos registraron `enviados 888/888 bytes` sin un solo error y no salió ni
un papel; los mismos trabajos, después de apagar y prender la impresora,
salieron bien — **con logs idénticos**. El cajero cobraba, la app confirmaba,
y nadie se enteraba de que el comensal no tenía su hoja.

Así que antes de mandar el trabajo se le pregunta a la impresora (`<ESC>!?` en
TSPL, `DLE EOT 1` en ESC/POS) y se **lee** la respuesta. Con un motivo
concreto se corta antes de gastar el trabajo.

##### La sonda tiene que dejar el parser limpio (o no imprime nada)

Esto se rompió de verdad, y el síntoma fue **idéntico** al bug que la sonda
venía a eliminar: `sonda 0x0 -> lista`, `enviados 888/888 bytes`, cero
errores, cero papel.

TSPL es un protocolo de **líneas terminadas en CRLF**, y la sonda va sin
terminador. La HiLabel contesta la consulta —se lee el `0x00`— pero **igual
deja esos tres bytes en su buffer de líneas**. El primer comando del trabajo
le llega entonces como:

```
\x1B!?SIZE 72 mm,87 mm     <- comando invalido, se descarta
```

Sin `SIZE`, la etiqueta nunca recibe su tamaño y no sale nada.

Se confirmó con dos etiquetas idénticas mandadas al plugin: la normal no
imprimió, la que llevaba un `\r\n` adelante salió perfecta. **Ahora la sonda
manda el CRLF ella misma** después de leer la respuesta.

En **ESC/POS no se manda**: ahí `0x0D`/`0x0A` son retorno de carro y avance de
línea, o sea que moverían el papel en cada impresión.

> **La regla general:** una sonda de diagnóstico que comparte el canal con los
> datos tiene que devolver el parser al estado en que lo encontró. Si no, el
> diagnóstico se convierte en la causa.

**El silencio NO se trata como falla**, a propósito: varias térmicas
económicas no implementan la consulta, y rechazar por no obtener respuesta
dejaría sin imprimir a una impresora sana — peor que el problema original.
En esos modelos la app no puede avisar si se traba, y el botón `Estado` lo
dice con esas palabras en vez de fingir que todo está bien.

#### En logcat

```bash
adb logcat -v time | grep -iE "Termica"
# [Termica] imprimiendo en tspl ancho 80 destino 86:67:...
# D ImpresoraTermica: sonda tspl: 0x0 -> lista          <- el estado crudo
# D ImpresoraTermica: enviados 565/565 bytes en trozos de 180
# [Termica] la impresora confirmo estado: lista
```

Los dos renglones que importan:

- **`sonda ... -> ...`** es el estado en crudo (`0x0` lista, `0x4` sin papel).
  El código hexadecimal va acá y **no** en pantalla: al dueño del restaurante
  un "código 0x0" le hace dudar justo cuando el mensaje dice que está todo
  bien.
- **`la impresora confirmo estado`** vs **`NO confirmo`** distingue "imprimió"
  de "se enviaron los bytes y nadie confirmó nada", que antes eran lo mismo.

Si falla, **no aparece** la línea de `enviados`: cortó antes.

---

## Notificaciones

Llegan por FCM nativo (`@capacitor/push-notifications`), no por Web Push
—que no existe en un WebView—. `capacitor-init.js` expone el token con la
misma forma que espera `push-notifications.js`, así que ese archivo no
necesita saber qué hay abajo.

### ⚠️ El plugin NO es opcional a medias: o va con Firebase, o no va

`@capacitor/push-notifications` arrastra el SDK nativo de Firebase, que se
inicializa en el **arranque de la aplicación**. Sin
`android/app/google-services.json`, el APK **compila bien, instala bien, y
crashea al abrir**:

> *"RestoMind continúa fallando"*

Nada en la consola de compilación lo delata — el error pasa en el
dispositivo. Pasó una vez y costó encontrarlo.

**Esto no es una limitación de Capacitor.** El archivo lo exige el SDK de
Firebase para Android: con React Native, Flutter, Cordova o Android nativo
puro, el resultado sería idéntico.

Por eso `tools/integrar-android.mjs` **frena el build** si detecta el plugin
instalado sin el archivo, con las dos salidas puestas en el mensaje. Es
preferible no poder compilar a repartir un APK que se sabe que no abre.

### Estado actual: sin push

El plugin está desinstalado, así que la app funciona y **no recibe avisos de
comandas**. Para activarlos, cuando exista el proyecto Firebase:

```bash
# 1. google-services.json va en android/app/
npm install @capacitor/push-notifications
npm run apk
```

Y activar el plugin de Gradle (`com.google.gms.google-services`) en los dos
`build.gradle`. El resto del circuito —`/push/registrar`, el canal
`comandas`, la prioridad alta en el backend— ya está hecho y probado.
