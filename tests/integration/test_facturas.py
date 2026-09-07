"""
Tests de facturación SUNAT.

Dos emisores posibles (backend.config.settings.emisor_facturacion):

- "sfs_local" (default): escribe .cab/.det en disco. Se prueba con una
  carpeta temporal real (tmp_path) — no hace falta mockear nada, es
  escritura de archivo puro, así que estos tests ejercitan el código real.
- "facturacion_pe": llama a un proveedor HTTP externo, que sí se mockea
  (backend.utils.facturacion_pe.generar_boleta) porque ahí no queremos
  pegarle a la red real en un test.

En ambos casos, lo que se prueba acá es LA LÓGICA DE NEGOCIO de RestoMind:
qué se guarda, qué se rechaza, el correlativo, el detalle copiado de la
comanda real.

La ESTRUCTURA de los archivos planos (cuántos campos lleva cada uno y qué
va en cada posición, según el Anexo I de SUNAT) se prueba aparte, en
tests/unit/test_sfs_export.py.
"""

import pytest

from backend.config import settings
from backend.utils.facturacion_pe import FacturacionPeError, FacturacionPeResultado


@pytest.fixture
def cliente_con_ruc(test_db, test_cliente):
    """El fixture test_cliente no trae RUC — la mayoría de tests de facturas
    lo necesitan configurado (es la primera validación del endpoint).

    usar_sunat=True porque este fixture representa un restaurante que SÍ
    emite desde RestoMind: tener RUC y emitir son dos cosas distintas (ver
    tests/integration/test_configuracion.py), y los endpoints de
    recuperación de boletas solo aplican al que emite. Es el mismo criterio
    que usó la migración con los clientes que ya existían."""
    test_cliente.ruc = "10200812234"
    test_cliente.razon_social = "Pollería Fogones"
    test_cliente.usar_sunat = True
    test_db.commit()
    return test_cliente


@pytest.fixture
def sfs_dir(tmp_path, monkeypatch):
    """Apunta SFS_EXPORT_DIR a una carpeta temporal real y la restaura al
    terminar el test (settings es un singleton importado en todo el código,
    así que monkeypatch.setattr sobre el objeto es lo que garantiza el
    rollback automático, no reasignar la variable de módulo)."""
    monkeypatch.setattr(settings, "sfs_export_dir", str(tmp_path))
    monkeypatch.setattr(settings, "emisor_facturacion", "sfs_local")
    return tmp_path


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


# ============ EMISOR sfs_local (default) ============

def test_generar_factura_sin_ruc_configurado_falla(test_client, test_cliente, test_platos, test_mesas, sfs_dir):
    """test_cliente (sin fixture cliente_con_ruc) no tiene RUC — debe rechazar
    ANTES de intentar escribir ningún archivo, con un mensaje accionable."""
    comanda_ids = _crear_y_cobrar_mesa(test_client, test_platos)

    resp = test_client.post("/api/facturas/generar", json={"comanda_ids": comanda_ids})

    assert resp.status_code == 400
    assert "RUC" in resp.json()["detail"]


def test_generar_factura_escribe_cab_y_det_en_la_carpeta_configurada(
    test_client, cliente_con_ruc, test_platos, test_mesas, sfs_dir
):
    comanda_ids = _crear_y_cobrar_mesa(test_client, test_platos)

    resp = test_client.post("/api/facturas/generar", json={"comanda_ids": comanda_ids})

    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["estado"] == "generado_localmente"
    assert data["numero_boleta"] == "B001-00000001"
    assert data["total"] == 90.00
    # subtotal + igv debe cuadrar exacto con total (ver _calcular_montos:
    # redondear cada uno por separado podía descuadrar el total en centavos).
    assert round(data["subtotal"] + data["igv"], 2) == data["total"]

    # Son CUATRO archivos, no dos: el Anexo I los agrupa bajo "Archivos
    # Obligatorios". Sin .tri (desglose de tributos) ni .ley (monto en
    # letras) el comprobante está incompleto para SUNAT.
    nombre_esperado = "10200812234-03-B001-00000001"
    ruta_cab = sfs_dir / f"{nombre_esperado}.cab"
    ruta_det = sfs_dir / f"{nombre_esperado}.det"
    for extension in ("cab", "det", "tri", "ley"):
        assert (sfs_dir / f"{nombre_esperado}.{extension}").exists(), f"falta el .{extension}"
    assert data["archivo_local"] == str(ruta_cab)

    contenido_det = ruta_det.read_text(encoding="latin-1")
    assert "Ceviche Cl" in contenido_det  # "Ceviche Clásico" sin acento en latin-1 no rompe la lectura
    assert "90.00" not in contenido_det.split("|")[0]  # sanity: no quedó todo en un solo campo


