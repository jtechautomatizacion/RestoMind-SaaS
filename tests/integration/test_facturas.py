"""
Tests de facturación SUNAT.

El sistema es 100% nube: el comprobante se firma y se envía desde el
servidor vía sunat-service. El emisor local (Facturador de escritorio +
archivos .cab/.det + agente de PowerShell) se eliminó, y con él los tests
que verificaban la estructura de esos archivos planos.

Lo que se prueba acá es LA LÓGICA DE NEGOCIO de RestoMind: qué comprobante
corresponde, qué se rechaza, los correlativos por serie, y que el detalle
salga de la comanda real y no de lo que mande el frontend.

El envío a SUNAT se sustituye por un doble: pegarle a SUNAT de verdad en un
test sería lento, dependiente de la red y emitiría comprobantes reales.
"""

import pytest

from backend.config import settings
from backend.models import Factura
from backend.utils.facturacion_pe import FacturacionPeError, FacturacionPeResultado
from backend.utils.sunat_cloud import SunatCloudError, SunatCloudResultado


@pytest.fixture
def cliente_con_ruc(test_db, test_cliente):
    """El fixture test_cliente no trae RUC — la mayoría de tests de facturas
    lo necesitan configurado (es la primera validación del endpoint).

    usar_sunat=True porque este fixture representa un restaurante que SÍ
    emite desde RestoMind: tener RUC y emitir son dos cosas distintas (ver
    tests/integration/test_configuracion.py)."""
    test_cliente.ruc = "10200812234"
    test_cliente.razon_social = "Pollería Fogones"
    test_cliente.usar_sunat = True
    test_db.commit()
    return test_cliente


@pytest.fixture
def regimen_general(test_db, cliente_con_ruc):
    """Restaurante que SÍ puede emitir facturas (Régimen Especial, MYPE o
    General). El default del sistema es lo contrario —Nuevo RUS, solo
    boletas— así que los tests del camino F001 lo piden explícito: hace
    visible de qué depende cada uno."""
    cliente_con_ruc.emite_facturas = True
    test_db.commit()
    return cliente_con_ruc


@pytest.fixture
def emisor_cloud(monkeypatch):
    """
    Emisión en la nube que siempre acepta.

    Se parchea el nombre TAL COMO lo importó routes/facturas.py
    (emitir_boleta_cloud), no el del módulo de origen: el import por valor
    ya copió la referencia y parchear el origen no tendría efecto.

    settings es un singleton importado en todo el código, así que
    monkeypatch.setattr sobre el OBJETO es lo que garantiza el rollback.
    """
    monkeypatch.setattr(settings, "emisor_facturacion", "sunat_cloud")
    monkeypatch.setattr(settings, "sunat_service_url", "http://sunat-service:8000")
    monkeypatch.setattr(settings, "sunat_service_token", "token-de-prueba")
    monkeypatch.setattr(
        "backend.routes.facturas.emitir_boleta_cloud",
        lambda **kw: SunatCloudResultado(
            exito=True, estado="accepted", codigo="0", cdr_xml="<ok/>"
        ),
    )


def _crear_y_cobrar_mesa(test_client, test_platos, numero_mesa=5):
    """Flujo real: crear comanda -> cobrar mesa. Devuelve los comanda_ids
    que el endpoint de facturas necesita, tal como los devolvería el
    frontend real después de POST /mesas/{id}/cobrar."""
    resp = test_client.post("/api/comandas", json={
        "numero_mesa": numero_mesa,
        "platos": [{"plato_id": test_platos[0].id, "cantidad": 2}],  # Ceviche x2 = 90.00
    })
    assert resp.status_code == 201, resp.text
    comanda_id = resp.json()["id"]

    resp = test_client.patch(f"/api/comandas/{comanda_id}/estado", json={"estado": "entregado"})
    assert resp.status_code == 200

    mesas_resp = test_client.get("/api/mesas").json()
    mesa = next(m for m in mesas_resp if m["numero"] == numero_mesa)

    resp = test_client.post(f"/api/mesas/{mesa['id']}/cobrar")
    assert resp.status_code == 200, resp.text
    return resp.json()["comanda_ids"]


# ============ REGLAS GENERALES DE EMISIÓN ============

def test_generar_factura_sin_ruc_configurado_falla(test_client, test_cliente, test_platos, test_mesas, emisor_cloud):
    """test_cliente (sin fixture cliente_con_ruc) no tiene RUC — debe rechazar
    ANTES de intentar emitir, con un mensaje accionable."""
    comanda_ids = _crear_y_cobrar_mesa(test_client, test_platos)

    resp = test_client.post("/api/facturas/generar", json={"comanda_ids": comanda_ids})

    assert resp.status_code == 400
    assert "RUC" in resp.json()["detail"]


