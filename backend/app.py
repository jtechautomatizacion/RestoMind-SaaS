from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from backend.config import settings
from backend.database import init_db, SessionLocal
from backend.middleware import SecurityHeadersMiddleware
from backend.seed import seed_if_empty, backfill_clientes_existentes
from backend.routes import platos, mesas, comandas, compras, dashboard, categorias, auth, superadmin, usuarios, facturas, caja, push, insumos, movimientos
from backend.migrate import migrate

# Ejecutar migración antes de init_db
migrate()

# Initialize database + seed de demo (idempotente)
init_db()
_seed_db = SessionLocal()
try:
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


# Health check endpoint
@app.get("/health")
async def health_check():
    return {"status": "ok", "version": "0.1.0"}


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


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        app,
        host=settings.host,
        port=settings.port,
    )
