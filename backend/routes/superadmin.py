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

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.auth import crear_token_superadmin, hash_password, verificar_password
from backend.database import get_db
from backend.dependencies import get_superadmin_email
from backend.email import enviar_email_credenciales
from backend.models import AuditLog, Cliente, Comanda, Mesa, Plato, SuperAdmin, Usuario
from backend.schemas import (
    AuditLogResponse,
    ChangePasswordRequest,
    ClienteConStats,
    ClienteCreateRequest,
    ClienteUpdateRequest,
    EstadoUpdate,
    ResetPasswordRequest,
    SuperAdminLoginRequest,
    SuperAdminLoginResponse,
    SuperAdminMe,
    SuperAdminUpdateRequest,
)
from backend.utils.auditoria import registrar_evento
from backend.utils.rate_limit import limpiar_intentos_login, registrar_login_fallido, verificar_intentos_login

router = APIRouter()


@router.post("/superadmin/login", response_model=SuperAdminLoginResponse)
def login_superadmin(payload: SuperAdminLoginRequest, request: Request, db: Session = Depends(get_db)):
    verificar_intentos_login(request)

    admin = db.query(SuperAdmin).filter(SuperAdmin.email == payload.email.strip().lower()).first()

    # Mismo mensaje para "no existe" y "contraseña incorrecta" — no dar
    # pistas de qué emails de superadmin existen.
    if not admin or not verificar_password(payload.password, admin.password_hash):
        registrar_login_fallido(request)
        raise HTTPException(status_code=401, detail="Email o contraseña incorrectos")

    limpiar_intentos_login(request)
    registrar_evento(db, actor=admin.email, accion="login", entidad="superadmin", entidad_id=admin.id)
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


@router.get("/superadmin/clientes/{cliente_id}/admin")
def obtener_admin_cliente(
    cliente_id: str,
    db: Session = Depends(get_db),
    _superadmin: str = Depends(get_superadmin_email),
):
    """Obtener datos del admin de un cliente (para editar)."""
    admin = db.query(Usuario).filter(Usuario.cliente_id == cliente_id, Usuario.rol == "admin").first()
    if not admin:
        raise HTTPException(status_code=404, detail="Admin no encontrado")
    return {"nombre": admin.nombre, "email": admin.email}


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
            ruc=cliente.ruc,
            razon_social=cliente.razon_social,
            direccion=cliente.direccion,
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
    superadmin_email: str = Depends(get_superadmin_email),
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
        ruc=payload.ruc,
        razon_social=payload.razon_social,
        direccion=payload.direccion,
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

    registrar_evento(
        db, actor=superadmin_email, accion="crear_cliente", entidad="cliente",
        entidad_id=cliente_id, cliente_id=cliente_id, detalle=f"admin: {admin_email}",
    )

    # Enviar email de bienvenida con credenciales (no bloquea si falla)
    enviar_email_credenciales(
        destinatario=admin_email,
        nombre_admin=payload.admin_nombre,
        email_login=admin_email,
        password=payload.admin_password,
        nombre_restaurante=payload.nombre,
    )

    return ClienteConStats(
        id=cliente.id, nombre=cliente.nombre, email=cliente.email, telefono=cliente.telefono,
        ruc=cliente.ruc, razon_social=cliente.razon_social, direccion=cliente.direccion,
        pais=cliente.pais, estado=cliente.estado, creado_en=cliente.creado_en,
        num_usuarios=1, num_platos=0, num_mesas=payload.num_mesas, ventas_mes_actual=0.0,
    )


