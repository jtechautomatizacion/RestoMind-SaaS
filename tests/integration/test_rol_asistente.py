"""
El rol 'asistente' y quién opera en modo "Todo en uno".

CONTEXTO
--------
RestoMind tenía cuatro roles: admin, mozo, cajero, jefe_cocina. La Vista
Unificada (Mesas + Cocina + Cobro en tres columnas) se ofrecía a quien
cumpliera "ve Mesas Y ve Cocina" — una regla DERIVADA, que metía adentro a
cuentas que nadie había decidido meter: una `cajero,jefe_cocina` existe
para que UNA persona cubra dos estaciones mientras OTRAS trabajan la sala,
y ahí una vista de tres columnas por cabeza es un riesgo concreto (dos
personas cobrando la misma mesa desde dos pantallas distintas).

'asistente' es la cuenta de quien atiende SOLO sin ser el dueño: cubre las
tres estaciones, opera en "Todo en uno", y NO ve Dashboard ni
Administración — los números del negocio y la configuración fiscal siguen
siendo del admin.

Lo que se prueba acá es la frontera: qué alcanza, qué no, y que no se pueda
armar una cuenta ambigua.
"""

import pytest

from backend.utils.roles import (
    ROLES_EXCLUSIVOS,
    ROLES_STAFF,
    ROLES_VISTA_UNIFICADA,
    ve_vista_unificada,
)
from tests.integration.test_endpoints import _crear_staff_y_loguear, _login_restaurante


# ---------------------------------------------------------------------------
# Quién opera en "Todo en uno"
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("rol_en_bd, esperado", [
    ("admin", True),              # el dueño que atiende solo
    ("asistente", True),          # personal de confianza que atiende solo
    ("mozo", False),
    ("cajero", False),
    ("jefe_cocina", False),
    # EL caso que motivó el cambio: cumple "ve Mesas Y ve Cocina", así que
    # la regla derivada vieja la dejaba pasar. Es una cuenta de trabajo en
    # equipo, no de trabajo solitario.
    ("cajero,jefe_cocina", False),
    ("mozo,jefe_cocina", False),
])
def test_solo_admin_y_asistente_operan_en_todo_en_uno(rol_en_bd, esperado):
    assert ve_vista_unificada(rol_en_bd) is esperado


def test_la_lista_de_vista_unificada_es_explicita_no_derivada():
    """Si alguien vuelve a derivarla de las pestañas, este test lo dice: la
    regla es una lista cerrada de roles, y el frontend tiene su espejo en
    ROLES_VISTA_UNIFICADA (app.js). Los dos lados deben decir lo mismo."""
    assert set(ROLES_VISTA_UNIFICADA) == {"admin", "asistente"}


# ---------------------------------------------------------------------------
# La cuenta: qué se puede crear y qué no
# ---------------------------------------------------------------------------


def test_se_puede_crear_una_cuenta_de_asistente(test_client_real_auth, test_cliente):
    creado, token = _crear_staff_y_loguear(test_client_real_auth, "Rosa Asistente", ["asistente"])
    assert creado["roles"] == ["asistente"]
    assert creado["celular"], "el backend genera el código de acceso"
    assert token


def test_asistente_no_se_combina_con_otros_roles(test_client_real_auth, test_cliente):
    """
    'asistente' ya cubre mesas + cocina + cobro. Combinarlo no agrega
    permisos y sí crea una cuenta ambigua: le toca la vista de "Todo en
    uno", o la enfocada? Se rechaza en la validación en vez de resolverse
    con una regla de desempate que nadie va a recordar dentro de un año.
    """
    token_admin = _login_restaurante(test_client_real_auth)
    for combinacion in (["asistente", "mozo"], ["cajero", "asistente"],
                        ["asistente", "mozo", "jefe_cocina"]):
        resp = test_client_real_auth.post("/api/usuarios/staff", json={
            "nombre": "Cuenta Ambigua", "password": "clave123", "roles": combinacion,
        }, headers={"Authorization": f"Bearer {token_admin}"})
        assert resp.status_code == 422, f"{combinacion} -> {resp.status_code}"


def test_la_regla_de_exclusividad_esta_declarada_una_sola_vez():
    """El backend valida contra ROLES_EXCLUSIVOS y el frontend pinta los
    switches con su espejo (ROLES_EXCLUSIVOS_UI en admin.js). Si alguien
    agrega otro rol exclusivo, tiene que tocar los dos."""
    assert ROLES_EXCLUSIVOS == ("asistente",)
    assert "asistente" in ROLES_STAFF


