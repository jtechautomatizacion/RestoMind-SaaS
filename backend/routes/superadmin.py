"""
Panel del revendedor: ver todos los restaurantes dados de alta, crear uno
nuevo desde el navegador (sin tocar la consola), suspenderlo si no paga,
resetear la contraseña de su admin si se traba.

Nada de esto es visible ni alcanzable por un restaurante cliente — vive
bajo /api/superadmin/*, con su propio login y su propio tipo de token
(ver backend/dependencies.py: get_superadmin_email exige tipo=='superadmin',
así que un token de restaurante no puede usarse acá aunque sea válido).
"""

from datetime import datetime
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.auth import crear_token_superadmin, hash_password, verificar_password
from backend.database import get_db
from backend.dependencies import get_superadmin_email
from backend.models import Cliente, Comanda, Mesa, Plato, SuperAdmin, Usuario
from backend.schemas import (
    ClienteConStats,
    ClienteCreateRequest,
    EstadoUpdate,
    ResetPasswordRequest,
    SuperAdminLoginRequest,
    SuperAdminLoginResponse,
    SuperAdminMe,
)

router = APIRouter()


@router.post("/superadmin/login", response_model=SuperAdminLoginResponse)
def login_superadmin(payload: SuperAdminLoginRequest, db: Session = Depends(get_db)):
    admin = db.query(SuperAdmin).filter(SuperAdmin.email == payload.email.strip().lower()).first()

    # Mismo mensaje para "no existe" y "contraseña incorrecta" — no dar
    # pistas de qué emails de superadmin existen.
    if not admin or not verificar_password(payload.password, admin.password_hash):
        raise HTTPException(status_code=401, detail="Email o contraseña incorrectos")

    token = crear_token_superadmin(admin.email)
    return SuperAdminLoginResponse(access_token=token, nombre=admin.nombre, email=admin.email)


@router.get("/superadmin/me", response_model=SuperAdminMe)
def me_superadmin(
    db: Session = Depends(get_db),
    superadmin_email: str = Depends(get_superadmin_email),
):
    """Para validar un token guardado al recargar la página, sin volver a pedir contraseña."""
    admin = db.query(SuperAdmin).filter(SuperAdmin.email == superadmin_email).first()
    if not admin:
        raise HTTPException(status_code=401, detail="Sesión inválida")
    return SuperAdminMe(nombre=admin.nombre, email=admin.email)


@router.get("/superadmin/clientes", response_model=List[ClienteConStats])
def listar_clientes(
    db: Session = Depends(get_db),
    _superadmin: str = Depends(get_superadmin_email),
):
    inicio_mes = datetime.utcnow().replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    resultado = []
    for cliente in db.query(Cliente).order_by(Cliente.creado_en.desc()).all():
        ventas_mes = (
            db.query(func.coalesce(func.sum(Comanda.total_cuenta), 0.0))
            .filter(
                Comanda.cliente_id == cliente.id,
                Comanda.estado == "cobrado",
                Comanda.actualizado_en >= inicio_mes,
            )
            .scalar()
        )
        resultado.append(ClienteConStats(
            id=cliente.id,
            nombre=cliente.nombre,
            email=cliente.email,
            telefono=cliente.telefono,
            pais=cliente.pais,
            estado=cliente.estado,
            creado_en=cliente.creado_en,
            num_usuarios=db.query(Usuario).filter(Usuario.cliente_id == cliente.id).count(),
            num_platos=db.query(Plato).filter(Plato.cliente_id == cliente.id).count(),
            num_mesas=db.query(Mesa).filter(Mesa.cliente_id == cliente.id).count(),
            ventas_mes_actual=round(ventas_mes, 2),
        ))
    return resultado


def _slug(texto: str) -> str:
    import re
    import unicodedata
    # Sin esto, "Pollería" se corta en el acento a mitad de palabra
    # ("poller-a-...") en vez de dar "polleria-..." — normalize + encode
    # ascii descompone "í" en "i" + acento combinante y descarta el acento.
    sin_tildes = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode("ascii")
    limpio = re.sub(r"[^a-z0-9]+", "-", sin_tildes.lower()).strip("-")
    return limpio or "restaurante"


@router.post("/superadmin/clientes", response_model=ClienteConStats, status_code=201)
def crear_cliente(
    payload: ClienteCreateRequest,
    db: Session = Depends(get_db),
    _superadmin: str = Depends(get_superadmin_email),
):
    cliente_id = payload.cliente_id or _slug(payload.nombre)

    if db.query(Cliente).filter(Cliente.id == cliente_id).first():
        raise HTTPException(status_code=400, detail=f"Ya existe un restaurante con id '{cliente_id}'")

    admin_email = payload.admin_email.strip().lower()
    if db.query(Usuario).filter(Usuario.email == admin_email).first():
        raise HTTPException(status_code=400, detail=f"Ya existe un usuario con el email '{admin_email}'")

    cliente = Cliente(
        id=cliente_id,
        nombre=payload.nombre,
        email=payload.email,
        telefono=payload.telefono,
        pais=payload.pais,
        moneda=payload.moneda,
    )
    db.add(cliente)

    db.add(Usuario(
        id=f"usr-admin-{cliente_id}",
        cliente_id=cliente_id,
        nombre=payload.admin_nombre,
        email=admin_email,
        password_hash=hash_password(payload.admin_password),
        rol="admin",
    ))

    for numero in range(1, payload.num_mesas + 1):
        db.add(Mesa(cliente_id=cliente_id, numero=numero, capacidad=4))

    db.commit()

    return ClienteConStats(
        id=cliente.id, nombre=cliente.nombre, email=cliente.email, telefono=cliente.telefono,
        pais=cliente.pais, estado=cliente.estado, creado_en=cliente.creado_en,
        num_usuarios=1, num_platos=0, num_mesas=payload.num_mesas, ventas_mes_actual=0.0,
    )


@router.patch("/superadmin/clientes/{cliente_id}/estado")
def cambiar_estado_cliente(
    cliente_id: str,
    payload: EstadoUpdate,
    db: Session = Depends(get_db),
    _superadmin: str = Depends(get_superadmin_email),
):
    if payload.estado not in ("activo", "inactivo", "suspendido"):
        raise HTTPException(status_code=400, detail="Estado inválido. Use: activo, inactivo o suspendido")

    cliente = db.query(Cliente).filter(Cliente.id == cliente_id).first()
    if not cliente:
        raise HTTPException(status_code=404, detail="Restaurante no encontrado")

    # Un cliente no-'activo' se corta en seco en el próximo login (ver
    # backend/routes/auth.py) aunque sus tokens ya emitidos sigan siendo
    # válidos hasta que expiren (12h) — no hay revocación instantánea de
    # tokens todavía, solo bloqueo de logins nuevos.
    cliente.estado = payload.estado
    db.commit()
    return {"id": cliente.id, "estado": cliente.estado}


@router.patch("/superadmin/clientes/{cliente_id}/reset-password")
def resetear_password_admin(
    cliente_id: str,
    payload: ResetPasswordRequest,
    db: Session = Depends(get_db),
    _superadmin: str = Depends(get_superadmin_email),
):
    admin = db.query(Usuario).filter(Usuario.cliente_id == cliente_id, Usuario.rol == "admin").first()
    if not admin:
        raise HTTPException(status_code=404, detail="Este restaurante no tiene un usuario admin")

    admin.password_hash = hash_password(payload.nueva_password)
    db.commit()
    return {"email": admin.email, "detail": "Contraseña actualizada"}
