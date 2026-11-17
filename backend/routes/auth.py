"""
Login. El único endpoint de toda la API que NO exige un token de entrada
(sería una paradoja: necesitarías estar logueado para poder loguearte).

No hay registro público (`POST /clientes` o similar) a propósito: en el
modelo de negocio de reventa, cada restaurante nuevo lo da de alta el
dueño del sistema (no el cliente final) con el script de onboarding
(`backend/scripts/crear_cliente.py`), no con una pantalla que cualquiera
pueda tocar desde internet.

DOS MODOS DE SESIÓN (ver backend/sesiones.py)
---------------------------------------------
  · App web (Flutter) — manda `X-Sesion: cookie`. Recibe un access token de
    15 min, que guarda SOLO en memoria, y una cookie HttpOnly con el refresh.
    Al recargar la página la sesión sigue con POST /auth/sesion/refresh.
  · APK instalado (Capacitor) — sin esa cabecera. Recibe el token de 12 h de
    siempre. Se mantiene para no dejar a ningún celular afuera hasta que el
    APK también pase a Flutter.
"""

import logging
from typing import Optional

from fastapi import APIRouter, Cookie, Depends, Header, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from backend import sesiones
from backend.auth import crear_token, crear_token_superadmin, verificar_password
from backend.database import get_db
from backend.dependencies import get_cliente_id, get_usuario_actual
from backend.models import Cliente, SuperAdmin, Usuario
from backend.schemas import LoginRequest, LoginResponse, LoginStaffRequest, UsuarioMe
from backend.utils.auditoria import registrar_evento
from backend.utils.rate_limit import limpiar_intentos_login, registrar_login_fallido, verificar_intentos_login
from backend.utils.roles import roles_de

logger = logging.getLogger(__name__)
router = APIRouter()


