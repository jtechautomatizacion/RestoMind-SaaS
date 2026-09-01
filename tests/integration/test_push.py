"""
Notificaciones push (Firebase Cloud Messaging).

IMPORTANTE — cómo se crean las cuentas en estos tests: las de staff se crean
con POST /api/usuarios/staff (el camino real de la app), NO con un fixture
que les invente un email. La primera versión de este archivo usaba fixtures
con email para jefe_cocina, y eso escondió el bug más grave del feature: el
vínculo del token se hacía contra Usuario.email, que para staff es NULL (su
identidad de login es el código de acceso). Los tests pasaban en verde
mientras cocina —el rol para el que existe el feature— no recibía nada.

Foco: (1) que jefe_cocina REAL reciba el aviso, (2) que el envío nunca rompa
la creación de una comanda, (3) que el opt-in/opt-out del admin funcione
incluso sin localStorage.
"""

from unittest.mock import MagicMock, patch

import pytest

from backend.models import PushSubscription, Usuario
from tests.conftest import TEST_CLIENTE_ID

TOKEN_A = "token-dispositivo-a-123456"
TOKEN_B = "token-dispositivo-b-123456"


@pytest.fixture(autouse=True)
def _sesion_del_background_task(test_db, monkeypatch):
    """notificar_nueva_comanda corre como BackgroundTask y abre su PROPIA
    sesión (la del request ya está cerrada cuando corre). En tests hay que
    apuntarla a la BD en memoria, o consultaría la base real y no vería
    ningún token. Cerrarla no rompe nada: una Session de SQLAlchemy vuelve a
    tomar conexión sola en el siguiente uso."""
    monkeypatch.setattr('backend.utils.push_notifications.SessionLocal', lambda: test_db)


def _crear_staff(test_client, nombre, rol):
    """Crea una cuenta de staff como lo hace la app de verdad: sin email,
    con código de acceso generado por el backend. Devuelve (usuario_id, codigo)."""
    resp = test_client.post('/api/usuarios/staff', json={
        "nombre": nombre, "password": "secreta123", "rol": rol,
    })
    assert resp.status_code == 201, resp.text
    return resp.json()["id"], resp.json()["celular"]


def _cliente_como(test_client, identidad):
    """Reapunta el override de get_usuario_actual a otra identidad (el 'sub'
    del JWT), para simular que quien llama es ese usuario."""
    from backend.app import app
    from backend.dependencies import get_usuario_actual
    app.dependency_overrides[get_usuario_actual] = lambda: identidad
    return test_client


def _mock_firebase():
    """Firebase 'configurado' con send_each_for_multicast mockeado. Devuelve
    el mock del envío para poder inspeccionar a qué tokens fue."""
    respuesta = MagicMock()
    respuesta.responses = []
    return patch('firebase_admin.messaging.send_each_for_multicast', return_value=respuesta)


def _crear_comanda(test_client, test_platos):
    return test_client.post('/api/comandas', json={
        "numero_mesa": 1,
        "platos": [{"plato_id": test_platos[0].id, "cantidad": 1}],
    })


# ---------- El caso que el feature existe para resolver ----------

def test_jefe_cocina_real_sin_email_recibe_la_notificacion(test_client, test_db, test_cliente, test_platos, test_mesas):
    """EL test del feature. El cocinero se crea por el camino real (sin
    email, con código de acceso) y registra su token con ese código como
    identidad — igual que su JWT en producción."""
    _, codigo = _crear_staff(test_client, "Chef Real", "jefe_cocina")
    assert test_db.query(Usuario).filter(Usuario.celular == codigo).first().email is None

    _cliente_como(test_client, codigo)
    assert test_client.post('/api/push/registrar', json={"token": TOKEN_A}).status_code == 204

    with patch('backend.utils.push_notifications._obtener_firebase_app', return_value=object()), \
         _mock_firebase() as mock_send, \
         patch('firebase_admin.messaging.MulticastMessage') as mock_msg:
        assert _crear_comanda(test_client, test_platos).status_code == 201

    mock_send.assert_called_once()
    assert mock_msg.call_args.kwargs["tokens"] == [TOKEN_A]


