"""
Notificaciones push (Firebase Cloud Messaging) cuando entra una comanda
nueva — para que cocina se entere incluso con la app minimizada, sin
depender de tener una impresora de cocina.

Requiere que el admin configure FIREBASE_CREDENTIALS_JSON en el .env con la
ruta al archivo de cuenta de servicio (ver backend/config.py). Sin eso, el
envío se salta en silencio: la app sigue funcionando exactamente igual,
solo sin avisos push — igual que registrar_evento() con la auditoría, esto
NUNCA debe tumbar la creación de una comanda por un problema de Firebase
(credenciales mal puestas, cuota agotada, token vencido, etc.).

El envío corre en un BackgroundTask (ver routes/comandas.py), NO dentro del
request: messaging.send_* es una llamada HTTP bloqueante a Google, y meterla
en el camino del POST /comandas le sumaba el round-trip completo a cada
pedido que toma el mozo (contra el criterio de <500ms de CLAUDE.md). Por eso
notificar_nueva_comanda() abre su propia sesión de BD: la del request ya
está cerrada cuando el background task corre.
"""

import time

from sqlalchemy.orm import Session

from backend.config import settings
from backend.database import SessionLocal
from backend.models import PushSubscription, Usuario

# Roles que reciben el aviso de comanda nueva. jefe_cocina es el motivo del
# feature; admin es opt-in (el switch de Admin > Personal crea/borra su token,
# ver frontend/js/push-notifications.js). No hay columna de "preferencia"
# aparte: la fila en PushSubscription YA ES el opt-in, una sola fuente de
# verdad que no puede desincronizarse de los tokens reales.
ROLES_NOTIFICABLES = ("jefe_cocina", "admin")

# Si la inicialización de Firebase falla (corte de red justo en el primer
# envío, credenciales que todavía no se montaron), se reintenta pasado este
# tiempo en vez de quedar deshabilitado hasta reiniciar el proceso.
_REINTENTO_INIT_SEGUNDOS = 60

_firebase_app = None
_ultimo_intento_init_fallido = 0.0


def _obtener_firebase_app():
    """Inicializa la Admin SDK de Firebase de forma perezosa (recién en el
    primer envío, no al arrancar la app, para no bloquear el arranque si
    Firebase está mal configurado). Devuelve None si no hay credenciales o
    si la librería/credenciales fallan — cualquiera de esas situaciones es
    "no hay push disponible", nunca un error fatal. Un fallo se reintenta
    pasado _REINTENTO_INIT_SEGUNDOS: un corte de red momentáneo no debe
    dejar el push muerto hasta el próximo reinicio del servidor."""
    global _firebase_app, _ultimo_intento_init_fallido

    if _firebase_app is not None:
        return _firebase_app

    if not settings.firebase_credentials_json:
        return None

    if time.monotonic() - _ultimo_intento_init_fallido < _REINTENTO_INIT_SEGUNDOS:
        return None

    try:
        import firebase_admin
        from firebase_admin import credentials

        cred = credentials.Certificate(settings.firebase_credentials_json)
        _firebase_app = firebase_admin.initialize_app(cred)
        return _firebase_app
    except Exception:
        _ultimo_intento_init_fallido = time.monotonic()
        return None


def _tokens_a_notificar(db: Session, cliente_id: str) -> list:
    """Tokens de este restaurante cuyos dueños deben recibir el aviso.
    El join es por usuario_id (FK), nunca por el 'sub' del JWT — ver el
    docstring de PushSubscription en models.py."""
    filas = (
        db.query(PushSubscription.token)
        .join(Usuario, Usuario.id == PushSubscription.usuario_id)
        .filter(
            PushSubscription.cliente_id == cliente_id,
            Usuario.rol.in_(ROLES_NOTIFICABLES),
            Usuario.estado == "activo",
        )
        .all()
    )
    return [fila[0] for fila in filas]


def _purgar_tokens_invalidos(db: Session, tokens: list) -> None:
    """Borra tokens que Firebase ya no reconoce. FCM los rota; sin esta
    limpieza la tabla acumula tokens muertos para siempre y cada comanda
    intenta enviarles igual."""
    if not tokens:
        return
    try:
        db.query(PushSubscription).filter(PushSubscription.token.in_(tokens)).delete(
            synchronize_session=False
        )
        db.commit()
    except Exception:
        db.rollback()


