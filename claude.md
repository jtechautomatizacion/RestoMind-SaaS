# 📋 RESTOMIND SAAS - DOCUMENTACIÓN TÉCNICA

**Versión MVP:** 1.0 — implementado y probado (20/20 tests)
**Última actualización:** 2026-08-29

> Este documento describe el diseño original. El estado real de la
> implementación, los bugs corregidos en el camino y las decisiones
> tomadas durante el desarrollo están en `SETUP_CHECKLIST.md`.
> Dos cosas se agregaron durante el desarrollo porque el MVP no
> cerraba sin ellas: **CU-05 Dashboard Financiero** y el **cobro de
> mesa** (`POST /api/mesas/{id}/cobrar`) — ver el final de este archivo.

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
  "estado": "activo",
  "creado_en": "2026-08-28T10:30:00Z"
}
```

**Validaciones:**
- ✅ cliente_id OBLIGATORIO (tomar de sesión)
- ✅ nombre: no vacío, máx 100 caracteres
- ✅ categoría: no vacía
- ✅ precio_venta: > 0, decimal con 2 decimales

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

**Versión:** 1.0 MVP  
**Estado:** Listo para Implementación  
**Última Actualización:** 2026-08-28