def test_el_detalle_sale_de_la_comanda_real_no_del_frontend(
    test_client, test_db, cliente_con_ruc, test_platos, test_mesas, emisor_cloud
):
    """
    La regla central del módulo: el comprobante declara lo que el sistema
    registró como vendido. Si se armara con lo que manda el cliente HTTP,
    cualquiera con el token de un mozo podría facturar productos que nunca
    se sirvieron.
    """
    resp = test_client.post("/api/comandas", json={
        "numero_mesa": 2,
        "platos": [
            {"plato_id": test_platos[0].id, "cantidad": 2},
            {"plato_id": test_platos[1].id, "cantidad": 1},
        ],
    })
    comanda_id = resp.json()["id"]
    total_real = resp.json()["total_cuenta"]
    test_client.patch(f"/api/comandas/{comanda_id}/estado", json={"estado": "entregado"})
    mesa = next(m for m in test_client.get("/api/mesas").json() if m["numero"] == 2)
    comanda_ids = test_client.post(f"/api/mesas/{mesa['id']}/cobrar").json()["comanda_ids"]

    data = test_client.post("/api/facturas/generar", json={"comanda_ids": comanda_ids}).json()

    assert data["total"] == total_real
    assert len(data["detalles"]) == 2
    # subtotal + IGV tiene que dar el total EXACTO: SUNAT rechaza el
    # comprobante donde no cuadra por un céntimo de redondeo.
    assert round(data["subtotal"] + data["igv"], 2) == data["total"]


def test_si_el_envio_falla_la_venta_no_se_pierde_y_es_reintentable(
    test_client, cliente_con_ruc, test_platos, test_mesas, monkeypatch
):
    """El servicio de emisión caído no puede hacer desaparecer la venta: el
    comprobante queda guardado y reintentable, con SU MISMO número."""
    monkeypatch.setattr(settings, "emisor_facturacion", "sunat_cloud")
    monkeypatch.setattr(settings, "sunat_service_url", "http://sunat-service:8000")
    monkeypatch.setattr(
        "backend.routes.facturas.emitir_boleta_cloud",
        lambda **kw: (_ for _ in ()).throw(SunatCloudError("servicio caído")),
    )
    comanda_ids = _crear_y_cobrar_mesa(test_client, test_platos)

    resp = test_client.post("/api/facturas/generar", json={"comanda_ids": comanda_ids})
    assert resp.status_code == 502
    factura_id = resp.json()["detail"]["factura"]["id"]
    assert resp.json()["detail"]["factura"]["estado"] == "pendiente"

    # Se "arregla" el servicio; el correlativo ya reservado (1) no cambia.
    monkeypatch.setattr(
        "backend.routes.facturas.emitir_boleta_cloud",
        lambda **kw: SunatCloudResultado(exito=True, estado="accepted", codigo="0", cdr_xml="<ok/>"),
    )
    resp = test_client.post(f"/api/facturas/{factura_id}/reintentar")
    assert resp.status_code == 200
    assert resp.json()["numero_boleta"] == "B001-00000001"


def test_generar_factura_dos_correlativos_consecutivos(test_client, cliente_con_ruc, test_platos, test_mesas, emisor_cloud):
    """El correlativo vive en Cliente.boleta_correlativo_actual y debe
    incrementar de verdad entre dos boletas del mismo restaurante."""
    ids_1 = _crear_y_cobrar_mesa(test_client, test_platos, numero_mesa=1)
    resp_1 = test_client.post("/api/facturas/generar", json={"comanda_ids": ids_1})
    assert resp_1.json()["numero_boleta"] == "B001-00000001"

    ids_2 = _crear_y_cobrar_mesa(test_client, test_platos, numero_mesa=2)
    resp_2 = test_client.post("/api/facturas/generar", json={"comanda_ids": ids_2})
    assert resp_2.json()["numero_boleta"] == "B001-00000002"


def test_generar_factura_comanda_no_cobrada_falla(test_client, cliente_con_ruc, test_platos, test_mesas, emisor_cloud):
    resp = test_client.post("/api/comandas", json={
        "numero_mesa": 2, "platos": [{"plato_id": test_platos[0].id, "cantidad": 1}],
    })
    comanda_id = resp.json()["id"]

    resp = test_client.post("/api/facturas/generar", json={"comanda_ids": [comanda_id]})
    assert resp.status_code == 400
    assert "no están cobradas" in resp.json()["detail"]


def test_generar_factura_dos_veces_la_misma_comanda_falla(test_client, cliente_con_ruc, test_platos, test_mesas, emisor_cloud):
    comanda_ids = _crear_y_cobrar_mesa(test_client, test_platos)

    resp_1 = test_client.post("/api/facturas/generar", json={"comanda_ids": comanda_ids})
    assert resp_1.status_code == 201

    resp_2 = test_client.post("/api/facturas/generar", json={"comanda_ids": comanda_ids})
    assert resp_2.status_code == 400
    assert "ya tienen una boleta emitida" in resp_2.json()["detail"]


