# Emitir boletas desde el servidor (emisor `sunat_cloud`)

Esta es la tercera forma de emitir boletas en RestoMind. Sirve para el
restaurante que **no tiene una PC con Windows** — el que trabaja solo con
tablets o celulares.

## Cuál te conviene

| | `sfs_local` (la de hoy) | `sunat_cloud` (esta) |
|---|---|---|
| Costo por boleta | S/ 0 | S/ 0 |
| ¿Necesita PC Windows prendida? | **Sí** | No |
| ¿Necesita certificado digital? | No | **Sí** |
| ¿RestoMind sabe si SUNAT aceptó? | No | **Sí** |
| ¿Hay que instalar algo en el local? | Sí (Facturador + agente) | No |

**Si ya tenés el Facturador andando y una PC en la caja, no cambies nada.**
Esta opción es para el local que no quiere depender de una computadora.

---

## Lo que hay que conseguir primero

### 1. El certificado digital tributario

Es un archivo `.pfx` con una clave. Es lo que le prueba a SUNAT que la
boleta la emitiste vos y no otro.

- Se compra en una entidad autorizada por INDECOPI. Cuesta más o menos
  **S/ 100 a S/ 300 al año**.
- **No se puede evitar.** Sin certificado, SUNAT no acepta nada.
- Mientras no lo tengas, podés probar todo con el **certificado de prueba
  que SUNAT publica gratis** para su ambiente BETA.

### 2. Estar dado de alta como emisor electrónico

Se hace en SUNAT Operaciones en Línea. Si ya venías emitiendo con el
Facturador, esto ya está.

### 3. Un usuario SOL secundario

No uses tu usuario principal. Creá uno aparte solo para facturar, así lo
podés dar de baja si algo pasa sin perder el acceso a tu cuenta.

---

## Instalación en el servidor

### Paso 1 — Poner los archivos del restaurante

Una carpeta por restaurante, con el `cliente_id` como nombre:

```bash
mkdir -p /opt/restomind/certs/rest-001
cd /opt/restomind/certs/rest-001

# 1. El certificado
cp /ruta/donde/lo/tengas/micertificado.pfx  certificado.pfx

# 2. La clave del certificado (sin Enter al final)
printf '%s' 'LA-CLAVE-DEL-PFX' > clave.txt

# 3. Usuario y clave SOL, en dos líneas
printf '%s\n%s\n' 'MIUSUARIO' 'MICLAVE' > sol.txt
```

**Cerrá los permisos.** Con estos archivos cualquiera puede facturar a
nombre del restaurante:

```bash
chmod 700 /opt/restomind/certs/rest-001
chmod 600 /opt/restomind/certs/rest-001/*
```

> Estos archivos **nunca** entran a la base de datos de RestoMind. El único
> proceso que los lee es el contenedor de emisión. Así, si alguien roba un
> backup de la base, no se lleva con qué facturar.

### Paso 2 — Generar el token del servicio

```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

Ponelo en el `.env`:

```ini
# El contenedor de emisión
SUNAT_MODE=beta
SUNAT_SERVICE_TOKEN=<lo que imprimió el comando>

# RestoMind (el mismo token)
EMISOR_FACTURACION=sunat_cloud
SUNAT_SERVICE_URL=http://127.0.0.1:8100
SUNAT_SERVICE_TOKEN=<el mismo de arriba>
```

### Paso 3 — Levantar el contenedor

```bash
cd /opt/restomind
docker compose up -d --build
docker compose logs -f sunat-service
```

Comprobar que está vivo:

```bash
curl http://127.0.0.1:8100/health
# {"ok":true,"modo":"beta","certs_dir_montado":true}
```

### Paso 4 — Migrar la base y reiniciar

```bash
python -m backend.migrate      # agrega facturas.cdr_xml
sudo systemctl restart restomind
```

---

## Probar SIN emitir nada de verdad

Con `SUNAT_MODE=beta` nada de lo que mandes cuenta como comprobante real.
Hacé un cobro de prueba y mirá los logs.

También podés armar el XML sin firmar ni enviar, que es donde están casi
todos los errores de formato:

```bash
curl -X POST http://127.0.0.1:8100/previsualizar \
  -H "X-Sunat-Token: $SUNAT_SERVICE_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "cliente_id":"rest-001","serie":"B001","numero":1,
    "fecha_emision":"2026-09-09",
    "emisor":{"tipo_doc":"6","numero_doc":"20123456789","razon_social":"MI RESTO SAC"},
    "receptor":{"tipo_doc":"0","numero_doc":"00000000","razon_social":"PUBLICO GENERAL"},
    "lines":[{"codigo":"1","descripcion":"Ceviche","cantidad":"1","precio_unitario":"100.00"}]
  }'
