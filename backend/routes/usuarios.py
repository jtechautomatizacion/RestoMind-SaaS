"""
Personal del restaurante — mozos, cajeros, cocineros, otros admins.

Vive dentro del tenant (a diferencia de /superadmin/*): cada Usuario que
se crea acá pertenece al cliente_id de quien lo crea, y solo un admin de
ESE restaurante puede administrarlo. Reemplaza (para quien lo adopte) al
selector de rol por dispositivo: en vez de que cualquiera toque un botón
"soy Mozo" en un celular compartido, cada persona tiene su login real y
su rol viene del JWT — ya no se puede falsear.
"""

import secrets
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
    UsuarioUpdateMeRequest,
    StaffCreateRequest,
)
from backend.utils.auditoria import registrar_evento
from backend.utils.security import validar_admin
from backend.utils.roles import serializar_roles

router = APIRouter()

_ROL_LABELS = {"mozo": "Mozo", "cajero": "Cajero", "jefe_cocina": "Cocina", "admin": "Administrador"}


def _generar_codigo_acceso(db: Session) -> str:
    """Código numérico de 6 dígitos, único en todo el sistema.

    Reemplaza al celular real como identificador de login del personal: el
    admin normalmente no tiene un número distinto para cada empleado (ni
    quiere repartir el suyo propio), y pedir un dato personal real que ni
    siquiera hace falta verificar es innecesario — 1 millón de
    combinaciones hace la colisión aleatoria despreciable, y aun así se
    revalida contra la BD antes de usarlo.
    """
    for _ in range(20):
        codigo = f"{secrets.randbelow(1_000_000):06d}"
        if not db.query(Usuario).filter(Usuario.celular == codigo).first():
            return codigo
    raise HTTPException(status_code=500, detail="No se pudo generar un código de acceso único, intenta de nuevo")


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

    # Un admin no puede crear otro admin: cada restaurante tiene exactamente
    # un admin, dado de alta por el superadmin al crear el cliente. Permitir
    # esto abriría una forma de que un admin se cubra las espaldas creando
    # un "repuesto" con el mismo nivel de acceso sin que el dueño lo sepa.
    if payload.rol == "admin":
        raise HTTPException(status_code=403, detail="Un administrador no puede crear otra cuenta de administrador")

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

    registrar_evento(
        db, actor=usuario_actual, accion="crear_usuario", entidad="usuario",
        entidad_id=usuario.id, cliente_id=cliente_id, detalle=f"rol: {usuario.rol}",
    )

    return usuario


@router.post("/usuarios/staff", response_model=UsuarioResponse, status_code=201)
def crear_staff(
    payload: StaffCreateRequest,
    db: Session = Depends(get_db),
    cliente_id: str = Depends(get_cliente_id),
    usuario_actual: str = Depends(get_usuario_actual),
):
    """Crear mozo, cajero o cocinero. El código de acceso lo genera el
    backend (ver _generar_codigo_acceso) — el admin no lo escribe."""
    validar_admin(db, usuario_actual, cliente_id)

    codigo_acceso = _generar_codigo_acceso(db)

    usuario = Usuario(
        id=f"usr-{cliente_id}-{codigo_acceso}",
        cliente_id=cliente_id,
        nombre=payload.nombre,
        celular=codigo_acceso,
        email=None,  # Staff NO tiene email
        password_hash=hash_password(payload.password),
        rol=serializar_roles(payload.roles),
    )
    db.add(usuario)
    db.commit()
    db.refresh(usuario)

    registrar_evento(
        db, actor=usuario_actual, accion="crear_staff", entidad="usuario",
        entidad_id=usuario.id, cliente_id=cliente_id, detalle=f"roles: {usuario.rol}",
    )

    return usuario


# Endpoints /me DEBEN ir ANTES de /{usuario_id} para que FastAPI los
# matchee antes (en orden de definición, rutas parametrizadas capturan lo que quieran)
@router.get("/usuarios/me", response_model=UsuarioResponse)
def obtener_mi_perfil(
    db: Session = Depends(get_db),
    cliente_id: str = Depends(get_cliente_id),
    usuario_actual: str = Depends(get_usuario_actual),
):
    """Obtener datos de la cuenta actual del usuario. Funciona con email (admin) o celular (staff)."""
    usuario = db.query(Usuario).filter(
        Usuario.cliente_id == cliente_id,
        (Usuario.email == usuario_actual) | (Usuario.celular == usuario_actual)
    ).first()
    if not usuario:
        raise HTTPException(status_code=401, detail="Sesión inválida")

    return usuario


