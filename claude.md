# 📋 RESTOMIND SAAS - DOCUMENTACIÓN TÉCNICA

**Versión MVP:** 2.1 — Login Dual (Email para Admin/Superadmin + Celular para Staff)
**Implementado y probado:** ✅ 100% Autenticación funcional
**Última actualización:** 2026-08-29

> Este documento describe el diseño original (MVPv1). El estado real de la
> implementación actual, bugs corregidos, features agregados y decisiones
> tomadas durante el desarrollo están en `SETUP_CHECKLIST.md`.
>
> **Lo que cambió desde MVPv1:**
> - ✅ **Login real con JWT** — autenticación segura con tokens validados
> - ✅ **Login dual:** Email (admin/superadmin) + Celular (staff: mozo/cajero/cocinero)
> - ✅ **Panel General (Superadmin)** — el dueño del sistema ve todos sus restaurantes clientes
> - ✅ **Personal con login individual** — cada mozo/cajero/cocinero tiene su propia cuenta con celular
> - ✅ **Rol desde JWT** — el rol viene del token, no de un click en el header
> - ✅ **Redirección inteligente** — superadmin → panel general, staff/admin → panel restaurante
> - ✅ **Logs de autenticación** — debugging detallado sin exponer datos sensibles
> - ✅ 64 tests automáticos (3x el MVP original)

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
- **Credencial:** Celular (número de teléfono) + Contraseña
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
- Input celular (número de teléfono)
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

- Límite: 5MB por archivo (una foto de celular sin comprimir).
- **La validación de formato no confía en el Content-Type que manda el
  cliente ni en la extensión del nombre del archivo** — ambos se falsean
  con un `curl -F`. Se valida la firma binaria real (primeros bytes del
  archivo: JPEG, PNG o WEBP). Un `.html` renombrado a `.png` se rechaza
  con 400 antes de tocar el disco.
- El archivo se guarda como `frontend/assets/platos/{plato_id}.{ext}`,
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
   - Nombre, **celular** (no email), contraseña, rol (Mozo / Cajero / Cocina)
   - El personal se loguea con celular + contraseña por `/api/auth/login-staff`, distinto del login del admin (email + contraseña por `/api/auth/login`) — ver [[sistema-login-dual]]
   - El celular debe ser único en todo el sistema

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
POST   /api/usuarios/staff           → crea mozo/cajero/cocina (nombre, celular, password, rol)
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

- Campo renombrado de "Email de login" a **"Celular de acceso"** — refleja que el personal entra con celular, no email.
- El selector de Rol al crear solo ofrece Mozo / Cajero / Cocina (sin "Administrador").
- Al editar la fila del propio admin ("Tú"), el email y el rol se muestran como texto fijo no editable, en vez de inputs — visualmente distinto a poder cambiar algo y que el backend lo rechace después.

### Validación de celular (formato peruano)

Todo campo de celular/teléfono en la app —el del personal, el de contacto del restaurante en el panel de superadmin, y el del login de Personal— exige el formato de un celular peruano real: **9 dígitos, empieza con 9** (ej. `987654321`).

- **Frontend:** `soloDigitos(event)` (en `app.js` y `superadmin.js`) filtra cualquier tecla que no sea número mientras el usuario escribe — no deja ni llegar a escribir una letra. Los inputs además usan `inputmode="numeric"` y `maxlength="9"`.
- **Backend:** `_validar_celular_peru()` en `schemas.py` es la validación real (la del frontend es solo UX; nunca hay que confiar en el cliente). Aplica a:
  - `StaffCreateRequest.celular` — obligatorio, para crear mozo/cajero/cocina
  - `ClienteCreateRequest.telefono` — opcional, pero si el superadmin lo llena al crear/editar un restaurante, tiene que ser un celular válido
- Si el formato no cumple, el backend responde 422 con un mensaje como *"El celular debe tener 9 dígitos y empezar con 9 (ej: 987654321)"*. `extraerMensajeError()` (en `app.js`/`superadmin.js`) es lo que traduce la respuesta 422 de FastAPI (una lista de objetos) a ese texto legible para el toast — sin esto, el usuario vería JSON crudo en la notificación de error.

### Celular duplicado: aviso sin filtrar datos de otro restaurante

El celular es único en **todo el sistema**, no solo por restaurante: `login-staff` resuelve a qué restaurante pertenece alguien buscando únicamente por celular, sin saber de antemano el `cliente_id` — así que dos restaurantes no pueden compartir un mismo celular de personal.

Al crear personal (`POST /usuarios/staff`), si el celular ya existe, el mensaje de error depende de a quién pertenece:

- **Mismo restaurante:** mensaje específico, con nombre y rol — es el propio dato del admin. *"Ya tienes este celular registrado: Pedro Ramírez (Mozo)"*.
- **Otro restaurante cliente:** mensaje genérico a propósito — *"Este celular ya está registrado en el sistema"*, sin nombrar el restaurante, el admin ni el empleado ajeno. Decir cuál restaurante lo tiene sería filtrar datos de otro cliente, algo que el aislamiento multi-tenant de esta app prohíbe explícitamente (ver "Aislamiento de Datos y Seguridad" arriba).

### El selector de dispositivo sigue existiendo

Para restaurantes que prefieren compartir un solo celular sin cuentas individuales, el botón redondo del header (selector manual de rol) continúa funcionando como respaldo. Las dos formas conviven:
- **Con cuentas:** login real + el rol viene del JWT ← preferible para múltiples personas
- **Sin cuentas:** un solo login compartido + selector manual en cada dispositivo ← para almacenes pequeños

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