def notificar_nueva_comanda(cliente_id: str, numero_mesa: int, comanda_id: int) -> None:
    """Envía el aviso de comanda nueva a los dispositivos registrados.

    Pensada para correr como BackgroundTask (ver routes/comandas.py): abre y
    cierra su propia sesión de BD, y nunca lanza excepción — un fallo acá
    jamás debe afectar a la comanda, que a esta altura ya está creada y
    visible en la pantalla de cocina por el camino normal.
    """
    db = None
    try:
        app = _obtener_firebase_app()
        if app is None:
            return

        db = SessionLocal()
        tokens = _tokens_a_notificar(db, cliente_id)
        if not tokens:
            return

        from firebase_admin import messaging

        # send_each_for_multicast: UNA llamada HTTP para todos los tokens en
        # vez de una por dispositivo, y devuelve el resultado individual de
        # cada uno (lo que permite detectar y purgar los que ya no sirven).
        respuesta = messaging.send_each_for_multicast(
            messaging.MulticastMessage(
                notification=messaging.Notification(
                    title="🍳 Nueva comanda",
                    body=f"Mesa {numero_mesa} — comanda #{comanda_id}",
                ),
                tokens=tokens,
                webpush=messaging.WebpushConfig(
                    notification=messaging.WebpushNotification(
                        vibrate=[200, 100, 200],
                        require_interaction=True,
                    ),
                ),
            ),
            app=app,
        )

        invalidos = [
            tokens[i]
            for i, r in enumerate(respuesta.responses)
            if not r.success and _es_token_muerto(r.exception)
        ]
        _purgar_tokens_invalidos(db, invalidos)
    except Exception:
        return
    finally:
        if db is not None:
            db.close()


def _es_token_muerto(exc) -> bool:
    """Distingue "este token ya no existe" (hay que borrarlo) de un fallo
    transitorio como una cuota agotada o un timeout (hay que conservarlo:
    el dispositivo sigue siendo válido)."""
    if exc is None:
        return False
    try:
        from firebase_admin import messaging
        from firebase_admin import exceptions as fb_exceptions

        if isinstance(exc, messaging.UnregisteredError):
            return True
        return isinstance(exc, fb_exceptions.InvalidArgumentError)
    except Exception:
        return False


def _resolver_usuario(db: Session, cliente_id: str, identidad: str):
    """Encuentra el Usuario detrás del 'sub' del JWT. Ese valor es el email
    para admin/superadmin y el código de acceso para el staff (ver
    auth.py:login_staff) — por eso hay que probar contra las dos columnas.
    Siempre acotado al cliente_id del token: nunca puede resolver a un
    usuario de otro restaurante."""
    return (
        db.query(Usuario)
        .filter(
            Usuario.cliente_id == cliente_id,
            (Usuario.email == identidad) | (Usuario.celular == identidad),
        )
        .first()
    )


def registrar_token(db: Session, cliente_id: str, identidad: str, token: str) -> None:
    """Guarda el token de este dispositivo. Idempotente: el mismo
    usuario+token no duplica fila, y una carrera entre dos registros
    simultáneos (aplicarPermisosRol puede dispararse más de una vez) se
    resuelve sin devolver un 500."""
    usuario = _resolver_usuario(db, cliente_id, identidad)
    if usuario is None:
        return

    existente = (
        db.query(PushSubscription)
        .filter(PushSubscription.usuario_id == usuario.id, PushSubscription.token == token)
        .first()
    )
    if existente:
        return

    try:
        db.add(PushSubscription(cliente_id=cliente_id, usuario_id=usuario.id, token=token))
        db.commit()
    except Exception:
        # UniqueConstraint: otro request idéntico ganó la carrera. El estado
        # final es el deseado (la fila existe), así que no es un error.
        db.rollback()


def eliminar_token(db: Session, cliente_id: str, identidad: str, token: str = None) -> None:
    """Da de baja tokens de este usuario. Sin `token`, borra TODOS los suyos.

    Ese caso no es un capricho: el switch del admin guarda el token del
    dispositivo en localStorage, y si el navegador se limpia (o se usa el
    botón ?reset de la app, que hace localStorage.clear()) el front ya no
    sabe qué token borrar. Sin este fallback, la fila quedaba viva para
    siempre y el admin seguía recibiendo avisos sin ninguna forma de
    apagarlos."""
    usuario = _resolver_usuario(db, cliente_id, identidad)
    if usuario is None:
        return

    query = db.query(PushSubscription).filter(PushSubscription.usuario_id == usuario.id)
    if token:
        query = query.filter(PushSubscription.token == token)

    query.delete(synchronize_session=False)
    db.commit()


def tiene_token_registrado(db: Session, cliente_id: str, identidad: str) -> bool:
    """¿Este usuario tiene algún dispositivo registrado? Es la fuente de
    verdad del switch del admin — el frontend la consulta para no depender
    solo de localStorage, que puede estar limpio aunque la fila exista."""
    usuario = _resolver_usuario(db, cliente_id, identidad)
    if usuario is None:
        return False

    return (
        db.query(PushSubscription.id)
        .filter(PushSubscription.usuario_id == usuario.id)
        .first()
        is not None
    )
