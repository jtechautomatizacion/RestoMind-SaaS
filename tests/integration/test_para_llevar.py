"""
Pedidos PARA LLEVAR.

CONTEXTO
--------
Hasta ahora todo pedido pertenecía a una mesa. El restaurante también vende
en el mostrador, y quiere poder medir cuánto de cada cosa.

El flujo es distinto y eso es lo que hay que proteger: para llevar SE COBRA AL
PEDIRLO (el cliente paga en el mostrador y espera), así que la comanda nace ya
en 'cobrado'. Eso mantiene intacta la definición de "venta" —las tres
consultas que calculan ingresos siguen filtrando por ese estado— pero rompe la
suposición de que 'cocina' es lo que cocina tiene pendiente. Para esos pedidos
manda `entregado_en`.

LA TRAMPA DEL CERO
------------------
`numero_mesa` vale 0 en un pedido para llevar, porque SQLite no deja relajar
un NOT NULL sobre una tabla con datos. El 0 es seguro porque las mesas se
numeran desde 1, pero eso hay que DEMOSTRARLO, no afirmarlo: si algún día
alguien crea una mesa 0, o una consulta deja de filtrar por número, un pedido
de mostrador aparecería como pedido de mesa. Hay un test dedicado a eso.
"""

from datetime import datetime

from backend.models import Comanda
from tests.integration.test_endpoints import _login_restaurante


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def _pedir_para_llevar(client, token, platos, **extra):
    cuerpo = {"tipo_pedido": "llevar", "platos": platos}
    cuerpo.update(extra)
    return client.post("/api/comandas", json=cuerpo, headers=_auth(token))


# ---------------------------------------------------------------------------
# No toca las mesas
# ---------------------------------------------------------------------------


def test_un_pedido_para_llevar_no_ocupa_ninguna_mesa(
    test_client_real_auth, test_cliente, test_platos, test_mesas
):
    client = test_client_real_auth
    token = _login_restaurante(client)

    antes = {m["numero"]: m["estado"] for m in client.get("/api/mesas", headers=_auth(token)).json()}

    r = _pedir_para_llevar(client, token, [{"plato_id": test_platos[0].id, "cantidad": 1}])
    assert r.status_code == 201, r.text

    despues = {m["numero"]: m["estado"] for m in client.get("/api/mesas", headers=_auth(token)).json()}
    assert despues == antes, "vender para llevar no puede ocupar una mesa"


def test_un_pedido_para_llevar_no_aparece_bajo_el_numero_de_una_mesa(
    test_client_real_auth, test_cliente, test_platos, test_mesas
):
    """LA TRAMPA DEL CERO, al derecho.

    Un pedido para llevar se identifica por su `id`, y una mesa por su
    `numero`. Son campos distintos que comparten espacio de números: existe un
    pedido para llevar con id 2 y existe la mesa 2. Si algo confundiera uno con
    otro, el mostrador entraría en la cuenta de un comensal — y esa cuenta se
    cobraría mal.

    Se fuerza la colisión a propósito en vez de confiar en que no pase.
    """
    client = test_client_real_auth
    token = _login_restaurante(client)

    # Primero la mesa, para que su comanda se lleve el id 1.
    r_mesa = client.post("/api/comandas", json={
        "numero_mesa": 2, "platos": [{"plato_id": test_platos[0].id, "cantidad": 1}],
    }, headers=_auth(token))
    assert r_mesa.status_code == 201, r_mesa.text
    total_solo_mesa = r_mesa.json()["total_cuenta"]

    # Después varios para llevar: alguno va a quedar con id 2, el mismo número
    # que la mesa de arriba.
    ids_llevar = []
    for _ in range(4):
        r = _pedir_para_llevar(client, token, [{"plato_id": test_platos[0].id, "cantidad": 2}])
        assert r.status_code == 201, r.text
        ids_llevar.append(r.json()["id"])
    assert 2 in ids_llevar, "el test no sirve si no se produjo la colisión que quiere probar"

    comandas_mesa_2 = [
        c for c in client.get("/api/comandas", headers=_auth(token)).json()
        if c["numero_mesa"] == 2
    ]
    assert comandas_mesa_2, "la comanda de la mesa 2 tiene que seguir ahí"
    assert all(c["tipo_pedido"] == "mesa" for c in comandas_mesa_2), (
        "ningún pedido para llevar puede aparecer bajo un número de mesa"
    )
    assert sum(c["total_cuenta"] for c in comandas_mesa_2) == total_solo_mesa


