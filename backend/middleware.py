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
        #
        # img-src incluye "blob:" porque la vista previa de la foto de un
        # plato (frontend/js/admin.js) usa URL.createObjectURL() antes de
        # subir el archivo — sin "blob:" el navegador bloquea esa preview
        # (y cualquier otra que use el mismo mecanismo) aunque la subida en
        # sí funcione bien.
        #
        # Los dos hosts de Google son EXCLUSIVAMENTE para Firebase Cloud
        # Messaging (notificaciones push a cocina, ver
        # frontend/js/push-notifications.js y sw.js):
        #   - www.gstatic.com  → de ahí se sirve el SDK de Firebase.
        #   - *.googleapis.com → las llamadas que el SDK hace para registrar
        #     el dispositivo y recibir mensajes (fcm/firebaseinstallations).
        #
        # www.gstatic.com está en connect-src ADEMÁS de en script-src, y no
        # es un descuido: el Service Worker lo carga con importScripts(), y
        # Chrome valida esa carga contra connect-src, no contra script-src
        # (una particularidad real de cómo Chrome aplica CSP dentro de un
        # Service Worker — el mensaje de error en consola dice literalmente
        # "violates ... connect-src", aunque sea un .js). Con solo
        # script-src, el SDK cargaba bien en la página normal pero fallaba
        # siempre dentro del Service Worker — que es justo donde hace falta
        # para que el push llegue con la app minimizada.
        #
        # Se listan host por host a propósito, en vez de abrir "https:"
        # entero: si mañana se cuela un script de otro origen, sigue
        # bloqueado.
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' https://www.gstatic.com; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data: blob:; "
            "connect-src 'self' https://www.gstatic.com https://fcm.googleapis.com "
            "https://firebaseinstallations.googleapis.com "
            "https://firebaseremoteconfig.googleapis.com; "
            "worker-src 'self'; "
            "object-src 'none'; "
            "frame-ancestors 'none'; "
            "base-uri 'self'"
        )

        # frontend/sw.js dice servir HTML/CSS/JS "network-first: siempre la
        # versión más nueva cuando hay conexión" — pero StaticFiles no
        # mandaba ningún Cache-Control, así que el navegador aplicaba SU
        # PROPIA caché heurística (con solo Last-Modified/ETag, Chrome
        # cachea por un tramo de la antigüedad del archivo). El fetch()
        # que hace el Service Worker se resolvía contra esa copia sin
        # tocar la red — "network-first" se volvía en la práctica
        # "cache-first silencioso": una cuenta mozo podía seguir corriendo
        # JS de ANTES de un fix (ej. el que evita pedir endpoints
        # admin-only) sin que ni un F5 lo notara, porque nunca llegaba a
        # preguntarle al servidor.
        #
        # "no-cache" (pese al nombre) SÍ permite guardar la respuesta —
        # obliga a revalidarla contra el servidor en cada uso. Con el ETag
        # ya presente, esa revalidación es un 304 casi gratis cuando el
        # archivo no cambió, y trae el contenido nuevo de inmediato cuando
        # sí cambió. Solo aplica a /static/: la API ya es network-only
        # (sin cache en absoluto) por el Service Worker.
        if request.url.path.startswith("/static/"):
            response.headers["Cache-Control"] = "no-cache"

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
