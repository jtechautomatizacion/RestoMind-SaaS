"""
El emisor "sunat_cloud" visto desde el endpoint real (POST /facturas/generar).

Lo que estos tests protegen es la diferencia entre "SUNAT dijo que no" y
"no se pudo llegar a SUNAT". Suena a detalle, pero decide si el restaurante
puede volver a intentar la misma boleta o si perdió el correlativo:

  - rechazo de SUNAT     -> 'error'      (reintentar igual da lo mismo)
  - red/servicio caídos  -> 'pendiente'  (reintentar SIRVE, mismo número)

Confundirlos deja al local con una venta cobrada y sin comprobante, o
gastando correlativos en cada reintento. Nada de esto se ve a simple vista
en producción hasta que pasa.
"""

import pytest

from backend.config import settings
from backend.models import Factura
from backend.utils.sunat_cloud import SunatCloudError, SunatCloudResultado


@pytest.fixture
def cliente_con_ruc(test_db, test_cliente):
    test_cliente.ruc = "10200812234"
    test_cliente.razon_social = "Pollería Fogones"
    test_cliente.usar_sunat = True
    test_db.commit()
    return test_cliente


@pytest.fixture
def emisor_cloud(monkeypatch):
    """settings es un singleton importado en todo el código, así que se
    parchea el atributo del objeto (no la variable de módulo) para que
    monkeypatch pueda restaurarlo al terminar."""
    monkeypatch.setattr(settings, "emisor_facturacion", "sunat_cloud")
    monkeypatch.setattr(settings, "sunat_service_url", "http://sunat-service:8000")
    monkeypatch.setattr(settings, "sunat_service_token", "token-de-prueba")


def _cobrar(test_client, test_platos, numero_mesa=5):
    resp = test_client.post("/api/comandas", json={
        "numero_mesa": numero_mesa,
        "platos": [{"plato_id": test_platos[0].id, "cantidad": 2}],
    })
    assert resp.status_code == 201, resp.text
    comanda_id = resp.json()["id"]

    test_client.patch(f"/api/comandas/{comanda_id}/estado", json={"estado": "entregado"})
    mesa = next(m for m in test_client.get("/api/mesas").json() if m["numero"] == numero_mesa)
    resp = test_client.post(f"/api/mesas/{mesa['id']}/cobrar")
    assert resp.status_code == 200, resp.text
    return resp.json()["comanda_ids"]


def _parchear_emision(monkeypatch, resultado=None, excepcion=None):
    """Se parchea el nombre TAL COMO lo importó routes/facturas.py
    (emitir_boleta_cloud), no el del módulo de origen: el import por valor
    ya copió la referencia y parchear el origen no tendría efecto."""
    def falso(**kwargs):
        if excepcion:
            raise excepcion
        return resultado
    monkeypatch.setattr("backend.routes.facturas.emitir_boleta_cloud", falso)


def test_una_boleta_aceptada_guarda_el_cdr_de_sunat(
    test_client, test_db, cliente_con_ruc, test_platos, test_mesas, emisor_cloud, monkeypatch
):
    """El CDR es la prueba de que SUNAT aceptó. Sin guardarlo, ante una
    fiscalización no hay con qué demostrarlo."""
    _parchear_emision(monkeypatch, SunatCloudResultado(
        exito=True, estado="accepted", codigo="0",
        descripcion="La Boleta numero B001-1, ha sido aceptada",
        cdr_xml="<ApplicationResponse>ok</ApplicationResponse>",
    ))

    resp = test_client.post("/api/facturas/generar", json={"comanda_ids": _cobrar(test_client, test_platos)})
    assert resp.status_code == 201, resp.text

    factura = test_db.query(Factura).one()
    assert factura.estado == "enviada_sunat"
    assert factura.cdr_xml == "<ApplicationResponse>ok</ApplicationResponse>"
    assert factura.enviado_en is not None
    assert factura.error_mensaje is None


def test_accepted_with_obs_cuenta_como_aceptada(
    test_client, test_db, cliente_con_ruc, test_platos, test_mesas, emisor_cloud, monkeypatch
):
    """SUNAT la registró y anotó una observación: YA ESTÁ EMITIDA. Tratarla
    como fallo haría que el local la reintente, y ese reintento sí sería
    rechazado por duplicado."""
    _parchear_emision(monkeypatch, SunatCloudResultado(
        exito=True, estado="accepted_with_obs", codigo="4000",
        descripcion="Aceptada con observaciones", cdr_xml="<obs/>",
    ))

    test_client.post("/api/facturas/generar", json={"comanda_ids": _cobrar(test_client, test_platos)})
    assert test_db.query(Factura).one().estado == "enviada_sunat"


