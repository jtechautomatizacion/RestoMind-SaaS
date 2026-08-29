"""
Personal del restaurante — mozos, cajeros, cocineros, otros admins.

Vive dentro del tenant (a diferencia de /superadmin/*): cada Usuario que
se crea acá pertenece al cliente_id de quien lo crea, y solo un admin de
ESE restaurante puede administrarlo. Reemplaza (para quien lo adopte) al
selector de rol por dispositivo: en vez de que cualquiera toque un botón
"soy Mozo" en un celular compartido, cada persona tiene su login real y
su rol viene del JWT — ya no se puede falsear.
"""

from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.auth import hash_password, verificar_password
from backend.database import get_db
from backend.dependencies import get_cliente_id, get_usuario_actual
from backend.models import Usuario
from backend.schemas import (
    ChangePasswordRequest,
    ResetPasswordRequest,
    UsuarioCreate,
    UsuarioResponse,
    UsuarioUpdate,
)
from backend.utils.security import validar_admin

router = APIRouter()


@router.get("/usuarios", response_model=List[UsuarioResponse])
def listar_usuarios(
    db: Session = Depends(get_db),
    cliente_id: str = Depends(get_cliente_id),
    usuario_actual: str = Depends(get_usuario_actual),
):
    validar_admin(db, usuario_actual, cliente_id)
    return (
        db.query(Usuario)
        .filter(Usuario.cliente_id == cliente_id)
        .order_by(Usuario.rol, Usuario.nombre)
        .all()
    )


@router.post("/usuarios", response_model=UsuarioResponse, status_code=201)
def crear_usuario(
    payload: UsuarioCreate,
    db: Session = Depends(get_db),
    cliente_id: str = Depends(get_cliente_id),
    usuario_actual: str = Depends(get_usuario_actual),
):
    validar_admin(db, usuario_actual, cliente_id)

    email = payload.email.strip().lower()
    # Usuario.email es único en TODO el sistema (no solo por restaurante):
    # el login resuelve el restaurante a partir del email, así que dos
    # restaurantes no pueden compartir un mismo email de staff.
    if db.query(Usuario).filter(Usuario.email == email).first():
        raise HTTPException(status_code=400, detail=f"Ya existe un usuario con el email '{email}'")

    usuario = Usuario(
        id=f"usr-{cliente_id}-{email.split('@')[0]}",
        cliente_id=cliente_id,
        nombre=payload.nombre,
        email=email,
        password_hash=hash_password(payload.password),
        rol=payload.rol,
    )
    db.add(usuario)
    db.commit()
    db.refresh(usuario)
    return usuario


# Endpoints /me DEBEN ir ANTES de /{usuario_id} para que FastAPI los
# matchee antes (en orden de definición, rutas parametrizadas capturan lo que quieran)
@router.get("/usuarios/me", response_model=UsuarioResponse)
def obtener_mi_perfil(
    db: Session = Depends(get_db),
    cliente_id: str = Depends(get_cliente_id),
    usuario_actual: str = Depends(get_usuario_actual),
):
    """Obtener datos de la cuenta actual del usuario."""
    usuario = db.query(Usuario).filter(
        Usuario.email == usuario_actual,
        Usuario.cliente_id == cliente_id
    ).first()
    if not usuario:
        raise HTTPException(status_code=401, detail="Sesión inválida")

    return UsuarioResponse.from_orm(usuario)


@router.patch("/usuarios/me/password")
def cambiar_mi_password(
    payload: ChangePasswordRequest,
    db: Session = Depends(get_db),
    cliente_id: str = Depends(get_cliente_id),
    usuario_actual: str = Depends(get_usuario_actual),
):
    """Cambiar la propia contraseña del usuario (admin, mozo, etc.)."""
    usuario = db.query(Usuario).filter(
        Usuario.email == usuario_actual,
        Usuario.cliente_id == cliente_id
    ).first()
    if not usuario:
        raise HTTPException(status_code=401, detail="Sesión inválida")

    # Verificar contraseña actual
    if not verificar_password(payload.password_actual, usuario.password_hash):
        raise HTTPException(status_code=400, detail="Contraseña actual incorrecta")

    usuario.password_hash = hash_password(payload.nueva_password)
    db.commit()
    return {"detail": "Contraseña actualizada exitosamente"}


@router.patch("/usuarios/{usuario_id}", response_model=UsuarioResponse)
def editar_usuario(
    usuario_id: str,
    payload: UsuarioUpdate,
    db: Session = Depends(get_db),
    cliente_id: str = Depends(get_cliente_id),
    usuario_actual: str = Depends(get_usuario_actual),
):
    validar_admin(db, usuario_actual, cliente_id)

    usuario = db.query(Usuario).filter(Usuario.id == usuario_id, Usuario.cliente_id == cliente_id).first()
    if not usuario:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    es_uno_mismo = usuario.email == usuario_actual
    datos = payload.model_dump(exclude_unset=True)

    # Sin este chequeo, un admin solitario podría quitarse su propio rol de
    # admin o desactivarse a sí mismo y quedar sin forma de deshacerlo —
    # nadie más en el restaurante podría volver a darle acceso.
    if es_uno_mismo:
        if datos.get("rol") and datos["rol"] != "admin":
            raise HTTPException(status_code=400, detail="No puedes quitarte tu propio rol de administrador")
        if datos.get("estado") == "inactivo":
            raise HTTPException(status_code=400, detail="No puedes desactivar tu propia cuenta")

    for campo, valor in datos.items():
        setattr(usuario, campo, valor)

    db.commit()
    db.refresh(usuario)
    return usuario


@router.patch("/usuarios/{usuario_id}/password")
def cambiar_password_usuario(
    usuario_id: str,
    payload: ResetPasswordRequest,
    db: Session = Depends(get_db),
    cliente_id: str = Depends(get_cliente_id),
    usuario_actual: str = Depends(get_usuario_actual),
):
    validar_admin(db, usuario_actual, cliente_id)

    usuario = db.query(Usuario).filter(Usuario.id == usuario_id, Usuario.cliente_id == cliente_id).first()
    if not usuario:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    usuario.password_hash = hash_password(payload.nueva_password)
    db.commit()
    return {"email": usuario.email, "detail": "Contraseña actualizada"}


@router.delete("/usuarios/{usuario_id}", status_code=204)
def eliminar_usuario(
    usuario_id: str,
    db: Session = Depends(get_db),
    cliente_id: str = Depends(get_cliente_id),
    usuario_actual: str = Depends(get_usuario_actual),
):
    validar_admin(db, usuario_actual, cliente_id)

    usuario = db.query(Usuario).filter(Usuario.id == usuario_id, Usuario.cliente_id == cliente_id).first()
    if not usuario:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    # Como quien llama ya tuvo que pasar validar_admin() (es admin) y esta
    # misma regla impide borrarse a sí mismo, siempre queda al menos un
    # admin activo (quien ejecuta la acción) — no hace falta un chequeo
    # aparte de "no dejes el restaurante sin administradores".
    if usuario.email == usuario_actual:
        raise HTTPException(status_code=400, detail="No puedes eliminar tu propia cuenta")

    db.delete(usuario)
    db.commit()