def test_borrar_cliente_no_deja_facturas_huerfanas(test_db, test_client, cliente_con_ruc, test_platos, test_mesas, emisor_cloud):
    """Mismo bug que ya se corrigió una vez para Categoria (ver CLAUDE.md):
    sin cascade, borrar un restaurante dejaba sus facturas y las filas de
    factura_comandas colgando en la BD — invisibles en la app (todo filtra
    por cliente_id) pero acumulándose para siempre. Con facturas es peor
    que con categorías: son registros tributarios."""
    from backend.models import Cliente, FacturaComanda

    comanda_ids = _crear_y_cobrar_mesa(test_client, test_platos)
    assert test_client.post("/api/facturas/generar", json={"comanda_ids": comanda_ids}).status_code == 201
    assert test_db.query(Factura).count() == 1
    assert test_db.query(FacturaComanda).count() == 1

    test_db.delete(test_db.query(Cliente).filter(Cliente.id == cliente_con_ruc.id).first())
    test_db.commit()

    assert test_db.query(Factura).count() == 0
    assert test_db.query(FacturaComanda).count() == 0


# ============ QUÉ COMPROBANTE CORRESPONDE ============
#
# Lo decide el SERVIDOR a partir de lo que el cajero tipeó en un solo campo.
# Es la regla fiscal: tenerla también en el JS garantizaría que algún día
# las dos versiones digan cosas distintas.

RUC_EN_PADRON = "20123456786"


@pytest.fixture
def padron(tmp_path, monkeypatch):
    """Padrón chico con la misma forma que el real (ver
    backend/scripts/cargar_padron_sunat.py)."""
    import sqlite3

    from backend.utils.padron import cerrar_conexion_del_hilo

    ruta = tmp_path / "padron.db"
    conn = sqlite3.connect(ruta)
    conn.execute("CREATE TABLE padron (ruc TEXT, nombre TEXT, estado TEXT, condicion TEXT)")
    conn.execute(
        "INSERT INTO padron VALUES (?,?,?,?)",
        (RUC_EN_PADRON, "DISTRIBUIDORA EL SOL SAC", "ACTIVO", "HABIDO"),
    )
    conn.execute("CREATE UNIQUE INDEX idx_ruc ON padron(ruc)")
    conn.commit()
    conn.close()

    cerrar_conexion_del_hilo()
    monkeypatch.setattr(settings, "padron_db_path", str(ruta))
    yield ruta
    cerrar_conexion_del_hilo()


def _cobrar_por_monto(test_client, test_platos, cantidad, numero_mesa=5):
    """Cobra una mesa con N unidades del primer plato (S/ 45 c/u), para
    poder cruzar el umbral de S/ 700 sin depender del fixture chico."""
    resp = test_client.post("/api/comandas", json={
        "numero_mesa": numero_mesa,
        "platos": [{"plato_id": test_platos[0].id, "cantidad": cantidad}],
    })
    assert resp.status_code == 201, resp.text
    comanda_id = resp.json()["id"]
    test_client.patch(f"/api/comandas/{comanda_id}/estado", json={"estado": "entregado"})
    mesa = next(m for m in test_client.get("/api/mesas").json() if m["numero"] == numero_mesa)
    return test_client.post(f"/api/mesas/{mesa['id']}/cobrar").json()["comanda_ids"]


def test_sin_documento_y_monto_chico_sale_boleta_a_publico_general(
    test_client, test_db, cliente_con_ruc, test_platos, test_mesas, emisor_cloud
):
    """El caso más común: nadie pide comprobante a su nombre."""
    comanda_ids = _crear_y_cobrar_mesa(test_client, test_platos)
    resp = test_client.post("/api/facturas/generar", json={"comanda_ids": comanda_ids})
    assert resp.status_code == 201, resp.text

    factura = test_db.query(Factura).one()
    assert factura.tipo_comprobante == "03"
    assert factura.serie == "B001"
    assert factura.tipo_documento_comprador == "0"
    assert factura.numero_documento_comprador == "00000000"


def test_sin_documento_desde_700_soles_se_exige_identificar_al_cliente(
    test_client, test_db, cliente_con_ruc, test_platos, test_mesas, emisor_cloud
):
    """
    SUNAT exige identificar al comprador en una boleta desde S/ 700.

    El rechazo llega DESPUÉS del cobro, no durante: la plata ya cambió de
    mano y la mesa ya se liberó. El comprobante queda pendiente y el cajero
    lo emite desde Admin > Boletas pidiéndole el documento al cliente.
    """
    comanda_ids = _cobrar_por_monto(test_client, test_platos, cantidad=16)  # 16 x 45 = 720

    resp = test_client.post("/api/facturas/generar", json={"comanda_ids": comanda_ids})

    assert resp.status_code == 400
    detalle = resp.json()["detail"]
    # Estructurado, no texto suelto: el frontend distingue ESTE caso de
    # cualquier otro fallo y pide el documento en el momento, con el cliente
    # todavía enfrente, en vez de mandar al cajero a Admin.
    assert detalle["codigo"] == "IDENTIFICAR_COMPRADOR"
    assert detalle["total"] == 720.0
    assert "700" in detalle["mensaje"]

    # Y no gastó ningún correlativo: un número consumido por un intento
    # fallido deja un hueco permanente en la serie.
    assert test_db.query(Factura).count() == 0
    test_db.refresh(cliente_con_ruc)
    assert cliente_con_ruc.boleta_correlativo_actual == 0

    # EL COBRO NO SE PERDIÓ: la venta queda esperando en Admin > Boletas
    # hasta que alguien agregue el documento.
    pendientes = test_client.get("/api/facturas/pendientes").json()
    assert len(pendientes["ventas_sin_boleta"]) == 1
    assert pendientes["ventas_sin_boleta"][0]["total"] == 720.0


