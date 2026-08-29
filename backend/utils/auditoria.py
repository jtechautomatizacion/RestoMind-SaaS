"""
Registro de auditoría: quién hizo qué, sobre qué entidad, y cuándo.

Complementa (no reemplaza) los logs de texto que ya existen para login
(backend/routes/auth.py) — este registro vive en la base de datos, en su
propia tabla, para poder consultarlo con una query en vez de grepear un
archivo, y para que sobreviva a la rotación o pérdida de esos logs. Es lo
primero que pide una auditoría formal: "¿quién eliminó esta cuenta y
cuándo?".
"""

from typing import Optional

from sqlalchemy.orm import Session

from backend.models import AuditLog


def registrar_evento(
    db: Session,
    actor: str,
    accion: str,
    entidad: str,
    entidad_id: str,
    cliente_id: Optional[str] = None,
    detalle: Optional[str] = None,
) -> None:
    """Nunca debe tumbar la operación que audita: si guardar el registro
    falla por lo que sea, se ignora en vez de propagar el error."""
    try:
        db.add(AuditLog(
            actor=actor,
            accion=accion,
            entidad=entidad,
            entidad_id=str(entidad_id),
            cliente_id=cliente_id,
            detalle=detalle,
        ))
        db.commit()
    except Exception:
        db.rollback()
