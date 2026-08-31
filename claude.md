# 📋 RESTOMIND SAAS - DOCUMENTACIÓN TÉCNICA

**Versión MVP:** 2.6 — Validador de Caja (Apertura/Cierre Diario + Reporte Imprimible)
**Implementado y probado:** ✅ 100% Autenticación + Seguridad + Facturación SUNAT SFS + Dashboard Financiero + Validador de Caja
**Última actualización:** 2026-08-31

> Este documento describe el diseño original (MVPv1). El estado real de la
> implementación actual, bugs corregidos, features agregados y decisiones
> tomadas durante el desarrollo están en `SETUP_CHECKLIST.md`.
>
> **Lo que cambió desde MVPv1:**
> - ✅ **Login real con JWT** — autenticación segura con tokens validados
> - ✅ **Login dual:** Email (admin/superadmin) + Código de acceso (staff: mozo/cajero/jefe_cocina)
> - ✅ **Panel General (Superadmin)** — el dueño del sistema ve todos sus restaurantes clientes
> - ✅ **Personal con login individual** — cada mozo/cajero/cocinero con código de acceso auto-generado
> - ✅ **Rol desde JWT** — el rol viene del token, no de un click en el header
> - ✅ **Redirección inteligente** — superadmin → panel general, staff/admin → panel restaurante
> - ✅ **Logs de autenticación** — debugging detallado sin exponer datos sensibles
> - ✅ 121 tests automáticos (cobertura de seguridad, rate limit, auditoría, facturación, edición de restaurante)
> - ✅ **[NUEVA] Hardening de producción:** SECRET_KEY obligatorio, rate limiting, CSP, headers de seguridad
> - ✅ **[NUEVA] Compresión de imágenes:** Pillow server-side (800px máx, JPEG 82%), preview con blob: URLs
> - ✅ **[NUEVA] Filtro de categorías:** Admin > Carta agrupa platos con chips por categoría
> - ✅ **[NUEVA] Tabla de auditoría:** Registro persistente de logins y cambios administrativos
> - ✅ **[NUEVA] Cascade delete:** Eliminar cliente limpia todas sus categorías (antes quedaban huérfanas)
> - ✅ **[NUEVA] Rediseño UI 3D:** ícono de mesa con relieve (gradientes + sombra), cajitas de texto con glow al enfocar, nav inferior con píldora animada — pensado para PWA, sin costo extra de rendimiento (ver sección "Rediseño Visual" más abajo)
> - ✅ **[NUEVA] Facturación SUNAT (SFS v1.3.2):** Exportador local de boletas (.cab/.det) para Facturador SUNAT
> - ✅ **[NUEVA] Validación de RUC:** Prefijo 10 o 20 requerido; rechaza tipeos antes de cobrar (frontend) y después (backend)
> - ✅ **[NUEVA] Admin > Boletas:** Pantalla de recuperación de boletas con error o nunca emitidas; reintento/emisión de cero
> - ✅ **[BUG FIX] Edición de restaurante:** PATCH /superadmin/clientes/{id} fallaba 100% de las veces sin cambiar contraseña (schema contradictorio); separado ClienteUpdateRequest
> - ✅ **[MEJORA] Orden de operaciones:** Commit de correlativo ANTES de escribir .cab/.det para evitar race conditions bajo concurrencia
> - ✅ **[NUEVA] Dashboard Financiero Completo:** Tabla detallada de ganancias diarias, Top 5 platos, colores consistentes (teal ventas/rojo gastos en gráfico + leyenda), etiquetas de barras con montos exactos (sin redondeo falso)
> - ✅ **[NUEVA] Tabla de Ganancias por Día:** Fecha / Ventas / Gastos / Ganancia / Margen %, orden DESC (más reciente primero), filas coloreadas según ganancia (verde positivo/rojo negativo), responsive (oculta Gastos y Margen en móvil ≤480px)
> - ✅ **[FIX] formatCompacto():** Ya no redondea falsos — 122.50 se muestra "122.50", no "123"; consistente con tabla de abajo y stat-tiles
> - ✅ **[NUEVA] Validador de Caja:** Admin > Caja — apertura (saldo inicial) y cierre (saldo contado) diario, con cálculo automático de ventas/gastos del día y detección de discrepancias (cuadrado / leve / grave). Reporte imprimible tipo boleta (resultado grande, QR, firmas). Ver sección "Validador de Caja" más abajo.
>
> **Pendiente (a futuro, no bloquea el flujo actual):**
> - ⏳ **Comandas en PDF** — generación/impresión de comanda y cuenta en PDF, por configurar

> **Para análisis técnico COMPLETO del sistema:**  
> → [`LOGIN_ANALYSIS.md`](LOGIN_ANALYSIS.md) — flujo de auth, tokens, permisos, seguridad  
> → [`PRODUCTION_READINESS.md`](PRODUCTION_READINESS.md) — checklist para despliegue en producción

---

## 🏷️ ESPECIFICACIONES GENERALES DEL SISTEMA

### Stack Tecnológico
- **Backend:** Python 3.11+ con FastAPI (framework REST ligero y veloz)
- **Base de Datos:** SQLite con soporte multi-tenant nativo
- **Frontend:** HTML5 + CSS3 + JavaScript Vanilla (sin frameworks pesados)
- **Acceso Móvil:** PWA (Progressive Web App) con manifest.json en modo standalone
- **Instalación:** pip + Uvicorn para desarrollo; gunicorn para producción

### Principios Arquitectónicos
- **Multi-Tenant:** Un único backend sirve N restaurantes usando 'cliente_id' como separador
- **Data Isolation:** Cada cliente solo accede a sus propios datos mediante filtros en WHERE clause
- **API-First:** Todos los datos fluyen vía endpoints REST JSON
- **Stateless Backend:** Sin sesiones persistentes en servidor (JWT opcional para fase 2)

### Modo PWA (Experiencia Móvil)
- Manifest.json configura app en modo "standalone" (sin barra de navegación visible)
- El URL se oculta en pantalla del mozo, mostrando solo el nombre "RestoMind"
- Funciona offline con caché básico vía service worker (solo lectura de datos cacheados)
- Instalable como icono en home del celular (Android y iOS)

### Aislamiento de Datos y Seguridad
- Campo obligatorio 'cliente_id' en TODAS las tablas de negocio
- Filtros automáticos en CADA consulta SELECT, UPDATE, DELETE para validar cliente_id
- No hay excepciones: ni reports, ni exports contienen datos de otros clientes
- Contraseñas hasheadas con bcrypt, sin plaintext en logs ni base de datos

---

## 🔐 AUTENTICACIÓN Y LOGIN

### Sistema de Login Dual

La aplicación soporta **tres tipos de usuarios** con métodos de acceso diferentes:

