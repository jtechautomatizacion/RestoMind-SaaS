"""
Login. El único endpoint de toda la API que NO exige un token de entrada
(sería una paradoja: necesitarías estar logueado para poder loguearte).

No hay registro público (`POST /clientes` o similar) a propósito: en el
modelo de negocio de reventa, cada restaurante nuevo lo da de alta el
dueño del sistema (no el cliente final) con el script de onboarding
(`backend/scripts/crear_cliente.py`), no con una pantalla que cualquiera
pueda tocar desde internet.
"""

import logging
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from backend.auth import crear_token, verificar_password, crear_token_superadmin
from backend.database import get_db
from backend.dependencies import get_cliente_id, get_usuario_actual
from backend.models import Cliente, Usuario, SuperAdmin
from backend.schemas import LoginRequest, LoginResponse, UsuarioMe, LoginStaffRequest
from backend.utils.auditoria import registrar_evento
from backend.utils.rate_limit import limpiar_intentos_login, registrar_login_fallido, verificar_intentos_login
from backend.utils.roles import roles_de

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/auth/login", response_model=LoginResponse)
def login(payload: LoginRequest, request: Request, db: Session = Depends(get_db)):
    verificar_intentos_login(request)

    email = payload.email.strip().lower()
    logger.info(f"[LOGIN] Intento con email: {email}")

    # Intentar primero con Usuario (admin del restaurante)
    usuario = db.query(Usuario).filter(Usuario.email == email).first()

    if usuario:
        logger.info(f"[LOGIN] Usuario encontrado: {usuario.id}, rol: {usuario.rol}")
    else:
        logger.info(f"[LOGIN] Usuario NO encontrado, intentando SuperAdmin...")
        # Intentar con SuperAdmin
        superadmin = db.query(SuperAdmin).filter(SuperAdmin.email == email).first()
        if superadmin:
            logger.info(f"[LOGIN] SuperAdmin encontrado: {superadmin.id}")
            if not verificar_password(payload.password, superadmin.password_hash):
                logger.warning(f"[LOGIN] SuperAdmin {email}: contraseña incorrecta")
                registrar_login_fallido(request)
                raise HTTPException(status_code=401, detail="Email o contraseña incorrectos")
            logger.info(f"[LOGIN] SuperAdmin {email}: login exitoso")
            limpiar_intentos_login(request)
            registrar_evento(db, actor=superadmin.email, accion="login", entidad="superadmin", entidad_id=superadmin.id)
            token = crear_token_superadmin(superadmin.email)
            return LoginResponse(
                access_token=token,
                usuario=UsuarioMe(
                    email=superadmin.email,
                    nombre=superadmin.nombre,
                    rol="superadmin",
                    roles=["superadmin"],
                    cliente_id="superadmin",
                    cliente_nombre="Panel General",
                ),
            )
        else:
            logger.warning(f"[LOGIN] Email {email} no encontrado en ninguna tabla")

    # Mismo mensaje de error para "no existe" y "contraseña incorrecta":
    # decirle a alguien "ese email no existe" es una fuga que le permite
    # enumerar cuentas válidas probando emails al voelo.
    credenciales_invalidas = HTTPException(status_code=401, detail="Email o contraseña incorrectos")

    if not usuario or not verificar_password(payload.password, usuario.password_hash):
        logger.warning(f"[LOGIN] Usuario {email}: contraseña incorrecta o usuario no existe")
        registrar_login_fallido(request)
        raise credenciales_invalidas

    if usuario.estado != "activo":
        raise HTTPException(status_code=403, detail="Este usuario está deshabilitado")

    cliente = db.query(Cliente).filter(Cliente.id == usuario.cliente_id).first()
    if not cliente or cliente.estado != "activo":
        raise HTTPException(status_code=403, detail="Esta cuenta de restaurante está deshabilitada")

    limpiar_intentos_login(request)
    registrar_evento(db, actor=usuario.email, accion="login", entidad="usuario", entidad_id=usuario.id, cliente_id=usuario.cliente_id)
    token = crear_token(email=usuario.email, cliente_id=usuario.cliente_id, rol=usuario.rol)
    return LoginResponse(
        access_token=token,
        usuario=UsuarioMe(
            email=usuario.email,
            nombre=usuario.nombre,
            rol=usuario.rol,
            roles=["admin"] if usuario.rol == "admin" else roles_de(usuario.rol),
            cliente_id=usuario.cliente_id,
            cliente_nombre=cliente.nombre,
            cliente_ruc=cliente.ruc,
            cliente_usar_sunat=bool(cliente.usar_sunat),
            cliente_emite_facturas=bool(cliente.emite_facturas),
            cliente_razon_social=cliente.razon_social,
            cliente_direccion=cliente.direccion,
            cliente_email=cliente.email,
        ),
    )