def test_un_pedido_de_mesa_sin_numero_se_rechaza(
    test_client_real_auth, test_cliente, test_platos, test_mesas
):
    """La contracara: `numero_mesa` es opcional en el schema para no tener que
    mandarlo en un pedido para llevar. Eso no puede volver opcional la mesa de
    un pedido DE MESA."""
    client = test_client_real_auth
    token = _login_restaurante(client)

    r = client.post("/api/comandas", json={
        "tipo_pedido": "mesa", "platos": [{"plato_id": test_platos[0].id, "cantidad": 1}],
    }, headers=_auth(token))
    assert r.status_code == 422, r.text


# ---------------------------------------------------------------------------
# El dinero
# ---------------------------------------------------------------------------


def test_nace_cobrado_y_cuenta_como_venta(
    test_client_real_auth, test_cliente, test_platos, test_mesas
):
    """Se paga al pedirlo, así que la venta entra en el momento.

    Si naciera en 'cocina', el dinero ya estaría en la caja pero no en ningún
    reporte hasta que alguien lo cerrara a mano — y nadie lo va a cerrar,
    porque no hay mesa que cobrar.
    """
    client = test_client_real_auth
    token = _login_restaurante(client)

    r = _pedir_para_llevar(client, token, [{"plato_id": test_platos[0].id, "cantidad": 2}])
    assert r.status_code == 201, r.text
    assert r.json()["estado"] == "cobrado"

    resumen = client.get("/api/dashboard/resumen?dias=1", headers=_auth(token)).json()
    assert resumen["totales"]["ventas"] >= r.json()["total_cuenta"]


def test_el_dashboard_separa_salon_de_mostrador(
    test_client_real_auth, test_cliente, test_platos, test_mesas
):
    """El reporte que se pidió: cuánto se vende en cada canal."""
    client = test_client_real_auth
    token = _login_restaurante(client)

    llevar = _pedir_para_llevar(client, token, [{"plato_id": test_platos[0].id, "cantidad": 3}])
    assert llevar.status_code == 201, llevar.text

    resumen = client.get("/api/dashboard/resumen?dias=1", headers=_auth(token)).json()
    por_tipo = {f["tipo"]: f for f in resumen["por_tipo_pedido"]}

    # Las dos filas siempre, aunque una esté en cero: un restaurante que aún no
    # vendió para llevar tiene que ver el renglón para saber que existe.
    assert set(por_tipo) == {"mesa", "llevar"}
    assert por_tipo["llevar"]["pedidos"] == 1
    assert por_tipo["llevar"]["total"] == llevar.json()["total_cuenta"]


# ---------------------------------------------------------------------------
# Cocina
# ---------------------------------------------------------------------------


def test_cocina_lo_ve_aunque_ya_este_cobrado(
    test_client_real_auth, test_cliente, test_platos, test_mesas
):
    """El que paga en el mostrador igual espera su comida.

    Este es el riesgo concreto de que nazca 'cobrado': el monitor de cocina
    filtraba por estado, así que un pedido pagado habría sido invisible y no se
    habría preparado nunca.
    """
    client = test_client_real_auth
    token = _login_restaurante(client)

    r = _pedir_para_llevar(client, token, [{"plato_id": test_platos[0].id, "cantidad": 1}])
    pedido_id = r.json()["id"]

    en_cocina = client.get("/api/monitor/cocina", headers=_auth(token)).json()
    assert pedido_id in [c["id"] for c in en_cocina]