#### 1. Superadmin (Panel General)
- **Credencial:** Email + Contraseña
- **Endpoint:** `POST /api/auth/login`
- **Tabla:** `superadmin`
- **Token:** Tipo `superadmin` (acceso a `/api/superadmin/*`)
- **Redirección:** Automática a `/static/superadmin.html`
- Puede ver y gestionar TODOS los restaurantes clientes

#### 2. Admin de Restaurante (Panel del Restaurante)
- **Credencial:** Email + Contraseña
- **Endpoint:** `POST /api/auth/login`
- **Tabla:** `usuarios` con `rol='admin'`
- **Token:** Tipo `usuario` (acceso a endpoints de su `cliente_id`)
- **Redirección:** A `/static/index.html` (panel principal)
- Puede ver y gestionar su restaurante

#### 3. Personal (Mozo, Cajero, Cocinero)
- **Credencial:** Código de acceso (6 dígitos, generado por el sistema al crear la cuenta — no un celular real) + Contraseña
- **Endpoint:** `POST /api/auth/login-staff`
- **Tabla:** `usuarios` con `rol` en ('mozo', 'cajero', 'cocinero')
- **Token:** Tipo `usuario` (acceso a endpoints de su `cliente_id`)
- **Redirección:** A `/static/index.html` (panel principal)
- El rol del JWT determina qué pestañas ven en la interfaz

### Flujo de Autenticación

```
1. Usuario abre /static/index.html
   ↓
2. initAuth() valida token guardado en localStorage
   ↓
3. Si no hay token → mostrar pantalla de login con 2 pestañas
   - Pestaña "Administrador": email + contraseña → /api/auth/login
   - Pestaña "Personal": celular + contraseña → /api/auth/login-staff
   ↓
4. Backend intenta autenticar:
   - Para /api/auth/login: busca en Usuario, luego en SuperAdmin
   - Para /api/auth/login-staff: busca en Usuario por celular
   ↓
5. Si login exitoso:
   - Backend devuelve access_token (JWT) + datos del usuario
   - Frontend guarda token en localStorage
   - Si rol=='superadmin': redirige a /static/superadmin.html
   - Si rol=='admin' o staff: muestra /static/index.html
   ↓
6. En cada petición API:
   - Frontend incluye header Authorization: Bearer <token>
   - Backend decodifica token y valida tipo + permisos
   - Si token expirado o inválido → mostrar login nuevamente
```

### Tokens JWT

**Estructura del token para usuarios de restaurante:**
```json
{
  "sub": "usuario_email_o_celular",
  "cliente_id": "rest-001",
  "rol": "admin|mozo|cajero|cocinero",
  "tipo": "usuario",
  "exp": <timestamp>
}
```

**Estructura del token para superadmin:**
```json
{
  "sub": "jtechautomatizacion@gmail.com",
  "tipo": "superadmin",
  "exp": <timestamp>
}
```

### Dependencias de Validación

- `get_cliente_id(payload)` → extrae `cliente_id` del token (solo para `tipo='usuario'`)
- `get_usuario_actual(payload)` → extrae `sub` (email/celular) del token (solo para `tipo='usuario'`)
- `get_superadmin_email(payload)` → extrae `sub` del token (solo para `tipo='superadmin'`)

Los endpoints regulares (mesas, platos, etc.) usan `get_cliente_id` y rechazar tokens de superadmin con 403. El superadmin accede a sus propios endpoints bajo `/api/superadmin/*`.

### Tablero de Login (UI)

**Desktop/Tablet:**
- Pantalla centrada con tarjeta blanca
- Dos pestañas: "Administrador" (icono persona) y "Personal" (icono personas)
- Botón de reset (↻) en esquina superior derecha para limpiar localStorage

**Tabla "Administrador":**
- Input email
- Input contraseña
- Mensaje de error compartido
- Botón "Ingresar"

**Tabla "Personal":**
- Input código de acceso (6 dígitos, generado por el sistema)
- Input contraseña
- Mensaje de error compartido
- Botón "Ingresar"

### Debugging y Logs

Todos los intentos de login se registran en los logs del servidor con:
- Email/celular intentado
- Si el usuario fue encontrado
- Si la contraseña fue validada
- Resultado final (éxito o error)

Ejemplo de logs:
```
[LOGIN] Intento con email: jtechautomatizacion@gmail.com
[LOGIN] SuperAdmin encontrado: super-dueno
[LOGIN] SuperAdmin jtechautomatizacion@gmail.com: login exitoso
```

---

## 🗄️ ESTRUCTURA DE BASE DE DATOS