def test_un_dni_produce_boleta(test_client, test_db, cliente_con_ruc, test_platos, test_mesas, emisor_cloud):
    comanda_ids = _crear_y_cobrar_mesa(test_client, test_platos)
    resp = test_client.post("/api/facturas/generar", json={
        "comanda_ids": comanda_ids, "documento_comprador": "73081441",
    })
    assert resp.status_code == 201, resp.text

    factura = test_db.query(Factura).one()
    assert factura.tipo_comprobante == "03"
    assert factura.serie == "B001"
    assert factura.tipo_documento_comprador == "1"
    assert factura.numero_documento_comprador == "73081441"


def test_un_ruc_produce_FACTURA_con_la_razon_social_del_padron(
    test_client, test_db, cliente_con_ruc, test_platos, test_mesas, emisor_cloud, padron,
    regimen_general,
):
    """
    Un RUC SIEMPRE produce factura, nunca boleta.

    Quien da su RUC lo hace para sustentar gasto o crédito fiscal, y una
    boleta no le sirve para eso: cambiarle el tipo de comprobante por
    nuestra cuenta le crea un problema comercial al restaurante.
    """
    comanda_ids = _crear_y_cobrar_mesa(test_client, test_platos)
    resp = test_client.post("/api/facturas/generar", json={
        "comanda_ids": comanda_ids, "documento_comprador": RUC_EN_PADRON,
    })
    assert resp.status_code == 201, resp.text

    factura = test_db.query(Factura).one()
    assert factura.tipo_comprobante == "01"
    assert factura.serie == "F001"
    assert factura.tipo_documento_comprador == "6"
    assert factura.nombre_comprador == "DISTRIBUIDORA EL SOL SAC"


def test_boletas_y_facturas_llevan_correlativos_INDEPENDIENTES(
    test_client, test_db, cliente_con_ruc, test_platos, test_mesas, emisor_cloud, padron,
    regimen_general,
):
    """
    EL test de este archivo.

    SUNAT exige que cada serie sea correlativa SIN HUECOS. Con un contador
    compartido, una factura intercalada entre dos boletas dejaría a las DOS
    series agujereadas — y el UNIQUE(cliente_id, serie, correlativo) no lo
    detecta, porque las combinaciones siguen siendo distintas. Pasaría en
    silencio hasta una fiscalización.
    """
    ids_1 = _crear_y_cobrar_mesa(test_client, test_platos, numero_mesa=1)
    b1 = test_client.post("/api/facturas/generar", json={"comanda_ids": ids_1}).json()

    ids_2 = _crear_y_cobrar_mesa(test_client, test_platos, numero_mesa=2)
    f1 = test_client.post("/api/facturas/generar", json={
        "comanda_ids": ids_2, "documento_comprador": RUC_EN_PADRON,
    }).json()

    ids_3 = _crear_y_cobrar_mesa(test_client, test_platos, numero_mesa=5)
    b2 = test_client.post("/api/facturas/generar", json={"comanda_ids": ids_3}).json()

    assert b1["numero_boleta"] == "B001-00000001"
    assert f1["numero_boleta"] == "F001-00000001"   # NO F001-00000002
    assert b2["numero_boleta"] == "B001-00000002"   # NO B001-00000003


def test_un_ruc_fuera_del_padron_se_rechaza_pidiendo_la_razon_social(
    test_client, test_db, cliente_con_ruc, test_platos, test_mesas, emisor_cloud, padron,
    regimen_general,
):
    """
    SUNAT no acepta una factura sin razón social, así que no se puede
    inventar. Tampoco se cae a boleta: el cliente que pidió factura la
    necesita, y darle otra cosa es un problema comercial del restaurante.
    El mensaje invita a escribir el nombre a mano.
    """
    comanda_ids = _crear_y_cobrar_mesa(test_client, test_platos)
    resp = test_client.post("/api/facturas/generar", json={
        "comanda_ids": comanda_ids, "documento_comprador": "20600055519",
    })

    assert resp.status_code == 400
    assert "razón social" in resp.json()["detail"]
    assert test_db.query(Factura).count() == 0


def test_la_razon_social_a_mano_permite_facturar_un_ruc_nuevo(
    test_client, test_db, cliente_con_ruc, test_platos, test_mesas, emisor_cloud, padron,
    regimen_general,
):
    """Salida para un RUC recién inscrito que el padrón local todavía no
    tiene. Sin esto, la venta se quedaría sin comprobante hasta que alguien
    recargue 1,6 GB de padrón."""
    comanda_ids = _crear_y_cobrar_mesa(test_client, test_platos)
    resp = test_client.post("/api/facturas/generar", json={
        "comanda_ids": comanda_ids,
        "documento_comprador": "20600055519",
        "razon_social_manual": "  IMPORTACIONES  NUEVAS   SAC  ",
    })
    assert resp.status_code == 201, resp.text

    factura = test_db.query(Factura).one()
    assert factura.serie == "F001"
    # Espacios repetidos normalizados: lo que va al comprobante tiene que
    # estar prolijo aunque el cajero tipee de apuro.
    assert factura.nombre_comprador == "IMPORTACIONES NUEVAS SAC"


