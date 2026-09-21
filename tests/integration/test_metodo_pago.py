"""
EFECTIVO contra YAPE/PLIN.

POR QUÉ IMPORTA
---------------
La caja cuenta dinero FÍSICO. Hasta ahora el sistema sumaba toda venta cobrada
al saldo esperado, sin importar cómo se pagó, porque no tenía forma de saberlo
— una simplificación que el propio docstring de CierreCaja dejaba anotada como
deuda. En un restaurante que cobra por Yape eso no era un detalle: el arqueo
arrastraba un faltante del tamaño exacto de lo cobrado por Yape, y el sistema
lo reportaba como discrepancia GRAVE. Es decir, marcaba como sospechoso el
caso normal, que es la forma más rápida de que alguien deje de mirar las
alertas.

LO QUE ESTOS TESTS PROTEGEN
---------------------------
1. Que el saldo esperado cuente SOLO efectivo (el corazón del cambio).
2. Que Yape siga siendo una venta a todos los demás efectos (dashboard,
   total vendido) — separar no puede significar desaparecer.
3. Que lo que no declara método siga contando como efectivo. De eso depende
   que ningún turno YA CERRADO cambie de significado hacia atrás, y que un
   APK viejo pueda seguir cobrando mientras el servidor ya se actualizó.
"""

import pytest

from backend.models import Comanda


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def _comanda_en_mesa(client, plato_id, numero_mesa=1, cantidad=1):
    """Crea una comanda de mesa y la deja entregada (lista para cobrar)."""
    comanda = client.post('/api/comandas', json={
        "numero_mesa": numero_mesa,
        "platos": [{"plato_id": plato_id, "cantidad": cantidad}],
    }).json()
    client.patch(f'/api/comandas/{comanda["id"]}/estado', json={"estado": "entregado"})
    return comanda


def _id_de_mesa(client, numero):
    mesas = client.get('/api/mesas').json()
    return next(m for m in mesas if m["numero"] == numero)["id"]


# ---------------------------------------------------------------------------
# Cobro de mesa
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("metodo", ["efectivo", "yape"])
def test_cobrar_una_mesa_guarda_con_que_se_pago(test_client, test_platos, test_mesas, metodo):
    _comanda_en_mesa(test_client, test_platos[0].id)

    resp = test_client.post(f'/api/mesas/{_id_de_mesa(test_client, 1)}/cobrar',
                            json={"metodo_pago": metodo})

    assert resp.status_code == 200, resp.text
    assert resp.json()["metodo_pago"] == metodo


def test_cobrar_sin_decir_nada_queda_en_efectivo(test_client, test_platos, test_mesas):
    """Un APK viejo cobra sin mandar cuerpo y tiene que seguir funcionando.

    Que el restaurante no pueda cobrar porque el servidor se actualizó antes
    que su teléfono sería un costo desproporcionado para ganar un dato. Queda
    'efectivo', que es lo que el sistema asumía de TODAS las ventas hasta
    ahora: el turno no cambia de resultado.
    """
    _comanda_en_mesa(test_client, test_platos[0].id)

    resp = test_client.post(f'/api/mesas/{_id_de_mesa(test_client, 1)}/cobrar')

    assert resp.status_code == 200, resp.text
    assert resp.json()["metodo_pago"] == "efectivo"


def test_el_metodo_queda_en_todas_las_comandas_de_la_mesa(
    test_client, test_db, test_platos, test_mesas
):
    """La mesa se cobra de una sola vez y con un solo pago."""
    _comanda_en_mesa(test_client, test_platos[0].id, cantidad=1)
    _comanda_en_mesa(test_client, test_platos[1].id, cantidad=2)

    test_client.post(f'/api/mesas/{_id_de_mesa(test_client, 1)}/cobrar',
                     json={"metodo_pago": "yape"})

    cobradas = test_db.query(Comanda).filter(Comanda.numero_mesa == 1).all()
    assert len(cobradas) == 2
    assert {c.metodo_pago for c in cobradas} == {"yape"}


def test_un_metodo_inventado_se_rechaza(test_client, test_platos, test_mesas):
    """Sin esto, un typo entra a la BD y rompe el desglose en silencio:
    'efectvo' no es 'yape', así que caería del lado del efectivo y el arqueo
    pediría contar plata que está en un celular."""
    _comanda_en_mesa(test_client, test_platos[0].id)

    resp = test_client.post(f'/api/mesas/{_id_de_mesa(test_client, 1)}/cobrar',
                            json={"metodo_pago": "bitcoin"})

    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Para llevar (nace cobrado)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("metodo", ["efectivo", "yape"])
