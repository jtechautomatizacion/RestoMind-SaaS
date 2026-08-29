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
uvicorn backend.app:app --reload --host 0.0.0.0 --port 8000
```

El backend está disponible en: `http://localhost:8000`
Documentación API (Swagger): `http://localhost:8000/docs`

### 5. Abrir frontend

```
Abre: http://localhost:8000/static/index.html
```

## 📁 Estructura del Proyecto

```
RestoMind-SaaS/
├── backend/
│   ├── __init__.py
│   ├── app.py                 # Aplicación FastAPI principal
│   ├── config.py              # Configuración
│   ├── database.py            # Setup de SQLite
│   ├── models.py              # Modelos SQLAlchemy (tablas BD)
│   ├── schemas.py             # Schemas Pydantic (validación)
│   ├── routes/
│   │   ├── __init__.py
│   │   ├── platos.py          # GET/POST /api/platos
│   │   ├── comandas.py        # GET/POST /api/comandas
│   │   ├── compras.py         # GET/POST /api/compras
│   │   └── mesas.py           # GET/POST /api/mesas
│   └── schemas/               # (alt: Pydantic schemas por ruta)
├── frontend/
│   ├── index.html             # App PWA principal
│   ├── manifest.json          # PWA manifest (standalone mode)
│   ├── sw.js                  # Service Worker (offline)
│   ├── css/
│   │   └── style.css
│   └── js/
│       ├── app.js             # Lógica principal
│       ├── mozo.js            # Interfaz del mozo
│       ├── cocina.js          # Monitor de cocina
│       └── admin.js           # Dashboard administrador
├── tests/
│   ├── integration/           # Tests de endpoints
│   └── unit/                  # Tests unitarios
├── docs/
│   ├── api-endpoints.md
│   └── database-schema.md
├── requirements.txt
├── .env.example
├── README.md
├── claude.md                  # Documentación para Claude (TÚ)
└── .gitignore
```

## 📋 Requerimientos (Documentación Técnica)

Ver `claude.md` para:
- Especificaciones técnicas completas
- Casos de uso y criterios de aceptación
- Estructura de base de datos
- API endpoints
- Estrategia de negocio

## 🔄 Flujo de Desarrollo (con Claude)

1. Claude lee `claude.md`
2. Claude crea/edita archivos según requerimientos
3. Tú ejecutas tests y validas
4. Iterate until MVP ready

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
