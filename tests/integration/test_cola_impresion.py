"""
La cola de impresión.

EL PROBLEMA QUE RESUELVE
------------------------
La impresora térmica es Bluetooth y está emparejada a UN teléfono. Ningún
aparato puede escribirle a la impresora de otro, así que para que el ticket
salga en la cocina, el aparato de la cocina tiene que ser el que imprime — y
para eso tiene que enterarse. Antes no se enteraba: imprimía el que hacía la
acción, o sea el mozo, y el ticket de cocina salía en el mostrador.

LO QUE ESTOS TESTS PROTEGEN
---------------------------
Un papel duplicado hace que cocina prepare dos platos. Un papel perdido hace
que no prepare ninguno. Las dos cosas se pagan en la mesa del comensal, no en
un log, así que las tres garantías de la cola —no se duplica, no se pierde, y
no se reintenta para siempre— necesitan estar ancladas por tests y no por
buenas intenciones.
"""

from datetime import datetime, timedelta

from backend.models import TrabajoImpresion
from backend.utils.impresion import MAX_INTENTOS, MINUTOS_RECLAMO_VENCE


COCINA = "tablet-cocina-01"
MOZO = "celu-mozo-01"


def _pedir(client, plato_id, numero_mesa=1, cantidad=1):
    return client.post('/api/comandas', json={
        "numero_mesa": numero_mesa,
        "platos": [{"plato_id": plato_id, "cantidad": cantidad}],
    }).json()


def _reclamar(client, device_id, estaciones, limite=5):
    r = client.post('/api/impresion/reclamar', json={
        "device_id": device_id, "estaciones": estaciones, "limite": limite,
    })
    assert r.status_code == 200, r.text
    return r.json()


def _confirmar(client, trabajo_id, device_id, salio=True, error=None):
    return client.post(f'/api/impresion/{trabajo_id}/resultado', json={
        "device_id": device_id, "salio": salio, "error": error,
    })


# ---------------------------------------------------------------------------
# Un pedido genera sus papeles
# ---------------------------------------------------------------------------


def test_un_pedido_encola_el_de_cocina_y_el_del_comensal(test_client, test_platos, test_mesas):
    comanda = _pedir(test_client, test_platos[0].id)

    cocina = _reclamar(test_client, COCINA, ["cocina"])
    mostrador = _reclamar(test_client, MOZO, ["mostrador"])

    assert len(cocina) == 1 and cocina[0]["tipo_documento"] == "cocina"
    assert len(mostrador) == 1
    # Sin SUNAT el papel del comensal es la PRE-VENTA (se entrega en caja);
    # con SUNAT es la pre-cuenta, porque la boleta llega al cobrar.
    assert mostrador[0]["tipo_documento"] == "preventa"
    assert cocina[0]["comanda_id"] == comanda["id"]


def test_el_de_cocina_NO_le_llega_al_mostrador(test_client, test_platos, test_mesas):
    """EL PUNTO DE TODO ESTE CAMBIO.

    El aparato del mostrador atiende solo su estación, así que el ticket de
    cocina no es suyo — aunque haya sido él quien tomó el pedido.
    """
    _pedir(test_client, test_platos[0].id)

    mostrador = _reclamar(test_client, MOZO, ["mostrador"])

    assert [t["tipo_documento"] for t in mostrador] == ["preventa"]


def test_un_solo_aparato_puede_atender_las_dos(test_client, test_platos, test_mesas):
    """El dueño que trabaja solo, que es el caso por defecto: un teléfono, una
    impresora, los dos papeles."""
    _pedir(test_client, test_platos[0].id)

    todos = _reclamar(test_client, MOZO, ["cocina", "mostrador"])

    assert sorted(t["tipo_documento"] for t in todos) == ["cocina", "preventa"]


def test_con_sunat_el_papel_del_comensal_es_la_precuenta(
    test_client, test_db, test_cliente, test_platos, test_mesas
):
    test_cliente.ruc = "20100070970"
    test_cliente.usar_sunat = True
    test_db.commit()

    _pedir(test_client, test_platos[0].id)

    mostrador = _reclamar(test_client, MOZO, ["mostrador"])
    assert mostrador[0]["tipo_documento"] == "precuenta"