def test_sin_padron_instalado_se_puede_facturar_igual_a_mano(
    test_client, test_db, cliente_con_ruc, test_platos, test_mesas, emisor_cloud, monkeypatch,
    regimen_general,
):
    """Que el padrón de 1,6 GB no esté cargado NO puede impedir facturar:
    un restaurante nuevo debe poder emitir desde el primer día."""
    from backend.utils.padron import cerrar_conexion_del_hilo

    cerrar_conexion_del_hilo()
    monkeypatch.setattr(settings, "padron_db_path", "/no/existe/padron.db")

    comanda_ids = _crear_y_cobrar_mesa(test_client, test_platos)
    resp = test_client.post("/api/facturas/generar", json={
        "comanda_ids": comanda_ids,
        "documento_comprador": RUC_EN_PADRON,
        "razon_social_manual": "CLIENTE SAC",
    })
    assert resp.status_code == 201, resp.text
    assert test_db.query(Factura).one().serie == "F001"


@pytest.mark.parametrize("documento, motivo", [
    ("123456789", "9 dígitos: ni DNI (8) ni RUC (11)"),
    ("11111111111", "11 dígitos con prefijo que SUNAT no usa"),
    ("30200812234", "prefijo 30 no existe para contribuyentes"),
    ("1020081223a", "letras"),
])
def test_documento_invalido_se_rechaza_antes_de_emitir(
    test_client, test_db, cliente_con_ruc, test_platos, test_mesas, emisor_cloud, documento, motivo
):
    """Rechazar rápido en vez de adivinar: un tipeo del cajero no debe
    convertirse en un comprobante que SUNAT rechaza DESPUÉS de emitido
    (cuando el correlativo ya se consumió y el cliente ya se fue)."""
    comanda_ids = _crear_y_cobrar_mesa(test_client, test_platos)
    resp = test_client.post("/api/facturas/generar", json={
        "comanda_ids": comanda_ids, "documento_comprador": documento,
    })
    assert resp.status_code == 422, f"{documento} ({motivo}) debería rechazarse"
    assert test_db.query(Factura).count() == 0


def test_documento_con_espacios_o_guiones_se_normaliza(
    test_client, test_db, cliente_con_ruc, test_platos, test_mesas, emisor_cloud
):
    """El cajero puede tipear "7308-1441" de apuro; se limpia en vez de
    rechazarlo, pero al comprobante llegan solo dígitos."""
    comanda_ids = _crear_y_cobrar_mesa(test_client, test_platos)
    resp = test_client.post("/api/facturas/generar", json={
        "comanda_ids": comanda_ids, "documento_comprador": "7308-1441",
    })
    assert resp.status_code == 201, resp.text

    factura = test_db.query(Factura).one()
    assert factura.tipo_documento_comprador == "1"
    assert factura.numero_documento_comprador == "73081441"


# ============ Recuperación de boletas (Admin > Boletas) ============

def test_pendientes_lista_factura_con_error_y_permite_reintentar(
    test_client, cliente_con_ruc, test_platos, test_mesas, monkeypatch
):
    """El caso real que se dio en producción: la emisión falla, la venta
    queda cobrada y el comprobante en 'error'. Sin esta pantalla, ese cobro
    es irrecuperable desde la app."""
    monkeypatch.setattr(settings, "emisor_facturacion", "sunat_cloud")
    monkeypatch.setattr(settings, "sunat_service_url", "http://sunat-service:8000")
    monkeypatch.setattr(
        "backend.routes.facturas.emitir_boleta_cloud",
        lambda **kw: SunatCloudResultado(
            exito=False, error_codigo="RECHAZO_SUNAT",
            error_mensaje="El RUC del emisor no está activo", reintentable=False,
        ),
    )

    comanda_ids = _crear_y_cobrar_mesa(test_client, test_platos)
    assert test_client.post("/api/facturas/generar", json={"comanda_ids": comanda_ids}).status_code == 502

    # La ruta no debe confundirse con GET /facturas/{factura_id}: si se
    # declarara después, "pendientes" se parsearía como int y daría 422.
    resp = test_client.get("/api/facturas/pendientes")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert len(data["facturas_con_error"]) == 1
    assert data["facturas_con_error"][0]["estado"] == "error"
    assert data["ventas_sin_boleta"] == []  # la Factura sí existe, no es este caso

    # Se corrige lo que fallaba y se reintenta.
    monkeypatch.setattr(
        "backend.routes.facturas.emitir_boleta_cloud",
        lambda **kw: SunatCloudResultado(exito=True, estado="accepted", codigo="0", cdr_xml="<ok/>"),
    )
    factura_id = data["facturas_con_error"][0]["id"]
    assert test_client.post(f"/api/facturas/{factura_id}/reintentar").status_code == 200

    assert test_client.get("/api/facturas/pendientes").json()["facturas_con_error"] == []