### Tabla: clientes
```sql
CREATE TABLE clientes (
  id TEXT PRIMARY KEY,           -- cliente-001, cliente-002
  nombre TEXT NOT NULL,           -- "La Marisquería del Chef"
  email TEXT UNIQUE NOT NULL,
  telefono TEXT,
  pais TEXT DEFAULT 'Perú',
  moneda TEXT DEFAULT 'PEN',
  estado TEXT DEFAULT 'activo',   -- activo, inactivo, suspendido
  creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### Tabla: usuarios
```sql
CREATE TABLE usuarios (
  id TEXT PRIMARY KEY,
  cliente_id TEXT NOT NULL,       -- Vínculo multi-tenant
  nombre TEXT NOT NULL,
  email TEXT UNIQUE NOT NULL,
  password_hash TEXT NOT NULL,
  rol TEXT DEFAULT 'mozo',        -- admin, jefe_cocina, mozo
  estado TEXT DEFAULT 'activo',
  creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY(cliente_id) REFERENCES clientes(id)
);
```

### Tabla: platos
```sql
CREATE TABLE platos (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  cliente_id TEXT NOT NULL,
  nombre TEXT NOT NULL,
  categoria TEXT NOT NULL,        -- Cebiches, Bebidas, Postres, etc.
  precio_venta DECIMAL(10,2) NOT NULL,
  descripcion TEXT,
  imagen_url TEXT,                -- Para futuras mejoras UI
  estado TEXT DEFAULT 'activo',   -- activo, inactivo
  creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  actualizado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY(cliente_id) REFERENCES clientes(id)
);
```

### Tabla: mesas
```sql
CREATE TABLE mesas (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  cliente_id TEXT NOT NULL,
  numero INTEGER NOT NULL,        -- 1, 2, 3, ..., 15
  capacidad INTEGER DEFAULT 4,    -- Número de personas
  ubicacion TEXT,                 -- "Patio", "Interior", etc.
  estado TEXT DEFAULT 'disponible', -- disponible, ocupada
  creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY(cliente_id) REFERENCES clientes(id),
  UNIQUE(cliente_id, numero)      -- Un número de mesa por cliente
);
```

### Tabla: comandas
```sql
CREATE TABLE comandas (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  cliente_id TEXT NOT NULL,
  numero_mesa INTEGER NOT NULL,
  total_cuenta DECIMAL(10,2) NOT NULL,
  estado TEXT DEFAULT 'cocina',   -- cocina, entregado, cobrado, cancelado
  creado_por TEXT,                -- Email del mozo que creo
  creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  actualizado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY(cliente_id) REFERENCES clientes(id)
);
```

### Tabla: comanda_platos
```sql
CREATE TABLE comanda_platos (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  comanda_id INTEGER NOT NULL,
  plato_id INTEGER NOT NULL,
  cantidad INTEGER DEFAULT 1,
  precio_unitario DECIMAL(10,2) NOT NULL,  -- Precio al momento de venta
  subtotal DECIMAL(10,2) NOT NULL,         -- cantidad × precio_unitario
  FOREIGN KEY(comanda_id) REFERENCES comandas(id),
  FOREIGN KEY(plato_id) REFERENCES platos(id)
);
```

### Tabla: compras
```sql
CREATE TABLE compras (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  cliente_id TEXT NOT NULL,
  descripcion TEXT NOT NULL,
  categoria TEXT,                 -- Insumos, Servicios, Otros
  monto DECIMAL(10,2) NOT NULL,
  fecha DATE NOT NULL,
  estado TEXT DEFAULT 'registrado', -- registrado, cancelado
  creado_por TEXT,                -- Email del admin
  creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY(cliente_id) REFERENCES clientes(id)
);
```

---

## 🎯 CASOS DE USO DEL MVP

### CU-01: Gestión de la Carta Inteligente (Administrador)

**Descripción:** El dueño configura su menú desde el dashboard.

**Endpoints:**
```
GET /api/platos              → Lista platos del cliente
POST /api/platos             → Crear nuevo plato
PATCH /api/platos/{id}       → Editar plato
PATCH /api/platos/{id}/estado → Desactivar plato
```

**Datos de Entrada (POST/PATCH):**
```json
{
  "nombre": "Ceviche Clásico",
  "categoria": "Cebiches",
  "precio_venta": 45.00,
  "descripcion": "Con leche de tigre fresca"
}
```

**Datos de Salida:**
```json
{
  "id": 101,
  "cliente_id": "rest-001",
  "nombre": "Ceviche Clásico",
  "categoria": "Cebiches",
  "precio_venta": 45.00,
  "descripcion": "Con leche de tigre fresca",
  "imagen_url": "/static/assets/platos/101.jpg",
  "estado": "activo",
  "creado_en": "2026-08-28T10:30:00Z"
}
```

**Validaciones:**
- ✅ cliente_id OBLIGATORIO (tomar de sesión)
- ✅ nombre: no vacío, máx 100 caracteres
- ✅ categoría: no vacía
- ✅ precio_venta: > 0, decimal con 2 decimales

#### Foto del plato (agregada durante la implementación)

**Por qué existe:** el campo `imagen_url` estaba en el esquema de base de
datos desde el diseño original pero nunca se conectó a nada — no había
forma de subir una foto. Un menú digital sin fotos de los platos es una
carta de restaurante sin fotos: se vende peor. Se agregó como acción
separada del CRUD del plato (no como parte del payload JSON) porque subir
un archivo binario dentro de un campo de un JSON obliga a base64, que
infla el payload ~33% — mala idea para el objetivo de celulares de gama
baja con datos móviles limitados.

```
POST   /api/platos/{plato_id}/imagen   → Sube/reemplaza la foto (multipart/form-data, campo "archivo")
DELETE /api/platos/{plato_id}/imagen   → Quita la foto (vuelve a null)
```

- Límite de subida: 5MB por archivo crudo (antes de procesarlo) — solo un
  freno contra un archivo absurdamente grande o una bomba de descompresión,
  no lo que define cuánto pesa lo que termina en disco (ver debajo).
- **La validación de formato no confía en el Content-Type que manda el
  cliente ni en la extensión del nombre del archivo** — ambos se falsean
  con un `curl -F`. Se valida la firma binaria real (primeros bytes del
  archivo: JPEG, PNG o WEBP). Un `.html` renombrado a `.png` se rechaza
  con 400 antes de tocar el disco.
- El archivo se guarda como `frontend/assets/platos/{plato_id}.jpg`,
  usando el `id` numérico del plato (ya validado por FastAPI como entero
  en la ruta) como nombre de archivo — nunca el `cliente_id` del header,
  que al no estar autenticado todavía podría inyectar un path
  (`../../../etc`) si se usara para armar la ruta en disco.
- Al reemplazar la foto de un plato se borra la versión anterior (aunque
  haya cambiado de extensión) para no dejar archivos huérfanos.
- El frontend comprime y redimensiona la imagen en el navegador antes de
  subirla (máx. 800px de lado, JPEG calidad 0.8, ver `frontend/js/admin.js`)
  — una foto de celular sin comprimir pesa 4-8MB; esto la deja normalmente
  en 150-300KB, clave para el objetivo de "gama media/baja".
- **El servidor también recomprime, siempre, sin importar cómo llegó la
  imagen** (`_recomprimir_a_jpeg()` en `backend/routes/platos.py`, con
  Pillow): mismo tope de 800px/calidad 82, y el resultado se guarda SIEMPRE
  como `.jpg` sin importar el formato de entrada. Esto es necesario porque
  la compresión del frontend es una cortesía del navegador, no una garantía
  — nada impide llamar a este endpoint directo con `curl` o un cliente
  HTTP saltándose esa compresión. Sin este paso, el storage de un SaaS
  multi-tenant (fotos de N restaurantes, cada uno con su propia carta)
  crecería sin límite con el tiempo. De paso, un archivo con firma binaria
  válida pero corrupto (que la sola detección de firma no atrapa) ahora
  también se rechaza con 400, porque Pillow no logra decodificarlo.

---

### CU-02: Registro y Envío de Comandas Express (Mozo)

**Descripción:** Mozo registra pedidos desde celular.

**Endpoints:**
```
GET /api/comandas              → Lista comandas activas
POST /api/comandas             → Crear comanda
GET /api/comandas/{id}         → Detalle de comanda
PATCH /api/comandas/{id}/estado → Actualizar estado
```

**Datos de Entrada (POST):**
```json
{
  "numero_mesa": 5,
  "platos": [
    { "plato_id": 101, "cantidad": 1 },
    { "plato_id": 105, "cantidad": 2 }
  ]
}
```

**Datos de Salida:**
```json
{
  "id": 501,
  "cliente_id": "rest-001",
  "numero_mesa": 5,
  "estado": "cocina",
  "total_cuenta": 95.00,
  "platos": [
    {
      "plato_id": 101,
      "nombre": "Ceviche Clásico",
      "cantidad": 1,
      "subtotal": 45.00
    },
    {
      "plato_id": 105,
      "nombre": "Jugo de Naranja",
      "cantidad": 2,
      "subtotal": 50.00
    }
  ],
  "creado_en": "2026-08-28T11:45:30Z"
}
```

**Validaciones:**
- ✅ cliente_id OBLIGATORIO
- ✅ número_mesa: Debe existir en tabla mesas del cliente
- ✅ platos: Array no vacío, mínimo 1 plato
- ✅ total_cuenta: Calculado suma(plato.precio_venta × cantidad)
- ✅ estado inicial: SIEMPRE 'cocina'

---

### CU-03: Monitor de Cocina en Tiempo Real (Cocina)

**Descripción:** Pantalla de cocina muestra cola de producción.

**Endpoints:**
```
GET /api/monitor/cocina        → Comandas en estado 'cocina'
PATCH /api/comandas/{id}/estado → Marcar como 'entregado'
```

**Datos de Entrada (PATCH):**
```json
{
  "estado": "entregado"
}
```

**Lógica:**
- Solo mostrar comandas con estado='cocina'
- Ordenar por creado_en ASC (más antiguas arriba = prioridad)
- Alerta: Si creado_en < (ahora - 15 minutos) → color rojo
- Al cambiar a 'entregado', actualizar mesa estado='disponible'

---

### CU-04: Control de Compras y Caja Chica (Administrador)

**Descripción:** Registra egresos diarios.

**Endpoints:**
```
GET /api/compras              → Lista compras del cliente
POST /api/compras             → Crear gasto
PATCH /api/compras/{id}       → Editar gasto (solo mismo día)
PATCH /api/compras/{id}/estado → Cancelar gasto
```

**Datos de Entrada (POST/PATCH):**
```json
{
  "descripcion": "Pescado rojo - Mercado Modelo",
  "categoria": "Insumos",
  "monto": 85.50,
  "fecha": "2026-08-28"
}
```

**Datos de Salida:**
```json
{
  "id": 801,
  "cliente_id": "rest-001",
  "descripcion": "Pescado rojo - Mercado Modelo",
  "categoria": "Insumos",
  "monto": 85.50,
  "fecha": "2026-08-28",
  "creado_por": "admin@rest001.com",
  "creado_en": "2026-08-28T08:15:00Z"
}
```

**Validaciones:**
- ✅ cliente_id OBLIGATORIO
- ✅ descripción: no vacía, máx 100 caracteres
- ✅ monto: > 0, decimal con 2 decimales
- ✅ fecha: No puede ser futura

---

### 💰 Cobro de Mesa (agregado durante la implementación)

**Por qué existe:** la especificación original no contemplaba cómo cerrar
una mesa. Sin esto, `mesa.estado` nunca volvía a `disponible` y no había
forma de que una venta contara como dinero real en ningún reporte.

```
POST /api/mesas/{mesa_id}/cobrar
```

- Cierra (`estado='cobrado'`) todas las comandas activas de esa mesa y la libera.
- Regla de negocio: **rechaza el cobro (400)** si alguna comanda de la mesa
  sigue en `'cocina'` — no se puede cobrar comida que el cliente no recibió.
- Respuesta: `{ "mesa_numero": 5, "total_cobrado": 95.00, "comandas_cerradas": 1 }`

---

### CU-05: Dashboard Financiero (agregado durante la implementación)

**Descripción:** "Cómo viaja mi dinero" — serie de ventas/gastos/ganancia
por día + ranking de platos más vendidos, para el panel del administrador.

```
GET /api/dashboard/resumen?dias=7   (1-30, default 7)
```

**Lógica:**
- Una venta cuenta cuando la comanda llega a `estado='cobrado'` (no al crearse).
- Gastos = suma de `compras` con `estado='registrado'` en el rango.
- Devuelve serie diaria completa (rellena días sin datos con ceros), totales
  del periodo y top 5 platos por ingresos.
- **Importante:** el rango de fechas se calcula en UTC porque los timestamps
  de la BD están en UTC (`datetime.utcnow()`). Mezclar con fecha local causaba
  que ventas cercanas a medianoche "desaparecieran" en zonas horarias como
  Perú (UTC-5). Ver `SETUP_CHECKLIST.md` para el detalle del bug.

---

## 🔧 IMPLEMENTACIÓN DEL BACKEND

### Estructura Recomendada

```
backend/
├── __init__.py
├── app.py                 # App FastAPI + setup
├── config.py              # Configuración (pydantic-settings)
├── database.py            # SQLAlchemy setup + engine
├── models.py              # Modelos SQLAlchemy (7 tablas)
├── schemas.py             # Schemas Pydantic (validación)
├── routes/
│   ├── __init__.py
│   ├── platos.py          # CU-01
│   ├── comandas.py        # CU-02 + CU-03
│   ├── compras.py         # CU-04
│   └── mesas.py           # GET /api/mesas (soporte)
└── utils/
    ├── __init__.py
    └── security.py        # cliente_id validation, etc.
