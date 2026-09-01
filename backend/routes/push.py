"""
Registro de tokens push (Firebase Cloud Messaging). Cualquier usuario
autenticado puede registrar el suyo; solo reciben avisos los roles de
ROLES_NOTIFICABLES (ver utils/push_notifications.py), porque hoy el único
aviso implementado es "llegó una comanda nueva".
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.dependencies import get_cliente_id, get_usuario_actual
from backend.config import settings
from backend.schemas import PushTokenRequest, PushDesregistrarRequest, PushEstadoResponse
from backend.utils.push_notifications import (
    registrar_token,
    eliminar_token,
    tiene_token_registrado,
)

router = APIRouter()


@router.get("/push/vapid-key")
def obtener_vapid_key(cliente_id: str = Depends(get_cliente_id)):
    """Clave pública para que el frontend pida el token FCM. No es secreta
    (se sirve al navegador igual), pero se exige sesión válida como el resto
    de la API: un endpoint sin ninguna dependencia de auth es justo lo que
    una auditoría marca, aunque el dato concreto no sea sensible."""
    return {"vapid_key": settings.firebase_vapid_key}


@router.get("/push/estado", response_model=PushEstadoResponse)
def estado_push(
    db: Session = Depends(get_db),
    cliente_id: str = Depends(get_cliente_id),
    usuario: str = Depends(get_usuario_actual),
):
    """Fuente de verdad del switch de notificaciones: ¿este usuario tiene
    algún dispositivo registrado? El frontend la usa para no depender solo
    de localStorage, que puede estar limpio aunque la fila exista (ver
    frontend/js/push-notifications.js)."""
    return PushEstadoResponse(activo=tiene_token_registrado(db, cliente_id, usuario))


@router.post("/push/registrar", status_code=204)
def registrar_push_token(
    payload: PushTokenRequest,
    db: Session = Depends(get_db),
    cliente_id: str = Depends(get_cliente_id),
    usuario: str = Depends(get_usuario_actual),
):
    registrar_token(db, cliente_id, usuario, payload.token)


@router.post("/push/desregistrar", status_code=204)
def desregistrar_push_token(
    payload: PushDesregistrarRequest,
    db: Session = Depends(get_db),
    cliente_id: str = Depends(get_cliente_id),
    usuario: str = Depends(get_usuario_actual),
):
    """POST y no DELETE a propósito: esta baja lleva cuerpo, y un DELETE con
    body lo descartan varios proxies (y ni el TestClient de Starlette lo
    soporta). Sin `token` en el cuerpo, da de baja TODOS los dispositivos
    del usuario — el caso del navegador que perdió su localStorage y ya no
    sabe qué token borrar."""
    eliminar_token(db, cliente_id, usuario, payload.token)