@router.post("/auth/login-staff", response_model=LoginResponse)
def login_staff(payload: LoginStaffRequest, request: Request, db: Session = Depends(get_db)):
    """Login para mozo, cajero, cocinero. Usa celular + contraseña."""
    verificar_intentos_login(request)

    usuario = db.query(Usuario).filter(Usuario.celular == payload.celular.strip()).first()

    credenciales_invalidas = HTTPException(status_code=401, detail="Celular o contraseña incorrectos")

    if not usuario or not verificar_password(payload.password, usuario.password_hash):
        registrar_login_fallido(request)
        raise credenciales_invalidas

    if usuario.estado != "activo":
        raise HTTPException(status_code=403, detail="Este usuario está deshabilitado")

    cliente = db.query(Cliente).filter(Cliente.id == usuario.cliente_id).first()
    if not cliente or cliente.estado != "activo":
        raise HTTPException(status_code=403, detail="Esta cuenta de restaurante está deshabilitada")

    limpiar_intentos_login(request)
    registrar_evento(db, actor=usuario.celular, accion="login", entidad="usuario", entidad_id=usuario.id, cliente_id=usuario.cliente_id)

    # Para staff, usamos celular en lugar de email en el token
    token = crear_token(email=usuario.celular, cliente_id=usuario.cliente_id, rol=usuario.rol)
    return LoginResponse(
        access_token=token,
        usuario=UsuarioMe(
            email=usuario.nombre,  # Mostrar nombre en lugar de email para staff
            nombre=usuario.nombre,
            rol=usuario.rol,
            roles=["admin"] if usuario.rol == "admin" else roles_de(usuario.rol),
            cliente_id=usuario.cliente_id,
            cliente_nombre=cliente.nombre,
            cliente_ruc=cliente.ruc,
            cliente_usar_sunat=bool(cliente.usar_sunat),
            cliente_emite_facturas=bool(cliente.emite_facturas),
            cliente_razon_social=cliente.razon_social,
            cliente_direccion=cliente.direccion,
            cliente_email=cliente.email,
        ),
    )


@router.get("/auth/me", response_model=UsuarioMe)
def me(
    db: Session = Depends(get_db),
    cliente_id: str = Depends(get_cliente_id),
    identidad: str = Depends(get_usuario_actual),
):
    """
    Para que el frontend valide un token guardado en localStorage al abrir
    la app (¿sigue siendo válido? ¿el usuario sigue activo?) sin tener que
    decodificar el JWT él mismo ni volver a pedir la contraseña.

    Busca por email O celular porque el 'sub' del token vale una cosa u otra
    según el tipo de cuenta: el EMAIL para el admin, pero el CÓDIGO DE
    ACCESO para el staff (ver login_staff arriba), que además tiene
    email=NULL. Con el filtro solo por email, este endpoint devolvía 401 a
    TODO el personal: entraban bien, y la siguiente recarga de la página los
    expulsaba al login con "Tu sesión expiró" (initAuth en
    frontend/js/auth.js llama acá al arrancar). Es el mismo criterio que ya
    usaban /usuarios/me y el registro de tokens push.
    """
    usuario = db.query(Usuario).filter(
        Usuario.cliente_id == cliente_id,
        (Usuario.email == identidad) | (Usuario.celular == identidad),
    ).first()
    if not usuario:
        raise HTTPException(status_code=401, detail="Sesión inválida")

    cliente = db.query(Cliente).filter(Cliente.id == cliente_id).first()
    return UsuarioMe(
        # El staff no tiene email: se muestra su nombre, igual que hace
        # login_staff, para que el header de la app no quede vacío tras
        # recargar.
        email=usuario.email or usuario.nombre,
        nombre=usuario.nombre,
        rol=usuario.rol,
        roles=["admin"] if usuario.rol == "admin" else roles_de(usuario.rol),
        cliente_id=usuario.cliente_id,
        cliente_nombre=cliente.nombre if cliente else "",
        cliente_ruc=cliente.ruc if cliente else None,
        cliente_usar_sunat=bool(cliente.usar_sunat) if cliente else False,
        cliente_emite_facturas=bool(cliente.emite_facturas) if cliente else False,
        cliente_razon_social=cliente.razon_social if cliente else None,
        cliente_direccion=cliente.direccion if cliente else None,
        cliente_email=cliente.email if cliente else None,
    )