@router.patch("/superadmin/clientes/{cliente_id}/estado")
def cambiar_estado_cliente(
    cliente_id: str,
    payload: EstadoUpdate,
    db: Session = Depends(get_db),
    superadmin_email: str = Depends(get_superadmin_email),
):
    if payload.estado not in ("activo", "inactivo", "suspendido"):
        raise HTTPException(status_code=400, detail="Estado inválido. Use: activo, inactivo o suspendido")

    cliente = db.query(Cliente).filter(Cliente.id == cliente_id).first()
    if not cliente:
        raise HTTPException(status_code=404, detail="Restaurante no encontrado")

    estado_anterior = cliente.estado
    # Un cliente no-'activo' se corta en seco en el próximo login (ver
    # backend/routes/auth.py) aunque sus tokens ya emitidos sigan siendo
    # válidos hasta que expiren (12h) — no hay revocación instantánea de
    # tokens todavía, solo bloqueo de logins nuevos.
    cliente.estado = payload.estado
    db.commit()

    registrar_evento(
        db, actor=superadmin_email, accion="cambiar_estado_cliente", entidad="cliente",
        entidad_id=cliente_id, cliente_id=cliente_id, detalle=f"{estado_anterior} -> {payload.estado}",
    )

    return {"id": cliente.id, "estado": cliente.estado}


@router.patch("/superadmin/clientes/{cliente_id}")
def editar_cliente(
    cliente_id: str,
    payload: ClienteUpdateRequest,
    db: Session = Depends(get_db),
    superadmin_email: str = Depends(get_superadmin_email),
):
    """Editar datos del cliente y su admin."""
    cliente = db.query(Cliente).filter(Cliente.id == cliente_id).first()
    if not cliente:
        raise HTTPException(status_code=404, detail="Restaurante no encontrado")

    admin = db.query(Usuario).filter(Usuario.cliente_id == cliente_id, Usuario.rol == "admin").first()
    if not admin:
        raise HTTPException(status_code=404, detail="Este restaurante no tiene un usuario admin")

    # Validar email único (si cambió)
    if payload.email and payload.email != cliente.email:
        otro = db.query(Cliente).filter(Cliente.email == payload.email, Cliente.id != cliente_id).first()
        if otro:
            raise HTTPException(status_code=400, detail=f"Ya existe un restaurante con el email '{payload.email}'")

    # Actualizar cliente
    cliente.nombre = payload.nombre
    cliente.email = payload.email
    cliente.telefono = payload.telefono
    cliente.ruc = payload.ruc
    cliente.razon_social = payload.razon_social
    cliente.direccion = payload.direccion
    cliente.pais = payload.pais or cliente.pais
    cliente.moneda = payload.moneda or cliente.moneda

    # Actualizar admin (email y/o contraseña)
    email_admin_cambio = False
    new_admin_email = payload.admin_email.strip().lower()
    old_admin_email = admin.email

    if new_admin_email != old_admin_email:
        # Validar que el nuevo email no existe en otro usuario
        otro = db.query(Usuario).filter(Usuario.email == new_admin_email, Usuario.id != admin.id).first()
        if otro:
            raise HTTPException(status_code=400, detail=f"Ya existe un usuario con el email '{new_admin_email}'")
        admin.email = new_admin_email
        email_admin_cambio = True

    # Actualizar contraseña si se proporcionó
    if payload.admin_password:
        admin.password_hash = hash_password(payload.admin_password)

    db.commit()

    registrar_evento(
        db, actor=superadmin_email, accion="editar_cliente", entidad="cliente",
        entidad_id=cliente_id, cliente_id=cliente_id,
        detalle=f"email_admin_cambio: {email_admin_cambio}",
    )

    # Si cambió el email del admin, reenviar credenciales
    if email_admin_cambio:
        enviar_email_credenciales(
            destinatario=new_admin_email,
            nombre_admin=admin.nombre,
            email_login=new_admin_email,
            password=payload.admin_password or "***",  # Si no cambió password, no la reenviamos
            nombre_restaurante=cliente.nombre,
        )

    return ClienteConStats(
        id=cliente.id, nombre=cliente.nombre, email=cliente.email, telefono=cliente.telefono,
        ruc=cliente.ruc, razon_social=cliente.razon_social, direccion=cliente.direccion,
        pais=cliente.pais, estado=cliente.estado, creado_en=cliente.creado_en,
        num_usuarios=db.query(Usuario).filter(Usuario.cliente_id == cliente.id).count(),
        num_platos=db.query(Plato).filter(Plato.cliente_id == cliente.id).count(),
        num_mesas=db.query(Mesa).filter(Mesa.cliente_id == cliente.id).count(),
        ventas_mes_actual=0.0,  # TODO: recalcular
    )


