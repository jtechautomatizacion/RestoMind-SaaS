"""
Dependencias compartidas de FastAPI.

Autenticación real vía JWT (Authorization: Bearer <token>). get_cliente_id
y get_usuario_actual son el único punto de la app que sabe de dónde sale
esa identidad — cada ruta que las usa (casi todas) queda protegida sin
que haya que tocar el archivo de esa ruta.
"""

from typing import Optional
from fastapi import Depends, Header, HTTPException
from backend.auth import decodificar_token


def _payload_del_token(authorization: Optional[str] = Header(default=None)) -> dict:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="No autenticado")

    token = authorization.removeprefix("Bearer ").strip()
    payload = decodificar_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Sesión inválida o expirada")

    return payload


def get_cliente_id(payload: dict = Depends(_payload_del_token)) -> str:
    return payload["cliente_id"]


def get_usuario_actual(payload: dict = Depends(_payload_del_token)) -> str:
    """Devuelve el email del usuario autenticado (el 'sub' del token)."""
    return payload["sub"]


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