def test_generar_factura_cabecera_tiene_los_18_campos_en_el_orden_del_spec(
    test_client, cliente_con_ruc, test_platos, test_mesas, sfs_dir
):
    """Posiciones según el Anexo I de SUNAT (AnexosIyII_Formato1.3.xlsx,
    hoja "Factura y boleta 2.1"). El índice de la lista es la posición del
    Anexo menos uno."""
    comanda_ids = _crear_y_cobrar_mesa(test_client, test_platos)
    resp = test_client.post("/api/facturas/generar", json={"comanda_ids": comanda_ids})
    assert resp.status_code == 201, resp.text

    ruta_cab = sfs_dir / "10200812234-03-B001-00000001.cab"
    campos = ruta_cab.read_text(encoding="latin-1").strip("\r\n").split("|")

    assert len(campos) == 18
    assert campos[0] == "0101"        # 1.  tipOperacion (venta interna)
    assert campos[3] == ""            # 4.  fecVencimiento: una boleta no vence
    assert campos[4] == "0000"        # 5.  codLocalEmisor
    assert campos[5] == "0"           # 6.  tipDocUsuario: Público General -> Varios
    assert campos[6] == "00000000"    # 7.  numDocUsuario
    assert campos[8] == "PEN"         # 9.  tipMoneda
    assert campos[12] == "0.00"       # 13. sumDescTotal
    assert campos[13] == "0.00"       # 14. sumOtrosCargos
    assert campos[14] == "0.00"       # 15. sumTotalAnticipos
    # 12. sumPrecioVenta == 16. sumImpVenta
    assert campos[11] == campos[15] == "90.00"
    assert campos[16] == "2.1"        # 17. ublVersionId
    assert campos[17] == "2.0"        # 18. customizationId


def test_generar_factura_detalle_multiples_platos_cuadra_exacto_con_cabecera(
    test_client, cliente_con_ruc, test_platos, test_mesas, sfs_dir
):
    """3 ceviches (S/45 c/u) + 2 jugos (S/5 c/u) = S/145. El IGV por línea
    se redondea independiente por línea; el ajuste de residuo en la última
    línea (ver _construir_detalle_lineas) debe hacer que la suma cuadre
    EXACTO con la cabecera — no "cerca", exacto — porque eso es lo primero
    que un validador de SUNAT cruza entre cabecera y detalle."""
    resp = test_client.post("/api/comandas", json={
        "numero_mesa": 5,
        "platos": [
            {"plato_id": test_platos[0].id, "cantidad": 3},  # Ceviche
            {"plato_id": test_platos[1].id, "cantidad": 2},  # Jugo
        ],
    })
    comanda_id = resp.json()["id"]
    test_client.patch(f"/api/comandas/{comanda_id}/estado", json={"estado": "entregado"})
    mesa = next(m for m in test_client.get("/api/mesas").json() if m["numero"] == 5)
    cobro = test_client.post(f"/api/mesas/{mesa['id']}/cobrar").json()

    resp = test_client.post("/api/facturas/generar", json={"comanda_ids": cobro["comanda_ids"]})
    assert resp.status_code == 201, resp.text
    data = resp.json()

    ruta_cab = sfs_dir / "10200812234-03-B001-00000001.cab"
    ruta_det = sfs_dir / "10200812234-03-B001-00000001.det"
    campos_cab = ruta_cab.read_text(encoding="latin-1").strip("\r\n").split("|")

    # read_text en modo texto normaliza cualquier fin de línea (\r\n, \r, \n)
    # a \n al leer (universal newlines) — separar por \n acá, no por \r\n,
    # sin importar qué se haya escrito en disco.
    lineas_det = [
        linea.split("|")
        for linea in ruta_det.read_text(encoding="latin-1").strip("\n").split("\n")
    ]
    assert len(lineas_det) == 2
    for campos_linea in lineas_det:
        assert len(campos_linea) == 36
        assert campos_linea[0] == "NIU"   # 1.  codUnidadMedida
        assert campos_linea[12] == "10"   # 13. tipAfeIGV: Gravado - Operación Onerosa

    # 35. mtoValorVentaItem y 9. mtoIgvItem, sumados sobre todas las líneas,
    # tienen que dar exactamente lo que declara la cabecera.
    suma_valor_venta_lineas = round(sum(float(l[34]) for l in lineas_det), 2)
    suma_igv_lineas = round(sum(float(l[8]) for l in lineas_det), 2)

    assert suma_valor_venta_lineas == float(campos_cab[10])  # 11. sumTotValVenta
    assert suma_igv_lineas == float(campos_cab[9])           # 10. sumTotTributos
    assert data["total"] == 145.00


