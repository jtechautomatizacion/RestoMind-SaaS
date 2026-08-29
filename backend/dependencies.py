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
