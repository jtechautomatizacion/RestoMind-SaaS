"""
Autenticación real (JWT) — reemplaza el modo de desarrollo que resolvía
cliente_id/usuario desde headers sin validar nada (X-Cliente-Id, X-Usuario).

Multi-tenant vía reventa: cada restaurante es un Cliente con sus propios
Usuarios. El token no lleva más que lo necesario para resolver quién es
quién (sub=email, cliente_id, rol) — cualquier chequeo de permiso más fino
(admin-only, etc.) sigue yendo a la base de datos en cada request vía
validar_admin(), así que revocar o cambiar el rol de un usuario surte
efecto de inmediato sin esperar a que expire su token viejo.
"""

from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
import jwt

from backend.config import settings

ALGORITMO = "HS256"
EXPIRACION_HORAS = 12  # Un turno largo de restaurante no debería requerir volver a loguearse a medio servicio.


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verificar_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:
        # Hash corrupto o en un formato que no es bcrypt (p.ej. datos de
        # seed viejos de antes de que existiera login real): tratarlo como
        # contraseña incorrecta, nunca como error 500.
        return False


def crear_token(email: str, cliente_id: str, rol: str) -> str:
    ahora = datetime.now(timezone.utc)
    payload = {
        "sub": email,
        "cliente_id": cliente_id,
        "rol": rol,
        "tipo": "usuario",
        "iat": ahora,
        "exp": ahora + timedelta(hours=EXPIRACION_HORAS),
    }
    return jwt.encode(payload, settings.secret_key, algorithm=ALGORITMO)


def crear_token_superadmin(email: str) -> str:
    """
    Sin cliente_id ni rol de restaurante: un token de superadmin no debe
    poder usarse por accidente contra una ruta de tenant (get_cliente_id
    rechaza cualquier token que no tenga tipo != 'superadmin' con cliente_id
    real, y viceversa las rutas de superadmin exigen tipo == 'superadmin').
    """
    ahora = datetime.now(timezone.utc)
    payload = {
        "sub": email,
        "tipo": "superadmin",
        "iat": ahora,
        "exp": ahora + timedelta(hours=EXPIRACION_HORAS),
    }
    return jwt.encode(payload, settings.secret_key, algorithm=ALGORITMO)


def decodificar_token(token: str) -> Optional[dict]:
    try:
        return jwt.decode(token, settings.secret_key, algorithms=[ALGORITMO])
    except jwt.PyJWTError:
        return None