def test_para_llevar_guarda_el_metodo_al_pedirlo(test_client, test_platos, test_mesas, metodo):
    """Para llevar se paga en el mostrador al pedirlo, así que el método se
    conoce en ese mismo momento — no hay un cobro posterior donde preguntarlo."""
    resp = test_client.post('/api/comandas', json={
        "tipo_pedido": "llevar",
        "metodo_pago": metodo,
        "platos": [{"plato_id": test_platos[0].id, "cantidad": 1}],
    })

    assert resp.status_code == 201, resp.text
    assert resp.json()["estado"] == "cobrado"
    assert resp.json()["metodo_pago"] == metodo


def test_para_llevar_sin_metodo_queda_en_efectivo(test_client, test_platos, test_mesas):
    """Igual que el cobro de mesa: un cliente viejo tiene que poder vender."""
    resp = test_client.post('/api/comandas', json={
        "tipo_pedido": "llevar",
        "platos": [{"plato_id": test_platos[0].id, "cantidad": 1}],
    })

    assert resp.status_code == 201, resp.text
    assert resp.json()["metodo_pago"] == "efectivo"


def test_un_pedido_de_mesa_no_puede_declarar_metodo_al_crearse(
    test_client, test_platos, test_mesas
):
    """Todavía no se cobró nada: aceptarlo dejaría una comanda en 'cocina' con
    método de pago, y de ahí a contarla como venta hay un paso."""
    resp = test_client.post('/api/comandas', json={
        "numero_mesa": 1,
        "metodo_pago": "yape",
        "platos": [{"plato_id": test_platos[0].id, "cantidad": 1}],
    })

    assert resp.status_code == 422


def test_una_comanda_sin_cobrar_no_tiene_metodo(test_client, test_platos, test_mesas):
    """NULL acá significa "todavía no se pagó", no "no se sabe"."""
    resp = test_client.post('/api/comandas', json={
        "numero_mesa": 1,
        "platos": [{"plato_id": test_platos[0].id, "cantidad": 1}],
    })

    assert resp.json()["estado"] == "cocina"
    assert resp.json()["metodo_pago"] is None


# ---------------------------------------------------------------------------
# CAJA — lo que de verdad cambia
# ---------------------------------------------------------------------------


def test_el_yape_no_entra_al_efectivo_que_hay_que_contar(
    test_client, test_platos, test_mesas
):
    """EL TEST CENTRAL DE TODO ESTE CAMBIO.

    Dos ventas iguales, una en efectivo y otra por Yape. En el cajón tiene que
    esperarse SOLO la de efectivo; la otra se informa aparte. Antes las dos
    sumaban al saldo esperado y la caja cerraba con un faltante igual al monto
    cobrado por Yape.
    """
    test_client.post('/api/caja/abrir', json={"saldo_inicial": 100.0})

    _comanda_en_mesa(test_client, test_platos[0].id, numero_mesa=1)   # 45.00
    test_client.post(f'/api/mesas/{_id_de_mesa(test_client, 1)}/cobrar',
                     json={"metodo_pago": "efectivo"})

    _comanda_en_mesa(test_client, test_platos[0].id, numero_mesa=2)   # 45.00
    test_client.post(f'/api/mesas/{_id_de_mesa(test_client, 2)}/cobrar',
                     json={"metodo_pago": "yape"})

    estado = test_client.get('/api/caja/estado').json()

    assert estado["ventas_efectivo_hasta_ahora"] == 45.0
    assert estado["ventas_yape_hasta_ahora"] == 45.0
    # El total vendido sigue siendo todo lo vendido: separar no es esconder.
    assert estado["ventas_hasta_ahora"] == 90.0


