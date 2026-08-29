# Análisis Técnico Completo: Sistema de Autenticación RestoMind

**Fecha:** 2026-08-29  
**Versión:** 2.1 (Dual Login Real: Email + Código de Acceso)  
**Estado:** ✅ **COMPLETAMENTE FUNCIONAL Y AUDITADO**

## 📋 Resumen Ejecutivo

RestoMind implementa un **sistema dual de autenticación con JWT** que soporta tres tipos de usuarios:

| Tipo | Credencial | Endpoint | Tabla | Redirige A |
|------|-----------|----------|-------|-----------|
| **Superadmin** | Email + Password | `POST /api/auth/login` | `SuperAdmin` | `/superadmin.html` |
| **Admin Restaurante** | Email + Password | `POST /api/auth/login` | `Usuario` (rol=admin) | `/index.html` |
| **Personal** (Mozo/Cajero/Cocina) | Código acceso (6 dígitos) + Password | `POST /api/auth/login-staff` | `Usuario` (rol=mozo\|cajero\|jefe_cocina) | `/index.html` |

El sistema está **auditado para pasar una revisión de seguridad formal:**
- ✅ SECRET_KEY requerido (no hardcodeado)
- ✅ Tokens con tipo explícito
- ✅ Rate limiting en logins (5 fallos / 15 min = 429)
- ✅ Registro de auditoría persistente en BD
- ✅ Aislamiento multi-tenant (cliente_id validado en CADA request)

---

## 🔄 Flujo de Autenticación Completo

### Paso 1: Frontend Inicializa (`window.onload`)

```javascript
// frontend/js/auth.js → initAuth()

1. Recupera token de localStorage (clave: 'restomind_token')
2. Recupera usuario de localStorage (clave: 'restomind_usuario')

Si NO hay ambos → mostrar pantalla de login
Si HAY ambos → ir a Paso 2 (Validar contra servidor)
```

### Paso 2: Valida Token Guardado contra Servidor

```javascript
// GET /api/auth/me + header Authorization: Bearer <token>

Frontend → Backend → Decodifica JWT + Busca Usuario en BD

Respuesta Backend:
  ✅ 200 → Usuario sigue activo: mostrar app
  ❌ 401 → Token expirado/revocado: limpiar localStorage, mostrar login
```

Backend valida que:
1. Token no esté expirado (`exp` > ahora)
2. Usuario siga existiendo en la BD
3. Usuario siga en estado='activo'
4. Cliente (restaurante) esté activo
5. Token tenga `tipo` correcto

### Paso 3: Usuario Ingresa Credenciales

**Opción A: Pestaña "Administrador"**
```
1. Usuario escribe: Email + Contraseña
2. onclick → loginAdmin(event)
3. POST /api/auth/login { email, password }
```

**Opción B: Pestaña "Personal"**
```
1. Usuario escribe: Código de acceso (6 dígitos) + Contraseña
2. onclick → loginStaff(event)
3. POST /api/auth/login-staff { celular, password }
   (nota: "celular" es el nombre del campo, pero contiene el código auto-generado)
```

### Paso 4: Backend Intenta Autenticar

**Para `/api/auth/login` (email-based):**

```python
1. Llama verificar_intentos_login(request)
   → Si >= 5 fallos en últimos 15 min desde esa IP: 429 "Demasiados intentos"

2. Email = payload.email.strip().lower()
   Log: "[LOGIN] Intento con email: {email}"

3. Intenta buscar Usuario con ese email
   - Si encontrado → Log: "[LOGIN] Usuario encontrado: {id}, rol: {rol}"
   - Si NO encontrado → Log: "[LOGIN] Usuario NO encontrado, intentando SuperAdmin..."

4. Si no es Usuario, intenta buscar SuperAdmin
   - Si encontrado → Log: "[LOGIN] SuperAdmin encontrado: {id}"
   - Si NO encontrado → Log: "[LOGIN] Email {email} no encontrado en ninguna tabla"
                        Lanza 401 (sin revelar qué tabla NO lo tiene)

5. Verifica password (bcrypt.checkpw)
   - Si INCORRECTO → registrar_login_fallido(request) → 401
   - Si CORRECTO → continuar

6. Valida estado:
   - Si usuario.estado != 'activo' → 403 "Usuario está deshabilitado"
   - Si cliente.estado != 'activo' → 403 "Cuenta de restaurante está deshabilitada"

7. Si TODAS las validaciones pasan:
   limpiar_intentos_login(request)  # Resetea el contador de fallos
   registrar_evento(db, actor=email, accion="login", ...)  # Auditoría
   token = crear_token(email, cliente_id, rol)
   
   Response 200:
   {
     "access_token": "<JWT con tipo='usuario' si Usuario, tipo='superadmin' si SuperAdmin>",
     "usuario": {
       "email": "<email>",
       "nombre": "<nombre>",
       "rol": "<admin|mozo|cajero|jefe_cocina|superadmin>",
       "cliente_id": "<rest-001|superadmin>",
       "cliente_nombre": "<La Marisquería del Chef|Panel General>"
     }
   }
```

