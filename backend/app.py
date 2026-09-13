from datetime import datetime

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from backend.config import settings
from backend.database import init_db, SessionLocal
from backend.middleware import SecurityHeadersMiddleware
from backend.seed import seed_if_empty, backfill_clientes_existentes
from backend.routes import platos, mesas, comandas, compras, dashboard, categorias, auth, superadmin, usuarios, facturas, caja, push, insumos, movimientos, configuracion, ruc
from backend.migrate import migrate

# Ejecutar migración antes de init_db
migrate()

# Initialize database + seed de demo (idempotente)
init_db()
_seed_db = SessionLocal()
try:
    # Solo fuera de producción: seed_if_empty crea un restaurante y un
    # admin de PRUEBA con contraseña "admin123" — pública, está en este
    # mismo archivo. En un VPS recién levantado, antes de que corra
    # backend/scripts/crear_cliente.py, esa sería la única cuenta del
    # sistema: cualquiera que conozca este repo (es público en GitHub)
    # podría loguearse como admin. backfill_clientes_existentes es otra
    # cosa — repara datos de restaurantes REALES que ya existen — y sí
    # tiene que correr siempre, en cualquier entorno.
    if settings.environment != "production":
        seed_if_empty(_seed_db)
    backfill_clientes_existentes(_seed_db)
finally:
    _seed_db.close()

# Create FastAPI app
app = FastAPI(
    title="RestoMind API",
    description="Sistema de comandas y control para restaurantes",
    version="0.1.0",
    debug=settings.debug
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Cabeceras de seguridad (CSP, X-Frame-Options, etc.) en toda respuesta.
app.add_middleware(SecurityHeadersMiddleware)

# Mount static files (frontend)
app.mount("/static", StaticFiles(directory="frontend"), name="static")


# Momento en que ESTE proceso cargó el código. No es "hace cuánto está
# arriba el servidor": con --reload, cada recarga levanta un worker nuevo y
# este valor se renueva. Si no se renueva, la recarga NO ocurrió.
_CODIGO_CARGADO_EN = datetime.utcnow()


# Health check endpoint
@app.get("/health")
async def health_check():
    """
    Además de "estoy vivo", responde QUÉ CÓDIGO está corriendo.

    Existe por un problema real que costó días: uvicorn con --reload dejó de
    recargar (el vigilante de archivos murió, algo habitual en Windows tras
    suspender el equipo) y el servidor siguió sirviendo código de 4 días
    antes, en silencio. Desde afuera todo parecía normal: /health decía
    "ok", el login andaba, las pantallas cargaban — solo faltaban las rutas
    nuevas, que respondían 404 sin ninguna pista de por qué.

    Con estos dos campos, una sola consulta lo delata:
        curl -s localhost:8000/health

    - cargado_en muy viejo -> el proceso no tomó tus cambios; reinícialo.
    - rutas no cambió tras agregar un endpoint -> lo mismo.

    Es información inocua (no dice versiones de librerías ni rutas del
    disco), así que no hace falta autenticarla — y tiene que ser pública
    justamente para que el healthcheck del contenedor pueda consultarla.
    """
    return {
        "status": "ok",
        "version": "0.1.0",
        "cargado_en": _CODIGO_CARGADO_EN.isoformat() + "Z",
        # Se cuenta sobre el esquema OpenAPI y NO sobre app.routes: esta
        # versión de FastAPI deja los routers incluidos como objetos
        # `_IncludedRouter` sin aplanar, así que app.routes devolvía 24
        # (17 routers + las rutas propias) en vez de los ~60 endpoints
        # reales — un número que parecía informativo y no lo era.
        # app.openapi() arma el esquema una sola vez y lo cachea, así que
        # solo la primera consulta paga ese costo.
        "rutas": len(app.openapi().get("paths", {})),
    }


# Root endpoint — redirige a la app
@app.get("/")
async def root():
    return RedirectResponse(url="/static/index.html")


# Routers
app.include_router(auth.router, prefix="/api", tags=["Autenticación"])
app.include_router(superadmin.router, prefix="/api", tags=["Superadmin"])
app.include_router(platos.router, prefix="/api", tags=["Platos"])
app.include_router(mesas.router, prefix="/api", tags=["Mesas"])
app.include_router(comandas.router, prefix="/api", tags=["Comandas"])
app.include_router(compras.router, prefix="/api", tags=["Compras"])
app.include_router(insumos.router, prefix="/api", tags=["Inventario"])
app.include_router(movimientos.router, prefix="/api", tags=["Inventario"])
app.include_router(dashboard.router, prefix="/api", tags=["Dashboard"])
app.include_router(categorias.router, prefix="/api", tags=["Categorías"])
app.include_router(usuarios.router, prefix="/api", tags=["Personal"])
app.include_router(facturas.router, prefix="/api", tags=["Facturación SUNAT"])
app.include_router(caja.router, prefix="/api", tags=["Caja"])
app.include_router(push.router, prefix="/api", tags=["Notificaciones Push"])
app.include_router(configuracion.router, prefix="/api", tags=["Configuración"])
app.include_router(ruc.router, prefix="/api", tags=["Consulta RUC"])


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        app,
        host=settings.host,
        port=settings.port,
    )