def test_la_caja_cuadra_contando_solo_el_efectivo(test_client, test_platos, test_mesas):
    """El cierre completo, que es donde el bug se pagaba caro.

    Se abre con 100, se cobran 45 en efectivo y 45 por Yape. El admin cuenta
    145 en el cajón (100 + 45), que es exactamente lo que hay. Tiene que dar
    CUADRADO. Con la lógica anterior el sistema esperaba 190 y lo marcaba como
    discrepancia grave de -45.
    """
    test_client.post('/api/caja/abrir', json={"saldo_inicial": 100.0})

    _comanda_en_mesa(test_client, test_platos[0].id, numero_mesa=1)
    test_client.post(f'/api/mesas/{_id_de_mesa(test_client, 1)}/cobrar',
                     json={"metodo_pago": "efectivo"})

    _comanda_en_mesa(test_client, test_platos[0].id, numero_mesa=2)
    test_client.post(f'/api/mesas/{_id_de_mesa(test_client, 2)}/cobrar',
                     json={"metodo_pago": "yape"})

    cierre = test_client.post('/api/caja/cerrar', json={"saldo_contado": 145.0}).json()

    assert cierre["saldo_esperado"] == 145.0
    assert cierre["diferencia"] == 0.0
    assert cierre["estado"] == "cuadrado"
    # El Yape queda registrado en el turno, fuera del arqueo.
    assert cierre["ventas_cobradas"] == 45.0
    assert cierre["ventas_yape"] == 45.0


def test_una_venta_vieja_sin_metodo_sigue_contando_como_efectivo(
    test_client, test_db, test_platos, test_mesas
):
    """Protege el historial.

    Las comandas cobradas ANTES de que existiera la columna quedaron en
    'efectivo' por migración, pero si alguna se cuela en NULL no puede
    desaparecer del arqueo: el turno pasaría a figurar con un faltante que
    nunca ocurrió. Se simula poniendo el NULL a mano.
    """
    test_client.post('/api/caja/abrir', json={"saldo_inicial": 0.0})

    _comanda_en_mesa(test_client, test_platos[0].id, numero_mesa=1)
    test_client.post(f'/api/mesas/{_id_de_mesa(test_client, 1)}/cobrar')

    comanda = test_db.query(Comanda).filter(Comanda.numero_mesa == 1).first()
    comanda.metodo_pago = None
    test_db.commit()

    estado = test_client.get('/api/caja/estado').json()

    assert estado["ventas_efectivo_hasta_ahora"] == 45.0
    assert estado["ventas_yape_hasta_ahora"] == 0.0


def test_cobrar_una_comanda_suelta_queda_en_efectivo(
    test_client, test_db, test_platos, test_mesas
):
    """PATCH /comandas/{id}/estado cobra sin pasar por la pantalla de cobro,
    así que nadie eligió método. Tiene que quedar en efectivo, no en NULL:
    NULL cuenta igual hoy, pero deja el dato sin explicación para siempre."""
    comanda = _comanda_en_mesa(test_client, test_platos[0].id)

    test_client.patch(f'/api/comandas/{comanda["id"]}/estado', json={"estado": "cobrado"})

    guardada = test_db.query(Comanda).filter(Comanda.id == comanda["id"]).first()
    assert guardada.estado == "cobrado"
    assert guardada.metodo_pago == "efectivo"


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------


def test_el_dashboard_separa_efectivo_de_yape(test_client, test_platos, test_mesas):
    _comanda_en_mesa(test_client, test_platos[0].id, numero_mesa=1)   # 45.00
    test_client.post(f'/api/mesas/{_id_de_mesa(test_client, 1)}/cobrar',
                     json={"metodo_pago": "efectivo"})

    test_client.post('/api/comandas', json={
        "tipo_pedido": "llevar",
        "metodo_pago": "yape",
        "platos": [{"plato_id": test_platos[1].id, "cantidad": 2}],   # 10.00
    })

    resumen = test_client.get('/api/dashboard/resumen?dias=1').json()
    por_metodo = {f["tipo"]: f for f in resumen["por_metodo_pago"]}

    # Las dos filas siempre, aunque una esté en cero: un restaurante que aún no
    # cobró por Yape tiene que ver el renglón para saber que puede.
    assert set(por_metodo) == {"efectivo", "yape"}
    assert por_metodo["efectivo"]["total"] == 45.0
    assert por_metodo["yape"]["total"] == 10.0

    # La suma de las partes es el total vendido. Si esto se rompe, el dueño ve
    # dos pantallas que se contradicen y deja de confiar en las dos.
    assert por_metodo["efectivo"]["total"] + por_metodo["yape"]["total"] == \
        resumen["totales"]["ventas"]


def test_sin_ventas_las_dos_filas_siguen_estando(test_client, test_platos, test_mesas):
    resumen = test_client.get('/api/dashboard/resumen?dias=1').json()
    por_metodo = {f["tipo"]: f["total"] for f in resumen["por_metodo_pago"]}

    assert por_metodo == {"efectivo": 0.0, "yape": 0.0}