def test_generar_factura_carpeta_no_configurada_falla_con_error_claro(
    test_client, cliente_con_ruc, test_platos, test_mesas, monkeypatch
):
    monkeypatch.setattr(settings, "sfs_export_dir", "")
    monkeypatch.setattr(settings, "emisor_facturacion", "sfs_local")
    comanda_ids = _crear_y_cobrar_mesa(test_client, test_platos)

    resp = test_client.post("/api/facturas/generar", json={"comanda_ids": comanda_ids})

    assert resp.status_code == 502
    factura = resp.json()["detail"]["factura"]
    assert factura["estado"] == "error"
    assert "SFS_EXPORT_DIR" in factura["error_mensaje"]


def test_generar_factura_carpeta_no_existe_es_reintentable_tras_corregir(
    test_client, cliente_con_ruc, test_platos, test_mesas, monkeypatch, tmp_path
):
    carpeta_inexistente = tmp_path / "no-existe-todavia"
    monkeypatch.setattr(settings, "sfs_export_dir", str(carpeta_inexistente))
    monkeypatch.setattr(settings, "emisor_facturacion", "sfs_local")
    comanda_ids = _crear_y_cobrar_mesa(test_client, test_platos)

    resp = test_client.post("/api/facturas/generar", json={"comanda_ids": comanda_ids})
    assert resp.status_code == 502
    factura_id = resp.json()["detail"]["factura"]["id"]

    # Se "corrige" creando la carpeta — el correlativo ya reservado (1) no
    # debe cambiar al reintentar.
    carpeta_inexistente.mkdir()
    resp = test_client.post(f"/api/facturas/{factura_id}/reintentar")
    assert resp.status_code == 200
    data = resp.json()
    assert data["estado"] == "generado_localmente"
    assert data["numero_boleta"] == "B001-00000001"


def test_generar_factura_dos_correlativos_consecutivos(test_client, cliente_con_ruc, test_platos, test_mesas, sfs_dir):
    """El correlativo vive en Cliente.boleta_correlativo_actual y debe
    incrementar de verdad entre dos boletas del mismo restaurante."""
    ids_1 = _crear_y_cobrar_mesa(test_client, test_platos, numero_mesa=1)
    resp_1 = test_client.post("/api/facturas/generar", json={"comanda_ids": ids_1})
    assert resp_1.json()["numero_boleta"] == "B001-00000001"

    ids_2 = _crear_y_cobrar_mesa(test_client, test_platos, numero_mesa=2)
    resp_2 = test_client.post("/api/facturas/generar", json={"comanda_ids": ids_2})
    assert resp_2.json()["numero_boleta"] == "B001-00000002"


