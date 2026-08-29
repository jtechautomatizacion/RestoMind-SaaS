# ✅ ESTADO DEL PROYECTO - RestoMind MVP

## 🎯 Estado Actual: MVP FUNCIONAL + ENHANCEMENTS

Los 5 casos de uso más 4 features adicionales, todos implementados, probados y conectados de punta a punta:

- ✅ **CU-01** Gestión de la Carta: crear/editar/**eliminar** platos (reemplazo de "desactivar")
- ✅ **CU-02** Comandas Express desde el celular del mozo + impresión dual (cocina + mozo)
- ✅ **CU-03** Monitor de Cocina en tiempo real
- ✅ **CU-04** Control de Compras: crear/editar/eliminar gastos (restricción same-day)
- ✅ **CU-05** Dashboard Financiero mejorado: top 3 platos, top 3 gastos, reporte Excel 3 hojas
- ✅ **Cobro de mesa** — flujo que no estaba en la especificación original y que hacía falta para cerrar el ciclo
- ✅ **Fotos de platos** — subir/reemplazar/quitar foto por plato, con compresión en navegador y validación de archivo real en servidor
- ✅ **Gestión de Categorías** — CRUD completo con iconos emoji, asignación dinámica en formularios, protección contra eliminación si hay platos
- ✅ **Reporte Excel** — 3 hojas (Detalle Ventas, Detalle Gastos, Resumen Diario), formato de soles "S/ X.XX", encabezados coloreados, rows congelados
- ✅ **Login real (JWT)** — multi-tenant de verdad: cada restaurante es un Cliente aislado, con sus propios usuarios; ya no hay acceso sin loguearse
- ✅ **Panel General (superadmin)** — pantalla aparte para el dueño del sistema: ve todos los restaurantes dados de alta, sus estadísticas, puede crear uno nuevo desde el navegador, suspenderlo o resetear la contraseña de su admin
- ✅ 56 tests automáticos (`pytest tests/ -v`), todos en verde (24 nuevos tests: categorías, platos, gastos, dashboard, login, panel general)
- ✅ Frontend PWA rediseñado: mobile-first, bottom nav, sin librerías externas, pensado para gama media/baja, service worker v14
- ✅ Datos semilla automáticos al arrancar + backfill automático para BDs existentes (crea admin user si falta, categorías si faltan, repara contraseñas de instalaciones pre-login)

## 🔐 Login real (JWT) — reemplaza el modo de desarrollo sin autenticación

**Por qué se hizo ahora:** el modelo de negocio pasó a ser reventa del
sistema a varios restaurantes. Sin login real, cualquiera que supiera la
URL de la API podía leer o modificar los datos de cualquier restaurante
con solo cambiar un header (`X-Cliente-Id`) — aceptable para una demo de
un solo cliente, inaceptable en cuanto hay más de un tenant.

**Cómo funciona:**
- `POST /api/auth/login` — recibe `{email, password}`, devuelve un JWT
  (`backend/auth.py`, HS256, 12h de expiración) que lleva `sub` (email),
  `cliente_id` y `rol`. Las contraseñas se guardan con bcrypt
  (`backend/models.py: Usuario.password_hash`), nunca en texto plano.
- **Punto único de resolución de identidad:** `backend/dependencies.py`
  (`get_cliente_id`, `get_usuario_actual`) decodifican el JWT del header
  `Authorization: Bearer <token>`. Como casi todas las rutas ya dependían
  de estas dos funciones (para el aislamiento multi-tenant que existía
  desde el MVP original), **quedaron protegidas automáticamente sin tocar
  ni una ruta** — el cambio fue enteramente en `dependencies.py` + `auth.py`.
- `GET /api/auth/me` — valida un token guardado y devuelve el usuario
  actual; lo usa el frontend al abrir la app para saber si la sesión
  sigue viva sin pedir contraseña de nuevo.
- **Sin registro público.** No existe `POST /clientes` ni pantalla de
  alta. Cada restaurante nuevo lo da de alta el dueño del sistema (no el
  cliente final) corriendo `python -m backend.scripts.crear_cliente` en
  el servidor — pide los datos por consola (nombre del restaurante,
  cuántas mesas, email/contraseña del admin) y crea el Cliente + su
  primer Usuario admin. El cliente final nunca ve ni sabe que este script
  existe: solo recibe su URL, su email y su contraseña.
- **Frontend** (`frontend/js/auth.js`): pantalla de login antes de la app,
  token guardado en `localStorage`, `Authorization: Bearer` en cada
  request, redirección automática al login si el token expira o es
  inválido (401), botón de cerrar sesión en el header.
- **Restaurante demo:** `admin@demo.local` / `admin123` (creado por
  `backend/seed.py`). Una instalación vieja (de antes de que existiera
  login) tenía un hash falso que nunca hubiera podido loguearse — el
  backfill automático (`backend/seed.py: backfill_clientes_existentes`)
  lo detecta y lo reemplaza por esta misma contraseña real al arrancar.

**Lo que NO cambió:** el selector de rol por dispositivo (Admin/Mozo/
Cocina/Cajero, botón redondo del header) sigue igual — es una capa
distinta: controla qué pestañas ve un celular compartido en el local,
mientras que el login controla a qué restaurante (tenant) pertenecen los
datos. Son ortogonales a propósito.

**Pendiente para más adelante:** el rol que trae el JWT (`admin`, `mozo`,
`jefe_cocina`) hoy solo se usa para poblar `usuario.rol` en la respuesta
de login; las rutas siguen validando "admin" consultando la tabla
`Usuario` en cada request (`validar_admin()`), no confiando en el rol
del token — a propósito, así revocar o cambiar el rol de alguien surte
efecto de inmediato sin esperar a que expire su token viejo.

## 🏢 Panel General (superadmin) — para administrar la reventa

**Por qué existe:** con login real ya no hay forma de ver "todos mis
restaurantes clientes" desde dentro de la app — cada login solo ve su
propio tenant, por diseño. Sin este panel, dar de alta un restaurante
nuevo requería SSH al servidor y correr un script a mano; suspender a un
cliente que no paga no tenía ninguna interfaz.

**Completamente separado del login de restaurantes, a propósito:**
- Tabla `SuperAdmin` (`backend/models.py`) — ni siquiera es un `Usuario`
  con `cliente_id` nulo: es otra tabla, con su propio login
  (`POST /api/superadmin/login`) y su propio tipo de JWT (`tipo:
  "superadmin"` en el payload, sin `cliente_id`). Así es imposible que un
  descuido de validación deje que un token de restaurante entre al panel
  general, o viceversa — `get_cliente_id`/`get_usuario_actual` rechazan
  cualquier token con `tipo == "superadmin"`, y `get_superadmin_email`
  rechaza cualquier token que no lo tenga (ver `backend/dependencies.py`).
- **Sin registro público**, igual que el alta de restaurantes: la única
  forma de crear una cuenta de superadmin es correr
  `python -m backend.scripts.crear_superadmin` en el servidor, una vez.

**Endpoints** (todos bajo `/api/superadmin/*`, todos exigen el JWT de superadmin):
```
POST  /superadmin/login                        → devuelve el token
GET   /superadmin/me                           → valida sesión guardada
GET   /superadmin/clientes                     → lista todos + stats
POST  /superadmin/clientes                     → da de alta un restaurante nuevo
PATCH /superadmin/clientes/{id}/estado         → activo/suspendido/inactivo
PATCH /superadmin/clientes/{id}/reset-password → resetea la contraseña de su admin
```

**`GET /superadmin/clientes`** trae, por cada restaurante: nombre, email,
estado, fecha de alta, número de usuarios/platos/mesas, y **ventas del
mes en curso** (suma de `Comanda.total_cuenta` con `estado='cobrado'`
desde el día 1 del mes en UTC) — lo mínimo para saber de un vistazo cuáles
clientes están activos usando el sistema.

**Suspender un restaurante** (`estado='suspendido'`) le bloquea el
próximo login (`POST /auth/login` ya validaba `cliente.estado != 'activo'`
desde que se implementó el login real) — pero **no invalida tokens ya
emitidos**: alguien que ya inició sesión sigue teniendo acceso hasta que
su token expire (máx. 12h). Revocación instantánea de tokens activos
queda para más adelante (ver "Próximos pasos").

**Frontend:** página completamente aparte —
`frontend/superadmin.html` + `frontend/js/superadmin.js` — deliberadamente
sin cargar `app.js`/`auth.js` (esos están atados a la sesión de UN
restaurante; mezclarlos habría sido una fuente fácil de bugs de
aislamiento). Pensada para escritorio, no para el celular del mozo.

**Bug real encontrado y corregido en el camino:** la función que arma el
`id` de un restaurante nuevo a partir de su nombre (`_slug()`) no manejaba
tildes — "Pollería" se cortaba mal ("poller-a-...") porque el regex
`[^a-z0-9]+` trata una vocal con tilde como carácter no válido igual que
un espacio. Se corrigió normalizando el texto (`unicodedata.normalize`)
antes de aplicar el regex, en los dos lugares donde existía esta función
(`backend/routes/superadmin.py` y `backend/scripts/crear_cliente.py`).

## 🎨 Features agregados en la sesión final (mejoras de UX/producto)

1. **Gestión de Categorías con Iconos**
   - Tabla `Categoria`: (id, cliente_id, nombre, icono)
   - CRUD completo: `GET/POST/DELETE /api/categorias`
   - Admin-only: creación/eliminación validada en backend
   - Icono emoji seleccionable (24 opciones: 🍽️ 🐟 🍤 🍣 🍚 🍜 🥟 🥡 🍲 🍗 🍟 🥩 🍕 🍔 🥪 🌮 🍳 🥗 🥤 ☕ 🍷 🍮 🍰 🍦)
   - Modal en Admin para crear/eliminar categorías
   - Dropdown dinámico en formulario de platos (icono + nombre)
   - Protección: no se puede eliminar una categoría si hay platos asignados

2. **Rediseño de Gestión de Platos**
   - Reemplazo de botón "activar/desactivar" por "✏️ Editar" y "🗑️ Eliminar"
   - Eliminación física si no tiene historial de ventas
   - Archivado automático (estado='inactivo') si tiene ventas registradas — preserva auditoría del dashboard
   - Admin-only validado en backend para crear/editar/eliminar/subir foto

3. **Rediseño de Gestión de Compras**
   - Botones "✏️ Editar" y "🗑️ Eliminar" junto a botón de "cancelar"
   - Restricción: editar/eliminar solo aplica al mismo día
   - Compras de días anteriores: solo se pueden "cancelar" (cambiar estado) — auditoría
   - Modal con título dinámico ("Registrar Gasto" vs. "Editar Gasto")
   - Admin-only validado en backend

4. **Dashboard Financiero Mejorado**
   - **Top 3 Platos** (antes era top 5): por ingresos totales en el rango
   - **Top 3 Gastos** (nuevo): por categoría, agrupa todos los gastos "Insumos", "Servicios", etc.
   - **Badges rediseñados**: cantidad con color diferenciado (naranja para platos, rojo para gastos)
   - **Botón "Descargar Reporte Excel"**: genera XLSX con 3 hojas:
     - **Detalle de Ventas**: fecha, hora, N° comanda, mesa, plato, categoría, cantidad, precio unitario, subtotal, total, atendido por
     - **Detalle de Gastos**: fecha, descripción, categoría, monto, estado (registrado/cancelado), registrado por
     - **Resumen Diario**: fecha, día, ventas, gastos, ganancia, N° comandas
   - Columnas de moneda en Excel: formato "S/ X.XX" (no solo número)
   - Encabezados coloreados (FF5A3C/naranja), rows congelados (no se pierden al scroll)
   - Ancho automático de columnas (máx. 40 caracteres para no saturar)

5. **Impresión de Comandas Dual**
   - Nuevo módulo `frontend/js/print.js` con función `imprimirComandaCocinaYMozo(comanda)`
   - Al enviar a cocina se lanzan **dos diálogos de impresión secuenciales**:
     1. **COCINA**: "qué preparar" (cantidad + nombre, sin precios)
     2. **COPIA MOZO**: "comprobante" con precios (para reclamos/cuadre de caja)
   - Secuencial (no paralelo) para permitir elegir impresora distinta en cada diálogo
   - Si no hay impresora o el usuario cancela: la comanda se guarda igual (no es bloqueante)
   - Formato A5/80mm térmico (lo estándar de restaurantes)

6. **Ícono de Mesa Rediseñado**
   - De un rectángulo plano a una **vista superior de mesa con sillas**
   - Círculo central (mesa) + 4 círculos rellenos (sillas alrededor)
   - Color gris cuando está disponible, naranja cuando está ocupada
   - Más profesional y comprensible

7. **Admin Validation Extraída a `backend/utils/security.py`**
   - Función `validar_admin(db, usuario_email, cliente_id)` centralizada
   - Usada en: crear/editar/eliminar platos, subir foto, crear/editar/eliminar compras, crear/eliminar categorías, crear/editar/eliminar mesas
   - Evita duplicación de código y garantiza consistencia

8. **Backfill Automático para BDs Existentes**
   - Función `backfill_clientes_existentes()` en `seed.py` corre cada arranque
   - Si una BD ya tiene un Cliente pero no tiene usuario admin: lo crea (`admin@demo.local`, rol='admin')
   - Si tiene Cliente pero no tiene Categorías: las crea automáticamente a partir de los platos existentes
   - Idempotente: cada chequeo es "si no existe, créalo"
   - Soluciona que usuarios con versión antigua no vean el dropdown de categorías ni puedan hacer acciones de admin

## 🐛 Bugs y huecos corregidos durante la implementación

1. **No existía forma de cobrar una mesa.** La especificación original solo contemplaba `cocina → entregado`, así que las mesas quedaban "ocupadas" para siempre y nunca había dinero que mostrar en ningún reporte. Se agregó `POST /api/mesas/{id}/cobrar`, que cierra todas las comandas activas de la mesa y la libera — pero **rechaza el cobro si todavía hay platos en cocina** (no se puede cobrar algo que el cliente no recibió).
2. **Dashboard mostraba S/ 0 aunque hubiera ventas.** Se mezclaba `date.today()` (hora local) con timestamps guardados en UTC (`datetime.utcnow()`). En Perú (UTC-5), pasada cierta hora la fecha UTC ya es "el día siguiente" y la venta caía fuera del rango consultado. Se corrigió usando UTC de forma consistente en el cálculo del rango de fechas.
3. **El mismo bug de fecha UTC/local existía también en Compras**, pasó desapercibido en la primera corrección: `date.today()` en `backend/routes/compras.py` podía rechazar un gasto de "hoy" como "fecha futura" cuando la fecha local y la UTC del servidor caen en días distintos. Corregido para usar UTC en todo el módulo, igual que el dashboard.
4. **Bug de CSS que dejaba 3 de las 4 pestañas invisibles para siempre** ("solo veo Mesas, nada más responde" — reportado en producción por el usuario). Cocina, Dinero y Admin (más la sub-pestaña Gastos dentro de Admin) tenían la clase `hidden` (`display:none !important`) además de su clase de componente; el código de navegación solo alternaba la clase `active`, nunca quitaba `hidden`, así que el `!important` ganaba siempre sin importar qué se tocara en el menú. Se quitó la clase redundante de esos 4 elementos.
5. **SQLite en memoria "perdía" las tablas en los tests.** Cada conexión nueva del pool abría una base `:memory:` distinta y vacía. Se forzó `StaticPool` para que todas las conexiones de test compartan la misma base.
6. **Plato duplicado en una comanda rompía el total.** Si el payload llegaba con el mismo `plato_id` dos veces (por ejemplo, un doble-tap accidental), se creaban dos filas en vez de sumar cantidades. Ahora se fusionan por `plato_id` antes de calcular el total.
7. **Editar un plato desde el admin creaba uno nuevo en vez de actualizarlo** (el formulario del modal siempre hacía `POST`). Se agregó seguimiento de "modo edición" para que dispare `PATCH` cuando corresponde.
8. **`min_items` en Pydantic v2** — sintaxis deprecada que rompía la validación de listas; se reemplazó por `min_length`.

## 📸 Fotos de platos

- `POST /api/platos/{id}/imagen` (multipart) y `DELETE /api/platos/{id}/imagen`.
- El servidor **no confía en el Content-Type ni en la extensión del archivo** que manda el cliente (ambos se falsean trivialmente); valida la firma binaria real (JPEG/PNG/WEBP) antes de guardar nada en disco.
- El nombre del archivo en disco es siempre `{plato_id}.{ext}` — nunca se usa `cliente_id` para construir la ruta, porque ese valor viene de un header sin autenticar y podría usarse para un path traversal (`../../../etc`) si se usara para armar una carpeta.
- El frontend comprime la foto en el navegador (canvas, máx. 800px, JPEG 0.8) antes de subirla — clave para el objetivo de celulares de gama baja con datos limitados.
- Se ve como miniatura en la carta del Mozo y en la lista de Admin; sin foto, se muestra un ícono placeholder (nunca un hueco vacío).

## 👤 Roles por dispositivo (Admin / Mozo / Cajero / Cocina)

**Por qué existe:** al conversar sobre quién cobra la mesa, surgió la
pregunta de cómo evitar que el mozo o el cajero vean pantallas que no les
corresponden sin construir un login completo todavía. La solución elegida
fue **una sola pantalla de Mesas para todos los roles, con botones
distintos según quién la usa** — en vez de duplicar la interfaz en un
"módulo de caja" aparte, que hubiera significado mantener dos vistas de
mesas sincronizadas por separado.

- El rol se elige **una vez por dispositivo** (el celular del mozo, el de
  caja) tocando el badge redondo del header ("Admin", "Mozo", etc.) y
  queda guardado en `localStorage` — no hay login todavía, así que esto
  es a propósito una configuración local del teléfono, no una cuenta de
  usuario. Cuando se implemente JWT, el mismo mecanismo (`aplicarPermisosRol`
  en `app.js`) sigue funcionando igual, solo cambia de dónde sale el rol.
- `ROLES_PERMITIDOS` en `frontend/js/app.js` define qué pestañas ve cada
  rol: Admin ve las 4 (Mesas/Cocina/Dinero/Admin); Mozo y Cajero solo ven
  Mesas; Cocina solo ve el monitor.
- **Dentro de la pestaña Mesas el comportamiento cambia según el rol**, no
  hay una pantalla nueva:
  - Mozo/Admin: tocar una mesa libre abre "Nuevo pedido"; tocar una
    ocupada abre su cuenta con opción de agregar más platos o cobrar.
  - Cajero: las mesas libres aparecen apagadas y no reaccionan al toque
    (no le sirven de nada); tocar una ocupada abre directamente su cuenta
    **sin** el botón "+ Agregar pedido" — el cajero cobra, no toma
    pedidos.
- **Importante:** esto es control de acceso en el frontend únicamente
  (oculta botones y pestañas), no reemplaza la autorización real en el
  backend. Los endpoints (`/comandas`, `/mesas/{id}/cobrar`, etc.) siguen
  sin validar rol — cualquiera con la URL directa podría llamarlos. Es
  aceptable para el MVP porque hoy el "rol" ni siquiera es una sesión
  autenticada; hay que resolverlo junto con la autenticación real (ver
  "Próximos pasos").

## 🪑 Gestión de mesas (agregado durante la implementación)

**Por qué existe:** la especificación original solo tenía `GET /api/mesas`
como "soporte"; no había forma de crear más mesas, corregir su capacidad o
ubicación, ni borrar una que ya no existe (mesa mal cargada, restaurante
que reduce aforo). El botón "Gestionar mesas" solo lo ve el rol Admin
(mismo mecanismo de `ROLES_PERMITIDOS` que las demás pestañas).

```
PATCH  /api/mesas/{id}    → Edita número, capacidad y/o ubicación (parcial)
DELETE /api/mesas/{id}    → Elimina la mesa
```

- **`PATCH`** valida que el nuevo número no choque con otra mesa del mismo
  cliente antes de guardar (la restricción `UNIQUE(cliente_id, numero)`
  de la BD ya lo protegía, pero así el error es un 400 claro, no un 500).
- **`DELETE`** rechaza (400) si la mesa está `ocupada` o si tiene
  comandas activas — no tiene sentido borrar una mesa con una cuenta
  pendiente de cobro; hay que cobrarla o cancelarla primero.
- También se rediseñaron las tarjetas de mesa (`frontend/css/style.css`):
  ícono de mesa, número más grande, capacidad/ubicación visibles, y el
  indicador de estado pasó a esquina superior derecha para no chocar con
  el monto cuando la mesa está ocupada.

## 📁 Estructura relevante

```
backend/
├── app.py                  # FastAPI + routers + seed automático al arrancar
├── auth.py                 # Nuevo: JWT + hashing de contraseñas (bcrypt)
├── config.py               # Settings (pydantic-settings) — secret_key real en .env
├── database.py             # SQLAlchemy engine/session
├── dependencies.py         # get_cliente_id/get_usuario_actual (leen el JWT), get_tz_offset
├── models.py                # 9 tablas (Categoria, SuperAdmin agregadas)
├── schemas.py              # Pydantic: validación + respuestas
├── seed.py                 # Datos demo idempotentes + backfill automático
├── services.py             # Reglas de negocio
├── scripts/
│   ├── crear_cliente.py     # Onboarding manual de un restaurante nuevo (CLI, alternativa al Panel General)
│   └── crear_superadmin.py  # Nuevo: bootstrap de TU cuenta del Panel General (una sola vez por servidor)
├── utils/
│   ├── __init__.py
│   └── security.py         # validar_admin() centralizado
└── routes/
    ├── auth.py             # POST /auth/login, GET /auth/me (login de restaurante)
    ├── superadmin.py       # Nuevo: login + CRUD de restaurantes para el Panel General
    ├── platos.py           # CU-01 (crear/editar/eliminar, admin-only)
    ├── categorias.py       # Nuevo: CRUD categorías con iconos
    ├── mesas.py            # Soporte + cobro de mesa
    ├── comandas.py         # CU-02 + CU-03 (monitor de cocina)
    ├── compras.py          # CU-04 (crear/editar/eliminar mismo día)
    └── dashboard.py        # CU-05 (top 3 platos/gastos, reporte Excel)

frontend/
├── index.html              # App de UN restaurante: login + bottom nav (Mesas/Cocina/Dinero/Admin)
├── superadmin.html         # Nuevo: Panel General — ve y administra TODOS los restaurantes
├── manifest.json           # PWA manifest
├── sw.js                   # Service worker (v14)
├── css/style.css           # Design system mobile-first (light + dark) — compartido por ambas páginas
├── assets/platos/          # Fotos subidas (gitignored, la crea el backend)
└── js/
    ├── app.js              # API client (Authorization: Bearer), navegación, toasts
    ├── auth.js             # Login/logout de restaurante, guarda el token, valida sesión al abrir
    ├── superadmin.js        # Nuevo: login/CRUD del Panel General — independiente de app.js/auth.js
    ├── charts.js           # Gráficos SVG a mano (sin librerías)
    ├── print.js            # Impresión dual de comandas
    ├── mozo.js             # Mesas, nuevo pedido, cuenta y cobro
    ├── cocina.js           # Monitor en tiempo real (polling 2s)
    ├── dashboard.js        # CU-05 mejorado (top 3, Excel, badges)
    └── admin.js            # Carta (con fotos), Categorías (CRUD), Gastos (editar/eliminar)

tests/
├── conftest.py             # Fixtures (BD en memoria con StaticPool) + fixture de auth real
├── unit/test_models.py
└── integration/test_endpoints.py   # 48 tests, cubren el ciclo completo + login
```

## 📋 Cómo correrlo

```bash
cd "d:\Cartera de proyectos\RestoMind-SaaS"
./venv/Scripts/activate            # Windows
pip install -r requirements.txt    # si falta algo
uvicorn backend.app:app --reload --host 0.0.0.0 --port 8000
```

- App (PWA), un restaurante: `http://localhost:8000/static/index.html` → pide login
- **Panel General (todos tus restaurantes)**: `http://localhost:8000/static/superadmin.html`
- Docs (Swagger): `http://localhost:8000/docs`
- Tests: `pytest tests/ -v`
- Restaurante demo: `admin@demo.local` / `admin123`
- Crear tu cuenta de superadmin (una sola vez, la primera vez que despliegas): `python -m backend.scripts.crear_superadmin` (interactivo, por consola)
- Dar de alta un restaurante nuevo: **desde el Panel General** una vez logueado (botón "Nuevo restaurante"), o por consola con `python -m backend.scripts.crear_cliente` si preferís no abrir el navegador

El primer arranque crea `restomind.db` con datos de demo (restaurante "La Marisquería del Chef", 8 mesas, 12 platos, usuario admin). Es idempotente: si borras el archivo `restomind.db`, se vuelve a sembrar solo. Una instalación con una BD de antes de que existiera login se repara sola al arrancar (ver sección "Login real" arriba).

**`.env` en el servidor de producción:** el `SECRET_KEY` con el que se firman los JWT vive en `.env` (gitignored, nunca se sube al repo). Generar uno propio por instalación:
```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```
Si dos instalaciones (dev y prod, por ejemplo) comparten el mismo `SECRET_KEY` por accidente, un token válido en una serviría en la otra — cada entorno necesita el suyo.

## 🔑 Decisiones de diseño a tener en cuenta

- **Multi-tenant con login real:** `cliente_id` se resuelve en `backend/dependencies.py` decodificando el JWT del header `Authorization: Bearer <token>` (ver sección "Login real" arriba). Un solo punto de cambio si el día de mañana se agrega SSO, OAuth, etc.
- **El dinero solo cuenta cuando se cobra**, no cuando se crea la comanda. El dashboard filtra por `estado == 'cobrado'`.
- **Charts sin librerías**: se generan como SVG puro en `charts.js` a propósito, para no depender de un CDN (rompería el modo offline de la PWA) y para mantener el bundle liviano en celulares de gama baja.
- **Selector de rol por dispositivo vs. login**: son dos capas distintas a propósito. El login dice "estos datos son del restaurante X"; el selector de rol (botón redondo del header) dice "este celular compartido hoy actúa como Mozo/Cocina/Admin". Fusionarlos requeriría que cada mesero tenga su propia cuenta — decisión de producto, no técnica, pendiente de que el usuario la pida.

## 📞 Próximos pasos sugeridos (post-MVP)

1. **Rate limiting en `/auth/login` y `/superadmin/login`** — hoy nada impide probar contraseñas al voleo (fuerza bruta). Un límite simple (ej. 5 intentos/minuto por IP) cierra ese hueco antes de exponer el sistema a internet público.
2. **Refresh tokens / logout del lado servidor** — hoy un JWT robado sigue siendo válido hasta que expira (12h) aunque el usuario "cierre sesión" (el logout actual solo borra el token del navegador). Suspender un cliente desde el Panel General tiene el mismo límite: bloquea logins nuevos, no tokens ya emitidos. Para revocación real haría falta una lista negra o tokens de vida más corta + refresh.
3. **Facturación dentro del Panel General**: hoy "ventas del mes" es solo informativo — no hay forma de cobrarle a un restaurante cliente desde el panel ni de ver un historial de pagos. Si el negocio crece, esto es lo próximo a agregar ahí mismo.
4. **Multi-restaurante con self-service**: hoy el alta la hace el dueño del sistema (por el Panel General o por consola). Si el negocio escala a que restaurantes se den de alta solos, hace falta una pantalla de registro pública + verificación de email + cobro automático.
5. **IA + Claude API**: reportes inteligentes sobre los datos que ya arroja el Dashboard (ver guía de negocio de JTech).
6. **Pagos**: integración Stripe/Culqi para cobro con QR (tanto para que el restaurante le cobre a sus clientes, como para que el sistema le cobre al restaurante).
7. **Zona horaria por cliente**: hoy el corte de "día" del dashboard usa UTC; con clientes en distintos países convendría guardar el timezone del restaurante (columna en `Cliente`, hoy `tz_offset` viaja por header y lo decide el navegador del que hace la consulta, no el restaurante en sí).

---

**Última actualización:** 2026-08-29 (sesión de login real + Panel General para multi-tenant de reventa)
**Estado:** ✅ MVP+ funcional, probado (56/56 tests), con autenticación real y panel de administración general — listo para dar de alta el primer restaurante de pago
**Próxima prioridad:** rate limiting en login antes de exponer el servidor a internet público
