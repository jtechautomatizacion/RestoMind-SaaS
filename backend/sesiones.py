"""
Sesiones de la app web: refresh token rotativo en cookie HttpOnly.

Es el modelo de sesión de Sac-Geo, llevado a RestoMind:

  · El ACCESS token (JWT) dura 15 minutos y la app lo guarda SOLO en memoria.
    Nunca en localStorage: un script inyectado no tiene de dónde robarlo.
  · El REFRESH viaja en la cookie `__Secure-restomind_refresh`: HttpOnly
    (JavaScript no la lee), Secure, SameSite=Strict y Path=/api/auth/sesion
    (el navegador solo la manda a refresh y logout, nunca al resto de la API).
  · Cada refresh ROTA el secreto. Presentar uno anterior es la señal de que
    alguien lo copió: se revoca la sesión entera y los dos quedan afuera.

`Secure` va siempre: los navegadores aceptan cookies Secure en
http://localhost, así que el desarrollo local no necesita degradarla y
producción no puede olvidarla.

Quién usa este modo lo decide el cliente con la cabecera `X-Sesion: cookie`
en el login. Sin ella, el login responde como siempre (token de 12 h): así el
APK que ya está instalado en los celulares sigue funcionando sin cambios.
"""

from __future__ import annotations

import hashlib
import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

from fastapi import Response
from sqlalchemy import update
from sqlalchemy.orm import Session

from backend.models import Cliente, SesionRefresh, Usuario

COOKIE_REFRESH = "__Secure-restomind_refresh"
RUTA_COOKIE = "/api/auth/sesion"
CABECERA_MODO = "X-Sesion"
MODO_COOKIE = "cookie"

DURACION_ACCESS = timedelta(minutes=15)
# Dos semanas: un celular de mozo no debería pedir la contraseña cada turno,
# pero una sesión olvidada en un aparato perdido tampoco puede vivir para siempre.
DURACION_SESION = timedelta(days=14)


def _hash(secreto: str) -> str:
    return hashlib.sha256(secreto.encode("utf-8")).hexdigest()


def _componer(sid: str, secreto: str) -> str:
    return f"{sid}.{secreto}"


def _separar(token: Optional[str]) -> Optional[tuple[str, str]]:
    if not token or "." not in token:
        return None
    sid, secreto = token.split(".", 1)
    try:
        uuid.UUID(sid)
    except ValueError:
        return None
    return (sid, secreto) if secreto else None


# ------------------------------------------------------------ la cookie -----

def poner_cookie(respuesta: Response, token: str, expira_en: datetime) -> None:
    """La cookie dura lo que le queda a la sesión, nunca más."""
    restante = int((expira_en - datetime.utcnow()).total_seconds())
    respuesta.set_cookie(
        key=COOKIE_REFRESH, value=token, max_age=max(restante, 0), path=RUTA_COOKIE,
        secure=True, httponly=True, samesite="strict",
    )


def borrar_cookie(respuesta: Response) -> None:
    respuesta.delete_cookie(
        key=COOKIE_REFRESH, path=RUTA_COOKIE, secure=True, httponly=True, samesite="strict",
    )


# ------------------------------------------------------------ la base -------

def crear(db: Session, usuario: Usuario) -> tuple[str, SesionRefresh]:
    """Abre una sesión tras un login con la contraseña YA verificada."""
    secreto = secrets.token_urlsafe(32)
    ahora = datetime.utcnow()
    sesion = SesionRefresh(
        id=str(uuid.uuid4()),
        usuario_id=usuario.id,
        cliente_id=usuario.cliente_id,
        hash_vigente=_hash(secreto),
        generacion=1,
        creada_en=ahora,
        expira_en=ahora + DURACION_SESION,
    )
    db.add(sesion)
    db.commit()
    return _componer(sesion.id, secreto), sesion


@dataclass(frozen=True)
class Rotacion:
    # ok | invalida | revocada | expirada | reuso | inactiva
    resultado: str
    usuario: Optional[Usuario] = None
    cliente: Optional[Cliente] = None
    token: Optional[str] = None
    sesion: Optional[SesionRefresh] = None


def _revocar(db: Session, sesion: SesionRefresh, motivo: str) -> None:
    if sesion.revocada_en is None:
        sesion.revocada_en = datetime.utcnow()
        sesion.motivo_revocacion = motivo
        db.commit()


def rotar(db: Session, token: Optional[str]) -> Rotacion:
    """Valida el refresh y lo sustituye por uno nuevo, o dice por qué no."""
    partes = _separar(token)
    if partes is None:
        return Rotacion("invalida")
    sid, secreto = partes
    sesion = db.get(SesionRefresh, sid)
    if sesion is None:
        return Rotacion("invalida")
    if sesion.revocada_en is not None:
        return Rotacion("revocada")
    if sesion.expira_en <= datetime.utcnow():
        _revocar(db, sesion, "expirada")
        return Rotacion("expirada")
    if sesion.hash_vigente != _hash(secreto):
        _revocar(db, sesion, "reuso")
        return Rotacion("reuso")

    usuario = db.get(Usuario, sesion.usuario_id)
    cliente = db.get(Cliente, sesion.cliente_id)
    if not usuario or usuario.estado != "activo" or not cliente or cliente.estado != "activo":
        _revocar(db, sesion, "inactiva")
        return Rotacion("inactiva")

    # El cambio de secreto es UNA sentencia condicionada al hash vigente: si dos
    # refresh con el mismo token llegan a la vez, solo uno encuentra el hash y
    # el otro queda como reuso. La carrera la resuelve SQLite, no Python.
    nuevo = secrets.token_urlsafe(32)
    filas = db.execute(
        update(SesionRefresh)
        .where(
            SesionRefresh.id == sid,
            SesionRefresh.hash_vigente == _hash(secreto),
            SesionRefresh.revocada_en.is_(None),
        )
        .values(
            hash_vigente=_hash(nuevo),
            generacion=SesionRefresh.generacion + 1,
            renovada_en=datetime.utcnow(),
        )
    ).rowcount
    db.commit()
    db.refresh(sesion)
    if filas != 1:
        _revocar(db, sesion, "reuso")
        return Rotacion("reuso")
    return Rotacion("ok", usuario, cliente, _componer(sid, nuevo), sesion)


def revocar_por_token(db: Session, token: Optional[str]) -> None:
    """Logout: revoca la sesión si el token es el vigente. Idempotente."""
    partes = _separar(token)
    if partes is None:
        return
    sid, secreto = partes
    sesion = db.get(SesionRefresh, sid)
    if sesion is not None and sesion.hash_vigente == _hash(secreto):
        _revocar(db, sesion, "logout")


def revocar_de_usuario(db: Session, usuario_id: str, motivo: str) -> int:
    """Cierra todas las sesiones vivas de una cuenta (contraseña cambiada,
    cuenta desactivada). El commit lo hace quien llama, junto con su cambio."""
    return db.execute(
        update(SesionRefresh)
        .where(SesionRefresh.usuario_id == usuario_id, SesionRefresh.revocada_en.is_(None))
        .values(revocada_en=datetime.utcnow(), motivo_revocacion=motivo)
    ).rowcount
