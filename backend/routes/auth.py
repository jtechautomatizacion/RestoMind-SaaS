"""
Login. El único endpoint de toda la API que NO exige un token de entrada
(sería una paradoja: necesitarías estar logueado para poder loguearte).

No hay registro público (`POST /clientes` o similar) a propósito: en el
modelo de negocio de reventa, cada restaurante nuevo lo da de alta el
dueño del sistema (no el cliente final) con el script de onboarding
(`backend/scripts/crear_cliente.py`), no con una pantalla que cualquiera
pueda tocar desde internet.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from backend.auth import crear_token, verificar_password
from backend.database import get_db
from backend.dependencies import get_cliente_id, get_usuario_actual
from backend.models import Cliente, Usuario
from backend.schemas import LoginRequest, LoginResponse, UsuarioMe

router = APIRouter()


@router.post("/auth/login", response_model=LoginResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    usuario = db.query(Usuario).filter(Usuario.email == payload.email.strip().lower()).first()

    # Mismo mensaje de error para "no existe" y "contraseña incorrecta":
    # decirle a alguien "ese email no existe" es una fuga que le permite
    # enumerar cuentas válidas probando emails al voleo.
    credenciales_invalidas = HTTPException(status_code=401, detail="Email o contraseña incorrectos")

    if not usuario or not verificar_password(payload.password, usuario.password_hash):
        raise credenciales_invalidas

    if usuario.estado != "activo":
        raise HTTPException(status_code=403, detail="Este usuario está deshabilitado")

    cliente = db.query(Cliente).filter(Cliente.id == usuario.cliente_id).first()
    if not cliente or cliente.estado != "activo":
        raise HTTPException(status_code=403, detail="Esta cuenta de restaurante está deshabilitada")

    token = crear_token(email=usuario.email, cliente_id=usuario.cliente_id, rol=usuario.rol)
    return LoginResponse(
        access_token=token,
        usuario=UsuarioMe(
            email=usuario.email,
            nombre=usuario.nombre,
            rol=usuario.rol,
            cliente_id=usuario.cliente_id,
            cliente_nombre=cliente.nombre,
        ),
    )


@router.get("/auth/me", response_model=UsuarioMe)
def me(
    db: Session = Depends(get_db),
    cliente_id: str = Depends(get_cliente_id),
    usuario_email: str = Depends(get_usuario_actual),
):
    """
    Para que el frontend valide un token guardado en localStorage al abrir
    la app (¿sigue siendo válido? ¿el usuario sigue activo?) sin tener que
    decodificar el JWT él mismo ni volver a pedir la contraseña.
    """
    usuario = db.query(Usuario).filter(Usuario.email == usuario_email, Usuario.cliente_id == cliente_id).first()
    if not usuario:
        raise HTTPException(status_code=401, detail="Sesión inválida")

    cliente = db.query(Cliente).filter(Cliente.id == cliente_id).first()
    return UsuarioMe(
        email=usuario.email,
        nombre=usuario.nombre,
        rol=usuario.rol,
        cliente_id=usuario.cliente_id,
        cliente_nombre=cliente.nombre if cliente else "",
    )
