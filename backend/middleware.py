"""
Cabeceras de seguridad HTTP aplicadas a toda respuesta.

No reemplazan HTTPS (eso lo resuelve el proxy/hosting delante de esta app —
ver PRODUCTION_READINESS.md), pero cierran clases de ataque baratas de
prevenir en el código y que un escáner de seguridad revisa primero.
"""

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from backend.config import settings


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)

        # Un navegador no debe "adivinar" el tipo de un archivo servido
        # (evita que un .txt subido como imagen se ejecute como script).
        response.headers["X-Content-Type-Options"] = "nosniff"

        # Nadie puede meter esta app en un <iframe> de otro sitio
        # (clickjacking: un botón invisible superpuesto al de "Cobrar mesa").
        response.headers["X-Frame-Options"] = "DENY"

        # No filtrar la URL completa (que puede llevar tokens en query string
        # en algún endpoint futuro) al navegar a un link externo.
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

        # CSP deliberadamente permisiva en script/style: el frontend actual
        # usa atributos onclick="..." inline en todo el HTML (ver
        # frontend/index.html), así que bloquear 'unsafe-inline' rompería la
        # UI entera sin una reescritura completa a addEventListener. Lo que sí
        # se puede cerrar sin tocar el frontend: no cargar nada de terceros,
        # no permitir <object>/<embed>, y no permitir que esta app se enmarque.
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data:; "
            "connect-src 'self'; "
            "object-src 'none'; "
            "frame-ancestors 'none'; "
            "base-uri 'self'"
        )

        # HSTS solo tiene sentido si el sitio ya se sirve por HTTPS (lo
        # confirma el proxy que hace la terminación TLS, vía X-Forwarded-Proto
        # — ver PRODUCTION_READINESS.md). Mandarlo sobre HTTP plano no hace
        # nada dañino, pero prometer "solo HTTPS por un año" sin tener aún el
        # certificado configurado sería mentirle al navegador.
        proto = request.headers.get("x-forwarded-proto", request.url.scheme)
        if settings.environment == "production" and proto == "https":
            response.headers["Strict-Transport-Security"] = (
                "max-age=31536000; includeSubDomains"
            )

        return response
