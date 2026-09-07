# RestoMind SaaS

Sistema web inteligente de comandas y control de operaciones para restaurantes, cebicherías y comercios gastronómicos locales.

## 🏗️ Stack

- **Backend:** Python 3.11+ con FastAPI
- **Base de Datos:** SQLite (multi-tenant via cliente_id)
- **Frontend:** HTML5 + CSS3 + JavaScript Vanilla (PWA)
- **Deployment:** Uvicorn (desarrollo), Gunicorn (producción)

## 🚀 Quick Start

### 1. Clonar y setup virtual environment

```bash
cd "d:\Cartera de proyectos\RestoMind-SaaS"
python -m venv venv
venv\Scripts\activate  # Windows
source venv/bin/activate  # macOS/Linux
```

### 2. Instalar dependencias

```bash
pip install -r requirements.txt
```

### 3. Configurar variables de entorno

```bash
cp .env.example .env
# Edita .env con tus valores
```

### 4. Ejecutar servidor backend

```bash
uvicorn backend.app:app --reload --reload-dir backend --reload-dir frontend --host 0.0.0.0 --port 8000
```

El backend está disponible en: `http://localhost:8000`

> **Los `--reload-dir` no son opcionales en Windows.** Sin ellos, el
> vigilante de `--reload` recorre TODO el proyecto en cada ciclo — unos
> 16.000 archivos, de los cuales ~12.000 están dentro de `.venv` y nunca
> cambian. Tras varias horas de trabajo eso agota los handles del sistema
> y el servidor muere con `WinError 1450` / `WinError 10055` ("recursos
> insuficientes"), que desde el navegador se ve como un simple "Sin
> conexión" sin explicar la causa. Acotándolo a `backend` y `frontend`,
> vigila solo el código que de verdad editás.
Documentación API (Swagger): `http://localhost:8000/docs`

### 5. Abrir frontend

```
Abre: http://localhost:8000/static/index.html
```

## 📁 Estructura del Proyecto

```
RestoMind-SaaS/
├── backend/
│   ├── app.py                 # FastAPI + routers + seed automático
│   ├── config.py               # Configuración (pydantic-settings)
│   ├── database.py             # Setup de SQLite/SQLAlchemy
│   ├── dependencies.py          # get_cliente_id, get_usuario_actual
│   ├── models.py                # Modelos SQLAlchemy (7 tablas)
│   ├── schemas.py                # Schemas Pydantic (validación)
│   ├── seed.py                   # Datos demo idempotentes
│   ├── services.py               # Reglas de negocio (estados, cobro)
│   └── routes/
│       ├── platos.py             # CU-01
│       ├── mesas.py              # Soporte + cobro de mesa
│       ├── comandas.py           # CU-02 + CU-03
│       ├── compras.py            # CU-04
│       └── dashboard.py          # CU-05
├── frontend/
│   ├── index.html              # PWA: bottom nav Mesas/Cocina/Dinero/Admin
│   ├── manifest.json            # PWA manifest (standalone mode)
│   ├── sw.js                    # Service Worker (offline)
│   ├── css/
│   │   └── style.css            # Design system mobile-first
│   └── js/
│       ├── app.js                # API client, navegación, toasts
│       ├── charts.js             # Gráficos SVG sin librerías
│       ├── mozo.js               # Mesas, pedido, cuenta, cobro
│       ├── cocina.js             # Monitor de cocina (polling)
│       ├── dashboard.js          # CU-05
│       └── admin.js              # Carta + Gastos
├── tests/
│   ├── conftest.py               # Fixtures (BD en memoria)
│   ├── integration/              # 26 tests de endpoints
│   └── unit/                     # Tests de modelos
├── requirements.txt
├── .env.example
├── README.md
├── claude.md                     # Especificación técnica
├── SETUP_CHECKLIST.md            # Estado real + bugs corregidos
└── .gitignore
```

## 📋 Documentación

- `claude.md` — especificación técnica: casos de uso, base de datos, endpoints.
- `SETUP_CHECKLIST.md` — estado real de la implementación, bugs encontrados y corregidos, decisiones de diseño.

## 📝 Testing

```bash
# Tests unitarios
pytest tests/unit -v

# Tests de integración
pytest tests/integration -v

# Con coverage
pytest --cov=backend tests/
```

## 🛠️ Tecnologías Clave

| Componente | Tech | Razón |
|---|---|---|
| Backend REST | FastAPI | Rápido, auto-docs, async-ready |
| BD | SQLite | Sin servidor, multi-tenant fácil |
| Validación | Pydantic | Type-safe, auto-validation |
| Frontend | Vanilla JS | Sin dependencias, PWA simple |
| PWA | manifest.json | Standalone mode, offline support |

## 📱 PWA Features

- Instalable en home screen (Android/iOS)
- Offline-ready (service worker)
- URL oculta en standalone mode
- Funciona sin internet después de caché inicial

## 🔐 Seguridad Multi-Tenant

- ✅ cliente_id obligatorio en TODAS las tablas
- ✅ Filtrado en backend (nunca del cliente)
- ✅ Validación de rol (admin, mozo, jefe_cocina)
- ✅ Contraseñas hasheadas (bcrypt, futuro)

## 📊 Primeros Pasos para Desarrollo

1. **Leer:** `claude.md` → Entiende requerimientos
2. **Setup:** `python -m venv venv && pip install -r requirements.txt`
3. **Run:** `uvicorn backend.app:app --reload`
4. **Code:** Crea modelos (database.py) → schemas (schemas.py) → routes (routes/*.py)
5. **Test:** `pytest tests/`

## 🚀 Deploy (Futuro)

```bash
gunicorn backend.app:app --bind 0.0.0.0:8000 --workers 4
```

---

**Última actualización:** 2026-08-28  
**Versión:** 0.1 (Preparación MVP)
