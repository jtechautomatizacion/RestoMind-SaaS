"""
API del agente que baja los comprobantes SUNAT a la PC del restaurante.

Lo que se prueba acá es lo que puede salir caro si falla:

- Que el token de un restaurante NO alcance los comprobantes de otro. Es
  la regla multi-tenant de CLAUDE.md, y acá pesa más que en el resto de la
  app: un token vive en el disco de una PC que está en el salón de un
  local, fuera de nuestro control.
- Que un comprobante ya entregado deje de aparecer, para que el Facturador
  no lo procese dos veces y emita la boleta duplicada ante SUNAT.
- Que un comprobante al que le falta un archivo NO se entregue a medias.
"""

from datetime import datetime

import pytest

from backend.auth import hash_password
from backend.config import settings
from backend.models import AgenteToken, Cliente, Factura

TOKEN_VALIDO = "token-de-prueba-del-agente-123456"
OTRO_TOKEN = "token-de-otro-restaurante-987654"


@pytest.fixture
def sfs_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "sfs_export_dir", str(tmp_path))
    monkeypatch.setattr(settings, "emisor_facturacion", "sfs_local")
    return tmp_path


@pytest.fixture
def cliente_con_ruc(test_db, test_cliente):
    test_cliente.ruc = "10200812234"
    test_cliente.razon_social = "Pollería Fogones"
    test_db.commit()
    return test_cliente


@pytest.fixture
def token_agente(test_db, cliente_con_ruc):
    test_db.add(AgenteToken(
        cliente_id=cliente_con_ruc.id,
        nombre="Caja principal",
        token_hash=hash_password(TOKEN_VALIDO),
    ))
    test_db.commit()
    return TOKEN_VALIDO


def _headers(token):
    return {"X-Agente-Token": token}


def _emitir_boleta(test_client, test_platos, numero_mesa=5):
    """Flujo real: comanda -> entregado -> cobrar -> generar boleta."""
    resp = test_client.post("/api/comandas", json={
        "numero_mesa": numero_mesa,
        "platos": [{"plato_id": test_platos[0].id, "cantidad": 2}],
    })
    comanda_id = resp.json()["id"]
    test_client.patch(f"/api/comandas/{comanda_id}/estado", json={"estado": "entregado"})
    mesa = next(m for m in test_client.get("/api/mesas").json() if m["numero"] == numero_mesa)
    cobro = test_client.post(f"/api/mesas/{mesa['id']}/cobrar").json()

    resp = test_client.post("/api/facturas/generar", json={"comanda_ids": cobro["comanda_ids"]})
    assert resp.status_code == 201, resp.text
    return resp.json()


# ---------- Autenticación ----------

def test_sin_token_no_se_puede_consultar(test_client):
    assert test_client.get("/api/agente/pendientes").status_code == 401
    assert test_client.get("/api/agente/ping").status_code == 401
    assert test_client.post("/api/agente/confirmar", json={"ids": [1]}).status_code == 401


def test_token_invalido_se_rechaza(test_client, token_agente):
    resp = test_client.get("/api/agente/pendientes", headers=_headers("token-inventado"))
    assert resp.status_code == 401


def test_token_revocado_deja_de_funcionar(test_client, test_db, token_agente):
    """Es la razón principal de tener un token propio en vez de un JWT: un
    JWT no se puede revocar hasta que expire."""
    assert test_client.get("/api/agente/ping", headers=_headers(TOKEN_VALIDO)).status_code == 200

    agente = test_db.query(AgenteToken).first()
    agente.estado = "revocado"
    test_db.commit()

    assert test_client.get("/api/agente/ping", headers=_headers(TOKEN_VALIDO)).status_code == 401