```

**Esto funciona sin certificado.** Sirve para verificar que los montos salen
bien antes de gastar en el `.pfx`.

Cuando todo esté bien, recién ahí `SUNAT_MODE=prod`.

---

## El detalle de los montos (importante)

En la carta ponés **S/ 118** y eso es lo que paga el comensal, con IGV
incluido. SUNAT quiere el precio **sin** IGV: S/ 100, y el impuesto aparte.

RestoMind hace esa cuenta solo, en un único lugar
(`backend/utils/sunat_cloud.py::precio_sin_igv`). Está así por una razón: si
alguien "simplifica" mandando el precio de carta directo, **cada boleta
declararía 18% de más** y nada fallaría a la vista. Los tests de
`tests/unit/test_sunat_cloud.py` existen para atrapar exactamente eso.

### El céntimo que no se puede evitar (leer antes de ir a producción)

Hay precios para los que **la boleta declara un céntimo distinto** de lo que
pagó el comensal. No es un error de programación: es cómo redondea SUNAT.

| Precio de carta | Se cobró | La boleta diría |
|---|---|---|
| S/ 10.00 × 1 | S/ 10.00 | **S/ 9.99** |
| S/ 45.00 × 1 | S/ 45.00 | **S/ 45.01** |
| S/ 120.00 × 1 | S/ 120.00 | **S/ 119.99** |
| S/ 45.00 × 2 | S/ 90.00 | S/ 90.00 ✓ |

**Por qué pasa.** SUNAT calcula el IGV como 18% de una base redondeada a
céntimos. Para S/ 10.00: con base 8.47 el total da 9.99; con 8.48 da 10.01.
**No existe ninguna base intermedia.** Ningún ajuste de decimales lo
arregla — se midió y con 4 decimales descuadran 5 de cada 12 boletas.

**Qué hace RestoMind.** No lo esconde: calcula el desvío antes de enviar y,
si lo hay, lo deja anotado en la boleta (visible en Admin > Boletas). Así,
al cuadrar la caja contra los comprobantes a fin de mes, la diferencia tiene
explicación en vez de parecer un faltante.

**Qué podés hacer vos.** Las opciones reales son dos, y es una decisión de
negocio, no técnica:

1. **Convivir con el céntimo.** Es lo que hace la mayoría de los locales, y
   SUNAT lo tolera. El desvío queda registrado.
2. **Elegir precios de carta que cuadren.** Un precio que sale de una base
   limpia siempre cuadra: S/ 9.99 en vez de S/ 10.00, S/ 45.02 en vez de
   S/ 45.00. Cambia los precios visibles, pero elimina el problema.

> Esto **no** aparece con `sfs_local`, porque ahí RestoMind manda el total ya
> descompuesto y el Facturador no lo recalcula.

---

## Qué hacer cuando algo falla

| Mensaje | Qué pasó | Qué hacer |
|---|---|---|
| `SIN_CERTIFICADO` | No hay `certificado.pfx` en la carpeta | Paso 1 |
| `CERTIFICADO_INVALIDO` | La clave está mal o el certificado venció | Revisar `clave.txt` |
| `SIN_CREDENCIALES_SOL` | Falta `sol.txt` o le falta una línea | Paso 1 |
| `RECHAZO_SUNAT` | SUNAT lo miró y dijo que no | Leer el detalle. Reintentar igual **no** sirve |
| `TRANSPORTE` | SUNAT no contestó (caído, sin red) | Reintentar desde Admin > Boletas. El número no se pierde |

Una boleta que falla **nunca se pierde ni gasta su número**: queda en
Admin > Boletas para reintentar. El correlativo se reserva al crearla y el
reintento usa el mismo, así que la numeración no se saltea.

---

## Volver atrás

Si esto no funciona, se vuelve al Facturador sin perder nada:

```ini
EMISOR_FACTURACION=sfs_local
```

Y reiniciar. Las boletas ya emitidas quedan como están — cada una guarda con
qué emisor salió.

---

## Lo que NO está incluido, y por qué

**La consulta de RUC en vivo** (el repositorio `sistema-de-consulta-ruc-sunat`
que aparecía en la propuesta original) **no se integró**, por dos motivos:

1. **No tiene licencia.** Un repositorio sin archivo de licencia es, por
   defecto, "todos los derechos reservados": legalmente no se puede usar
   dentro de un producto que se vende. Habría que pedirle permiso por escrito
   al autor.
2. **El padrón no viene incluido** (el repo pesa 83 KB). Son unos 10 millones
   de registros para descargar y armar, en un VPS de 2 GB que ya corre
   RestoMind, nginx y SQLite.

RestoMind ya valida que el RUC tenga 11 dígitos y empiece en 10 o 20, que es
lo que evita el 99% de los errores de tipeo. Buscar la razón social a partir
del RUC es cómodo, pero no hace falta para emitir.