def test_generar_factura_comanda_no_cobrada_falla(test_client, cliente_con_ruc, test_platos, test_mesas, sfs_dir):
    resp = test_client.post("/api/comandas", json={
        "numero_mesa": 1,
        "platos": [{"plato_id": test_platos[0].id, "cantidad": 1}],
    })
    comanda_id = resp.json()["id"]  # sigue en estado 'cocina', nunca se cobró

    resp = test_client.post("/api/facturas/generar", json={"comanda_ids": [comanda_id]})

    assert resp.status_code == 400
    assert "cobradas" in resp.json()["detail"]


def test_generar_factura_dos_veces_la_misma_comanda_falla(test_client, cliente_con_ruc, test_platos, test_mesas, sfs_dir):
    comanda_ids = _crear_y_cobrar_mesa(test_client, test_platos)

    resp_1 = test_client.post("/api/facturas/generar", json={"comanda_ids": comanda_ids})
    assert resp_1.status_code == 201

    resp_2 = test_client.post("/api/facturas/generar", json={"comanda_ids": comanda_ids})
    assert resp_2.status_code == 400
    assert "ya tienen una boleta" in resp_2.json()["detail"]


# ============ Resolución automática de documento del comprador ============

def test_documento_vacio_es_publico_general(test_client, cliente_con_ruc, test_platos, test_mesas, sfs_dir):
    comanda_ids = _crear_y_cobrar_mesa(test_client, test_platos)
    resp = test_client.post("/api/facturas/generar", json={"comanda_ids": comanda_ids})
    assert resp.status_code == 201

    campos = (sfs_dir / "10200812234-03-B001-00000001.cab").read_text(encoding="latin-1").split("|")
    assert campos[5] == "0"  # 6. tipDocUsuario: No domiciliado/Varios
    assert campos[6] == "00000000"  # 7. numDocUsuario
    assert campos[7] == "CLIENTES VARIOS"  # 8. rznSocialUsuario


def test_documento_8_digitos_es_dni(test_client, cliente_con_ruc, test_platos, test_mesas, sfs_dir):
    comanda_ids = _crear_y_cobrar_mesa(test_client, test_platos)
    resp = test_client.post("/api/facturas/generar", json={
        "comanda_ids": comanda_ids, "documento_comprador": "73081441",
    })
    assert resp.status_code == 201

    campos = (sfs_dir / "10200812234-03-B001-00000001.cab").read_text(encoding="latin-1").split("|")
    assert campos[5] == "1"  # 6. tipDocUsuario: DNI
    assert campos[6] == "73081441"  # 7. numDocUsuario
    assert campos[7] == "-"  # 8. rznSocialUsuario


def test_documento_11_digitos_es_ruc(test_client, cliente_con_ruc, test_platos, test_mesas, sfs_dir):
    comanda_ids = _crear_y_cobrar_mesa(test_client, test_platos)
    resp = test_client.post("/api/facturas/generar", json={
        "comanda_ids": comanda_ids, "documento_comprador": "20600055519",
    })
    assert resp.status_code == 201

    campos = (sfs_dir / "10200812234-03-B001-00000001.cab").read_text(encoding="latin-1").split("|")
    assert campos[5] == "6"  # 6. tipDocUsuario: RUC
    assert campos[6] == "20600055519"  # 7. numDocUsuario
    assert campos[7] == "-"  # 8. rznSocialUsuario


@pytest.mark.parametrize("documento, motivo", [
    ("123456789", "9 dígitos: ni DNI (8) ni RUC (11)"),
    ("11111111111", "11 dígitos pero no empieza en 10 ni 20: no es un RUC válido"),
    ("30200812234", "prefijo 30 no existe para contribuyentes que emiten boletas"),
    ("1020081223a", "letras"),
])
def test_documento_invalido_se_rechaza_antes_de_tocar_disco(
    test_client, cliente_con_ruc, test_platos, test_mesas, sfs_dir, documento, motivo
):
    """Rechazar rápido en vez de adivinar: un tipeo del cajero no debe
    convertirse en un comprobante que SUNAT rechaza DESPUÉS de emitido
    (cuando el correlativo ya se consumió y el cliente ya se fue)."""
    comanda_ids = _crear_y_cobrar_mesa(test_client, test_platos)
    resp = test_client.post("/api/facturas/generar", json={
        "comanda_ids": comanda_ids, "documento_comprador": documento,
    })
    assert resp.status_code == 422, f"{documento} ({motivo}) debería rechazarse"
    assert not list(sfs_dir.iterdir())  # no se escribió nada