```

### Key Files to Create

**1. backend/config.py**
- Settings usando pydantic_settings
- DEBUG, ENVIRONMENT, DATABASE_URL, SECRET_KEY
- CORS origins

**2. backend/database.py**
- SQLAlchemy engine + sessionmaker
- Base declarative
- get_db() dependency injection

**3. backend/models.py**
- 7 tablas: Cliente, Usuario, Plato, Mesa, Comanda, ComandaPlato, Compra
- Relationships via ForeignKey
- índices en cliente_id

**4. backend/schemas.py**
- Pydantic schemas para validación
- Create schemas (input), Response schemas (output)
- Validators para reglas de negocio

**5. backend/routes/platos.py**
- GET /api/platos
- POST /api/platos
- PATCH /api/platos/{id}
- PATCH /api/platos/{id}/estado
- Siempre filtrar por cliente_id

**6. backend/routes/comandas.py**
- GET /api/comandas
- POST /api/comandas (calcula total, crea comanda_platos)
- GET /api/comandas/{id}
- PATCH /api/comandas/{id}/estado
- GET /api/monitor/cocina (solo estado='cocina', ordenado ASC)

**7. backend/routes/compras.py**
- GET /api/compras
- POST /api/compras
- PATCH /api/compras/{id}
- PATCH /api/compras/{id}/estado

**8. backend/routes/mesas.py**
- GET /api/mesas
- POST /api/mesas (crear mesa en setup)
- PATCH /api/mesas/{id}/estado (actualizar estado)

**9. backend/app.py**
- FastAPI app init
- CORS middleware
- Include routers
- Health check endpoint: GET /health

---

## 📱 IMPLEMENTACIÓN DEL FRONTEND

### Estructura

```
frontend/
├── index.html             # HTML único (SPA)
├── manifest.json          # PWA manifest
├── sw.js                  # Service Worker
├── css/
│   └── style.css
└── js/
    ├── app.js             # Lógica compartida (auth, API client)
    ├── mozo.js            # Interfaz del mozo (seleccionar platos)
    ├── cocina.js          # Monitor de cocina (ver comandas)
    └── admin.js           # Dashboard admin (crear platos, ver reportes)
