# ✅ SETUP CHECKLIST - RestoMind MVP

## 🎯 Estado Actual

**COMPLETADO:**
- ✅ Estructura de directorios (backend, frontend, tests, docs)
- ✅ Archivos de configuración (requirements.txt, .env.example, .gitignore)
- ✅ Documentación (README.md, claude.md)
- ✅ Modelos SQLAlchemy (7 tablas definidas)
- ✅ Schemas Pydantic (validación)
- ✅ App FastAPI base (config, database, main app)
- ✅ Stubs de rutas (platos, comandas, compras, mesas)
- ✅ Frontend PWA (HTML, CSS, JS base)
- ✅ Service Worker
- ✅ Tests base (conftest, ejemplos)

**PENDIENTE (Para Sonnet):**
- ❌ Implementar endpoints API (backend/routes/*.py)
- ❌ Lógica de negocio (crear comandas, calcular totales, etc.)
- ❌ Tests completos
- ❌ Seeding de datos iniciales
- ❌ Validación de cliente_id en endpoints
- ❌ UI refinements en frontend

---

## 🚀 PRÓXIMOS PASOS PARA SONNET

### Fase 1: Backend API Completa

**Tarea 1: Implementar CU-01 (Platos)**
```
archivo: backend/routes/platos.py
- GET /api/platos (listar activos)
- POST /api/platos (crear)
- PATCH /api/platos/{id} (editar)
- PATCH /api/platos/{id}/estado (activar/desactivar)
- Validar cliente_id en cada request
```

**Tarea 2: Implementar CU-02 + CU-03 (Comandas)**
```
archivo: backend/routes/comandas.py
- GET /api/comandas (listar)
- POST /api/comandas (crear + calcular total)
- GET /api/comandas/{id} (detalle con platos)
- PATCH /api/comandas/{id}/estado (cambiar estado)
- GET /api/monitor/cocina (solo cocina, ordenado ASC)
- Crear comanda_platos al guardar comanda
```

**Tarea 3: Implementar CU-04 (Compras)**
```
archivo: backend/routes/compras.py
- GET /api/compras
- POST /api/compras
- PATCH /api/compras/{id}
- PATCH /api/compras/{id}/estado
```

**Tarea 4: Implementar Mesas (Soporte)**
```
archivo: backend/routes/mesas.py
- GET /api/mesas
- POST /api/mesas
- PATCH /api/mesas/{id}/estado
```

### Fase 2: Tests

**Tarea 5: Tests Unitarios**
```
- test_models.py: Validar creación de objetos
- test_schemas.py: Validar validación Pydantic
```

**Tarea 6: Tests de Integración**
```
- test_endpoints.py: Validar todos los endpoints
- test_multitenant.py: Validar aislamiento cliente_id
```

---

## 📋 INSTRUCCIONES PARA EJECUTAR AHORA

### 1. Instalar dependencias

```bash
cd "d:\Cartera de proyectos\RestoMind-SaaS"
pip install -r requirements.txt
```

### 2. Crear archivo .env

```bash
cp .env.example .env
# .env ya tiene valores por defecto, no cambiar nada por ahora
```

### 3. Ejecutar servidor backend

```bash
uvicorn backend.app:app --reload --host 0.0.0.0 --port 8000
```

Debería ver:
```
INFO:     Uvicorn running on http://0.0.0.0:8000
```

### 4. Verificar salud

Abre en navegador:
```
http://localhost:8000/health
```

Debería responder:
```json
{"status": "ok", "version": "0.1.0"}
```

### 5. Abrir frontend PWA

```
http://localhost:8000/static/index.html
```

Verás 3 tabs vacíos (Mozo, Cocina, Admin) porque falta implementar endpoints.

### 6. Ver documentación API (Swagger)

```
http://localhost:8000/docs
```

Verás endpoints base, pero sin rutas implementadas.

### 7. Ejecutar tests (opcional por ahora)

```bash
pytest tests/ -v
```

---

## 📁 Archivos Críticos para Sonnet

**Leer PRIMERO:**
1. `claude.md` → Requerimientos técnicos completos
2. `README.md` → Setup del proyecto
3. `backend/models.py` → Estructura de datos
4. `backend/schemas.py` → Validaciones

**Editar DURANTE Implementación:**
1. `backend/routes/platos.py`
2. `backend/routes/comandas.py`
3. `backend/routes/compras.py`
4. `backend/routes/mesas.py`
5. `tests/integration/test_endpoints.py`

**NO Tocar (Ya Listo):**
- `backend/config.py` ✓
- `backend/database.py` ✓
- `backend/app.py` (solo descomentar routers cuando estén listos)
- `frontend/` (PWA lista, solo llenar datos de API)

---

## 🔑 Claves para Sonnet

### Patrón API (usar en todos los endpoints)

```python
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from backend.database import get_db

router = APIRouter()

@router.get("/platos")
async def get_platos(db: Session = Depends(get_db)):
    # TODO: Obtener cliente_id del request (por ahora hardcoded)
    cliente_id = "rest-001"
    
    platos = db.query(Plato).filter(
        Plato.cliente_id == cliente_id,
        Plato.estado == "activo"
    ).all()
    
    return platos
```

### Cliente ID (TODO - Solución Temporal)

Por ahora, hardcodear `cliente_id = "rest-001"` en todos los endpoints.
En Fase 2, extraerlo de JWT o sesión.

### Manejo de Errores

```python
if not objeto:
    raise HTTPException(status_code=404, detail="No encontrado")

if not autorizado:
    raise HTTPException(status_code=403, detail="Sin permisos")
```

---

## 🎯 MVP Definition (Para Sonnet)

El MVP está **LISTO** cuando:

- ✅ Todos los 4 CU tienen endpoints trabajando
- ✅ Todos los tests de integración pasan
- ✅ Frontend carga datos desde API
- ✅ Mozo puede crear comandas
- ✅ Cocina ve monitor actualizado
- ✅ Admin crea platos y registra gastos
- ✅ Cliente_id validado en CADA endpoint
- ✅ Sin errores en console (browser + servidor)

---

## 📞 Próximos Pasos Después del MVP

1. **Autenticación:** Login/logout con JWT
2. **Múltiples clientes:** Crear sistema de registro
3. **IA + Claude API:** Reportes inteligentes
4. **Pagos:** Integración Stripe/Culqi
5. **Mobile:** App nativa iOS/Android

---

**Última Actualización:** 2026-08-28  
**Estado:** ✅ Listo para Sonnet Empezar a Programar