def test_un_asistente_existente_se_puede_editar_sin_romperse(test_client_real_auth, test_cliente):
    """El pattern de 'rol' (valor único) en los schemas no incluía el rol
    nuevo: sin eso, editarle el NOMBRE a un asistente devolvía 422 y la
    cuenta quedaba imposible de administrar."""
    creado, _ = _crear_staff_y_loguear(test_client_real_auth, "Rosa Asistente", ["asistente"])
    token_admin = _login_restaurante(test_client_real_auth)

    resp = test_client_real_auth.patch(
        f"/api/usuarios/{creado['id']}",
        json={"nombre": "Rosa Quispe"},
        headers={"Authorization": f"Bearer {token_admin}"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["roles"] == ["asistente"]


# ---------------------------------------------------------------------------
# La frontera de permisos: es personal, NO es el dueño
# ---------------------------------------------------------------------------


def test_el_asistente_NO_ve_el_dinero_ni_la_administracion(test_client_real_auth, test_cliente):
    """
    EL test de esta sección, y el que justifica que 'asistente' sea un rol
    aparte en vez de "admin sin algunas pestañas".

    Atiende toda la sala, pero las ganancias, los gastos, la caja, la
    gestión de cuentas y la configuración fiscal son del dueño. Si alguna
    de estas rutas deja de dar 403, el rol dejó de ser lo que dice ser.
    """
    _, token = _crear_staff_y_loguear(test_client_real_auth, "Rosa Asistente", ["asistente"])
    headers = {"Authorization": f"Bearer {token}"}

    for ruta in (
        "/api/dashboard/resumen",     # ganancias, márgenes, top de platos
        "/api/caja/estado",           # saldo y arqueo
        "/api/usuarios",              # gestión de cuentas
        "/api/facturas",              # historial de comprobantes
        "/api/facturas/pendientes",
        "/api/configuracion",         # RUC, certificado, switch de SUNAT
    ):
        assert test_client_real_auth.get(ruta, headers=headers).status_code == 403, ruta


def test_el_asistente_SI_atiende_mesas_y_cocina(test_client_real_auth, test_cliente, test_mesas):
    """La contracara: el rol tiene que servir para trabajar. Si esto falla,
    se creó una cuenta que no puede hacer nada."""
    _, token = _crear_staff_y_loguear(test_client_real_auth, "Rosa Asistente", ["asistente"])
    headers = {"Authorization": f"Bearer {token}"}

    assert test_client_real_auth.get("/api/mesas", headers=headers).status_code == 200
    assert test_client_real_auth.get("/api/platos", headers=headers).status_code == 200
    assert test_client_real_auth.get("/api/monitor/cocina", headers=headers).status_code == 200

    # Las comandas entregadas son la tercera fuente de "Todo en uno": con ellas
    # se arma la columna "Esperando la cuenta". Sin este acceso, el asistente
    # vería las mesas y la cocina pero NUNCA a quién cobrarle — y el síntoma
    # sería una columna vacía, que se lee como "no hay nadie esperando" en vez
    # de como una falta de permisos.
    assert test_client_real_auth.get(
        "/api/comandas?estado=entregado", headers=headers
    ).status_code == 200

    # El gate de caja es para CUALQUIER rol (mozo y cocina necesitan saber
    # si pueden operar) y nunca devuelve montos — ver CLAUDE.md.
    gate = test_client_real_auth.get("/api/caja/gate", headers=headers)
    assert gate.status_code == 200
    assert "saldo" not in str(gate.json())


def test_el_asistente_recibe_el_aviso_de_cocina(test_db, test_cliente):
    """Entra por la misma puerta que jefe_cocina —cubre la cocina— y es
    quien más lo necesita: atiende solo, así que mientras toma un pedido en
    la sala no hay nadie mirando la pantalla de cocina."""
    from backend.auth import hash_password
    from backend.models import PushSubscription, Usuario
    from backend.utils.push_notifications import _tokens_a_notificar

    test_db.add(Usuario(
        id="u-asis", cliente_id=test_cliente.id, nombre="Rosa", email=None,
        celular="777001", password_hash=hash_password("clave123"),
        rol="asistente", estado="activo",
    ))
    test_db.flush()
    test_db.add(PushSubscription(
        cliente_id=test_cliente.id, usuario_id="u-asis", token="tok-asistente",
    ))
    test_db.commit()

    assert "tok-asistente" in _tokens_a_notificar(test_db, test_cliente.id)


def test_un_mozo_puro_sigue_sin_recibir_el_aviso_de_cocina(test_db, test_cliente):
    """Contracara del anterior: agregar 'asistente' al filtro no puede
    haber abierto la puerta a todo el staff."""
    from backend.auth import hash_password
    from backend.models import PushSubscription, Usuario
    from backend.utils.push_notifications import _tokens_a_notificar

    test_db.add(Usuario(
        id="u-mozo", cliente_id=test_cliente.id, nombre="Pedro", email=None,
        celular="777002", password_hash=hash_password("clave123"),
        rol="mozo", estado="activo",
    ))
    test_db.flush()
    test_db.add(PushSubscription(
        cliente_id=test_cliente.id, usuario_id="u-mozo", token="tok-mozo",
    ))
    test_db.commit()

    assert "tok-mozo" not in _tokens_a_notificar(test_db, test_cliente.id)


def test_el_asistente_de_OTRO_restaurante_no_ve_estas_mesas(
    test_client_real_auth, test_db, test_cliente, test_mesas
):
    """La regla que CLAUDE.md marca como crítica, aplicada al rol nuevo: un
    rol más amplio no afloja el aislamiento multi-tenant."""
    from backend.auth import hash_password
    from backend.models import Cliente, Usuario

    test_db.add(Cliente(id="otro-rest", nombre="Otro", email="otro@x.com"))
    test_db.flush()
    test_db.add(Usuario(
        id="u-asis-otro", cliente_id="otro-rest", nombre="Ajena", email=None,
        celular="777003", password_hash=hash_password("clave123"),
        rol="asistente", estado="activo",
    ))
    test_db.commit()

    login = test_client_real_auth.post("/api/auth/login-staff", json={
        "celular": "777003", "password": "clave123",
    })
    assert login.status_code == 200, login.text
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    mesas = test_client_real_auth.get("/api/mesas", headers=headers)
    assert mesas.status_code == 200
    assert mesas.json() == [], "vio mesas de un restaurante que no es el suyo"
