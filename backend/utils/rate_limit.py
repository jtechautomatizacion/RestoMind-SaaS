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


# ============ LÍMITE POR VOLUMEN (no por fallos) ============

# El de arriba cuenta fallos porque frena adivinación de contraseñas. Este
# cuenta TODOS los pedidos, porque frena algo distinto: la extracción masiva
# de un endpoint que funciona perfectamente. Es el caso de la consulta de
# RUC, donde detrás hay millones de nombres de personas naturales — ahí el
# abuso son miles de consultas EXITOSAS, no fallidas.
_accesos: Dict[str, List[float]] = defaultdict(list)


def limitar_por_volumen(request: Request, clave: str, maximo: int, ventana_segundos: int) -> None:
    """
    429 si esta IP superó `maximo` pedidos de `clave` en la ventana.

    La cuota se cuenta por IP y no por usuario a propósito: un token robado
    o un script con credenciales válidas es justo el escenario a contener, y
    ahí el usuario del token no es una barrera.
    """
    ahora = time.time()
    k = f"{clave}:{_ip_de(request)}"
    vigentes = [t for t in _accesos[k] if ahora - t < ventana_segundos]

    if len(vigentes) >= maximo:
        _accesos[k] = vigentes
        raise HTTPException(
            status_code=429,
            detail="Demasiadas consultas seguidas. Espera un momento.",
        )

    vigentes.append(ahora)
    _accesos[k] = vigentes


def limpiar_limites_por_volumen() -> None:
    """Solo para los tests: TestClient reporta siempre la misma IP falsa, así
    que sin resetear, un test gastaría la cuota del siguiente."""
    _accesos.clear()