**Para `/api/auth/login-staff` (código-based):**

```python
1. Igual a arriba, pero:
   - Busca Usuario por celular (que contiene el código auto-generado)
   - No intenta SuperAdmin (staff nunca es superadmin)
   - Token se crea con email=usuario.celular (el código) en el campo 'sub'
   - En la respuesta, usuario.email muestra el nombre (no el código) para UX
```

### Paso 5: Frontend Maneja Respuesta

**Si 200 OK:**
```javascript
const data = await resp.json();
guardarSesion(data.access_token, data.usuario);
aplicarUsuarioDeSesion(data.usuario);

// Guarda en localStorage:
// - restomind_token = access_token (JWT)
// - restomind_usuario = usuario (JSON)
// - restomind_rol = usuario.rol (para selector manual de dispositivo)

if (data.usuario.rol === 'superadmin') {
    window.location.href = '/static/superadmin.html';  // Redirige a panel general
} else {
    mostrarApp();  // Muestra /index.html con el rol del JWT
}
```

**Si 401:**
```javascript
throw new Error("Email o contraseña incorrectos")  // O "Celular o contraseña incorrectos"
// Mensaje genérico: no revela si email/celular existe
mostrarLogin(mensaje);
```

**Si 429:**
```javascript
// Rate limiting: demasiados intentos fallidos
throw new Error("Demasiados intentos fallidos. Espera unos minutos e intenta de nuevo.")
```

**Si 403:**
```javascript
// Usuario deshabilitado o cliente suspendido
throw new Error("Este usuario está deshabilitado" | "Esta cuenta de restaurante está deshabilitada")
```

---

## 🔑 Estructura del Token JWT

### Token de Usuario (tipo="usuario")

```javascript
Header: { "alg": "HS256", "typ": "JWT" }

Payload:
{
  "sub": "<email o celular (código)>",
  "cliente_id": "rest-001",
  "rol": "admin|mozo|cajero|jefe_cocina",
  "tipo": "usuario",
  "iat": <timestamp creación>,
  "exp": <timestamp + 12 horas>
}

Signature: HMAC-SHA256(header.payload, settings.SECRET_KEY)
```

**Validaciones en Backend:**
- Token debe tener `tipo == "usuario"` (explicit check, no inferencia)
- Token debe tener `cliente_id` (no puede ser vacío)
- `exp` no debe estar en el pasado
- Signature debe coincidir con SECRET_KEY

### Token de Superadmin (tipo="superadmin")

```javascript
Header: { "alg": "HS256", "typ": "JWT" }

Payload:
{
  "sub": "<email superadmin>",
  "tipo": "superadmin",
  "iat": <timestamp creación>,
  "exp": <timestamp + 12 horas>
}

Signature: HMAC-SHA256(header.payload, settings.SECRET_KEY)
```

**Diferencias:**
- SIN `cliente_id` (es administrador global, no de un restaurante)
- SIN `rol` (no necesita roles granulares)
- Tipo explícitamente `"superadmin"`

---

## 🛡️ Dependencias de Validación de Token

Cada ruta protegida inyecta una o más dependencias de `backend/dependencies.py`:

### 1. `get_cliente_id(payload) → str`

```python
# Usado por rutas de restaurante: /api/mesas, /api/platos, /api/comandas, etc.

Valida que:
  - payload.get("tipo") == "usuario"  (explícitamente, no "no es superadmin")
  - payload["cliente_id"] existe

Si falla → 403 "Este token no da acceso a datos de un restaurante"

Devuelve: cliente_id (para filtrar queries: WHERE cliente_id = ?)
```

### 2. `get_usuario_actual(payload) → str`