def test_admin_recibe_solo_si_registro_su_token(test_client, test_db, test_cliente, test_platos, test_mesas):
    """El admin es opt-in: sin token no le llega nada; con token (switch
    encendido) sí."""
    with patch('backend.utils.push_notifications._obtener_firebase_app', return_value=object()), \
         _mock_firebase() as mock_send:
        assert _crear_comanda(test_client, test_platos).status_code == 201
    mock_send.assert_not_called()

    test_client.post('/api/push/registrar', json={"token": TOKEN_A})

    with patch('backend.utils.push_notifications._obtener_firebase_app', return_value=object()), \
         _mock_firebase() as mock_send, \
         patch('firebase_admin.messaging.MulticastMessage') as mock_msg:
        assert _crear_comanda(test_client, test_platos).status_code == 201
    mock_send.assert_called_once()
    assert mock_msg.call_args.kwargs["tokens"] == [TOKEN_A]


def test_mozo_con_token_no_recibe_el_aviso(test_client, test_db, test_cliente, test_platos, test_mesas):
    """El aviso es de cocina: un mozo con token registrado no debe recibirlo."""
    _, codigo = _crear_staff(test_client, "Pedro", "mozo")
    _cliente_como(test_client, codigo)
    test_client.post('/api/push/registrar', json={"token": TOKEN_A})

    with patch('backend.utils.push_notifications._obtener_firebase_app', return_value=object()), \
         _mock_firebase() as mock_send:
        assert _crear_comanda(test_client, test_platos).status_code == 201

    mock_send.assert_not_called()


def test_varios_dispositivos_reciben_en_un_solo_envio(test_client, test_db, test_cliente, test_platos, test_mesas):
    """Un cocinero con tablet + celular: ambos tokens en UNA sola llamada a
    Firebase, no una por dispositivo."""
    _, codigo = _crear_staff(test_client, "Chef", "jefe_cocina")
    _cliente_como(test_client, codigo)
    test_client.post('/api/push/registrar', json={"token": TOKEN_A})
    test_client.post('/api/push/registrar', json={"token": TOKEN_B})

    with patch('backend.utils.push_notifications._obtener_firebase_app', return_value=object()), \
         _mock_firebase() as mock_send, \
         patch('firebase_admin.messaging.MulticastMessage') as mock_msg:
        assert _crear_comanda(test_client, test_platos).status_code == 201

    mock_send.assert_called_once()
    assert sorted(mock_msg.call_args.kwargs["tokens"]) == sorted([TOKEN_A, TOKEN_B])


# ---------- Robustez: nunca romper la comanda ----------

def test_comanda_se_crea_sin_ningun_token_registrado(test_client, test_platos, test_mesas):
    assert _crear_comanda(test_client, test_platos).status_code == 201


def test_comanda_se_crea_sin_firebase_configurado(test_client, test_cliente, test_platos, test_mesas):
    """Caso por defecto (nadie configuró Firebase): la app funciona igual."""
    test_client.post('/api/push/registrar', json={"token": TOKEN_A})
    assert _crear_comanda(test_client, test_platos).status_code == 201


def test_comanda_se_crea_aunque_firebase_lance_excepcion(test_client, test_cliente, test_platos, test_mesas):
    test_client.post('/api/push/registrar', json={"token": TOKEN_A})

    with patch('backend.utils.push_notifications._obtener_firebase_app', return_value=object()), \
         patch('firebase_admin.messaging.send_each_for_multicast', side_effect=Exception("Firebase caído")):
        assert _crear_comanda(test_client, test_platos).status_code == 201


def test_notificar_sin_firebase_no_lanza(test_db, test_cliente):
    from backend.utils.push_notifications import notificar_nueva_comanda
    notificar_nueva_comanda(TEST_CLIENTE_ID, numero_mesa=1, comanda_id=999)


# ---------- Registro / baja de tokens ----------

def test_registrar_token_lo_vincula_al_usuario_por_id(test_client, test_db, test_cliente):
    assert test_client.post('/api/push/registrar', json={"token": TOKEN_A}).status_code == 204

    fila = test_db.query(PushSubscription).first()
    assert fila is not None
    assert fila.cliente_id == TEST_CLIENTE_ID
    assert fila.usuario_id == 'usr-admin-001'  # FK, no el 'sub' del JWT