```

### Key Features

**index.html:**
- Single HTML file
- Tabs/navigation para Mozo, Cocina, Admin
- PWA meta tags
- Manifest link

**manifest.json:**
- "display": "standalone" (oculta URL)
- "name": "RestoMind"
- "start_url": "/"
- Icons para diferentes tamaños

**sw.js:**
- Cache static assets
- Offline fallback (básico)
- Background sync (futuro)

**js/app.js:**
- API client (fetch wrapper)
- Auth management (localStorage)
- Utility functions

**js/mozo.js:**
- GET /api/mesas → mostrar lista
- GET /api/platos → mostrar por categoría
- POST /api/comandas → crear comanda
- Visual feedback

**js/cocina.js:**
- GET /api/monitor/cocina (cada 2 seg)
- PATCH /api/comandas/{id}/estado → marcar listo
- Tarjetas visuales con números de mesa grandes

**js/admin.js:**
- POST /api/platos → crear plato
- GET /api/platos → listar
- Dashboard básico

---

## 🔐 SEGURIDAD MULTI-TENANT

### Reglas Críticas

**REGLA 1: Filtro cliente_id en CADA consulta**
```python
# ✅ CORRECTO
db.query(Plato).filter(Plato.cliente_id == cliente_id).all()

# ❌ INCORRECTO
db.query(Plato).all()  # Expone todos los platos de todos los clientes
```

**REGLA 2: cliente_id sacado SIEMPRE del JWT o sesión**
```python
# ✅ CORRECTO
cliente_id = get_cliente_id_from_request(request)
db.query(Plato).filter(Plato.cliente_id == cliente_id).all()

# ❌ INCORRECTO
cliente_id = request.json.get("cliente_id")  # Usuario puede cambiar esto
```

**REGLA 3: Validar rol antes de operaciones sensibles**
```python
# ✅ Solo admin puede crear platos
if usuario.rol != "admin":
    raise HTTPException(status_code=403)
