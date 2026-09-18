# Cómo se trabaja una app móvil, y cómo se trabaja ésta

Escrito para el dueño de RestoMind: alguien que programa solo, que ya tiene la
app funcionando, y que va a vender el sistema a varios restaurantes. La
primera parte explica cómo lo hace la industria y por qué; la segunda, los
comandos concretos de este proyecto.

---

## 1. La pregunta de fondo: ¿testing y producción son lo mismo?

**El código, sí. La configuración, no. Y los datos, jamás.**

Esa distinción es toda la respuesta, y vale la pena entender cada parte.

### El código tiene que ser idéntico

Si el APK de pruebas corriera un código distinto del que se entrega, probar
no probaría nada: estarías aprobando un programa y entregando otro. Por eso
no se usan `if (esPruebas) { ... }` repartidos por el código. Lo que cambia
entra **desde afuera**, como configuración.

### La configuración tiene que ser distinta

A qué servidor le habla, cómo se llama la app, qué ícono usa. Nada de eso
cambia el comportamiento del programa: cambia contra qué trabaja.

### Los datos tienen que estar separados

Éste es el que más caro se paga cuando se ignora. Hasta hace unos días, este
proyecto tenía la URL de producción escrita adentro del código del APK. Cada
prueba de impresión creaba **comandas reales en la base del restaurante**, y
no había forma de notarlo mirando la app.

Ese es el accidente clásico. No pasa por descuido: pasa porque el sistema no
hacía visible la diferencia.

### Cuántos entornos usa la industria

| Entorno | Para qué | Quién lo usa |
|---|---|---|
| **Desarrollo** | Escribir código, romper cosas | Vos, en tu PC |
| **Pruebas / staging** | Probar como si fuera real, sin serlo | Vos, en tu celular |
| **Producción** | El negocio de verdad | Los restaurantes |

Equipos grandes agregan más (QA, preproducción, canary). Para un producto de
una persona, **tres son el número correcto**: menos deja huecos, más son
entornos que nadie mantiene y que terminan mintiendo.

---

## 2. Por qué son dos apps instaladas, y no una que cambia de servidor

Android identifica cada app por su `applicationId`. Dos APK con el mismo id
son la misma app para el sistema, aunque por dentro sean distintos.

Consecuencia concreta, que ya pasó acá: instalar el APK de pruebas
**reemplazaba** la app real del restaurante. Se perdía la sesión abierta y la
impresora configurada, y quedaba una sola app cuyo servidor dependía de cuál
fue el último APK instalado. Imposible saber, mirando el teléfono, contra qué
estaba trabajando.

La solución estándar se llama **product flavors**, y se resume en una línea:

```gradle
pruebas {
    applicationIdSuffix ".pruebas"        // com.restomind.pos.pruebas
    resValue "string", "app_name", "RestoMind PRUEBAS"
}
```

Con eso son dos apps para Android: dos íconos, dos sesiones, dos
configuraciones de impresora, y conviven en el mismo teléfono. Podés tener la
app real del restaurante abierta y la de pruebas al lado.

---

## 3. Cómo se actualiza la app

### Lo primero: la firma

**Android solo acepta actualizar una app si el APK nuevo está firmado con la
misma clave que el instalado.**

Si perdés esa clave:

- no podés publicar ninguna actualización más de esta app, nunca;
- cada restaurante tendría que desinstalar —perdiendo sus datos— e instalar
  la app nueva como si fuera de otra empresa.

No hay forma de recuperarla. Google no puede reemplazarla. Se genera una vez:

```bash
node tools/crear-clave.mjs
```

Y se respalda **fuera de la computadora**: un disco externo, o tu gestor de
contraseñas. No está en git a propósito — con ese archivo, cualquiera puede
publicar un APK que los teléfonos aceptarían como actualización legítima
tuya.

Si hay una sola cosa de este documento que valga la pena recordar, es ésta.

### Lo segundo: el número de versión

`version.json`, en la raíz:

```json
{ "versionCode": 2, "versionName": "1.1.0" }
```

- **`versionCode`** es un entero que **solo sube**. Es lo único que mira
  Android para decidir si un APK es más nuevo que el instalado. Si no sube,
  el teléfono rechaza la instalación con un "app no instalada" que no explica
  nada. Nunca se reutiliza un número ya entregado, ni siquiera corrigiendo un
  error: se sube al siguiente.
- **`versionName`** es la que lee una persona. `MAYOR.MENOR.PARCHE` —
  parche para arreglos, menor para cosas nuevas, mayor para cambios grandes.

### Lo tercero: que el restaurante se entere

Sin una tienda, nada le avisa: baja el APK de un enlace y ahí se queda. Un
local puede trabajar meses con una versión vieja, y el primer síntoma sería
un bug ya corregido reportado como nuevo.

Por eso el backend publica cuál es la versión vigente:

```
GET /api/app/version   ->  { version_code, version_name, url_descarga }
```

La app se compara al arrancar y muestra un aviso si está atrasada. **Avisa,
no obliga**: forzar una actualización en medio del servicio, con mesas
abiertas y gente esperando, es peor que dejar correr una versión vieja un
rato más.

Se configura en el `.env` del servidor, y se sube **recién cuando el APK
nuevo ya está descargable**:

