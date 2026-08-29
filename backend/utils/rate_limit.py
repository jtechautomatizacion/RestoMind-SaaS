"""
Rate limiting simple en memoria para los endpoints de login.

Solo cuenta intentos FALLIDOS, no cada request: en un restaurante real,
varios mozos/cajeros pueden loguearse casi al mismo tiempo desde el mismo
WiFi (misma IP pública) al empezar un turno — contar también los éxitos
bloquearía el turno entero por una coincidencia de horario. Lo que hay
que frenar es que alguien pruebe contraseñas a repetición.

Vive en memoria de un solo proceso — no alcanza si el día de mañana esto
corre en varios workers/servidores (ahí hace falta algo compartido como
Redis), pero cubre el caso real de esta app hoy: un único proceso uvicorn.
"""

import time
from collections import defaultdict
from typing import Dict, List

from fastapi import HTTPException, Request

MAX_INTENTOS_FALLIDOS = 5
VENTANA_SEGUNDOS = 15 * 60

_fallos: Dict[str, List[float]] = defaultdict(list)


def _ip_de(request: Request) -> str:
    return request.client.host if request.client else "desconocido"


def _limpiar(ip: str) -> List[float]:
    ahora = time.time()
    vigentes = [t for t in _fallos[ip] if ahora - t < VENTANA_SEGUNDOS]
    _fallos[ip] = vigentes
    return vigentes


def verificar_intentos_login(request: Request) -> None:
    """Llamar ANTES de validar credenciales. 429 si ya hay demasiados
    fallos recientes desde esta IP."""
    ip = _ip_de(request)
    if len(_limpiar(ip)) >= MAX_INTENTOS_FALLIDOS:
        raise HTTPException(
            status_code=429,
            detail="Demasiados intentos fallidos. Espera unos minutos e intenta de nuevo.",
        )


def registrar_login_fallido(request: Request) -> None:
    """Llamar cuando las credenciales resultan inválidas (no ante un 403
    de cuenta deshabilitada — eso no es indicio de fuerza bruta)."""
    _fallos[_ip_de(request)].append(time.time())


def limpiar_intentos_login(request: Request) -> None:
    """Llamar tras un login exitoso: no hace falta seguir arrastrando
    fallos viejos de esa IP."""
    _fallos.pop(_ip_de(request), None)
