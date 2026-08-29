"""
REGLA 3 (CLAUDE.md): validar rol antes de operaciones sensibles.
Único punto de verificación de "es admin" para no repetir la misma
consulta en cada archivo de rutas.
"""

from fastapi import HTTPException
from sqlalchemy.orm import Session
from backend.models import Usuario


def validar_admin(db: Session, usuario_email: str, cliente_id: str) -> None:
    """Lanza 403 si el usuario no existe o no es admin del cliente."""
    usuario = db.query(Usuario).filter(
        Usuario.email == usuario_email,
        Usuario.cliente_id == cliente_id,
    ).first()
    if not usuario or usuario.rol != "admin":
        raise HTTPException(status_code=403, detail="Esta acción requiere permisos de administrador")