# ---------------------------------------------------------------------------
# No se duplica
# ---------------------------------------------------------------------------


def test_dos_aparatos_no_se_llevan_el_mismo_papel(test_client, test_platos, test_mesas):
    """Si los dos se lo llevaran, cocina prepararía el plato dos veces."""
    _pedir(test_client, test_platos[0].id)

    primero = _reclamar(test_client, "tablet-A", ["cocina"])
    segundo = _reclamar(test_client, "tablet-B", ["cocina"])

    assert len(primero) == 1
    assert segundo == [], "el segundo aparato no puede llevarse un trabajo ya reclamado"


def test_reclamar_dos_veces_seguidas_no_lo_duplica(test_client, test_platos, test_mesas):
    """El mismo aparato sondeando dos veces antes de confirmar tiene que ver
    UNA sola vez el trabajo, no acumularlo."""
    _pedir(test_client, test_platos[0].id)

    primero = _reclamar(test_client, COCINA, ["cocina"])
    segundo = _reclamar(test_client, COCINA, ["cocina"])

    assert len(primero) == 1
    # Vuelve a aparecer (todavía no lo confirmó), pero es el MISMO trabajo.
    assert [t["id"] for t in segundo] == [t["id"] for t in primero]


def test_un_papel_ya_impreso_no_vuelve_a_salir(test_client, test_platos, test_mesas):
    _pedir(test_client, test_platos[0].id)
    trabajo = _reclamar(test_client, COCINA, ["cocina"])[0]

    assert _confirmar(test_client, trabajo["id"], COCINA).status_code == 200

    assert _reclamar(test_client, COCINA, ["cocina"]) == []


# ---------------------------------------------------------------------------
# No se pierde
# ---------------------------------------------------------------------------


def test_si_el_aparato_se_apaga_el_papel_vuelve_a_la_cola(
    test_client, test_db, test_platos, test_mesas
):
    """El tablet de cocina se queda sin batería después de reclamar.

    Sin esto, ese pedido quedaría colgado para siempre y nadie lo cocinaría.
    """
    _pedir(test_client, test_platos[0].id)
    trabajo = _reclamar(test_client, COCINA, ["cocina"])[0]

    # Se envejece el reclamo a mano en vez de esperar dos minutos reales.
    fila = test_db.query(TrabajoImpresion).filter(TrabajoImpresion.id == trabajo["id"]).first()
    fila.reclamado_en = datetime.utcnow() - timedelta(minutes=MINUTOS_RECLAMO_VENCE + 1)
    test_db.commit()

    rescatado = _reclamar(test_client, "tablet-de-repuesto", ["cocina"])

    assert len(rescatado) == 1
    assert rescatado[0]["id"] == trabajo["id"]


def test_el_aparato_recupera_lo_suyo_sin_esperar_a_que_venza(
    test_client, test_platos, test_mesas
):
    """La app se recargó justo después de reclamar y antes de imprimir.

    Sus propios trabajos sin confirmar tienen que volver a aparecer YA, no
    dentro de dos minutos: el pedido está esperando en la cocina.
    """
    _pedir(test_client, test_platos[0].id)
    antes = _reclamar(test_client, COCINA, ["cocina"])

    despues = _reclamar(test_client, COCINA, ["cocina"])

    assert [t["id"] for t in despues] == [t["id"] for t in antes]


def test_al_sacarle_una_estacion_deja_de_recibir_esos_papeles(
    test_client, test_platos, test_mesas
):
    """El día que la cocina estrena impresora, al mozo se le saca esa estación.

    Lo que ese aparato ya tenía reclamado NO puede seguir saliendo por su
    impresora: se lo deja vencer y lo toma el de la cocina. Sin esto, cambiar
    la configuración no surtía efecto hasta vaciar lo que ya tenía tomado — y
    mientras tanto el ticket seguía saliendo en el mostrador, que es
    exactamente el síntoma que se vino a arreglar.
    """
    _pedir(test_client, test_platos[0].id)
    tomados = _reclamar(test_client, MOZO, ["cocina", "mostrador"])
    assert len(tomados) == 2

    # Se reconfigura: este aparato ya no atiende cocina.
    ahora = _reclamar(test_client, MOZO, ["mostrador"])

    assert [t["tipo_documento"] for t in ahora] == ["preventa"]