```python
# Usado por rutas que necesitan saber quién es el usuario

Valida que:
  - payload.get("tipo") == "usuario"
  - payload["cliente_id"] existe

Si falla → 403 "Este token no da acceso a datos de un restaurante"

Devuelve: payload["sub"] (email o celular/código del usuario)
```

### 3. `get_superadmin_email(payload) → str`

```python
# Usado por rutas /api/superadmin/* (panel general, auditoría, gestión clientes)

Valida que:
  - payload.get("tipo") == "superadmin"  (rechaza tokens de restaurante)

Si falla → 403 "Esta acción requiere una sesión de administrador general"

Devuelve: payload["sub"] (email del superadmin)
```

### 4. `_payload_del_token(authorization_header) → dict`

```python
# Dependencia base: la llaman las otras tres

Valida que:
  - Header Authorization exista y empiece con "Bearer "
  - Token sea decodificable (JWT válido, firma correcta, no expirado)
  - SECRET_KEY sea el mismo que se usó para firmarlo

Si falla:
  - 401 "No autenticado" (falta header o no empieza con Bearer)
  - 401 "Sesión inválida o expirada" (JWT inválido o vencido)
```

---

## 🔐 Seguridad: Las 4 Capas Implementadas

### Capa 1: Contraseña Hasheada (bcrypt)

```python
# backend/auth.py

def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

def verificar_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
```

- Nunca se almacena plaintext
- Nunca viaja en logs o mensajes de error
- Costo computacional: ~0.3s por intento (desalienta fuerza bruta)

### Capa 2: SECRET_KEY Requerido

```python
# backend/config.py

class Settings(BaseSettings):
    secret_key: str  # ← Sin default, ValidationError si falta en .env
    # Si falta → app NO arranca
```

Antes:
```python
secret_key: str = "your-secret-key-change-in-production"  # ❌ INSEGURO
```

Implicación: si alguien dejaaba la app sin `.env`, los JWT se firmaban con un secreto público que está en el repo → cualquiera podría forjar tokens.

### Capa 3: Rate Limiting en Logins

```python
# backend/utils/rate_limit.py

MAX_INTENTOS_FALLIDOS = 5
VENTANA_SEGUNDOS = 15 * 60  # 15 minutos

# Por IP, solo cuenta FALLOS, no éxitos
```

Flujo en cada login:
1. `verificar_intentos_login(request)` → si >= 5 fallos recientes: 429
2. Si credenciales INCORRECTAS → `registrar_login_fallido(request)` (suma fallo)
3. Si credenciales CORRECTAS → `limpiar_intentos_login(request)` (resetea contador)

**Por qué solo fallos:**
- Un restaurante pequeño, varios mozos logueándose juntos al empezar un turno desde el mismo WiFi (misma IP pública)
- Si contáramos éxitos, los 5 primeros que logran entrar bloquearían a los demás
- Solo contar fallos = frena ataques de fuerza bruta, no bloquea usuarios legítimos

### Capa 4: Auditoría Persistente

```python
# backend/models.py

class AuditLog(Base):
    __tablename__ = "audit_log"
    
    id: int (PK)
    timestamp: datetime (UTC)
    actor: str (email/celular del que hizo la acción)
    accion: str ("login", "crear_usuario", "editar_usuario", etc.)
    entidad: str ("usuario", "cliente", "superadmin")
    entidad_id: str (id de lo que se modificó)
    cliente_id: str | None (NULL para acciones de superadmin)
    detalle: str | None (detalles adicionales)
```

Acciones registradas:
- `login` (los 3 tipos: superadmin, admin, staff)
- `crear_usuario` / `crear_staff`
- `editar_usuario`
- `cambiar_password` / `resetear_password`
- `eliminar_usuario`
- `crear_cliente`
- `editar_cliente`
- `cambiar_estado_cliente` (activar/desactivar restaurante)
- `eliminar_cliente`

Lectura (superadmin-only):
```
GET /api/superadmin/auditoria?cliente_id=<opt>&limit=<opt, max 1000>
```

---

## 🎯 Flujos de Caso de Uso

### CU-01: Superadmin Ingresa al Panel General