@router.delete("/superadmin/clientes/{cliente_id}", status_code=204)
def eliminar_cliente(
    cliente_id: str,
    db: Session = Depends(get_db),
    superadmin_email: str = Depends(get_superadmin_email),
):
    """Eliminar un cliente y todos sus datos (usuarios, platos, mesas, comandas, etc)."""
    cliente = db.query(Cliente).filter(Cliente.id == cliente_id).first()
    if not cliente:
        raise HTTPException(status_code=404, detail="Restaurante no encontrado")

    nombre_cliente = cliente.nombre

    # Eliminar en cascada (SQLAlchemy lo hace automáticamente si está bien configurado)
    db.delete(cliente)
    db.commit()

    registrar_evento(
        db, actor=superadmin_email, accion="eliminar_cliente", entidad="cliente",
        entidad_id=cliente_id, cliente_id=cliente_id, detalle=nombre_cliente,
    )


@router.patch("/superadmin/clientes/{cliente_id}/reset-password")
def resetear_password_admin(
    cliente_id: str,
    payload: ResetPasswordRequest,
    db: Session = Depends(get_db),
    superadmin_email: str = Depends(get_superadmin_email),
):
    admin = db.query(Usuario).filter(Usuario.cliente_id == cliente_id, Usuario.rol == "admin").first()
    if not admin:
        raise HTTPException(status_code=404, detail="Este restaurante no tiene un usuario admin")

    admin.password_hash = hash_password(payload.nueva_password)
    db.commit()

    registrar_evento(
        db, actor=superadmin_email, accion="resetear_password", entidad="usuario",
        entidad_id=admin.id, cliente_id=cliente_id, detalle=admin.email,
    )

    return {"email": admin.email, "detail": "Contraseña actualizada"}


@router.patch("/superadmin/me/password")
def cambiar_password_superadmin(
    payload: ChangePasswordRequest,
    db: Session = Depends(get_db),
    superadmin_email: str = Depends(get_superadmin_email),
):
    """Cambiar la propia contraseña del superadmin."""
    admin = db.query(SuperAdmin).filter(SuperAdmin.email == superadmin_email).first()
    if not admin:
        raise HTTPException(status_code=401, detail="Sesión inválida")

    # Verificar contraseña actual
    if not verificar_password(payload.password_actual, admin.password_hash):
        raise HTTPException(status_code=400, detail="Contraseña actual incorrecta")

    admin.password_hash = hash_password(payload.nueva_password)
    db.commit()
    return {"detail": "Contraseña actualizada exitosamente"}


@router.patch("/superadmin/me")
def actualizar_perfil_superadmin(
    payload: SuperAdminUpdateRequest,
    db: Session = Depends(get_db),
    superadmin_email: str = Depends(get_superadmin_email),
):
    """Actualizar datos del perfil del superadmin (nombre, email)."""
    admin = db.query(SuperAdmin).filter(SuperAdmin.email == superadmin_email).first()
    if not admin:
        raise HTTPException(status_code=401, detail="Sesión inválida")

    if payload.nombre:
        admin.nombre = payload.nombre.strip()

    if payload.email:
        nuevo_email = payload.email.strip().lower()
        # Validar que el nuevo email sea único
        otro = db.query(SuperAdmin).filter(SuperAdmin.email == nuevo_email, SuperAdmin.id != admin.id).first()
        if otro:
            raise HTTPException(status_code=400, detail=f"Ya existe un superadmin con el email '{nuevo_email}'")
        admin.email = nuevo_email

    db.commit()
    return SuperAdminMe(nombre=admin.nombre, email=admin.email)


@router.get("/superadmin/auditoria", response_model=List[AuditLogResponse])
def listar_auditoria(
    db: Session = Depends(get_db),
    _superadmin: str = Depends(get_superadmin_email),
    cliente_id: str = None,
    limit: int = 200,
):
    """Consultar el registro de auditoría (login, altas, bajas, cambios de
    contraseña). Filtrable por restaurante; sin filtro trae de todos."""
    query = db.query(AuditLog).order_by(AuditLog.timestamp.desc())
    if cliente_id:
        query = query.filter(AuditLog.cliente_id == cliente_id)
    return query.limit(min(limit, 1000)).all()
