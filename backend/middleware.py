"""
Cabeceras de seguridad HTTP aplicadas a toda respuesta.

No reemplazan HTTPS (eso lo resuelve el proxy delante de esta app — ver
PRODUCTION_READINESS.md), pero cierran clases de ataque baratas de prevenir en
el código y que un escáner de seguridad revisa primero.
"""

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from backend.config import settings

# CSP de la app web (Flutter) y de la API. Es la estricta, al estilo Sac-Geo:
#   · script-src sin 'unsafe-inline' ni dominios ajenos. 'wasm-unsafe-eval' es
#     lo único extra y es obligatorio: CanvasKit, el motor de dibujo de Flutter,
#     es WebAssembly. La app se compila con --csp para que el JS de Dart no use
#     eval ni new Function.
#   · connect-src 'self': la app no habla con ningún otro origen. Fuentes y
#     CanvasKit van empaquetados (--no-web-resources-cdn), no se bajan de Google.
#   · style-src 'unsafe-inline': Flutter posiciona sus capas con estilos en
#     línea. Un estilo no ejecuta código; el riesgo es mínimo frente a script-src.
CSP_APP = (
    "default-src 'self'; "
    "script-src 'self' 'wasm-unsafe-eval'; "
    "style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data: blob:; "
    "font-src 'self' data:; "
    "connect-src 'self'; "
    "worker-src 'self' blob:; "
    "manifest-src 'self'; "
    "object-src 'none'; "
    "frame-ancestors 'none'; "
    "form-action 'self'; "
    "base-uri 'self'"
)

# CSP de las páginas HTML viejas de /static/ (el panel del superadmin y la
# página de descarga del APK). Usan onclick="..." en línea, así que no pueden
# cerrar 'unsafe-inline' sin reescribirse. Siguen sin poder cargar nada ajeno.
CSP_HTML_VIEJO = (
    "default-src 'self'; "
    "script-src 'self' 'unsafe-inline'; "
    "style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data: blob:; "
    "connect-src 'self'; "
    "object-src 'none'; "
    "frame-ancestors 'none'; "
    "base-uri 'self'"
)

_RUTAS_API = ("/api/", "/health", "/docs", "/redoc", "/openapi.json")


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)
        ruta = request.url.path

        # El navegador no "adivina" el tipo de un archivo (un .txt subido como
        # imagen no se ejecuta como script).
        response.headers["X-Content-Type-Options"] = "nosniff"
        # Nadie mete esta app en un <iframe> de otro sitio (clickjacking: un
        # botón invisible encima de "Cobrar").
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Content-Security-Policy"] = (
            CSP_HTML_VIEJO if ruta.startswith("/static/") else CSP_APP
        )

        # Los archivos de la app (Flutter en "/", HTML viejo en /static/) se
        # REVALIDAN en cada uso. Sin Cache-Control el navegador aplica su caché
        # heurística y un aparato puede seguir corriendo código de antes de un
        # arreglo sin que ni un F5 lo note. "no-cache" sí guarda la copia: con
        # el ETag, revalidar cuesta un 304 cuando no cambió nada.
        if not ruta.startswith(_RUTAS_API):
            response.headers["Cache-Control"] = "no-cache"

        # HSTS solo si ya se sirve por HTTPS (lo confirma el proxy con
        # X-Forwarded-Proto). Prometer "solo HTTPS por un año" sin certificado
        # sería mentirle al navegador.
        proto = request.headers.get("x-forwarded-proto", request.url.scheme)
        if settings.environment == "production" and proto == "https":
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"

        return response