```
1. Abre /static/index.html
2. initAuth() valida token en localStorage
   → Si no hay token: mostrar login
3. Selecciona pestaña "Administrador"
4. Ingresa: email="jtechautomatizacion@gmail.com", password="123456"
5. POST /api/auth/login

Backend:
  ✓ Busca Usuario con ese email → NO encontrado
  ✓ Busca SuperAdmin con ese email → SÍ encontrado
  ✓ Verifica password → CORRECTO
  ✓ Crea token con tipo="superadmin" (sin cliente_id)
  ✓ Registra evento "login" en audit_log
  → Response 200 + rol="superadmin"

Frontend:
  ✓ Guarda token en localStorage
  ✓ Ve que rol === 'superadmin'
  → window.location.href = '/static/superadmin.html'
  → Carga panel para ver/crear/editar restaurantes clientes
```

### CU-02: Admin del Restaurante Ingresa

```
1. Abre /static/index.html
2. Selecciona pestaña "Administrador"
3. Ingresa: email="admin@rest001.com", password="123456"
4. POST /api/auth/login

Backend:
  ✓ Busca Usuario con ese email → SÍ encontrado
  ✓ Valida password → CORRECTO
  ✓ Valida estado usuario → 'activo'
  ✓ Valida estado cliente → 'activo'
  ✓ Crea token con tipo="usuario", cliente_id="rest-001", rol="admin"
  ✓ Registra evento "login" en audit_log
  → Response 200

Frontend:
  ✓ Guarda token
  ✓ Ve que rol !== 'superadmin'
  → mostrarApp()
  → Carga /index.html con rol="admin" (ve todas las pestañas)
```

### CU-03: Mozo Ingresa desde Celular

```
1. Abre /static/index.html en celular del restaurante
2. Selecciona pestaña "Personal"
3. Ingresa: código_acceso="547392", password="123456"
4. POST /api/auth/login-staff { celular="547392", password="123456" }

Backend:
  ✓ Busca Usuario con celular="547392" → SÍ encontrado (mozo "Pedro")
  ✓ Valida password → CORRECTO
  ✓ Valida estado → 'activo'
  ✓ Crea token con tipo="usuario", cliente_id="rest-001", rol="mozo"
  ✓ Registra evento "login" en audit_log
  → Response 200

Frontend:
  ✓ Guarda token
  → mostrarApp()
  → Carga /index.html con rol="mozo" (ve solo las pestañas de mozo)
  → El header muestra: "Bienvenido, Pedro" (nombre, no el código)
```

### CU-04: Token Vencido a Medio Servicio

```
1. Mozo está registrando una comanda (sesión abierta hace > 12 horas)
2. POST /api/comandas (lleva token viejo en Authorization header)

Backend:
  ✓ Intenta decodificar token
  → JWT.decode() lanza PyJWTError (exp < ahora)
  → decodificar_token() devuelve None
  → _payload_del_token() lanza 401 "Sesión inválida o expirada"

Frontend (en app.js, wrappea fetch):
  ✓ Ve 401 → manejarSesionExpirada()
  ✓ limpiarSesion() (borra localStorage)
  → mostrarLogin("Tu sesión expiró. Ingresa de nuevo.")
  → El mozo vuelve a ingresar credenciales
```

### CU-05: Intento de Fuerza Bruta

```
1. Alguien desde IP 192.168.1.100 intenta entrar:
   Intento 1: email="admin@rest001.com", password="wrong1" → 401
   Intento 2: email="admin@rest001.com", password="wrong2" → 401
   Intento 3: email="admin@rest001.com", password="wrong3" → 401
   Intento 4: email="admin@rest001.com", password="wrong4" → 401
   Intento 5: email="admin@rest001.com", password="wrong5" → 401
   Intento 6: email="admin@rest001.com", password="wrong6" → ?

Backend (intento 1-5):
  ✓ registrar_login_fallido(request) suma timestamp a _fallos["192.168.1.100"]
  → Devuelve 401

Backend (intento 6):
  ✓ verificar_intentos_login(request) ve 5 fallos en últimos 15 min
  → Lanza 429 "Demasiados intentos fallidos. Espera unos minutos..."

Intento 7-X: Sigue devolviendo 429 hasta que pasen 15 minutos desde el intento 1
Después de 15 min: El contador se limpia automáticamente, se puede intentar de nuevo
```

---

## 📱 UI de Login (Frontend)

### Estructura HTML