def _usuario_me(usuario: Usuario, cliente: Optional[Cliente]) -> UsuarioMe:
    """Identidad + datos del negocio que la app necesita desde que abre sesión
    (imprimir tickets, saber si factura). Un solo armado para login, refresh y /me."""
    return UsuarioMe(
        # El staff no tiene email: se muestra su nombre para que el encabezado
        # de la app no quede vacío.
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


def _identificador(usuario: Usuario) -> str:
    """El `sub` del token: email para el admin, código de acceso para el staff."""
    return usuario.email or usuario.celular


def _emitir(
    db: Session, usuario: Usuario, cliente: Cliente, modo: Optional[str], respuesta: Response,
) -> LoginResponse:
    if modo == sesiones.MODO_COOKIE:
        refresh, sesion = sesiones.crear(db, usuario)
        sesiones.poner_cookie(respuesta, refresh, sesion.expira_en)
        token = crear_token(
            _identificador(usuario), usuario.cliente_id, usuario.rol,
            duracion=sesiones.DURACION_ACCESS, sid=sesion.id,
        )
    else:
        token = crear_token(_identificador(usuario), usuario.cliente_id, usuario.rol)
    return LoginResponse(access_token=token, usuario=_usuario_me(usuario, cliente))


def _validar_cuenta_activa(db: Session, usuario: Usuario) -> Cliente:
    if usuario.estado != "activo":
        raise HTTPException(status_code=403, detail="Este usuario está deshabilitado")
    cliente = db.query(Cliente).filter(Cliente.id == usuario.cliente_id).first()
    if not cliente or cliente.estado != "activo":
        raise HTTPException(status_code=403, detail="Esta cuenta de restaurante está deshabilitada")
    return cliente


@router.post("/auth/login", response_model=LoginResponse)
def login(
    payload: LoginRequest,
    request: Request,
    respuesta: Response,
    db: Session = Depends(get_db),
    modo: Optional[str] = Header(default=None, alias=sesiones.CABECERA_MODO),
):
    verificar_intentos_login(request)
    email = payload.email.strip().lower()
    usuario = db.query(Usuario).filter(Usuario.email == email).first()

    if not usuario:
        superadmin = db.query(SuperAdmin).filter(SuperAdmin.email == email).first()
        if superadmin:
            if not verificar_password(payload.password, superadmin.password_hash):
                logger.warning("[LOGIN] superadmin: contraseña incorrecta")
                registrar_login_fallido(request)
                raise HTTPException(status_code=401, detail="Email o contraseña incorrectos")
            limpiar_intentos_login(request)
            registrar_evento(db, actor=superadmin.email, accion="login", entidad="superadmin", entidad_id=superadmin.id)
            # El superadmin no abre sesión con cookie: su panel es otra página
            # (/static/superadmin.html) con su propio login.
            return LoginResponse(
                access_token=crear_token_superadmin(superadmin.email),
                usuario=UsuarioMe(
                    email=superadmin.email,
                    nombre=superadmin.nombre,
                    rol="superadmin",
                    roles=["superadmin"],
                    cliente_id="superadmin",
                    cliente_nombre="Panel General",
                ),
            )

    # Mismo mensaje para "no existe" y "contraseña incorrecta": decir "ese
    # email no existe" permite enumerar cuentas válidas.
    if not usuario or not verificar_password(payload.password, usuario.password_hash):
        logger.warning("[LOGIN] credenciales inválidas")
        registrar_login_fallido(request)
        raise HTTPException(status_code=401, detail="Email o contraseña incorrectos")

    cliente = _validar_cuenta_activa(db, usuario)
    limpiar_intentos_login(request)
    registrar_evento(db, actor=usuario.email, accion="login", entidad="usuario", entidad_id=usuario.id, cliente_id=usuario.cliente_id)
    return _emitir(db, usuario, cliente, modo, respuesta)


@router.post("/auth/login-staff", response_model=LoginResponse)
def login_staff(
    payload: LoginStaffRequest,
    request: Request,
    respuesta: Response,
    db: Session = Depends(get_db),
    modo: Optional[str] = Header(default=None, alias=sesiones.CABECERA_MODO),
):
    """Login para el personal: código de acceso de 6 dígitos + contraseña."""
    verificar_intentos_login(request)
    usuario = db.query(Usuario).filter(Usuario.celular == payload.celular.strip()).first()

    if not usuario or not verificar_password(payload.password, usuario.password_hash):
        registrar_login_fallido(request)
        raise HTTPException(status_code=401, detail="Código o contraseña incorrectos")

    cliente = _validar_cuenta_activa(db, usuario)
    limpiar_intentos_login(request)
    registrar_evento(db, actor=usuario.celular, accion="login", entidad="usuario", entidad_id=usuario.id, cliente_id=usuario.cliente_id)
    return _emitir(db, usuario, cliente, modo, respuesta)


@router.post("/auth/sesion/refresh", response_model=LoginResponse)
def refrescar(
    respuesta: Response,
    db: Session = Depends(get_db),
    refresh: Optional[str] = Cookie(default=None, alias=sesiones.COOKIE_REFRESH),
):
    """Renueva el access token con la cookie de refresh, y ROTA esa cookie.

    Cualquier fallo responde 401 y borra la cookie: la app vuelve al login. No se
    distingue el motivo hacia afuera (caducada, revocada o reusada), pero el reuso
    sí queda en la auditoría porque es la señal de un token robado."""
    r = sesiones.rotar(db, refresh)
    if r.resultado != "ok":
        if r.resultado == "reuso":
            logger.warning("[SESION] reuso de refresh token: sesión revocada")
            registrar_evento(db, actor="sistema", accion="sesion_reuso", entidad="sesion", entidad_id=None)
        rechazo = JSONResponse(status_code=401, content={"detail": "La sesión terminó. Inicie sesión de nuevo."})
        sesiones.borrar_cookie(rechazo)
        return rechazo
    sesiones.poner_cookie(respuesta, r.token, r.sesion.expira_en)
    token = crear_token(
        _identificador(r.usuario), r.usuario.cliente_id, r.usuario.rol,
        duracion=sesiones.DURACION_ACCESS, sid=r.sesion.id,
    )
    return LoginResponse(access_token=token, usuario=_usuario_me(r.usuario, r.cliente))


@router.post("/auth/sesion/logout", status_code=204)
def cerrar_sesion(
    respuesta: Response,
    db: Session = Depends(get_db),
    refresh: Optional[str] = Cookie(default=None, alias=sesiones.COOKIE_REFRESH),
):
    """Revoca la sesión de ESTE aparato y borra la cookie. Idempotente: sin
    cookie o con una vieja, igual responde 204."""
    sesiones.revocar_por_token(db, refresh)
    sesiones.borrar_cookie(respuesta)
    respuesta.status_code = 204
    return respuesta


@router.get("/auth/me", response_model=UsuarioMe)
def me(
    db: Session = Depends(get_db),
    cliente_id: str = Depends(get_cliente_id),
    identidad: str = Depends(get_usuario_actual),
):
    """Valida el token y devuelve la identidad actual.

    Busca por email O celular porque el 'sub' vale el EMAIL para el admin y el
    CÓDIGO DE ACCESO para el staff (que tiene email=NULL)."""
    usuario = db.query(Usuario).filter(
        Usuario.cliente_id == cliente_id,
        (Usuario.email == identidad) | (Usuario.celular == identidad),
    ).first()
    if not usuario:
        raise HTTPException(status_code=401, detail="Sesión inválida")
    cliente = db.query(Cliente).filter(Cliente.id == cliente_id).first()
    return _usuario_me(usuario, cliente)