```
APK_VERSION_CODE=2
APK_VERSION_NAME=1.1.0
APK_URL=https://...
```

---

## 4. Cómo entregarles la app a tus clientes

Cuatro caminos reales, de menos a más formal:

| Camino | Ventaja | Costo |
|---|---|---|
| **Enlace directo** (lo que hacés hoy) | Cero trámite, cero espera | El cliente tiene que permitir "orígenes desconocidos"; nadie le avisa de las actualizaciones (por eso el aviso del punto 3) |
| **Play Store, listado privado** | El cliente actualiza solo, como cualquier app | Cuenta de desarrollador (pago único ~25 USD), revisión de Google |
| **Managed Google Play** | Pensado justamente para apps de empresa | Necesita que el cliente tenga Android Enterprise — improbable en un restaurante chico |
| **Firebase App Distribution** | Muy cómodo para tus propias pruebas | Es para testers, no para clientes finales |

**Para cinco restaurantes, el enlace directo alcanza.** Cuando sean veinte,
la Play Store se paga sola: te ahorra explicarle a cada dueño cómo instalar
un APK, y las actualizaciones dejan de ser un trabajo tuyo.

### Una fecha que conviene tener en el radar

Google empezó a exigir que el desarrollador esté **verificado** para poder
instalar apps por fuera de las tiendas. Arrancó el **30 de septiembre de
2026**, pero solo en **Brasil, Indonesia, Singapur y Tailandia** — Perú no
entra todavía. Google anunció que lo expande al resto del mundo **durante
2027**.

Qué significa para vos: **hoy no te afecta**, pero antes de 2027 vas a tener
que registrarte como desarrollador o pasar a distribuir por la Play Store. No
es urgente; sí conviene no enterarse el día que deje de funcionar.

---

## 5. Los comandos de este proyecto

### El ciclo normal de trabajo

```bash
# 1. Programar, con el servidor de desarrollo de siempre (puerto 8000)
.venv/Scripts/python.exe -m uvicorn backend.app:app --host 0.0.0.0 --port 8000

# 2. Probar en el celular, contra una base que no es la de nadie
npm run servir-testing        # backend de pruebas, puerto 8010
npm run apk:testing           # -> RestoMind-pruebas.apk
adb install -r RestoMind-pruebas.apk

# 3. Cuando está bien: subir la versión y entregar
#    (editar version.json: versionCode +1)
npm run apk                   # -> RestoMind.apk, firmado
```

### Las tres bases de datos

| Base | Dónde | Quién la usa |
|---|---|---|
| `restomind.db` | tu PC, puerto 8000 | vos programando |
| `restomind-testing.db` | tu PC, puerto 8010 | el celular de pruebas |
| la del VPS | `app.jtechsolutiones.com` | los restaurantes |

Puertos distintos a propósito: compartiendo el 8000, cuál de los dos servidores
contesta dependería de cuál arrancó primero, y el celular escribiría en una
base u otra según el orden en que se prendieron las cosas.

### Cómo saber contra qué está hablando el APK

`npm run apk:testing` lo dice al compilar, y lo lee del archivo que quedó
adentro del paquete — no de una variable — así que si el reemplazo fallara,
el mensaje lo delata en vez de confirmar algo que no pasó:

```
El APK va a hablar con:  http://192.168.18.33:8010
  (texto plano: es un APK de PRUEBAS, no lo distribuyas)
```

En el teléfono se distingue solo: la de pruebas se llama **RestoMind
PRUEBAS**.

---

## 6. Tres cosas que rompen y cuyo síntoma engaña

Las tres aparecieron armando esto, y ninguna dice lo que realmente pasa.

**"Sin conexión" cuando el backend está andando.** Puede ser cualquiera de
tres cosas, y ninguna es el wifi:
1. Android bloquea `http://` sin aviso (se resuelve permitiendo texto plano
   solo para el host de pruebas);
2. el WebView lo bloquea **igual** por contenido mixto — la página vive en
   `https://localhost` y pedir a un `http://` está prohibido. Acá el backend
   no registra **ninguna** petición, así que parece un problema de red. Solo
   logcat lo dice;
3. el firewall de Windows. Ojo con éste: la regla que ya existía era para el
   Python del sistema, y el backend corre con el del `.venv` — **otro
   binario**, sin permiso.

**"App no instalada" al actualizar.** Casi siempre el `versionCode` no subió,
o el APK está firmado con otra clave.

**La IP de tu PC cambia sola.** El router la reparte por DHCP. Por eso
`npm run apk:testing` la detecta **en cada compilación** en vez de tenerla
escrita: con un número fijo, el día que cambie el APK deja de conectar y el
síntoma es —otra vez— "Sin conexión".

---

## 7. Lo que falta

- **Generar la clave de firma** (`node tools/crear-clave.mjs`) y respaldarla.
  Hasta que exista, `npm run apk` produce un APK sin firmar que no se puede
  instalar.
- **Publicar `APK_VERSION_CODE` y `APK_URL`** en el `.env` del servidor, para
  que el aviso de actualización empiece a funcionar.
- **Decidir cuándo pasar a la Play Store.** No es urgente con cinco clientes;
  sí antes de 2027, por el punto 4.