def test_pendientes_detecta_venta_cobrada_que_nunca_llego_a_facturarse(
    test_client, cliente_con_ruc, test_platos, test_mesas, emisor_cloud
):
    """Caso distinto: la petición de facturar nunca llegó al servidor (se
    cortó la red justo al cobrar), así que NO hay Factura que reintentar —
    hay que emitirla de cero sobre esas comandas."""
    comanda_ids = _crear_y_cobrar_mesa(test_client, test_platos)  # cobrada, nunca facturada

    data = test_client.get("/api/facturas/pendientes").json()
    assert data["facturas_con_error"] == []
    assert len(data["ventas_sin_boleta"]) == 1
    venta = data["ventas_sin_boleta"][0]
    assert sorted(venta["comanda_ids"]) == sorted(comanda_ids)
    assert venta["total"] == 90.00

    assert test_client.post("/api/facturas/generar", json={"comanda_ids": venta["comanda_ids"]}).status_code == 201
    assert test_client.get("/api/facturas/pendientes").json()["ventas_sin_boleta"] == []


# ============ EMISOR facturacion_pe (de pago, sigue disponible) ============

def _resultado_exitoso(**overrides):
    base = dict(
        exito=True,
        numero_boleta_proveedor="F001-1",
        pdf_url="https://facturacion.pe/pdf/fake.pdf",
        qr_code="data:image/png;base64,fake",
        codigo_hash="hash-fake",
    )
    base.update(overrides)
    return FacturacionPeResultado(**base)


def _resultado_rechazado(mensaje="RUC no encontrado"):
    return FacturacionPeResultado(exito=False, error_mensaje=mensaje)


@pytest.fixture
def usar_facturacion_pe(monkeypatch):
    monkeypatch.setattr(settings, "emisor_facturacion", "facturacion_pe")


def test_facturacion_pe_ok(test_client, cliente_con_ruc, test_platos, test_mesas, usar_facturacion_pe, monkeypatch):
    monkeypatch.setattr("backend.routes.facturas.generar_boleta", lambda **kwargs: _resultado_exitoso())
    comanda_ids = _crear_y_cobrar_mesa(test_client, test_platos)

    resp = test_client.post("/api/facturas/generar", json={"comanda_ids": comanda_ids})

    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["estado"] == "enviada_sunat"
    assert data["pdf_url"] == "https://facturacion.pe/pdf/fake.pdf"


def test_facturacion_pe_rechazo_queda_en_error_y_es_reintentable(
    test_client, cliente_con_ruc, test_platos, test_mesas, usar_facturacion_pe, monkeypatch
):
    monkeypatch.setattr("backend.routes.facturas.generar_boleta", lambda **kwargs: _resultado_rechazado("RUC no encontrado"))
    comanda_ids = _crear_y_cobrar_mesa(test_client, test_platos)

    resp = test_client.post("/api/facturas/generar", json={"comanda_ids": comanda_ids})
    assert resp.status_code == 502
    factura = resp.json()["detail"]["factura"]
    assert factura["estado"] == "error"
    factura_id = factura["id"]

    monkeypatch.setattr("backend.routes.facturas.generar_boleta", lambda **kwargs: _resultado_exitoso())
    resp = test_client.post(f"/api/facturas/{factura_id}/reintentar")
    assert resp.status_code == 200
    assert resp.json()["numero_boleta"] == "B001-00000001"  # mismo número, no se saltó


def test_facturacion_pe_caida_de_red_no_pierde_el_intento(
    test_client, cliente_con_ruc, test_platos, test_mesas, usar_facturacion_pe, monkeypatch
):
    def _falla_de_red(**kwargs):
        raise FacturacionPeError("timeout")

    monkeypatch.setattr("backend.routes.facturas.generar_boleta", _falla_de_red)
    comanda_ids = _crear_y_cobrar_mesa(test_client, test_platos)

    resp = test_client.post("/api/facturas/generar", json={"comanda_ids": comanda_ids})
    assert resp.status_code == 502
    assert resp.json()["detail"]["factura"]["estado"] == "pendiente"


# ============ RÉGIMEN TRIBUTARIO: QUIÉN PUEDE FACTURAR ============
#
# Un contribuyente del NUEVO RUS tiene PROHIBIDO emitir facturas: solo
# boletas de venta y tickets. Hacerlo igual es una infracción del emisor, y
# le da al comprador un crédito fiscal que no le corresponde.
#
# Por eso `emite_facturas` arranca en False para TODOS: emitir boletas de
# más nunca es infracción; facturar sin poder, sí.


def test_por_defecto_un_restaurante_NO_puede_facturar(test_db, test_cliente):
    """El caso seguro es el default. Que un restaurante del Régimen General
    tenga que pedir que se lo activen es un trámite; que uno del Nuevo RUS
    emita facturas sin darse cuenta es una infracción."""
    assert test_cliente.emite_facturas is False