```

**REGLA 4: Logs de auditoría**
- Quién creó/editó/eliminó qué
- Timestamp para investigaciones

---

## ✅ CRITERIOS DE ACEPTACIÓN MVP

### Funcionalidad
- [ ] **CU-01:** Admin puede crear, editar y desactivar platos
- [ ] **CU-02:** Mozo registra comanda con múltiples platos desde celular
- [ ] **CU-03:** Pantalla cocina muestra comandas sin recargar, "Listo" desaparece
- [ ] **CU-04:** Admin registra compras rápidamente

### Datos
- [ ] Multi-tenant: cliente_id en TODAS las tablas
- [ ] BD normalizada 3FN
- [ ] Timestamps en UTC

### Seguridad
- [ ] cliente_id validado en backend para CADA request
- [ ] Roles definidos (admin, mozo, jefe_cocina)
- [ ] Contraseñas hasheadas (bcrypt, futuro)

### Rendimiento
- [ ] Respuesta API < 500ms
- [ ] Pantalla cocina actualiza cada 2s (polling)
- [ ] PWA carga en < 3s en 4G

### UX/UI
- [ ] Interfaz móvil responsiva (320px+)
- [ ] Botones táctiles grandes (48x48px+)
- [ ] Confirmaciones visuales

---

## 🚀 ORDEN DE IMPLEMENTACIÓN

### Fase 1: Setup Base (Sonnet - Sesión 1)
- [ ] backend/config.py
- [ ] backend/database.py (SQLAlchemy engine)
- [ ] backend/models.py (7 tablas)
- [ ] backend/schemas.py
- [ ] backend/app.py (health check)
- [ ] Fixture de datos de prueba

### Fase 2: API Backend (Sonnet - Sesión 2)
- [ ] backend/routes/platos.py (CU-01)
- [ ] backend/routes/mesas.py (soporte)
- [ ] backend/routes/comandas.py (CU-02)
- [ ] Tests unitarios

### Fase 3: API Backend Part 2 (Sonnet - Sesión 3)
- [ ] backend/routes/compras.py (CU-04)
- [ ] backend/routes/monitor cocina
- [ ] Tests integración

### Fase 4: Frontend PWA (Sonnet - Sesión 4+)
- [ ] frontend/index.html + manifest.json
- [ ] frontend/js/app.js (API client)
- [ ] frontend/js/mozo.js (CU-02)
- [ ] frontend/js/cocina.js (CU-03)
- [ ] frontend/js/admin.js (CU-01, CU-04)
- [ ] frontend/css/style.css

---

## 👥 Personal con Login Real por Rol

**Contexto:** El MVP original tenía un botón en el header para "elegir rol" (Mozo/Cocina/Admin) sin que nada lo validara. Esto servía para desarrollo y prototipos. Con login JWT implementado, el siguiente paso era dar cuentas reales a cada miembro del equipo.

### Cómo funciona

1. **El admin del restaurante crea cuentas de personal** desde Admin → Personal (nueva pestaña)
   - Nombre, contraseña, rol (Mozo / Cajero / Cocina) — **no pide celular**: el backend genera un código de acceso de 6 dígitos, único en todo el sistema, y lo muestra al admin para que se lo pase al empleado (ver "Código de acceso generado" más abajo)
   - El personal se loguea con ese código + contraseña por `/api/auth/login-staff`, distinto del login del admin (email + contraseña por `/api/auth/login`) — ver [[sistema-login-dual]]

2. **Cada cuenta se loguea con su credencial y contraseña**
   - El JWT que se emite lleva el rol de verdad (no es un click sin validar)
   - El rol del JWT manda sobre el selector de dispositivo — si Pedro se loguea como mozo, el celular se comporta como el de un mozo, automáticamente

3. **Backend valida permisos usando el rol del JWT**
   - `POST /api/platos` solo funciona si `rol == "admin"`
   - `POST /api/usuarios/staff` solo funciona si `rol == "admin"`
   - Endpoints de mozo (mesas, comandas) aceptan cualquier rol excepto superadmin

### Un admin no puede crear (ni ascender a) otro admin

Cada restaurante tiene exactamente un admin, dado de alta por el superadmin al registrar el cliente (ver `backend/scripts/crear_cliente.py`). Esto es intencional, no un descuido:

- `POST /api/usuarios` con `rol="admin"` → **403**. Este endpoint (email-based, genérico) queda solo para uso interno/futuro; desde el panel de Admin → Personal ya no se ofrece "Administrador" como opción de rol.
- `PATCH /api/usuarios/{id}` con `rol="admin"` sobre una cuenta que no es admin → **403**. Bloquea el camino indirecto de "crear un mozo y después ascenderlo".
- Si algún día un restaurante necesita un segundo admin, lo hace el superadmin, no el propio admin del restaurante.

### Endpoints de Personal

Todos admin-only (requieren `rol == "admin"` en el JWT):
```
GET    /api/usuarios                 → lista el personal del restaurante (incluye al propio admin)
POST   /api/usuarios/staff           → crea mozo/cajero/cocina (nombre, password, rol — el código de acceso lo genera el backend)
PATCH  /api/usuarios/{id}            → edita nombre/rol/estado (rol nunca puede ser "admin" salvo que ya lo sea)
PATCH  /api/usuarios/{id}/password   → resetea contraseña de alguien
DELETE /api/usuarios/{id}            → elimina la cuenta
```

> `rol` para cocina es literalmente `"jefe_cocina"` en toda la app (permisos, dashboard, `ROL_LABELS`) — no `"cocinero"`. Antes había una inconsistencia en `StaffCreateRequest` que hacía fallar silenciosamente la creación de cuentas de cocina; ya está corregida.

### Protecciones contra auto-bloqueo

- Un admin **no puede desactivarse a sí mismo** (`PATCH /api/usuarios/{mi_id}` con `estado='inactivo'` → 400)
- Un admin **no puede quitarse su propio rol de admin** (`PATCH /api/usuarios/{mi_id}` con `rol='mozo'` → 400)
- Un admin **no puede eliminarse a sí mismo** (`DELETE /api/usuarios/{mi_id}` → 400)
- Un admin **no puede crear ni ascender a otro admin** (ver arriba)

Estas reglas juntas garantizan que un restaurante **nunca** se queda sin ningún admin, y que nunca termina con más de uno sin que el superadmin lo decida explícitamente.

### UI del modal "Nueva Cuenta" / "Editar Cuenta"

- Al crear, no hay campo de celular: un texto avisa que el código de acceso se genera solo al guardar.
- El selector de Rol al crear solo ofrece Mozo / Cajero / Cocina (sin "Administrador").
- Al editar una cuenta de personal, el código de acceso ya generado se muestra de solo lectura, etiquetado **"Código de acceso"**.
- Al editar la fila del propio admin ("Tú"), el email y el rol se muestran como texto fijo no editable, en vez de inputs — visualmente distinto a poder cambiar algo y que el backend lo rechace después.

### Código de acceso generado (no un celular real)

**Por qué existe:** al principio el personal se creaba con un celular real como identificador de login (validado con formato peruano: 9 dígitos, empieza con 9). En la práctica, el admin de un restaurante chico no tiene un número distinto por cada mozo/cajero/cocinero, y menos quiere repartir el suyo propio como credencial compartida. Pedir un celular real ahí no protegía nada — el login nunca lo verificaba por SMS ni nada parecido, solo lo usaba como texto único — así que era un dato personal de más sin ningún beneficio, justo lo que una auditoría de datos señalaría.

- `POST /api/usuarios/staff` ya **no** recibe celular en el payload (solo `nombre`, `password`, `rol`). El backend genera un código numérico de 6 dígitos con `_generar_codigo_acceso()` (`backend/routes/usuarios.py`), revalidando contra la BD que sea único en todo el sistema (colisión aleatoria despreciable con 1 millón de combinaciones, pero igual se revisa).
- La respuesta de creación incluye el código generado (campo `celular` en `UsuarioResponse` — el nombre de columna no cambió para no forzar una migración, pero ya no representa un celular real). El frontend lo muestra en el toast de éxito y queda visible después en la fila de esa persona dentro de Admin → Personal.
- El campo ya no se valida con `_validar_celular_peru()` — esa función se sigue usando solo para `ClienteCreateRequest.telefono` (el teléfono de contacto real del restaurante, un concepto aparte).
- Cuentas de personal creadas **antes** de este cambio, con un celular real de 9 dígitos, siguen funcionando igual: el login nunca valida el formato, solo compara el valor guardado.
- Como el código sale del backend, ya no puede haber duplicados que el admin provoque sin querer — se eliminó por completo la lógica de "celular ya registrado" (tanto el aviso específico del mismo restaurante como el genérico de otro cliente).

### El selector de dispositivo sigue existiendo

Para restaurantes que prefieren compartir un solo celular sin cuentas individuales, el botón redondo del header (selector manual de rol) continúa funcionando como respaldo. Las dos formas conviven:
- **Con cuentas:** login real + el rol viene del JWT ← preferible para múltiples personas
- **Sin cuentas:** un solo login compartido + selector manual en cada dispositivo ← para almacenes pequeños

---

## 🛡️ ENDURECIMIENTO PARA UNA FUTURA AUDITORÍA

**Contexto:** con el flujo de login ya completo (email para admin/superadmin, código de acceso para personal), se revisó qué señalaría una auditoría de seguridad/datos. Se corrigieron cuatro puntos; el mínimo de contraseña (6 caracteres) queda **a propósito** sin tocar por ahora — el dueño lo está usando corto para acelerar su propio QA/QC, y lo subirá más adelante.

### 1. `SECRET_KEY` ya no tiene un valor por defecto inseguro

`backend/config.py` tenía `secret_key: str = "your-secret-key-change-in-production"`. Si `.env` no definía `SECRET_KEY` (un despliegue nuevo, un contenedor sin ese archivo), la app arrancaba igual y firmaba los JWT con ese string público que está en el código fuente — cualquiera podría forjar un token de admin o superadmin. Ahora `secret_key: str` no tiene default: si falta, `Settings()` lanza `ValidationError` y **la app no arranca**. Test: `tests/unit/test_config.py::test_settings_falla_sin_secret_key`.

### 2. El token declara su tipo explícitamente

Antes, `get_cliente_id`/`get_usuario_actual` (`backend/dependencies.py`) aceptaban cualquier token que **no** dijera `tipo == "superadmin"`, en vez de exigir `tipo == "usuario"` explícito. `crear_token()` (`backend/auth.py`) ahora siempre incluye `"tipo": "usuario"`, y las dependencias exigen ese valor exacto — un token de un tipo futuro/desconocido que no declare `tipo` ya no se cuela por descarte. Test: `test_token_sin_tipo_explicito_no_accede_a_rutas_de_restaurante`.

### 3. Rate limiting en los tres logins

`backend/utils/rate_limit.py` — en memoria, por IP, **solo cuenta intentos fallidos** (los éxitos no restan del límite: varios mozos entrando desde el mismo WiFi al empezar un turno no deberían gastar la cuota de nadie). 5 fallos en 15 minutos → `429` en el siguiente intento desde esa IP. Aplicado a `/auth/login`, `/auth/login-staff` y `/superadmin/login`.

Deliberadamente simple (sin Redis): esta app corre como un solo proceso uvicorn, así que el estado en memoria alcanza. Si el día de mañana corre en varios workers/servidores, esto hay que moverlo a algo compartido.

> **Nota para tests:** `TestClient` de Starlette siempre reporta el mismo host falso (`"testclient"`), así que sin resetear el contador entre tests, un test que prueba credenciales inválidas (401 esperado) podía terminar chocando con el límite y viendo un 429 que no tiene nada que ver con lo que prueba. `tests/conftest.py` tiene un fixture `autouse` (`_reset_rate_limit_login`) que limpia el estado antes y después de cada test.

### 4. Registro de auditoría (tabla `audit_log`)

`backend/models.py: AuditLog` — quién (`actor`), qué acción, sobre qué entidad, cuándo, y en qué restaurante (`cliente_id`, nulo para acciones a nivel superadmin). Vive en su propia tabla en la BD, no solo en logs de texto: sobrevive a la rotación/pérdida de esos logs y se puede consultar con una query. Esto es lo primero que pide una auditoría formal: *"¿quién eliminó esta cuenta y cuándo?"*.

`backend/utils/auditoria.py::registrar_evento()` nunca tumba la operación que audita — si guardar el evento falla, se ignora en vez de propagar el error.

Acciones que quedan registradas: `login` (los tres tipos de cuenta), `crear_usuario`, `crear_staff`, `editar_usuario`, `resetear_password`, `eliminar_usuario`, `crear_cliente`, `editar_cliente`, `cambiar_estado_cliente`, `eliminar_cliente`.

Para que no sea un registro de solo-escritura, hay un endpoint de lectura:
```
GET /api/superadmin/auditoria?cliente_id=<opcional>&limit=<opcional, máx 1000>
```
Superadmin-only (mismo tipo de token que el resto de `/superadmin/*`).

---

## 🎨 REDISEÑO VISUAL (UI 3D, pensado para PWA)

**Contexto:** con el flujo de login, seguridad y datos ya sólidos, tocaba
subir el nivel visual — la app se usa como un aplicativo móvil real (PWA
instalada en el celular del mozo/cajero/cocina), no como una demo de
escritorio. El objetivo: que se sienta "profesional y dinámica" sin romper
la restricción de rendimiento que ya tenía el CSS desde el inicio (gama
media/baja: sin `backdrop-filter`, sin animaciones costosas — ver el
comentario en la cabecera de `frontend/css/style.css`).

### Ícono de mesa con relieve 3D

Antes era un círculo plano + 4 puntos como sillas. Ahora (`frontend/js/mozo.js`,
`frontend/css/style.css`, `frontend/index.html`):

- El disco de la mesa usa un **gradiente radial** (claro arriba-izquierda,
  oscuro abajo-derecha) en vez de un color sólido — da sensación de
  superficie curva/pulida.
- **Sombra elíptica** debajo de la mesa (ancla el ícono al piso, look "flotante").
- **Brillo especular** (una elipse blanca translúcida) arriba-izquierda,
  simula reflejo de luz sobre una superficie brillante.
- Las sillas tienen su propio gradiente lineal, en vez de color plano.
- Los gradientes viven en un único `<defs>` global inyectado en
  `frontend/index.html` (no uno por botón) — evita duplicar SVG cuando hay
  20+ mesas en la grilla, y usa `var()` en los `<stop>` para heredar el
  tema oscuro automáticamente sin lógica en JS.
- **Nada de esto usa `filter`/blur**: son formas planas (`circle`, `ellipse`)
  con gradiente — mismo costo de pintado que un ícono de color sólido.

### Interacciones táctiles ("feel" de app nativa)

- Al presionar una mesa: se "hunde" (`scale(0.94) translateY(1px)` +
  reducción de sombra) en vez de solo achicarse — imita un botón físico.
- Mesas ocupadas: halo cálido (`box-shadow` extra) además del cambio de
  color, para que salten a la vista en una grilla grande sin depender solo
  del color (accesibilidad para daltonismo parcial).
- Botón primario (`.btn-primary`): gradiente diagonal + sombra que se
  comprime al presionar, en vez de un color plano.
- Nav inferior: el ítem activo tiene una "píldora" de fondo detrás del
  ícono, con una animación de entrada corta (`scale` + `opacity`) — patrón
  que ya usan iOS/Android nativos, reemplaza el simple cambio de color de
  antes.

### Cajitas de texto (inputs, textarea, select)

Usadas en todos los formularios y en el login. Cambios en
`.form-group input/textarea/select`:

- Relieve "hundido" sutil (`box-shadow: inset`) — el campo se distingue de
  la tarjeta que lo contiene en vez de ser un rectángulo plano indistinguible.
- Al enfocar: **glow cálido** alrededor del borde (color del acento) en vez
  del outline azul genérico del navegador, con transición suave.
- Hover: el borde se oscurece levemente como anticipo antes de tocar.
- Labels en mayúsculas con letter-spacing, mismo lenguaje visual que ya
  usaban los títulos de sección (`.section-title`) — antes eran inconsistentes.
- `<select>` con flecha custom en SVG (antes usaba el ícono feo por defecto
  del navegador, distinto en cada plataforma).

### Por qué nada de esto pesa más

Todo el rediseño usa únicamente `linear-gradient`/`radial-gradient`,
`box-shadow` y `transform` — las tres primitivas más baratas de pintar en
CSS (compositing por GPU, sin recalcular píxeles como sí exige
`backdrop-filter` o un blur). Cero librerías nuevas, cero imágenes
adicionales, cero peso extra en la carga de la PWA.

---

## 💰 VALIDADOR DE CAJA

**Contexto:** el dashboard financiero (CU-05) ya mostraba cuánto "debería"
haber entrado en ventas, pero nada comparaba eso contra el dinero físico
real en la caja al cerrar el día — el punto exacto donde aparecen los
errores de vuelto, los faltantes y (en el peor caso) el fraude interno.
Este validador cierra ese hueco.

### Flujo (dos pasos separados en el tiempo, no un formulario único)

```
Mañana: POST /api/caja/abrir   { saldo_inicial }
   ↓ (el día opera normal: comandas, compras)
Noche:  POST /api/caja/cerrar  { saldo_contado, retiros_personales, razon_discrepancia? }
```

El cierre calcula, sin que el admin escriba nada de eso a mano:
```
saldo_esperado = saldo_inicial + ventas_cobradas - gastos_efectivo - retiros_personales
diferencia     = saldo_contado - saldo_esperado
estado         = cuadrado (|diferencia| < 0.01)
               | discrepancia_leve (|diferencia| <= 5)
               | discrepancia_grave (|diferencia| > 5)
```

`ventas_cobradas`/`gastos_efectivo` se calculan igual que el dashboard
(`backend/routes/dashboard.py`): comandas con `estado='cobrado'` y compras
`estado='registrado'` del día, usando el mismo criterio de zona horaria
LOCAL del restaurante (header `X-TZ-Offset`) para no contar mal una venta
cobrada cerca de medianoche.

**Simplificación deliberada del MVP:** todo el dinero de `Comanda`/`Compra`
se asume efectivo — la app aún no distingue método de pago (efectivo/
tarjeta/Yape). Un restaurante que cobra con tarjeta verá diferencias en su
cierre que no son fraude, son ventas con tarjeta. Documentado también en
`CierreCaja` (`backend/models.py`) para que quien implemente método de
pago sepa que este cálculo necesita filtrar por ahí.

### Solo puede haber UNA caja abierta a la vez

Lo impone `POST /caja/abrir`: si el admin se olvida de cerrar un día,
`POST /caja/cerrar` sigue apuntando a **esa** caja pendiente aunque ya no
sea "hoy" (`es_atrasada=true` en `GET /caja/estado` avisa al frontend) —
nunca se puede abrir una caja nueva encima de una sin cerrar, y nunca se
cierra por accidente el día equivocado. `UniqueConstraint(cliente_id, fecha)`
en la tabla es la red de seguridad final contra dos aperturas el mismo día.

### Endpoints (`backend/routes/caja.py`, todos admin-only)

```
GET  /api/caja/estado     → snapshot en vivo: hay_caja_abierta, caja_abierta
                             (con ventas/gastos recalculados en cada consulta
                             mientras sigue abierta), caja_cerrada_hoy si ya
                             se cerró, es_atrasada si es de un día anterior
POST /api/caja/abrir      → { saldo_inicial }
POST /api/caja/cerrar     → { saldo_contado, retiros_personales?, razon_discrepancia? }
GET  /api/caja/historial  → últimos N cierres (no incluye la caja abierta)
```

### Frontend: Admin → Caja

Tres estados posibles en pantalla, el backend decide cuál mostrar (el
frontend nunca infiere el estado localmente, para no desincronizarse si
hay dos pestañas del admin abiertas a la vez):

1. **Sin caja hoy** → formulario "Abrir caja"
2. **Caja abierta** → resumen en vivo (ventas/gastos hasta ahora) +
   formulario "Cerrar caja" (con aviso si es una caja atrasada de otro día)
3. **Caja de hoy ya cerrada** → resultado + botón para reimprimir el reporte

`frontend/js/caja.js` maneja el flujo; `frontend/js/cierre-caja-print.js`
genera el reporte imprimible.

### Reporte imprimible (`cierre-caja-print.js`)

Diseñado para que el dueño lo entienda en 2-3 segundos, no en 30 —
mismo principio que una boleta electrónica: resultado (✅/⚠️/❌) primero y
GRANDE, números secundarios más chicos, sin obligar a sumar nada mentalmente.

- Banner de resultado con color según estado (verde/amarillo/rojo)
- Esperado vs Contado lado a lado, Diferencia destacada
- Detalles (saldo inicial, ventas, gastos, retiros) en texto más chico
- Razón de discrepancia si el admin la anotó
- Firmas (cerrado por / revisado por) y QR de verificación
- Se abre solo en una pestaña nueva al cerrar caja (`window.open` +
  `document.write`), con botón de imprimir — pensado para PDF o impresora
  A4, no para la impresora térmica de 80mm de las comandas

### Historial y auditoría

`GET /caja/historial` alimenta la lista de cierres pasados en la misma
pantalla, cada uno reimprimible. Cada apertura/cierre queda además en
`audit_log` (`registrar_evento`, acciones `abrir_caja`/`cerrar_caja`) —
mismo mecanismo que el resto de acciones sensibles de la app.

---

## 🚀 LISTOS PARA PRODUCCIÓN

**Contexto:** con el login y la auditoría ya endurecidos, faltaba cerrar lo
que un despliegue real necesita antes de recibir tráfico de un dominio de
verdad: CORS bien configurado, cabeceras de seguridad HTTP, y un checklist
para no depender de memoria al elegir hosting.

**Ver [`PRODUCTION_READINESS.md`](PRODUCTION_READINESS.md)** para la
checklist completa (qué ya está resuelto en código, qué variables de entorno
hay que cambiar, y qué le toca al proxy/hosting — HTTPS, no a esta app).

Resumen de lo agregado:
- `backend/config.py` ahora falla al arrancar en `ENVIRONMENT=production` si
  `DEBUG=true` o si `CORS_ORIGINS` sigue en los valores de desarrollo (o es
  `"*"`) — mismo principio que el fail-fast de `SECRET_KEY`.
- `backend/middleware.py` (nuevo): cabeceras de seguridad en toda respuesta
  (CSP, `X-Frame-Options`, `X-Content-Type-Options`, `Referrer-Policy`, y
  `Strict-Transport-Security` cuando detecta HTTPS vía `X-Forwarded-Proto`).
- La contraseña mínima **sigue en 6 caracteres**, a propósito — no se tocó.

---

## 📝 NOTAS PARA EL DESARROLLADOR

**Importante:**
- No uses ORM complejo; SQLAlchemy básico funciona
- No agregues features no pedidas (YAGNI)
- Refactoriza solo si es evidente (DRY)
- Tests primero, luego código (TDD opcional pero recomendado)
- Comenta solo el WHY, no el WHAT
- Usa type hints en Python

**Git:**
- Commit pequeños, frecuentes
- Mensaje descriptivo: "feat: create platos endpoint" o "fix: cliente_id filter"
- Una feature = uno o dos commits máximo

**Testing:**
- Tests unitarios para schemas/models
- Tests integración para endpoints (sin BD real, con fixture)
- Cobertura target: 80%+

---

**Versión:** 2.1 (Login Real Dual: Email para Admin/Superadmin, Celular para Staff)  
**Estado:** ✅ **LOGIN COMPLETAMENTE FUNCIONAL** — Autenticación probada y operativa  
**Última Actualización:** 2026-08-29  
**Tests:** 64/64 pasando  

### ✅ Login Implementado y Probado

- ✅ Endpoint `/api/auth/login` unificado (intenta Usuario → SuperAdmin)
- ✅ Endpoint `/api/auth/login-staff` para staff con celular
- ✅ UI con dual-tab login en pantalla inicial
- ✅ Tokens JWT con tipos diferenciados (usuario vs superadmin)
- ✅ Redirección automática: superadmin → `/superadmin.html`, staff/admin → `/index.html`
- ✅ Logs detallados para debugging de autenticación
- ✅ Botón de reset (↻) para tablets sin teclado
- ✅ Auto-limpieza de localStorage corrupto en recarga
- ✅ Contraseña hasheada con bcrypt, nunca plaintext

**Documentación de cambios:** Ver `SETUP_CHECKLIST.md`