@pytest.mark.parametrize("documento", ["10200812234", "20600055519"])
def test_ruc_con_prefijo_valido_se_acepta(
    test_client, cliente_con_ruc, test_platos, test_mesas, sfs_dir, documento
):
    """10 = persona natural con negocio, 20 = persona jurídica: los dos
    prefijos que SUNAT usa para contribuyentes."""
    comanda_ids = _crear_y_cobrar_mesa(test_client, test_platos)
    resp = test_client.post("/api/facturas/generar", json={
        "comanda_ids": comanda_ids, "documento_comprador": documento,
    })
    assert resp.status_code == 201, resp.text


def test_documento_con_espacios_o_guiones_se_normaliza(
    test_client, cliente_con_ruc, test_platos, test_mesas, sfs_dir
):
    """El cajero puede tipear "7308-1441" de apuro; se limpia en vez de
    rechazarlo, pero lo que llega al .cab son solo dígitos."""
    comanda_ids = _crear_y_cobrar_mesa(test_client, test_platos)
    resp = test_client.post("/api/facturas/generar", json={
        "comanda_ids": comanda_ids, "documento_comprador": "7308-1441",
    })
    assert resp.status_code == 201, resp.text

    campos = (sfs_dir / "10200812234-03-B001-00000001.cab").read_text(encoding="latin-1").split("|")
    assert campos[5] == "1"  # 6. tipDocUsuario: DNI
    assert campos[6] == "73081441"  # 7. numDocUsuario, sin el guion


def test_borrar_cliente_no_deja_facturas_huerfanas(test_db, test_client, cliente_con_ruc, test_platos, test_mesas, sfs_dir):
    """Mismo bug que ya se corrigió una vez para Categoria (ver CLAUDE.md):
    sin cascade, borrar un restaurante dejaba sus facturas y las filas de
    factura_comandas colgando en la BD — invisibles en la app (todo filtra
    por cliente_id) pero acumulándose para siempre. Con facturas es peor
    que con categorías: son registros tributarios."""
    from backend.models import Cliente, Factura, FacturaComanda

    comanda_ids = _crear_y_cobrar_mesa(test_client, test_platos)
    assert test_client.post("/api/facturas/generar", json={"comanda_ids": comanda_ids}).status_code == 201
    assert test_db.query(Factura).count() == 1
    assert test_db.query(FacturaComanda).count() == 1

    test_db.delete(test_db.query(Cliente).filter(Cliente.id == cliente_con_ruc.id).first())
    test_db.commit()

    assert test_db.query(Factura).count() == 0
    assert test_db.query(FacturaComanda).count() == 0


def test_pendientes_lista_factura_con_error_y_permite_reintentar(
    test_client, cliente_con_ruc, test_platos, test_mesas, monkeypatch, tmp_path
):
    """El caso real que se dio en producción: la emisión falla (carpeta del
    Facturador mal configurada), la venta queda cobrada y la boleta en
    'error'. Sin esta pantalla el cobro es irrecuperable desde la app."""
    carpeta = tmp_path / "todavia-no"
    monkeypatch.setattr(settings, "sfs_export_dir", str(carpeta))
    monkeypatch.setattr(settings, "emisor_facturacion", "sfs_local")

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

    carpeta.mkdir()
    factura_id = data["facturas_con_error"][0]["id"]
    assert test_client.post(f"/api/facturas/{factura_id}/reintentar").status_code == 200

    assert test_client.get("/api/facturas/pendientes").json()["facturas_con_error"] == []


def test_pendientes_detecta_venta_cobrada_que_nunca_llego_a_facturarse(
    test_client, cliente_con_ruc, test_platos, test_mesas, sfs_dir
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