def test_el_uso_del_token_queda_registrado(test_client, test_db, token_agente):
    """ultimo_uso_en es lo que permite detectar desde el servidor un agente
    que dejó de reportarse, antes de que el restaurante llame porque no le
    salen las boletas."""
    assert test_db.query(AgenteToken).first().ultimo_uso_en is None

    test_client.get("/api/agente/ping", headers=_headers(TOKEN_VALIDO))

    test_db.expire_all()
    assert test_db.query(AgenteToken).first().ultimo_uso_en is not None


# ---------- Entrega de comprobantes ----------

def test_ping_informa_cuantos_hay_pendientes(test_client, token_agente, test_platos, test_mesas, sfs_dir):
    vacio = test_client.get("/api/agente/ping", headers=_headers(TOKEN_VALIDO)).json()
    assert vacio["pendientes"] == 0
    assert vacio["cliente_nombre"]

    _emitir_boleta(test_client, test_platos)

    lleno = test_client.get("/api/agente/ping", headers=_headers(TOKEN_VALIDO)).json()
    assert lleno["pendientes"] == 1


def test_los_cuatro_archivos_llegan_con_el_contenido_del_disco(
    test_client, token_agente, test_platos, test_mesas, sfs_dir
):
    _emitir_boleta(test_client, test_platos)

    resp = test_client.get("/api/agente/pendientes", headers=_headers(TOKEN_VALIDO))
    assert resp.status_code == 200
    comprobantes = resp.json()["comprobantes"]
    assert len(comprobantes) == 1

    c = comprobantes[0]
    assert c["nombre_base"] == "10200812234-03-B001-00000001"
    assert c["numero_boleta"] == "B001-00000001"

    # Byte a byte contra lo que hay en disco: el agente lo va a escribir tal
    # cual en la carpeta del Facturador, así que cualquier transformación en
    # el camino (fin de línea, encoding) llegaría al comprobante final.
    for extension in ("cab", "det", "tri", "ley"):
        en_disco = (sfs_dir / f"{c['nombre_base']}.{extension}").read_bytes().decode("latin-1")
        assert c[extension] == en_disco


def test_el_crlf_sobrevive_al_viaje_por_la_api(test_client, token_agente, test_platos, test_mesas, sfs_dir):
    """El formato exige CRLF. Si la API lo devolviera traducido a \\n, el
    agente escribiría archivos que el Facturador no puede parsear."""
    _emitir_boleta(test_client, test_platos)
    c = test_client.get("/api/agente/pendientes", headers=_headers(TOKEN_VALIDO)).json()["comprobantes"][0]

    for extension in ("cab", "det", "tri", "ley"):
        assert c[extension].endswith("\r\n")
        assert "\r\r" not in c[extension]


def test_un_comprobante_confirmado_no_vuelve_a_aparecer(
    test_client, token_agente, test_platos, test_mesas, sfs_dir
):
    """Si volviera a aparecer, el agente lo escribiría de nuevo en la
    carpeta y el Facturador podría emitir la boleta dos veces ante SUNAT."""
    _emitir_boleta(test_client, test_platos)
    pendientes = test_client.get("/api/agente/pendientes", headers=_headers(TOKEN_VALIDO)).json()
    ids = [c["id"] for c in pendientes["comprobantes"]]

    resp = test_client.post("/api/agente/confirmar", json={"ids": ids}, headers=_headers(TOKEN_VALIDO))
    assert resp.status_code == 204

    despues = test_client.get("/api/agente/pendientes", headers=_headers(TOKEN_VALIDO)).json()
    assert despues["comprobantes"] == []
    assert test_client.get("/api/agente/ping", headers=_headers(TOKEN_VALIDO)).json()["pendientes"] == 0


