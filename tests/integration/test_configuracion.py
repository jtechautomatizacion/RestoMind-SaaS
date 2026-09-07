"""
Interruptor de facturación por restaurante (Cliente.usar_sunat).

EL PROBLEMA QUE RESUELVE
------------------------
Antes, "¿este restaurante emite boletas?" se deducía de "¿tiene RUC?". Eso
mezcla dos cosas que no son la misma: tener RUC es un dato tributario del
negocio; emitir desde ESTA app es una decisión operativa que además cambia
con el tiempo — se vende desde el primer día y el Facturador se configura
después.

Con la lógica vieja, un restaurante sin RUC recibía un toast rojo en CADA
cobro ("Cobro OK, pero la boleta NO se emitió") y se le llenaba
Admin > Boletas de pendientes que nadie iba a emitir jamás.
"""

import pytest

from backend.models import Cliente


@pytest.fixture
def cliente_con_ruc(test_db, test_cliente):
    test_cliente.ruc = "10200812234"
    test_cliente.razon_social = "Pollería Fogones"
    test_db.commit()
    return test_cliente


def _crear_y_cobrar_mesa(test_client, test_platos, numero_mesa=5):
    resp = test_client.post("/api/comandas", json={
        "numero_mesa": numero_mesa,
        "platos": [{"plato_id": test_platos[0].id, "cantidad": 2}],
    })
    comanda_id = resp.json()["id"]
    test_client.patch(f"/api/comandas/{comanda_id}/estado", json={"estado": "entregado"})
    mesa = next(m for m in test_client.get("/api/mesas").json() if m["numero"] == numero_mesa)
    return test_client.post(f"/api/mesas/{mesa['id']}/cobrar").json()


# ---------- Valor por defecto y compatibilidad ----------

def test_un_restaurante_nuevo_no_emite_boletas(test_client, test_cliente):
    """Default False a propósito: se vende desde el día uno, SUNAT se
    configura después. Lo contrario obliga a configurar el Facturador
    antes de poder cobrar la primera mesa."""
    cfg = test_client.get("/api/configuracion").json()
    assert cfg["usar_sunat"] is False
    assert cfg["tiene_ruc"] is False


def test_la_sesion_informa_si_el_restaurante_emite(test_client_real_auth, test_cliente, test_db):
    """El frontend decide con este dato si intentar emitir tras cobrar —
    sin él volvería el toast rojo en cada venta."""
    from tests.conftest import TEST_USUARIO_EMAIL, TEST_USUARIO_PASSWORD
    login = test_client_real_auth.post("/api/auth/login", json={
        "email": TEST_USUARIO_EMAIL, "password": TEST_USUARIO_PASSWORD,
    })
    assert login.json()["usuario"]["cliente_usar_sunat"] is False

    test_cliente.ruc = "10200812234"
    test_cliente.usar_sunat = True
    test_db.commit()

    login2 = test_client_real_auth.post("/api/auth/login", json={
        "email": TEST_USUARIO_EMAIL, "password": TEST_USUARIO_PASSWORD,
    })
    assert login2.json()["usuario"]["cliente_usar_sunat"] is True


# ---------- Reglas del interruptor ----------

def test_no_se_puede_activar_sin_ruc(test_client, test_cliente):
    """Sin RUC no hay comprobante posible: dejar prenderlo solo llevaría al
    mismo error en cada cobro, pero ahora sin explicación."""
    resp = test_client.patch("/api/configuracion", json={"usar_sunat": True})
    assert resp.status_code == 400
    assert "RUC" in resp.json()["detail"]


def test_con_ruc_se_puede_activar_y_desactivar(test_client, cliente_con_ruc):
    activado = test_client.patch("/api/configuracion", json={"usar_sunat": True})
    assert activado.status_code == 200
    assert activado.json()["usar_sunat"] is True

    apagado = test_client.patch("/api/configuracion", json={"usar_sunat": False})
    assert apagado.status_code == 200
    assert apagado.json()["usar_sunat"] is False


def test_el_cambio_queda_auditado(test_client, test_db, cliente_con_ruc):
    from backend.models import AuditLog

    test_client.patch("/api/configuracion", json={"usar_sunat": True})

    evento = (
        test_db.query(AuditLog)
        .filter(AuditLog.accion == "cambiar_configuracion")
        .order_by(AuditLog.id.desc())
        .first()
    )
    assert evento is not None
    assert "False -> True" in evento.detalle


def test_reenviar_el_mismo_valor_no_genera_evento(test_client, test_db, cliente_con_ruc):
    """El frontend puede reenviar el estado actual; eso no es un cambio y
    no debe ensuciar la auditoría."""
    from backend.models import AuditLog

    test_client.patch("/api/configuracion", json={"usar_sunat": False})
    eventos = test_db.query(AuditLog).filter(AuditLog.accion == "cambiar_configuracion").count()
    assert eventos == 0


# ---------- Efecto sobre Admin > Boletas ----------

def test_sin_emitir_no_hay_ventas_pendientes_de_boleta(
    test_client, test_cliente, test_platos, test_mesas
):
    """EL bug: cada cobro se sumaba a una lista de pendientes que crecía
    para siempre y que nadie iba a resolver — ruido que además esconde un
    pendiente de verdad el día que sí se active la facturación."""
    _crear_y_cobrar_mesa(test_client, test_platos)

    pendientes = test_client.get("/api/facturas/pendientes").json()
    assert pendientes["ventas_sin_boleta"] == []
    assert pendientes["facturas_con_error"] == []


def test_al_activar_la_facturacion_las_ventas_si_aparecen_como_pendientes(
    test_client, test_db, cliente_con_ruc, test_platos, test_mesas
):
    """Contracara: apagar el interruptor no puede volverse una forma de
    esconder boletas que sí había que emitir."""
    cliente_con_ruc.usar_sunat = True
    test_db.commit()

    _crear_y_cobrar_mesa(test_client, test_platos)

    pendientes = test_client.get("/api/facturas/pendientes").json()
    assert len(pendientes["ventas_sin_boleta"]) == 1


# ---------- Permisos ----------

def test_solo_el_admin_toca_la_configuracion(test_client_real_auth, test_cliente):
    from tests.integration.test_endpoints import _crear_staff_y_loguear

    _, token = _crear_staff_y_loguear(test_client_real_auth, "Pedro Mozo", ["mozo"])
    headers = {"Authorization": f"Bearer {token}"}

    assert test_client_real_auth.get("/api/configuracion", headers=headers).status_code == 403
    assert test_client_real_auth.patch(
        "/api/configuracion", json={"usar_sunat": True}, headers=headers,
    ).status_code == 403


def test_sin_sesion_no_se_puede_leer_ni_cambiar(test_client_real_auth, test_cliente):
    assert test_client_real_auth.get("/api/configuracion").status_code == 401
    assert test_client_real_auth.patch(
        "/api/configuracion", json={"usar_sunat": True},
    ).status_code == 401
