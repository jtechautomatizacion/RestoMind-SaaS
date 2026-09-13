# Consulta de RUC con el Padrón Reducido de SUNAT

Cuando un comensal pide factura y dicta su RUC, el cajero tiene que tipear
la razón social exacta. Con esto la escribe el sistema.

Todo corre **en tu servidor**: sin APIs de pago, sin límites de consultas y
sin depender de que un tercero siga en línea.

---

## Lo primero: ¿es legal?

**Sí, con condiciones que ya están implementadas.** Vale la pena entenderlas
porque si el sistema escala, esto es lo que te van a preguntar.

**La fuente es oficial y pública.** SUNAT publica el Padrón Reducido en
[su página de descargas](https://www.sunat.gob.pe/descargaPRR/mrc137_padron_reducido.html)
justamente para que los contribuyentes puedan validar a sus contrapartes.
Completar la razón social de un comprobante es el uso para el que existe.

**Pero contiene datos personales.** Los RUC que empiezan en **10, 15, 16 y
17 son personas naturales**: su "razón social" es el nombre y apellidos de
una persona real. Eso es dato personal bajo la **Ley N° 29733**.

Procesarlo es lícito porque viene de una **fuente de acceso público**, pero
eso no habilita cualquier uso. Tres reglas que el código ya aplica y que
conviene no aflojar:

| Regla | Dónde está | Por qué |
|---|---|---|
| Solo se guardan 4 campos | `cargar_padron_sunat.py` | Las 11 columnas de domicilio se descartan: una boleta no las pide. Guardar el domicilio de 19 millones de personas sin usarlo es acumulación innecesaria |
| Nunca sin autenticar | `routes/ruc.py` | Un endpoint público sobre esta base es una API de divulgación masiva de datos personales |
| Cuota por IP | `rate_limit.py` | Sin tope, cualquiera se descarga el padrón entero desde tu servidor |

**Lo que NO podés hacer** con estos datos: revenderlos, usarlos para
marketing, o exponer una búsqueda pública por nombre. Nada de eso es
"consultar el padrón para facturar".

> Esto es orientación de ingeniería, no asesoría legal. Si el sistema escala
> a muchos restaurantes, conviene que un abogado revise tu política de
> privacidad.

---

## Lo segundo: ¿te entra en el VPS?

Números **medidos**, no estimados:

| | |
|---|---|
| ZIP a descargar | **374 MB** |
| Texto sin comprimir | **1,497 MB** (nunca toca el disco: se procesa al vuelo) |
| Contribuyentes | ~19 millones |
| **Base final** | **~1.6 GB** |
| Velocidad de carga | ~300,000 filas/seg |
| Tiempo total | ~5-10 min (el índice es lo lento) |

**RAM:** no es problema. SQLite trabaja sobre disco; una consulta toca unas
pocas páginas. Tus 2 GB alcanzan de sobra.

**Disco:** necesitás ~2 GB libres. Verificá antes con `df -h`.

**Cuidado:** la primera carga hace trabajar el disco varios minutos. Corrila
**fuera del horario de atención** o el servicio a los comensales se va a
sentir lento.

---

## Instalación

```bash
cd /opt/restomind
mkdir -p data

# Descarga y construye en un solo paso (~5-10 min)
python -m backend.scripts.cargar_padron_sunat
```

Probá primero con una muestra, que tarda segundos:

```bash
python -m backend.scripts.cargar_padron_sunat --limite 100000
```

Verificá:

```bash
curl -H "Authorization: Bearer $TOKEN" http://127.0.0.1:8000/api/ruc-padron/estado
# {"disponible":true,"contribuyentes":19123456,"actualizado_en":"..."}
```

**Sin este paso la app funciona igual.** La consulta de RUC responde 503 con
instrucciones; todo lo demás anda normal.

## Mantenerlo al día

SUNAT lo actualiza **a diario**. Una vez por semana de madrugada alcanza:

```bash
crontab -e
# domingos 3:30 AM
30 3 * * 0 cd /opt/restomind && /opt/restomind/.venv/bin/python -m backend.scripts.cargar_padron_sunat >> /var/log/padron.log 2>&1
```

**No hay ventana de corte.** El script construye en un archivo aparte y solo
al final lo reemplaza de un golpe. Durante los 10 minutos de carga, las
consultas siguen respondiendo con la base anterior.

---

## Los endpoints

```
GET /api/ruc/{ruc}            → cualquier rol con sesión
GET /api/ruc-padron/estado    → solo admin
```

```jsonc
// GET /api/ruc/20123456786
{
  "ruc": "20123456786",
  "encontrado": true,
  "nombre": "MI RESTO SAC",
  "estado": "ACTIVO",
  "condicion": "HABIDO",
  "persona_natural": false,
  "puede_facturarse": true,
  "advertencia": null
}
```

- **`encontrado: false` no es un error** (responde 200). Puede ser un RUC
  reciente o tu copia estar vieja. El cajero igual emite escribiendo el
  nombre a mano.
- **`advertencia`** aparece cuando el contribuyente está de baja o no
  habido. Avisar **antes** de emitir sirve; después, SUNAT ya observó el
  comprobante.
- **`persona_natural`** te dice si mostrar "Nombre" en vez de "Razón social".

**Ruta:** quedó en `/api/ruc/{ruc}` y no en `/api/v1/ruc/{ruc}` para seguir
la convención del resto de la app (`/api/mesas`, `/api/facturas`...).
Introducir un `/v1` solo acá dejaría dos estilos conviviendo sin que nada
más esté versionado.

---

## Rendimiento real

Medido sobre datos reales del padrón, 2000 consultas aleatorias:

| | |
|---|---|
| Mediana | **0.022 ms** |
| p95 | 0.040 ms |
| p99 | 0.063 ms |

Tu objetivo eran 50 ms en móvil. La consulta usa **el 0.04% de ese
presupuesto**; los otros ~49.9 ms son el viaje de red hasta el VPS.

**Por eso no se agregó Redis.** Cachear algo que tarda 0.022 ms no ahorra
nada perceptible, y sumaría un servicio más que mantener, monitorear y que
puede quedar desincronizado. Si algún día la consulta se vuelve lenta, será
por el disco del VPS, y ahí la respuesta es más caché de SQLite, no otra
pieza.

---

## De paso: dos bugs que esto destapó

**1. Se rechazaban RUC válidos.** La validación aceptaba solo prefijos
`10` y `20`. SUNAT también usa **15, 16 y 17** para personas naturales. En
una muestra de 154,132 contribuyentes reales, **11,432 (7.4%)** empezaban en
15 o 17 — a todos ellos la app les rechazaba el RUC al pedir factura.

**2. No se validaba el dígito verificador.** Un RUC con un dígito mal
tipeado pasaba la validación y lo rechazaba SUNAT después, con la venta ya
cobrada. Ahora se verifica antes (algoritmo comprobado contra esos 154,132
RUC reales, 100% de coincidencia).