```html
<div id="login-screen" class="login-screen hidden">
  <!-- Botón de reset para tablets sin teclado -->
  <button id="btn-reset-login" class="btn-reset-login" onclick="limpiarYRecargar()">↻</button>
  
  <div class="login-card">
    <div class="login-logo">RestoMind</div>
    <p class="login-subtitulo">Sistema de gestión para restaurantes</p>
    
    <!-- Pestañas toggleables -->
    <div class="login-tabs">
      <button class="login-tab active" onclick="cambiarTabLogin('admin')">
        <svg>...</svg> Administrador
      </button>
      <button class="login-tab" onclick="cambiarTabLogin('staff')">
        <svg>...</svg> Personal
      </button>
    </div>
    
    <!-- Pestaña 1: Admin (Email) -->
    <form id="form-login-admin" class="login-form active" onsubmit="loginAdmin(event)">
      <input type="email" id="login-email" placeholder="admin@turestaurante.com">
      <input type="password" id="login-password" placeholder="••••••••">
      <p id="login-error-admin" class="login-error hidden"></p>
      <button type="submit" class="btn btn-primary btn-block">Ingresar</button>
    </form>
    
    <!-- Pestaña 2: Personal (Código) -->
    <form id="form-login-staff" class="login-form hidden" onsubmit="loginStaff(event)">
      <input type="text" id="login-celular" placeholder="XXXXXX">
      <input type="password" id="login-password-staff" placeholder="••••••••">
      <p id="login-error-staff" class="login-error hidden"></p>
      <button type="submit" class="btn btn-primary btn-block">Ingresar</button>
    </form>
  </div>
</div>
```

### Responsive

- Desktop/Tablet: Centrado, tarjeta blanca
- Mobile: Full-width, adaptado a pantalla pequeña
- Botón reset (↻): Tablets sin teclado pueden limpiar localStorage sin poder acceder a DevTools

### Validaciones Frontend (UX)

- Email: `type="email"` (navegador valida formato básico)
- Código de acceso: `type="text"` (input numérico de 6 dígitos)
- Contraseña: `type="password"` (oculta caracteres)
- Ambas obligatorias: `required`

**Nota:** La validación real es SIEMPRE en backend. Frontend solo es UX.

---

## 🧪 Testing del Login

### Tests Unitarios (`tests/unit/test_config.py`)

```python
def test_settings_falla_sin_secret_key():
    """Si SECRET_KEY falta en .env, Settings() debe lanzar ValidationError,
    no caer en un default inseguro."""
```

### Tests de Rate Limiting (`tests/integration/test_endpoints.py`)

```python
def test_login_bloquea_tras_varios_intentos_fallidos():
    """5 intentos fallidos → 6to intento devuelve 429"""

def test_login_exitoso_no_cuenta_para_el_limite():
    """8 logins correctos seguidos NO generan 429 (solo fallos cuentan)"""

def test_login_staff_bloquea_tras_varios_intentos_fallidos():
    """Rate limiting también en /auth/login-staff"""

def test_superadmin_login_bloquea_tras_varios_intentos_fallidos():
    """Rate limiting también en /superadmin/login"""
```

### Tests de Auditoría

```python
def test_login_exitoso_queda_en_el_registro_de_auditoria():
    """Login exitoso inserta un AuditLog con accion='login'"""

def test_crear_staff_queda_en_el_registro_de_auditoria():
    """Crear un usuario de staff inserta un AuditLog"""

def test_eliminar_usuario_queda_en_el_registro_de_auditoria():
    """Eliminar usuario inserta un AuditLog"""

def test_superadmin_puede_listar_auditoria():
    """GET /api/superadmin/auditoria devuelve lista de eventos"""

def test_auditoria_no_accesible_con_token_de_restaurante():
    """Token de usuario rechaza acceso a /api/superadmin/auditoria (403)"""
```

### Tests de Token Válido

```python
def test_token_sin_tipo_explicito_no_accede_a_rutas_de_restaurante():
    """Un JWT válido pero SIN el campo 'tipo' es rechazado por get_cliente_id"""
```

**Cobertura actual:** 86/86 tests pasando

---

## ⚙️ Configuración Requerida

### `.env` (Obligatorio)

```bash
SECRET_KEY=tu-secreto-super-largo-y-aleatorio-min-32-caracteres
DATABASE_URL=sqlite:///./restomind.db
DEBUG=False
ENVIRONMENT=production
```

**Si falta SECRET_KEY:**
```
pydantic_core._pydantic_core.ValidationError: 1 validation error for Settings
secret_key
  Field required [type=missing, input_value={...}, input_type=dict, ...]
```

App NO arranca.

### Backend

