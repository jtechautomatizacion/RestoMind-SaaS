# Punto de control — 2026-09-18

Dónde quedó el proyecto, qué está verificado y qué no, para retomar sin
volver a averiguarlo.

**Estado:** 360 tests en verde · árbol de git limpio · APK de pruebas
instalado en el celular.

---

## Lo que existe ahora y antes no

| | Dónde | Verificado |
|---|---|---|
| Entorno de **pruebas** aislado | `npm run servir-testing` (puerto 8010) | sí — el celular le pega y producción no se toca |
| **Dos apps** en el mismo teléfono | `com.restomind.pos` y `.pruebas` | sí — conviven, datos separados |
| Pedidos **para llevar** | Mesas y "Todo en uno" | sí — 11 tests |
| **Aviso** de comanda nueva | sonido + vibración | sí — la lógica, en banco de pruebas |
| **Ícono y splash** de la marca | generados del logo | sí — a ojo, en el teléfono |
| Aviso de **versión nueva** | `GET /api/app/version` | sí — endpoint responde |
| **Consulta de estado** de la impresora | botón `Estado` en Admin → Impresora | sí — contra la HiLabel real: `0x0` lista y `0x4` sin papel |
| El cobro **se niega** a imprimir con falla física | `plugin-impresora/ImpresoraTermica.java` | sí — con la tapa abierta no manda el trabajo |

---

## Lo que hay que probar A MANO, y por qué

La suite no llega acá. Decirlo explícito vale más que suponer que está
cubierto.

1. **Que el ticket salga en papel.** Los tests verifican que el HTML se
   genera y que se convierte a bytes de impresora (542 bytes para un pedido
   para llevar). Que la impresora física lo imprima depende del papel, del
   Bluetooth y del lenguaje — eso solo se ve en el mostrador.
   *Verificado a mano el 2026-09-18 contra la HiLabel: sale el papel, y con
   la tapa abierta el cobro avisa en vez de fingir que imprimió.*
2. **Que las fotos se vean en el APK.** Se verificó que el backend las sirve
   (HTTP 200, JPEG) y que la app arma bien la URL. Falta confirmarlo en
   pantalla.
3. **Los dos logins en el APK** (admin y superadmin). Se verificó que el
   backend los acepta y que la página del superadmin ya carga su
   configuración. Falta entrar de verdad.
4. **El splash** en Android 12+.

---

## Las trampas que ya nos costaron, para no repetirlas

Cada una se rompió de verdad en este proyecto. Ninguna daba un error que
apuntara al problema.

### "Unexpected token '<' ... is not valid JSON"

**Siempre es lo mismo:** una ruta relativa dentro del APK. La app se sirve
desde `https://localhost`, así que `/api/...` le pega al PROPIO TELÉFONO, que
contesta `index.html`. El código esperaba JSON y recibió HTML.

Pasó dos veces: primero en `superadmin.js`, que tenía su propia línea
`const API_BASE_URL = '/api'` escrita aparte; después en TODA la app, cuando
la compilación borró media configuración (ver abajo).

**Regla:** toda URL contra el backend sale de `window.RESTOMIND_API_BASE`, y
toda ruta de archivo pasa por `urlDeArchivo()`. Las dos viven en
`frontend/js/destino-api.js`, que es el único lugar donde se decide el origen.

### La compilación borraba media configuración

`preparar-apk.mjs` fijaba el destino **escribiendo dos líneas encima de todo
el archivo**. Mientras `destino-api.js` tuvo una línea, funcionó. Cuando pasó
a tener la lógica del origen, la compilación la borró: de 68 líneas quedaban 2.

El APK se armaba, instalaba y abría perfecto. El archivo roto solo se veía
abriendo el paquete.

**Ahora:** se reemplaza el valor y no el archivo, y la compilación **verifica
lo que empaquetó** — no la variable que quiso escribir, porque esa diferencia
era el bug. Si falta cualquiera de los cuatro globales, corta.

### "La impresora despierta y no imprime"

Tiene DOS causas distintas, y se ven igual desde afuera.

**1. El lenguaje.** Una impresora de ETIQUETAS (Hilebel, Niimbot, Zebra…) no
entiende ESC/POS: recibe los bytes, no reconoce ningún comando y no hace nada.
**No hay error en ninguna parte.**

Pasó dos veces. La segunda al instalar la app de pruebas, que por tener otro
`applicationId` arranca con almacenamiento propio y quedó en ESC/POS.

**Ahora:** la app preselecciona TSPL si el nombre es de una marca de
etiquetas, y el aviso de la prueba dice en qué lenguaje salió.

**2. La impresora está trabada, y la app decía que había impreso.** Un
`write()` sobre el socket SPP tiene éxito mientras el enlace RFCOMM esté vivo,
y eso **no** significa que el firmware procesó nada: trabada, mantiene el
enlace abierto y tira los bytes.

Medido: cuatro trabajos seguidos registraron `enviados 888/888 bytes` sin un
solo error y no salió ni un papel; los mismos, después de apagar y prender la
impresora, salieron bien — **con logs idénticos**. El cajero cobraba, la app
confirmaba, y nadie se enteraba de que el comensal no tenía su hoja.

**Ahora:** se le pregunta a la impresora ANTES de mandarle el trabajo
(`<ESC>!?` en TSPL, `DLE EOT 1` en ESC/POS) y se **lee** la respuesta — el
socket siempre fue bidireccional, solo se estaba escribiendo. Con un motivo
concreto corta antes de gastar el trabajo, y el botón **`Estado`** (Admin →
Impresora) lo consulta sin gastar papel.