@router.patch("/usuarios/me")
def editar_mi_perfil(
    payload: UsuarioUpdateMeRequest,
    db: Session = Depends(get_db),
    cliente_id: str = Depends(get_cliente_id),
    usuario_actual: str = Depends(get_usuario_actual),
):
    """Editar solo el nombre. Email y rol NO se pueden cambiar."""
    usuario = db.query(Usuario).filter(
        Usuario.cliente_id == cliente_id,
        (Usuario.email == usuario_actual) | (Usuario.celular == usuario_actual)
    ).first()
    if not usuario:
        raise HTTPException(status_code=401, detail="Sesión inválida")

    if payload.nombre:
        usuario.nombre = payload.nombre.strip()

    db.commit()
    db.refresh(usuario)
    return usuario


@router.patch("/usuarios/me/password")
def cambiar_mi_password(
    payload: ChangePasswordRequest,
    db: Session = Depends(get_db),
    cliente_id: str = Depends(get_cliente_id),
    usuario_actual: str = Depends(get_usuario_actual),
):
    """Cambiar la propia contraseña del usuario (admin, mozo, etc.)."""
    usuario = db.query(Usuario).filter(
        Usuario.cliente_id == cliente_id,
        (Usuario.email == usuario_actual) | (Usuario.celular == usuario_actual)
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

    # Verificar si es el mismo usuario (por email o celular)
    es_uno_mismo = (usuario.email == usuario_actual) or (usuario.celular == usuario_actual)
    datos = payload.model_dump(exclude_unset=True)

    # Protecciones para que un admin no se auto-bloquee
    if es_uno_mismo and usuario.rol == "admin":
        if datos.get("rol") and datos["rol"] != "admin":
            raise HTTPException(status_code=400, detail="No puedes quitarte tu propio rol de administrador")
        if datos.get("estado") == "inactivo":
            raise HTTPException(status_code=400, detail="No puedes desactivar tu propia cuenta")

    # Tampoco puede ascender a otra cuenta a admin (mismo motivo que en la
    # creación: un solo admin por restaurante, dado de alta por el superadmin).
    if datos.get("rol") == "admin" and usuario.rol != "admin":
        raise HTTPException(status_code=403, detail="No puedes ascender esta cuenta a administrador")

    # No permitir cambiar email de admin ni celular de staff
    if "email" in datos and usuario.email:  # Es admin
        raise HTTPException(status_code=400, detail="No puedes cambiar tu email")
    if "celular" in datos and usuario.celular:  # Es staff
        raise HTTPException(status_code=400, detail="No puedes cambiar tu celular")

    # 'roles' (lista) es el campo real para editar los permisos de una
    # cuenta de personal — reemplaza el set completo de roles de esa
    # cuenta (no lo suma al anterior). No es una columna de Usuario, así
    # que se serializa a CSV en 'rol' y se saca de 'datos' antes del loop
    # genérico de abajo (setattr(usuario, 'roles', ...) fallaría).
    roles_nuevos = datos.pop("roles", None)
    if roles_nuevos is not None:
        if usuario.rol == "admin":
            raise HTTPException(status_code=400, detail="No se pueden asignar roles de personal a una cuenta de administrador")
        datos["rol"] = serializar_roles(roles_nuevos)

    for campo, valor in datos.items():
        setattr(usuario, campo, valor)

    db.commit()
    db.refresh(usuario)

    registrar_evento(
        db, actor=usuario_actual, accion="editar_usuario", entidad="usuario",
        entidad_id=usuario.id, cliente_id=cliente_id, detalle=str(datos),
    )

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

    registrar_evento(
        db, actor=usuario_actual, accion="resetear_password", entidad="usuario",
        entidad_id=usuario.id, cliente_id=cliente_id,
    )

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

    nombre_eliminado = usuario.nombre
    rol_eliminado = usuario.rol

    db.delete(usuario)
    db.commit()

    registrar_evento(
        db, actor=usuario_actual, accion="eliminar_usuario", entidad="usuario",
        entidad_id=usuario_id, cliente_id=cliente_id, detalle=f"{nombre_eliminado} ({rol_eliminado})",
    )
