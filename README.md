# RestoMind SaaS

Sistema web inteligente de comandas y control de operaciones para restaurantes, cebicherías y comercios gastronómicos locales.

## 🏗️ Stack

- **Backend:** Python 3.11+ con FastAPI
- **Base de Datos:** SQLite (multi-tenant via cliente_id)
- **App web (PWA):** Flutter 3.47 (`flutter_app/`, compilada en `web/`)
- **APK de Android:** el frontend HTML/JS de `frontend/` empaquetado con Capacitor (pasa a Flutter en la próxima etapa, con la impresora Bluetooth)
- **Facturación SUNAT:** contenedor Docker `sunat-service`
- **Deployment:** nginx + uvicorn con systemd en el VPS

## 🚀 Quick Start

Todo en un comando, con la guía completa en [`docs/LOCAL.md`](docs/LOCAL.md):

```bash
npm run local          # Docker (SUNAT) + backend + app web en http://localhost:8000
npm run verificar      # TODAS las pruebas: Flutter, web/ al día, APK y pytest
npm run web            # recompila la app Flutter y la publica en web/
npm run local:parar
```

Requisitos una sola vez: Docker Desktop, `python -m venv .venv` (con punto: los
scripts lo buscan por esa ruta) + `pip install -r requirements.txt`,
`npm install`, Flutter 3.47.7 en `C:\src\flutter` y un `.env` copiado de
`.env.example`.

> **Sin `--reload` en Windows.** En esta máquina uvicorn detecta el cambio y el
> proceso nuevo nunca levanta (CLAUDE.md, "--reload NO RECARGA"). `npm run local`
> reinicia completo, que es un segundo y es confiable.

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
3. **Run:** `uvicorn backend.app:app --reload --reload-dir backend --reload-dir frontend` (los `--reload-dir` no son opcionales en Windows — ver la nota más arriba en este mismo README)
4. **Code:** Crea modelos (database.py) → schemas (schemas.py) → routes (routes/*.py)
5. **Test:** `pytest tests/`

## 🚀 Deploy (Futuro)

```bash
gunicorn backend.app:app --bind 0.0.0.0:8000 --workers 4
```

---

**Última actualización:** 2026-08-28  
**Versión:** 0.1 (Preparación MVP)