def test_un_rechazo_de_sunat_queda_en_error_y_no_en_pendiente(
    test_client, test_db, cliente_con_ruc, test_platos, test_mesas, emisor_cloud, monkeypatch
):
    _parchear_emision(monkeypatch, SunatCloudResultado(
        exito=False, error_codigo="RECHAZO_SUNAT",
        error_mensaje="El RUC del emisor no está activo", reintentable=False,
    ))

    test_client.post("/api/facturas/generar", json={"comanda_ids": _cobrar(test_client, test_platos)})

    factura = test_db.query(Factura).one()
    assert factura.estado == "error"
    assert "no está activo" in factura.error_mensaje


def test_si_sunat_no_contesta_la_boleta_queda_reintentable(
    test_client, test_db, cliente_con_ruc, test_platos, test_mesas, emisor_cloud, monkeypatch
):
    """'pendiente' y no 'error': el comprobante está bien, falló el camino."""
    _parchear_emision(monkeypatch, SunatCloudResultado(
        exito=False, error_codigo="TRANSPORTE",
        error_mensaje="No se pudo contactar a SUNAT", reintentable=True,
    ))

    test_client.post("/api/facturas/generar", json={"comanda_ids": _cobrar(test_client, test_platos)})
    assert test_db.query(Factura).one().estado == "pendiente"


def test_si_el_microservicio_esta_caido_la_venta_igual_queda_cobrada(
    test_client, test_db, cliente_con_ruc, test_platos, test_mesas, emisor_cloud, monkeypatch
):
    """
    El contenedor de emisión caído NO puede hacer desaparecer la venta: la
    plata ya la pagó el comensal y la mesa ya se liberó.

    Responde 502 —no 201— y ESO ESTÁ BIEN: es la misma convención que ya usa
    sfs_local cuando la carpeta del Facturador no existe. El frontend
    necesita saber que la boleta no salió (es el aviso que ve el cajero);
    lo que no puede pasar es que la Factura se pierda. Por eso el 502 trae
    la factura completa en el cuerpo y queda reintentable.
    """
    _parchear_emision(monkeypatch, excepcion=SunatCloudError("servicio no responde"))

    resp = test_client.post("/api/facturas/generar", json={"comanda_ids": _cobrar(test_client, test_platos)})
    assert resp.status_code == 502, resp.text

    cuerpo = resp.json()["detail"]
    assert cuerpo["factura"]["estado"] == "pendiente"
    # El correlativo YA quedó reservado: el reintento lo reusa en vez de
    # pedir uno nuevo (ver test_el_reintento_no_gasta_otro_correlativo).
    assert cuerpo["factura"]["numero_correlativo"] == 1

    factura = test_db.query(Factura).one()
    assert factura.estado == "pendiente"
    assert factura.total == 90.0  # la venta quedó registrada por su monto real


def test_el_reintento_no_gasta_otro_correlativo(
    test_client, test_db, cliente_con_ruc, test_platos, test_mesas, emisor_cloud, monkeypatch
):
    """La numeración de comprobantes no puede tener huecos ante SUNAT. Si
    cada reintento pidiera un número nuevo, una tarde con mala conexión
    dejaría la serie llena de saltos."""
    _parchear_emision(monkeypatch, SunatCloudResultado(
        exito=False, error_codigo="TRANSPORTE", error_mensaje="caído", reintentable=True,
    ))
    test_client.post("/api/facturas/generar", json={"comanda_ids": _cobrar(test_client, test_platos)})

    factura = test_db.query(Factura).one()
    correlativo_original = factura.numero_correlativo

    _parchear_emision(monkeypatch, SunatCloudResultado(
        exito=True, estado="accepted", codigo="0", cdr_xml="<ok/>",
    ))
    resp = test_client.post(f"/api/facturas/{factura.id}/reintentar")
    assert resp.status_code == 200, resp.text

    test_db.refresh(factura)
    assert factura.numero_correlativo == correlativo_original
    assert factura.estado == "enviada_sunat"
    assert test_db.query(Factura).count() == 1


def test_la_factura_de_otro_restaurante_no_se_puede_reintentar(
    test_client, test_db, cliente_con_ruc, test_platos, test_mesas, emisor_cloud, monkeypatch
):
    """Aislamiento multi-tenant sobre el emisor nuevo: una boleta lleva RUC,
    montos y el documento del comensal."""
    _parchear_emision(monkeypatch, SunatCloudResultado(
        exito=False, error_codigo="TRANSPORTE", error_mensaje="caído", reintentable=True,
    ))
    test_client.post("/api/facturas/generar", json={"comanda_ids": _cobrar(test_client, test_platos)})

    factura = test_db.query(Factura).one()
    factura.cliente_id = "otro-restaurante"
    test_db.commit()

    assert test_client.post(f"/api/facturas/{factura.id}/reintentar").status_code == 404