El silencio **no** se trata como falla, a propósito: varias térmicas económicas
no implementan la consulta, y rechazar por no obtener respuesta dejaría sin
imprimir a una impresora sana. Detalle completo en `APK_ANDROID.md`.

### La consulta de estado dejó de imprimir TODO (y el síntoma era el mismo)

La peor de todas, porque **el arreglo causó el bug que venía a arreglar**, con
el mismo síntoma exacto: `sonda 0x0 -> lista`, `enviados 888/888 bytes`, cero
errores, cero papel.

TSPL es un protocolo de **líneas terminadas en CRLF** y la sonda (`<ESC>!?`) va
sin terminador. La impresora contesta la consulta **y además deja esos tres
bytes en su buffer de líneas**, así que el primer comando del trabajo le llega
como `\x1B!?SIZE 72 mm,87 mm` — inválido, se descarta, la etiqueta nunca recibe
su tamaño.

**Cómo se encontró:** dos etiquetas idénticas mandadas directo al plugin, una
con un `\r\n` adelante y otra sin él. La normal no imprimió; la del CRLF salió
perfecta. Un experimento de dos casos vale más que leer el firmware.

**Ahora:** la sonda manda el CRLF ella misma después de leer la respuesta. En
ESC/POS no, porque ahí `0x0D`/`0x0A` mueven el papel.

**La regla que queda:** una sonda de diagnóstico que comparte el canal con los
datos tiene que devolver el parser al estado en que lo encontró.

### Editar el Java de la impresora en el lugar equivocado

`android/app/src/main/java/com/restomind/pos/ImpresoraTermica.java` es una
**copia generada**. La fuente es `plugin-impresora/ImpresoraTermica.java`, y
`tools/integrar-android.mjs` la copia encima **en cada build** — por diseño,
para que no se pierda con `cap sync`.

Editar la copia y compilar sale **BUILD SUCCESSFUL** con los cambios borrados.
Se detecta preguntándole al puente qué métodos expone:

```js
Object.keys(window.Capacitor.Plugins.ImpresoraTermica)
// si el método nuevo no está, se compiló la copia vieja
```

### `gradlew` no arranca si la ruta del proyecto tiene espacios

```
"D:\Cartera" no se reconoce como un comando interno o externo
```

Es un bug conocido de Node en Windows (`nodejs/node#38490`): el citado que
arma para `cmd.exe /d /s /c` no sobrevive un `cwd` con espacios. Ya está
corregido en `tools/compilar.mjs` (usa `shell: true`), pero si aparece en otro
script que llame a un `.bat`, es esto.

### Con la app en segundo plano, los callbacks del plugin no llegan

Android congela el WebView cuando la app pasa a background: el **nativo sigue
corriendo** (sondea, imprime) pero el resultado nunca vuelve al JS, así que el
`await` queda colgado para siempre. Depurando por DevTools se ve como un bug
del plugin.

Se confirma en `http://localhost:9222/json/list`: `"visible": false`. En uso
real no pasa —el cajero tiene la app al frente— pero si alguna vez un cobro
queda colgado, mirá si la pantalla estaba apagada.

### 80 mm de papel no son 80 mm imprimibles

El cabezal cubre **72 mm (576 puntos)**. Lo que se posiciona más allá no da
error: la impresora lo ENVUELVE al renglón siguiente, y el ticket sale partido
("Importe" → "Impo"/"rte").

`npm run probar-termica` dibuja la hoja y lo denuncia. La comprobación mide
contra el ancho del cabezal —un dato físico, escrito a mano en el llamador— y
no contra lo que declara el código: la primera versión medía contra sí misma y
por eso no servía para nada.

### Un error de pantalla se comía el ticket

Imprimir iba DESPUÉS de refrescar la pantalla y en el mismo `try`. Cualquier
error al redibujar se llevaba puesta la impresión, y el pedido quedaba bien
guardado: el síntoma era "no imprime", sin ningún error a la vista.

**Ahora:** imprimir va primero y en su propio `try`. Es el orden correcto de
todos modos — el cliente espera el papel, no que se redibuje una grilla.

---

## Cómo retomar

```bash
# 1. Backend de pruebas (base propia, puerto 8010)
npm run servir-testing

# 2. Si querés datos frescos de tu base real
npm run clonar-a-pruebas

# 3. APK de pruebas al celular
npm run apk:testing
adb install -r RestoMind-pruebas.apk

# 4. Antes de dar algo por terminado
python -m pytest -q          # 360 en verde
npm run probar-termica       # dibuja los tickets y busca desbordes
```

---

## Lo que falta

- **Generar la clave de firma** (`node tools/crear-clave.mjs`) y respaldarla
  fuera de la PC. Sin ella, `npm run apk` produce un APK sin firmar que no se
  instala. Y sin ella no hay actualizaciones nunca (ver `COMO_TRABAJAR.md`).
- **Reinstalar la app de producción** en el celular: se desinstaló durante las
  pruebas. Conviene hacerlo recién con la clave ya generada, para que las
  actualizaciones futuras entren sin desinstalar.
- **Notificaciones con la app cerrada.** Necesitan un proyecto Firebase que
  hoy no existe; el APK no trae el plugin. El aviso con la app abierta ya
  funciona y no depende de nada de eso.
- **Publicar `APK_VERSION_CODE` y `APK_URL`** en el `.env` del servidor para
  que el aviso de versión nueva empiece a servir.
