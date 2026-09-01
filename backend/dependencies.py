"""
Dependencias compartidas de FastAPI.

Autenticación real vía JWT (Authorization: Bearer <token>). get_cliente_id
y get_usuario_actual son el único punto de la app que sabe de dónde sale
esa identidad — cada ruta que las usa (casi todas) queda protegida sin
que haya que tocar el archivo de esa ruta.
"""

from datetime import datetime
from typing import Optional

from fastapi import Depends, Header, HTTPException, Request
from sqlalchemy.orm import Session

from backend.auth import decodificar_token, verificar_password
from backend.database import get_db
from backend.models import AgenteToken
from backend.utils.rate_limit import limpiar_intentos_login, registrar_login_fallido, verificar_intentos_login


def _payload_del_token(authorization: Optional[str] = Header(default=None)) -> dict:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="No autenticado")

    token = authorization.removeprefix("Bearer ").strip()
    payload = decodificar_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Sesión inválida o expirada")

    return payload


def get_cliente_id(payload: dict = Depends(_payload_del_token)) -> str:
    # Exige tipo == "usuario" explícito, no solo "no es superadmin": un
    # token viejo o de un tipo futuro que no declare "tipo" en absoluto no
    # debería colarse acá solo porque no dice "superadmin" — más frágil que
    # chequear lo que SÍ tiene que ser.
    if payload.get("tipo") != "usuario" or "cliente_id" not in payload:
        raise HTTPException(status_code=403, detail="Este token no da acceso a datos de un restaurante")
    return payload["cliente_id"]


def get_usuario_actual(payload: dict = Depends(_payload_del_token)) -> str:
    """Devuelve el email del usuario autenticado (el 'sub' del token)."""
    if payload.get("tipo") != "usuario" or "cliente_id" not in payload:
        raise HTTPException(status_code=403, detail="Este token no da acceso a datos de un restaurante")
    return payload["sub"]


def get_superadmin_email(payload: dict = Depends(_payload_del_token)) -> str:
    """
    Para las rutas de /superadmin/*: exige un token emitido por el login
    de superadmin, no uno de restaurante (aunque ambos sean JWT válidos
    firmados con el mismo secret_key).
    """
    if payload.get("tipo") != "superadmin":
        raise HTTPException(status_code=403, detail="Esta acción requiere una sesión de administrador general")
    return payload["sub"]


def get_cliente_id_agente(
    request: Request,
    x_agente_token: Optional[str] = Header(default=None, alias="X-Agente-Token"),
    db: Session = Depends(get_db),
) -> str:
    """
    Autentica al agente que corre en la PC del restaurante (ver
    routes/agente.py) y devuelve su cliente_id, para que las consultas se
    filtren igual que en el resto de la app.

    No usa JWT a propósito: el agente no es una sesión de usuario. Un JWT
    expiraría a las 12 h (nadie va a estar re-logueando una PC en el salón
    de un restaurante), daría acceso a toda la API del tenant desde una
    máquina que no controlamos, y no se podría revocar.

    El token se compara con bcrypt contra los hashes guardados. Eso implica
    recorrer los tokens activos en vez de buscar por índice — es O(n) sobre
    la cantidad de agentes dados de alta (uno o dos por restaurante), y a
    cambio el token nunca queda almacenado en claro. Si algún día son
    miles, se le antepone un prefijo identificador al token para poder
    buscar la fila directo y verificar un solo hash.

    Rate limiting igual que los tres logins de la app: cada intento fallido
    obliga a un bcrypt.checkpw() contra CADA token activo, que es una
    operación deliberadamente cara (ese es el punto de bcrypt). Sin límite,
    eso es una vía de denegación de servicio — un atacante manda intentos
    fallidos sin parar y satura la CPU del servidor a costa de restaurantes
    reales tratando de usar la app.
    """
    verificar_intentos_login(request)

    if not x_agente_token:
        raise HTTPException(status_code=401, detail="Falta el token del agente")

    for agente in db.query(AgenteToken).filter(AgenteToken.estado == "activo").all():
        if verificar_password(x_agente_token, agente.token_hash):
            # Deja rastro de que este agente sigue vivo, para poder detectar
            # desde el servidor uno que dejó de reportarse (PC apagada, sin
            # internet, tarea programada borrada) antes de que el
            # restaurante llame porque no le salen las boletas.
            agente.ultimo_uso_en = datetime.utcnow()
            db.commit()
            limpiar_intentos_login(request)
            return agente.cliente_id

    registrar_login_fallido(request)
    # Mismo mensaje para "no existe" y "revocado": a un cliente no
    # autenticado no se le confirma si un token existió alguna vez.
    raise HTTPException(status_code=401, detail="Token de agente inválido")


def get_tz_offset(x_tz_offset: Optional[str] = Header(default=None, alias="X-TZ-Offset")) -> int:
    """
    Minutos a sumar a la hora local del restaurante para obtener UTC
    (el valor de Date.prototype.getTimezoneOffset() del navegador; Perú = 300).

    La BD guarda todos los timestamps en UTC. Sin este dato el backend no
    puede saber a qué día del restaurante pertenece una venta hecha de noche:
    una comanda cobrada el viernes 22:33 en Lima se guarda como sábado 03:33 UTC.
    Si el header falta o viene mal, se asume 0 (servidor en UTC).
    """
    try:
        offset = int(x_tz_offset)
    except (TypeError, ValueError):
        return 0
    # UTC-14 .. UTC+14; cualquier cosa fuera de ese rango es basura o un intento
    # de correr el rango de fechas a voluntad.
    return offset if -840 <= offset <= 840 else 0