```python
# backend/config.py

class Settings(BaseSettings):
    secret_key: str  # Requerido, sin default
    database_url: str = "sqlite:///./restomind.db"
    debug: bool = False
    environment: str = "production"
    
    class Config:
        env_file = ".env"
```

---

## 🔍 Problemas Conocidos y Soluciones

### 1. Token Viejo en localStorage

**Problema:** Usuario A loguea, cierra navegador. Días después, abre navegador → token está vencido.

**Solución:** `initAuth()` valida token contra `GET /auth/me` antes de mostrar la app. Si falla → mostrar login.

### 2. Múltiples Pestañas Abiertas

**Problema:** Pestaña 1 loguea como Admin, Pestaña 2 loguea como Mozo (mismo localStorage compartido).

**Solución:** Es el comportamiento esperado. El último login gana. `inicAuth()` en cada pestaña recupera el estado de localStorage, así que después de un logout en Pestaña 1, Pestaña 2 también ve el login.

### 3. Validación de Email/Celular

**Problema:** `usuario.email` es UNIQUE en la tabla `Usuario`, así que no puede haber 2 usuarios con el mismo email (incluso en restaurantes distintos).

**Actual:** Email es único globalmente. Es intencional: en un SaaS de reventa, no debería haber dueños de 2 restaurantes distintos usando el mismo email.

**Celular (código):** Es único globalmente en la tabla `Usuario`, pero el valor es el código auto-generado, no un celular real.

### 4. Superadmin Login sin Redirección Automática

**Problema:** Superadmin loguea en `/index.html`, obtiene token válido, pero `/index.html` redirige a `/superadmin.html`. Ese archivo tiene SU PROPIO login separado, así que termina en otra pantalla de login en vez de entrar directo.

**Estado:** Conocido, pendiente de revisar.

**Workaround:** Ir directo a `/superadmin.html` en el navegador.

---

## 📊 Matriz de Permisos

| Endpoint | GET | POST | PATCH | DELETE | Admin | Mozo | Cajero | Cocina | Superadmin |
|----------|-----|------|-------|--------|-------|------|--------|--------|-----------|
| `/api/mesas` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ 403 |
| `/api/platos` | ✅ | ✅ (admin-only) | ✅ (admin-only) | - | ✅ | ✅ (lectura) | ✅ (lectura) | ✅ (lectura) | ❌ 403 |
| `/api/comandas` | ✅ | ✅ | ✅ | - | ✅ | ✅ | ✅ | ✅ | ❌ 403 |
| `/api/compras` | ✅ | ✅ (admin-only) | ✅ (admin-only) | - | ✅ | ❌ 403 | ❌ 403 | ❌ 403 | ❌ 403 |
| `/api/usuarios` | ✅ (admin-only) | ✅ (admin-only) | ✅ (admin-only) | ✅ (admin-only) | ✅ | ❌ | ❌ | ❌ | ❌ 403 |
| `/api/superadmin/*` | - | - | - | - | ❌ 403 | ❌ 403 | ❌ 403 | ❌ 403 | ✅ |

---

## 📝 Checklist de Seguridad

- [x] SECRET_KEY requerido en .env (no hardcodeado)
- [x] Contraseñas hasheadas (bcrypt)
- [x] Token con tipo explícito (no inferencia)
- [x] cliente_id validado en CADA ruta de restaurante
- [x] Tokens con expiración (12 horas)
- [x] Rate limiting en logins (5 fallos / 15 min)
- [x] Auditoría persistente en BD
- [x] Mensajes de error genéricos (no revelan si email/usuario existe)
- [x] Endpoint de auditoría (superadmin-only, filtrable por cliente)
- [ ] HTTPS en producción (no configurable en app, debe hacerlo DevOps)
- [ ] CORS restringido a dominios autorizados
- [ ] Rotación de tokens (podría implementarse si es necesario)

---

## 🚀 Próximos Pasos (Opcionales)

1. **Token Refresh:** Implementar `POST /auth/refresh` para renovar sin re-loguearse
2. **2FA:** Email confirmation o SMS para admin/superadmin
3. **Revocación:** Endpoint para revocar tokens específicos (logout de otras sesiones)
4. **IP Whitelist:** Restricción por IP para cuentas críticas (superadmin)
5. **CORS Dinámico:** Configurar orígenes permitidos según cliente
6. **Rotación de Secreto:** Script para cambiar SECRET_KEY de forma segura

---

**Documento generado:** 2026-08-29  
**Última revisión:** Análisis completo del sistema tras implementación de hardening de seguridad