def test_deja_de_verse_en_cocina_al_entregarlo(
    test_client_real_auth, test_cliente, test_platos, test_mesas
):
    client = test_client_real_auth
    token = _login_restaurante(client)

    r = _pedir_para_llevar(client, token, [{"plato_id": test_platos[0].id, "cantidad": 1}])
    pedido_id = r.json()["id"]

    entrega = client.patch(f"/api/comandas/{pedido_id}/estado",
                           json={"estado": "entregado"}, headers=_auth(token))
    assert entrega.status_code == 200, entrega.text

    en_cocina = client.get("/api/monitor/cocina", headers=_auth(token)).json()
    assert pedido_id not in [c["id"] for c in en_cocina]


def test_entregarlo_no_lo_descuenta_de_las_ventas(
    test_client_real_auth, test_cliente, test_platos, test_mesas, test_db
):
    """Entregar es logística, no plata: el estado 'cobrado' no se toca.

    Si marcar "Listo" moviera el estado, la venta desaparecería del día y la
    caja no cuadraría por un pedido que sí se cobró.
    """
    client = test_client_real_auth
    token = _login_restaurante(client)

    r = _pedir_para_llevar(client, token, [{"plato_id": test_platos[0].id, "cantidad": 1}])
    pedido_id = r.json()["id"]
    ventas_antes = client.get("/api/dashboard/resumen?dias=1", headers=_auth(token)).json()["totales"]["ventas"]

    client.patch(f"/api/comandas/{pedido_id}/estado", json={"estado": "entregado"}, headers=_auth(token))

    ventas_despues = client.get("/api/dashboard/resumen?dias=1", headers=_auth(token)).json()["totales"]["ventas"]
    assert ventas_despues == ventas_antes

    comanda = test_db.query(Comanda).filter(Comanda.id == pedido_id).first()
    assert comanda.estado == "cobrado"
    assert isinstance(comanda.entregado_en, datetime)


def test_entregar_dos_veces_no_pisa_la_hora_original(
    test_client_real_auth, test_cliente, test_platos, test_mesas, test_db
):
    """Dos toques al botón "Listo" no pueden reescribir cuándo se entregó."""
    client = test_client_real_auth
    token = _login_restaurante(client)

    pedido_id = _pedir_para_llevar(client, token, [{"plato_id": test_platos[0].id, "cantidad": 1}]).json()["id"]

    client.patch(f"/api/comandas/{pedido_id}/estado", json={"estado": "entregado"}, headers=_auth(token))
    test_db.expire_all()
    primera = test_db.query(Comanda).filter(Comanda.id == pedido_id).first().entregado_en

    client.patch(f"/api/comandas/{pedido_id}/estado", json={"estado": "entregado"}, headers=_auth(token))
    test_db.expire_all()
    segunda = test_db.query(Comanda).filter(Comanda.id == pedido_id).first().entregado_en

    assert primera == segunda


# ---------------------------------------------------------------------------
# Multi-tenant
# ---------------------------------------------------------------------------


def test_un_restaurante_no_ve_los_pedidos_para_llevar_de_otro(
    test_client_real_auth, test_cliente, test_platos, test_mesas, test_db
):
    """La regla de toda la app: el aislamiento no lo afloja una función nueva."""
    from backend.models import Cliente

    client = test_client_real_auth
    token = _login_restaurante(client)

    pedido_id = _pedir_para_llevar(client, token, [{"plato_id": test_platos[0].id, "cantidad": 1}]).json()["id"]

    otro = Cliente(id="otro-rest", nombre="Otro", email="otro@ejemplo.com")
    test_db.add(otro)
    test_db.commit()

    ajenas = test_db.query(Comanda).filter(Comanda.cliente_id == "otro-rest").all()
    assert pedido_id not in [c.id for c in ajenas]
    assert ajenas == []