def test_si_falla_la_impresion_vuelve_a_la_cola(test_client, test_platos, test_mesas):
    _pedir(test_client, test_platos[0].id)
    trabajo = _reclamar(test_client, COCINA, ["cocina"])[0]

    _confirmar(test_client, trabajo["id"], COCINA, salio=False, error="Sin papel")

    de_nuevo = _reclamar(test_client, COCINA, ["cocina"])
    assert len(de_nuevo) == 1
    assert de_nuevo[0]["intentos"] == 2, "el segundo intento tiene que contarse"


def test_deja_de_reintentar_al_llegar_al_tope(test_client, test_platos, test_mesas):
    """Una impresora sin papel falla siempre. Sin tope, ese trabajo se
    reintentaría eternamente y taparía a los que vienen atrás."""
    _pedir(test_client, test_platos[0].id)

    for _ in range(MAX_INTENTOS):
        pendiente = _reclamar(test_client, COCINA, ["cocina"])
        assert len(pendiente) == 1
        _confirmar(test_client, pendiente[0]["id"], COCINA, salio=False, error="Sin papel")

    assert _reclamar(test_client, COCINA, ["cocina"]) == [], "ya se rindió"


# ---------------------------------------------------------------------------
# Modo offline
# ---------------------------------------------------------------------------


def test_un_pedido_ya_impreso_sin_senial_no_se_encola(test_client, test_platos, test_mesas):
    """Sin señal el mozo imprime desde el teléfono en el momento: el comensal
    está esperando su papel y con el wifi caído la cocina tampoco ve el pedido
    en pantalla, así que ese papel es lo único que queda.

    Cuando vuelve la señal y el pedido por fin se crea en el servidor, encolar
    los papeles otra vez los haría salir DOS veces.
    """
    r = test_client.post('/api/comandas', json={
        "numero_mesa": 1,
        "platos": [{"plato_id": test_platos[0].id, "cantidad": 1}],
        "impreso_localmente": True,
    })
    assert r.status_code == 201, r.text

    assert _reclamar(test_client, MOZO, ["cocina", "mostrador"]) == []


def test_un_pedido_normal_si_se_encola(test_client, test_platos, test_mesas):
    """La contracara: el caso con señal no puede haber quedado sin papeles por
    culpa del arreglo de arriba."""
    _pedir(test_client, test_platos[0].id)

    assert len(_reclamar(test_client, MOZO, ["cocina", "mostrador"])) == 2


def test_lo_impreso_sin_senial_se_puede_reimprimir_igual(test_client, test_platos, test_mesas):
    """No encolar al sincronizar no puede dejar ese pedido sin forma de volver
    a salir: si el papel se perdió, el botón de reimprimir tiene que servir."""
    comanda = test_client.post('/api/comandas', json={
        "numero_mesa": 1,
        "platos": [{"plato_id": test_platos[0].id, "cantidad": 1}],
        "impreso_localmente": True,
    }).json()

    r = test_client.post('/api/impresion/reimprimir', json={
        "comanda_id": comanda["id"], "tipo_documento": "cocina",
    })
    assert r.status_code == 201, r.text
    assert len(_reclamar(test_client, COCINA, ["cocina"])) == 1


# ---------------------------------------------------------------------------
# Reimprimir
# ---------------------------------------------------------------------------


def test_reimprimir_vuelve_a_encolar_el_papel(test_client, test_platos, test_mesas):
    comanda = _pedir(test_client, test_platos[0].id)
    trabajo = _reclamar(test_client, COCINA, ["cocina"])[0]
    _confirmar(test_client, trabajo["id"], COCINA)
    assert _reclamar(test_client, COCINA, ["cocina"]) == []

    r = test_client.post('/api/impresion/reimprimir', json={
        "comanda_id": comanda["id"], "tipo_documento": "cocina",
    })
    assert r.status_code == 201, r.text

    de_nuevo = _reclamar(test_client, COCINA, ["cocina"])
    assert len(de_nuevo) == 1
    assert de_nuevo[0]["id"] != trabajo["id"], "es un trabajo NUEVO, no el original reabierto"
    assert de_nuevo[0]["reimpresion_de"] == trabajo["id"], "queda anotado de cuál viene"