def test_en_NUEVO_RUS_un_RUC_produce_BOLETA_no_factura(
    test_client, test_db, cliente_con_ruc, test_platos, test_mesas, emisor_cloud, padron
):
    """
    EL test de esta sección.

    El comensal da su RUC y el restaurante es NRUS: le corresponde BOLETA,
    con su RUC como documento del adquiriente (catálogo 06 de SUNAT lo
    admite). NO una factura.
    """
    assert cliente_con_ruc.emite_facturas is False   # NRUS

    comanda_ids = _crear_y_cobrar_mesa(test_client, test_platos)
    resp = test_client.post("/api/facturas/generar", json={
        "comanda_ids": comanda_ids, "documento_comprador": RUC_EN_PADRON,
    })
    assert resp.status_code == 201, resp.text

    factura = test_db.query(Factura).one()
    assert factura.tipo_comprobante == "03"          # boleta, NO "01"
    assert factura.serie == "B001"                   # NO "F001"
    assert factura.tipo_documento_comprador == "6"   # el RUC del comensal
    assert factura.numero_documento_comprador == RUC_EN_PADRON

    # Y el correlativo de facturas queda intacto: en NRUS esa serie no se usa.
    test_db.refresh(cliente_con_ruc)
    assert cliente_con_ruc.factura_correlativo_actual == 0


def test_en_NUEVO_RUS_un_RUC_fuera_del_padron_NO_frena_la_venta(
    test_client, test_db, cliente_con_ruc, test_platos, test_mesas, emisor_cloud, padron
):
    """Una boleta es válida sin razón social del comprador, así que un RUC
    que el padrón no tiene no puede bloquear nada. Solo una FACTURA exige el
    nombre — y un NRUS no emite facturas."""
    comanda_ids = _crear_y_cobrar_mesa(test_client, test_platos)
    resp = test_client.post("/api/facturas/generar", json={
        "comanda_ids": comanda_ids, "documento_comprador": "20600055519",
    })

    assert resp.status_code == 201, resp.text
    assert test_db.query(Factura).one().serie == "B001"


def test_con_el_regimen_habilitado_el_mismo_RUC_produce_FACTURA(
    test_client, test_db, cliente_con_ruc, test_platos, test_mesas, emisor_cloud, padron
):
    """La contracara: activar el campo habilita la serie F001 y su
    correlativo propio. Si esto falla, se rompió el camino del Régimen
    General al blindar el del Nuevo RUS."""
    cliente_con_ruc.emite_facturas = True
    test_db.commit()
    comanda_ids = _crear_y_cobrar_mesa(test_client, test_platos)
    resp = test_client.post("/api/facturas/generar", json={
        "comanda_ids": comanda_ids, "documento_comprador": RUC_EN_PADRON,
    })
    assert resp.status_code == 201, resp.text

    factura = test_db.query(Factura).one()
    assert factura.tipo_comprobante == "01"
    assert factura.serie == "F001"
    assert factura.nombre_comprador == "DISTRIBUIDORA EL SOL SAC"

    test_db.refresh(cliente_con_ruc)
    assert cliente_con_ruc.factura_correlativo_actual == 1


def test_un_DNI_produce_boleta_en_los_dos_regimenes(
    test_client, test_db, cliente_con_ruc, test_platos, test_mesas, emisor_cloud
):
    """El régimen solo decide qué pasa con un RUC: un DNI siempre es boleta."""
    cliente_con_ruc.emite_facturas = True
    test_db.commit()

    comanda_ids = _crear_y_cobrar_mesa(test_client, test_platos)
    test_client.post("/api/facturas/generar", json={
        "comanda_ids": comanda_ids, "documento_comprador": "73081441",
    })

    factura = test_db.query(Factura).one()
    assert factura.serie == "B001"
    assert factura.tipo_documento_comprador == "1"


# ============ CALIBRACIÓN CONTRA UN COMPROBANTE REAL DE SUNAT ============


def test_los_montos_coinciden_con_la_boleta_real_EB01_1297():
    """
    Calibrado contra un comprobante EMITIDO de verdad (boleta EB01-1297,
    S/ 150.00). Lo que declara el visor oficial de SUNAT:

        Valor Unitario    127.11864     <- 5 decimales
        Importe de Venta  149.9999952
        Op. Gravada       127.12
        IGV                22.88
        Importe Total     150.00

    Si alguien "simplifica" la precisión, el Valor Unitario impreso deja de
    coincidir con el que SUNAT emitiría para el mismo importe.
    """
    from decimal import Decimal

    from backend.routes.facturas import _calcular_montos
    from backend.utils.sunat_cloud import precio_sin_igv

    assert precio_sin_igv(150.00) == Decimal("127.11864")
    assert precio_sin_igv(150.00) * Decimal("1.18") == Decimal("149.9999952")

    subtotal, igv = _calcular_montos(150.00)
    assert subtotal == 127.12
    assert igv == 22.88
    assert round(subtotal + igv, 2) == 150.00


# ---------------------------------------------------------------------------
# Lo que el cliente recibe EN PAPEL
#
# El tique impreso es lo único que el comensal se lleva, y hasta acá tenía
# dos campos que no decían nada: CLIENTE salía siempre "-" aunque el RUC
# estuviera en el padrón, y CAJERO salía de la cuenta logueada en el
# navegador —no de quien atendió—, así que una reimpresión desde otra
# cuenta cambiaba quién figuraba en un comprobante ya emitido.
# ---------------------------------------------------------------------------