def test_registrar_mismo_token_dos_veces_no_duplica(test_client, test_db, test_cliente):
    test_client.post('/api/push/registrar', json={"token": TOKEN_A})
    test_client.post('/api/push/registrar', json={"token": TOKEN_A})

    assert test_db.query(PushSubscription).filter(PushSubscription.token == TOKEN_A).count() == 1


def test_desregistrar_con_token_borra_solo_ese_dispositivo(test_client, test_db, test_cliente):
    test_client.post('/api/push/registrar', json={"token": TOKEN_A})
    test_client.post('/api/push/registrar', json={"token": TOKEN_B})

    assert test_client.post('/api/push/desregistrar', json={"token": TOKEN_A}).status_code == 204

    quedan = [f.token for f in test_db.query(PushSubscription).all()]
    assert quedan == [TOKEN_B]


def test_desregistrar_sin_token_borra_todos_los_dispositivos(test_client, test_db, test_cliente):
    """El caso del navegador que perdió su localStorage: sin saber qué token
    borrar, la baja sin token da de baja todos — si no, el admin quedaba
    recibiendo avisos sin forma de apagarlos."""
    test_client.post('/api/push/registrar', json={"token": TOKEN_A})
    test_client.post('/api/push/registrar', json={"token": TOKEN_B})

    assert test_client.post('/api/push/desregistrar', json={}).status_code == 204
    assert test_db.query(PushSubscription).count() == 0


def test_estado_refleja_si_hay_dispositivos_registrados(test_client, test_cliente):
    assert test_client.get('/api/push/estado').json()["activo"] is False

    test_client.post('/api/push/registrar', json={"token": TOKEN_A})
    assert test_client.get('/api/push/estado').json()["activo"] is True

    test_client.post('/api/push/desregistrar', json={})
    assert test_client.get('/api/push/estado').json()["activo"] is False


def test_eliminar_usuario_borra_sus_tokens(test_client, test_db, test_cliente):
    """Sin este cascade, los tokens quedaban huérfanos y una cuenta nueva
    podía heredar los avisos del empleado anterior."""
    usuario_id, codigo = _crear_staff(test_client, "Chef", "jefe_cocina")

    _cliente_como(test_client, codigo)
    test_client.post('/api/push/registrar', json={"token": TOKEN_A})
    assert test_db.query(PushSubscription).count() == 1

    _cliente_como(test_client, "admin@test.local")
    assert test_client.delete(f'/api/usuarios/{usuario_id}').status_code in (200, 204)

    assert test_db.query(PushSubscription).count() == 0


# ---------- Seguridad ----------

def test_endpoints_de_push_exigen_sesion(test_client_real_auth, test_cliente):
    """Sin token de sesión, ningún endpoint de push responde — vapid-key
    incluido (su valor no es secreto, pero un endpoint sin auth es lo que
    marca una auditoría)."""
    for metodo, ruta, cuerpo in [
        ("get", '/api/push/vapid-key', None),
        ("get", '/api/push/estado', None),
        ("post", '/api/push/registrar', {"token": TOKEN_A}),
        ("post", '/api/push/desregistrar', {}),
    ]:
        resp = getattr(test_client_real_auth, metodo)(ruta, **({"json": cuerpo} if cuerpo is not None else {}))
        assert resp.status_code == 401, f"{metodo.upper()} {ruta} respondió {resp.status_code}"


def test_no_notifica_a_usuarios_de_otro_restaurante(test_client, test_db, test_cliente, test_platos, test_mesas):
    """Aislamiento multi-tenant: un token de otro cliente_id no debe recibir
    las comandas de este restaurante."""
    from backend.auth import hash_password
    from backend.models import Cliente

    test_db.add(Cliente(id='otro-cliente', nombre='Otro', email='otro@x.com'))
    test_db.add(Usuario(
        id='usr-otro-cocina', cliente_id='otro-cliente', nombre='Chef Ajeno',
        celular='999999', password_hash=hash_password('secreta123'),
        rol='jefe_cocina', estado='activo',
    ))
    test_db.add(PushSubscription(
        cliente_id='otro-cliente', usuario_id='usr-otro-cocina', token='token-ajeno-123456',
    ))
    test_db.commit()

    with patch('backend.utils.push_notifications._obtener_firebase_app', return_value=object()), \
         _mock_firebase() as mock_send:
        assert _crear_comanda(test_client, test_platos).status_code == 201

    mock_send.assert_not_called()