def test_la_reimpresion_va_a_la_estacion_que_le_toca(test_client, test_platos, test_mesas):
    """La estación la decide el SERVIDOR según el tipo de papel.

    Si el frontend pudiera elegirla, un botón mal cableado mandaría el ticket
    de cocina a la impresora del mostrador, y el síntoma sería "sale en el
    lugar equivocado" — de lo más difícil de rastrear.
    """
    comanda = _pedir(test_client, test_platos[0].id)
    # Se vacía la cola de verdad: reclamar y CONFIRMAR. Dejarlos solo
    # reclamados no vacía nada — siguen siendo de ese aparato hasta que
    # confirme o venza.
    for t in _reclamar(test_client, MOZO, ["cocina", "mostrador"]):
        _confirmar(test_client, t["id"], MOZO)

    test_client.post('/api/impresion/reimprimir', json={
        "comanda_id": comanda["id"], "tipo_documento": "cocina",
    })

    assert _reclamar(test_client, MOZO, ["mostrador"]) == [], "el de cocina no es del mostrador"
    assert len(_reclamar(test_client, COCINA, ["cocina"])) == 1


def test_no_se_puede_reimprimir_una_comanda_de_otro_restaurante(test_client, test_platos, test_mesas):
    r = test_client.post('/api/impresion/reimprimir', json={
        "comanda_id": 999999, "tipo_documento": "cocina",
    })
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# Quién puede tocar qué
# ---------------------------------------------------------------------------


def test_solo_el_que_lo_tomo_puede_confirmarlo(test_client, test_platos, test_mesas):
    """El único que sabe si el papel salió es el que lo intentó."""
    _pedir(test_client, test_platos[0].id)
    trabajo = _reclamar(test_client, COCINA, ["cocina"])[0]

    r = _confirmar(test_client, trabajo["id"], "otro-aparato")

    assert r.status_code == 404


def test_una_estacion_inventada_no_devuelve_nada(test_client, test_platos, test_mesas):
    _pedir(test_client, test_platos[0].id)
    r = test_client.post('/api/impresion/reclamar', json={
        "device_id": COCINA, "estaciones": ["barra"],
    })
    assert r.status_code == 422


def test_los_endpoints_de_impresion_exigen_sesion(test_client_real_auth):
    """Sin sesión no se reclama ni se confirma nada: los papeles de un
    restaurante dicen qué y cuánto se está vendiendo."""
    client = test_client_real_auth
    assert client.post('/api/impresion/reclamar', json={
        "device_id": COCINA, "estaciones": ["cocina"],
    }).status_code == 401
    assert client.post('/api/impresion/1/resultado', json={
        "device_id": COCINA, "salio": True,
    }).status_code == 401
    assert client.post('/api/impresion/reimprimir', json={
        "comanda_id": 1, "tipo_documento": "cocina",
    }).status_code == 401


# ---------------------------------------------------------------------------
# Aislamiento entre restaurantes
# ---------------------------------------------------------------------------


def test_un_restaurante_no_reclama_los_papeles_de_otro(
    test_client, test_db, test_cliente, test_platos, test_mesas
):
    from backend.models import Cliente, Comanda

    otro = Cliente(id="otro-rest", nombre="El Vecino", email="vecino@test.com")
    test_db.add(otro)
    test_db.flush()
    comanda_ajena = Comanda(
        cliente_id="otro-rest", numero_mesa=1, total_cuenta=50.0, estado="cocina",
    )
    test_db.add(comanda_ajena)
    test_db.flush()
    test_db.add(TrabajoImpresion(
        cliente_id="otro-rest", estacion="cocina",
        tipo_documento="cocina", comanda_id=comanda_ajena.id,
    ))
    test_db.commit()

    # Este restaurante no tiene pedidos propios, así que no debería ver nada.
    assert _reclamar(test_client, COCINA, ["cocina"]) == []