def test_reconfirmar_no_corre_la_fecha_de_entrega(
    test_client, test_db, token_agente, test_platos, test_mesas, sfs_dir
):
    """El agente confirma, se corta la red antes de recibir la respuesta, y
    reintenta. La fecha original de entrega no debe moverse."""
    _emitir_boleta(test_client, test_platos)
    ids = [c["id"] for c in test_client.get(
        "/api/agente/pendientes", headers=_headers(TOKEN_VALIDO)).json()["comprobantes"]]

    test_client.post("/api/agente/confirmar", json={"ids": ids}, headers=_headers(TOKEN_VALIDO))
    test_db.expire_all()
    primera = test_db.query(Factura).filter(Factura.id == ids[0]).first().descargado_en

    test_client.post("/api/agente/confirmar", json={"ids": ids}, headers=_headers(TOKEN_VALIDO))
    test_db.expire_all()
    assert test_db.query(Factura).filter(Factura.id == ids[0]).first().descargado_en == primera


def test_un_comprobante_sin_sus_archivos_en_disco_no_se_entrega(
    test_client, token_agente, test_platos, test_mesas, sfs_dir
):
    """Mandarle al Facturador tres de cuatro archivos es peor que no
    mandarle nada: se queda esperando el que falta, o procesa algo a
    medias. El comprobante sigue contando como pendiente para que se pueda
    reintentar desde Admin > Boletas."""
    _emitir_boleta(test_client, test_platos)
    (sfs_dir / "10200812234-03-B001-00000001.tri").unlink()

    resp = test_client.get("/api/agente/pendientes", headers=_headers(TOKEN_VALIDO))
    assert resp.json()["comprobantes"] == []
    # Sigue pendiente: no se lo dio por entregado.
    assert test_client.get("/api/agente/ping", headers=_headers(TOKEN_VALIDO)).json()["pendientes"] == 1


# ---------- Aislamiento entre restaurantes ----------

def test_un_agente_no_ve_comprobantes_de_otro_restaurante(
    test_client, test_db, token_agente, cliente_con_ruc, test_platos, test_mesas, sfs_dir
):
    """El token vive en una PC que está en el salón de un local. Si con él
    se pudieran leer las boletas de otro restaurante, ese token sería una
    filtración de datos tributarios de un tercero."""
    _emitir_boleta(test_client, test_platos)

    test_db.add(Cliente(id="otro-resto", nombre="Otro Restaurante",
                        email="otro@test.local", ruc="20600055519"))
    test_db.add(AgenteToken(cliente_id="otro-resto", nombre="Su caja",
                            token_hash=hash_password(OTRO_TOKEN)))
    test_db.commit()

    ajeno = test_client.get("/api/agente/pendientes", headers=_headers(OTRO_TOKEN))
    assert ajeno.status_code == 200
    assert ajeno.json()["comprobantes"] == []
    assert test_client.get("/api/agente/ping", headers=_headers(OTRO_TOKEN)).json()["cliente_id"] == "otro-resto"


def test_no_se_pueden_confirmar_comprobantes_de_otro_restaurante(
    test_client, test_db, token_agente, test_platos, test_mesas, sfs_dir
):
    """Sin el filtro por cliente_id, un token podría marcar como entregadas
    las boletas de otro local: desaparecerían de su cola sin haber llegado
    nunca a su Facturador, y nadie se enteraría hasta que SUNAT reclame."""
    _emitir_boleta(test_client, test_platos)
    ids = [c["id"] for c in test_client.get(
        "/api/agente/pendientes", headers=_headers(TOKEN_VALIDO)).json()["comprobantes"]]

    test_db.add(Cliente(id="otro-resto", nombre="Otro", email="o@test.local", ruc="20600055519"))
    test_db.add(AgenteToken(cliente_id="otro-resto", nombre="Su caja",
                            token_hash=hash_password(OTRO_TOKEN)))
    test_db.commit()

    resp = test_client.post("/api/agente/confirmar", json={"ids": ids}, headers=_headers(OTRO_TOKEN))
    assert resp.status_code == 204  # No falla, pero tampoco hace nada.

    test_db.expire_all()
    assert test_db.query(Factura).filter(Factura.id == ids[0]).first().descargado_en is None
    # Y para su dueño legítimo sigue pendiente.
    assert test_client.get("/api/agente/ping", headers=_headers(TOKEN_VALIDO)).json()["pendientes"] == 1
