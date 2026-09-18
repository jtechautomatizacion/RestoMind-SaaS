from datetime import datetime
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from backend.config import settings
from backend.database import init_db, SessionLocal
from backend.middleware import SecurityHeadersMiddleware
from backend.seed import seed_if_empty, backfill_clientes_existentes
from backend.routes import platos, mesas, comandas, compras, dashboard, categorias, auth, superadmin, usuarios, facturas, caja, push, insumos, movimientos, configuracion, ruc, app_version
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
#
# A los dominios del .env se les suman los orígenes de la app empaquetada.
# Capacitor NO sirve el frontend desde el dominio del backend: los archivos
# viajan dentro del APK y el WebView los expone en https://localhost. Sin
# estos orígenes, la app instalada recibe un bloqueo de CORS en CADA llamada
# —incluido el login— y en pantalla se ve como "no hay conexión", que manda
# a revisar el wifi en vez de la configuración.
#
# Van en el código y no en el .env a propósito: no dependen del despliegue
# (son siempre los mismos, los define Capacitor), y si dependieran del .env
# alcanzaría con olvidarlos en un servidor nuevo para que la app móvil
# quedara muerta ahí sin que nada más lo delate.
ORIGENES_APP_NATIVA = [
    "https://localhost",   # Android con androidScheme "https"
    "capacitor://localhost",  # iOS, si algún día se compila
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.cors_origins) + ORIGENES_APP_NATIVA,
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
def _hay_codigo_mas_nuevo_en_disco() -> bool:
    """
    ¿Hay algún .py del backend modificado DESPUÉS de que arrancó este
    proceso? Si lo hay, lo que está sirviendo no es lo que está en el disco.

    Es la contraparte accionable de `cargado_en`: ese campo obliga a mirar
    una fecha y decidir si "parece vieja"; este responde sí o no.

    En el VPS siempre da False —los archivos no cambian entre despliegues—
    así que no es un campo de desarrollo colado en producción: ahí es la
    confirmación de que el servicio corre exactamente el código desplegado,
    justo lo que se quiere saber después de un deploy.

    Nunca levanta: si no se puede leer el directorio (permisos, ruta rara),
    devuelve False. Un healthcheck que se cae por intentar diagnosticar es
    peor que no tener el diagnóstico.
    """
    try:
        raiz = Path(__file__).resolve().parent
        for archivo in raiz.rglob("*.py"):
            if "__pycache__" in archivo.parts:
                continue
            if datetime.utcfromtimestamp(archivo.stat().st_mtime) > _CODIGO_CARGADO_EN:
                return True
    except Exception:  # noqa: BLE001 — diagnosticar nunca puede tumbar /health
        return False
    return False


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
        # El campo que convierte "fijate si cargado_en te parece viejo" en
        # una respuesta. Comparar a ojo no alcanzó: esto volvió a pasar, y
        # el síntoma fue un 422 al crear una cuenta con un rol nuevo —
        # nada que sugiriera "el servidor no tomó tus cambios".
        "codigo_desactualizado": _hay_codigo_mas_nuevo_en_disco(),
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
app.include_router(app_version.router, prefix="/api", tags=["Version de la app"])


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        app,
        host=settings.host,
        port=settings.port,
    )