def test_en_NUEVO_RUS_la_boleta_con_RUC_trae_la_razon_social_del_padron(
    test_client, test_db, cliente_con_ruc, test_platos, test_mesas, emisor_cloud, padron
):
    """
    Que el comprobante sea boleta y no factura no vuelve anónimo al
    comprador: si el padrón tiene el RUC, el nombre va en el papel y en el
    XML. Es el caso del restaurante real (Nuevo RUS) con un comensal que da
    su RUC.
    """
    comanda_ids = _crear_y_cobrar_mesa(test_client, test_platos)
    resp = test_client.post("/api/facturas/generar", json={
        "comanda_ids": comanda_ids, "documento_comprador": RUC_EN_PADRON,
    })
    assert resp.status_code == 201, resp.text

    assert resp.json()["nombre_comprador"] == "DISTRIBUIDORA EL SOL SAC"
    assert test_db.query(Factura).one().nombre_comprador == "DISTRIBUIDORA EL SOL SAC"


def test_un_DNI_no_inventa_un_nombre(
    test_client, test_db, cliente_con_ruc, test_platos, test_mesas, emisor_cloud, padron
):
    """RENIEC no es una fuente disponible acá, y una boleta es válida sin el
    nombre del adquiriente. El papel dice "-", que es la verdad — no un
    nombre sacado de ningún lado."""
    comanda_ids = _crear_y_cobrar_mesa(test_client, test_platos)
    resp = test_client.post("/api/facturas/generar", json={
        "comanda_ids": comanda_ids, "documento_comprador": "12345678",
    })
    assert resp.status_code == 201, resp.text
    assert resp.json()["nombre_comprador"] == "-"


def test_el_nombre_escrito_a_mano_le_gana_al_padron(
    test_client, test_db, cliente_con_ruc, test_platos, test_mesas, emisor_cloud, padron
):
    """El cajero tiene al cliente enfrente; el padrón puede estar
    desactualizado. Si alguien escribió el nombre, ese es el que vale."""
    comanda_ids = _crear_y_cobrar_mesa(test_client, test_platos)
    resp = test_client.post("/api/facturas/generar", json={
        "comanda_ids": comanda_ids,
        "documento_comprador": RUC_EN_PADRON,
        "razon_social_manual": "NOMBRE QUE DIO EL CLIENTE SAC",
    })
    assert resp.status_code == 201, resp.text
    assert resp.json()["nombre_comprador"] == "NOMBRE QUE DIO EL CLIENTE SAC"


def test_el_cajero_del_tique_es_quien_tomo_el_pedido(
    test_client, test_db, cliente_con_ruc, test_platos, test_mesas, emisor_cloud
):
    """
    CAJERO sale del nombre REAL de la cuenta que creó la comanda, resuelto
    en el servidor al emitir.

    Comanda.creado_por guarda el 'sub' del JWT — el email del admin, pero el
    código de acceso de seis dígitos del staff. Imprimirlo crudo pondría
    "482913" en el papel del cliente.
    """
    from backend.models import Usuario
    from backend.auth import hash_password

    test_db.add(Usuario(
        id="u-mozo-tique", cliente_id=cliente_con_ruc.id, nombre="Pedro Quispe",
        email=None, celular="482913", password_hash=hash_password("123456"), rol="mozo",
    ))
    test_db.commit()

    # La comanda la toma el mozo (su 'sub' es el código de acceso)...
    from backend.dependencies import get_usuario_actual
    from backend.app import app
    app.dependency_overrides[get_usuario_actual] = lambda: "482913"
    comanda_ids = _crear_y_cobrar_mesa(test_client, test_platos)
    # ...y el admin emite. El tique tiene que decir quién ATENDIÓ.
    app.dependency_overrides[get_usuario_actual] = lambda: "admin@test.local"

    resp = test_client.post("/api/facturas/generar", json={"comanda_ids": comanda_ids})
    assert resp.status_code == 201, resp.text

    assert resp.json()["cajero_nombre"] == "Pedro Quispe"
    assert "482913" not in str(resp.json()["cajero_nombre"])
    assert test_db.query(Factura).one().cajero_nombre == "Pedro Quispe"


def test_una_cuenta_borrada_no_deja_un_codigo_suelto_en_el_tique(
    test_client, test_db, cliente_con_ruc, test_platos, test_mesas, emisor_cloud
):
    """Si la cuenta que tomó el pedido ya no existe, el campo queda vacío y
    el tique imprime "-" — nunca el código de acceso crudo."""
    from backend.dependencies import get_usuario_actual
    from backend.app import app

    app.dependency_overrides[get_usuario_actual] = lambda: "999111"  # nadie
    comanda_ids = _crear_y_cobrar_mesa(test_client, test_platos)
    app.dependency_overrides[get_usuario_actual] = lambda: "admin@test.local"

    resp = test_client.post("/api/facturas/generar", json={"comanda_ids": comanda_ids})
    assert resp.status_code == 201, resp.text
    assert resp.json()["cajero_nombre"] is None
