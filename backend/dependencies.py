"""
Dependencias compartidas de FastAPI.

MVP sin login: el cliente_id se resuelve desde el header X-Cliente-Id.
Cuando se implemente autenticación (JWT), este archivo es el único punto
a modificar: get_cliente_id pasará a leer el token en vez del header.
"""

from typing import Optional
from fastapi import Header
from backend.config import settings


def get_cliente_id(x_cliente_id: Optional[str] = Header(default=None, alias="X-Cliente-Id")) -> str:
    return x_cliente_id or settings.default_cliente_id


def get_usuario_actual(x_usuario: Optional[str] = Header(default=None, alias="X-Usuario")) -> str:
    return x_usuario or "admin@demo.local"


def get_tz_offset(x_tz_offset: Optional[str] = Header(default=None, alias="X-TZ-Offset")) -> int:
    """
    Minutos a sumar a la hora local del restaurante para obtener UTC
    (el valor de Date.prototype.getTimezoneOffset() del navegador; Perú = 300).

    La BD guarda todos los timestamps en UTC. Sin este dato el backend no
    puede saber a qué día del restaurante pertenece una venta hecha de noche:
    una comanda cobrada el viernes 22:33 en Lima se guarda como sábado 03:33 UTC.
    Si el header falta o viene mal, se asume 0 (servidor en UTC).
    """
    try:
        offset = int(x_tz_offset)
    except (TypeError, ValueError):
        return 0
    # UTC-14 .. UTC+14; cualquier cosa fuera de ese rango es basura o un intento
    # de correr el rango de fechas a voluntad.
    return offset if -840 <= offset <= 840 else 0
