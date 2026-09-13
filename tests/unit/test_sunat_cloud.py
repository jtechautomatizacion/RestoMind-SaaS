"""
Tests del emisor "sunat_cloud" (backend/utils/sunat_cloud.py).

El grueso está en la conversión de IGV, que es donde una integración mal
hecha emite boletas con montos equivocados sin que nada falle a la vista:
RestoMind guarda los precios CON IGV incluido y sunat-py los espera SIN. Si
alguien "simplifica" pasando el precio de carta directo, cada boleta declara
18% de más y estos tests son lo único que lo detecta antes que SUNAT.
"""

from decimal import Decimal
from unittest.mock import patch

import httpx
import pytest

from backend.utils.sunat_cloud import (
    RECEPTOR_GENERICO,
    SunatCloudError,
    _lineas,
    _receptor,
    diferencia_contra_lo_cobrado,
    emitir_boleta,
    precio_sin_igv,
    total_que_declarara_sunat,
)


# ============ CONVERSIÓN DE IGV ============

def test_un_precio_de_carta_se_convierte_a_base_imponible():
    # S/ 118.00 con IGV incluido son S/ 100.00 de base + S/ 18.00 de IGV.
    assert precio_sin_igv(118.00) == Decimal("100.00")


def _detalle(precio, cantidad):
    return [{"plato_id": 1, "descripcion": "Plato", "cantidad": cantidad,
             "precio_unitario": precio, "subtotal": precio * cantidad}]


@pytest.mark.parametrize("precio, cantidad, cobrado", [
    (45.00, 2, "90.00"),
    (12.50, 3, "37.50"),
    (8.90, 7, "62.30"),
    (35.40, 4, "141.60"),
    (19.90, 3, "59.70"),
    (23.00, 5, "115.00"),
    (15.00, 2, "30.00"),
])
def test_la_boleta_declara_exactamente_lo_que_pago_el_comensal(precio, cantidad, cobrado):
    """
    Comprueba contra la réplica EXACTA de la aritmética de SUNAT
    (total_que_declarara_sunat), no contra base × cantidad × 1.18.

    La diferencia importa: SUNAT redondea DOS veces (la base de la línea y
    después su IGV), y la fórmula de un solo redondeo da por buenos casos
    que en realidad descuadran. Un test que valida con la fórmula
    equivocada da confianza falsa, que es peor que no tenerlo.
    """
    assert total_que_declarara_sunat(_detalle(precio, cantidad)) == Decimal(cobrado)


def test_dos_decimales_en_la_base_descuadran_la_boleta():
    """
    Fija la razón de PRECISION_BASE (5 decimales, los que usa SUNAT) para
    que nadie la 'simplifique' a 2: con 2 decimales, S/ 45.00 × 2 declara
    S/ 90.01.
    """
    base_2dec = (Decimal("45.00") / Decimal("1.18")).quantize(Decimal("0.01"))
    linea = (base_2dec * 2).quantize(Decimal("0.01"))
    con_2dec = linea + (linea * Decimal("0.18")).quantize(Decimal("0.01"))
    assert con_2dec == Decimal("90.01")   # el bug

    assert total_que_declarara_sunat(_detalle(45.00, 2)) == Decimal("90.00")   # el arreglo


@pytest.mark.parametrize("precio, cantidad, cobrado, declarado", [
    (10.00, 1, "10.00", "9.99"),
    (45.00, 1, "45.00", "45.01"),
    (120.00, 1, "120.00", "119.99"),
    (7.50, 6, "45.00", "45.01"),
    (25.00, 4, "100.00", "100.01"),
])
def test_hay_precios_para_los_que_NINGUNA_base_da_el_total_exacto(
    precio, cantidad, cobrado, declarado
):
    """
    Deja registrada una limitación real, no un bug pendiente.

    SUNAT calcula el IGV como 18% de una base redondeada a céntimos. Para
    S/ 10.00: con base 8.47 el total da 9.99 y con 8.48 da 10.01 — no
    existe ninguna base intermedia. Ningún ajuste de decimales lo arregla.

    Por eso el código NO intenta corregirlo: lo DETECTA
    (diferencia_contra_lo_cobrado) y lo anota en la Factura, para que el
    desvío no pase desapercibido al cuadrar la caja contra los comprobantes.

    Si mañana la aritmética cambiara y estos casos empezaran a cuadrar,
    este test falla y hay que revisar la decisión — no borrarlo sin más.
    """
    detalles = _detalle(precio, cantidad)
    assert total_que_declarara_sunat(detalles) == Decimal(declarado)
    assert diferencia_contra_lo_cobrado(detalles, float(cobrado)) != 0


def test_redondea_hacia_arriba_y_no_como_lo_hace_python_por_defecto():
    """
    Python redondea 'al par' (banker's rounding): con ROUND_HALF_EVEN un
    valor justo en el medio se va hacia abajo la mitad de las veces. El
    criterio tributario es HALF_UP.
    """
    # 0.00002950 / 1.18 = 0.000025 exacto: cae justo en el medio del QUINTO
    # decimal Y el dígito previo es par, que es la única combinación donde
    # los dos modos de redondeo dan resultados distintos. Con un valor
    # cualquiera, este test pasaría igual sin el fix y no probaría nada.
    exacto = Decimal("0.00002950")
    assert precio_sin_igv(exacto) == Decimal("0.00003")   # HALF_UP; HALF_EVEN daría 0.00002


def test_no_pierde_precision_por_usar_float():
    """Se convierte desde str y no desde float: Decimal(0.1) arrastra el
    error binario de IEEE754."""
    assert precio_sin_igv(0.1) == Decimal("0.08475")


# ============ ARMADO DE LÍNEAS ============

def test_las_lineas_llevan_el_precio_sin_igv_no_el_de_la_carta():
    detalles = [{
        "plato_id": 7, "descripcion": "Ceviche", "cantidad": 2,
        "precio_unitario": 118.00, "subtotal": 236.00,
    }]
    linea = _lineas(detalles)[0]
    assert linea["precio_unitario"] == "100.00000"   # NO "118.00"
    assert linea["codigo"] == "7"
    assert linea["descripcion"] == "Ceviche"
    assert linea["unidad"] == "NIU"


def test_un_plato_borrado_igual_produce_una_linea_emitible():
    """El código de producto es obligatorio en el UBL. Un plato eliminado
    dejaría plato_id en None y sin este marcador el XML sale inválido —
    la venta ya ocurrió, la boleta tiene que poder emitirse igual."""
    detalles = [{
        "plato_id": None, "descripcion": "Plato eliminado", "cantidad": 1,
        "precio_unitario": 20.00, "subtotal": 20.00,
    }]
    assert _lineas(detalles)[0]["codigo"] == "SIN-COD"


# ============ RECEPTOR ============

def test_sin_documento_la_boleta_va_a_publico_general():
    """Es el caso normal: el comensal no pide comprobante a su nombre."""
    assert _receptor(None, None, None) == RECEPTOR_GENERICO


def test_con_dni_se_usa_el_documento_del_comensal():
    r = _receptor("1", "45678912", "Juan Perez")
    assert r["tipo_doc"] == "1"
    assert r["numero_doc"] == "45678912"
    assert r["razon_social"] == "Juan Perez"


def test_con_documento_pero_sin_nombre_no_manda_razon_social_vacia():
    """SUNAT rechaza el XML con la razón social en blanco."""
    assert _receptor("1", "45678912", None)["razon_social"] == "CLIENTE"


# ============ MANEJO DE FALLAS ============

def _config(url="http://sunat-service:8000", token="t"):
    return patch.multiple(
        "backend.utils.sunat_cloud.settings",
        sunat_service_url=url, sunat_service_token=token, sunat_service_timeout=5,
    )


def _emitir():
    return emitir_boleta(
        cliente_id="rest-001", ruc_emisor="20123456789",
        razon_social_emisor="Mi Resto SAC", direccion_emisor="Av. Lima 123",
        serie="B001", numero_correlativo=1, fecha_emision="2026-09-09",
        detalles=[{"plato_id": 1, "descripcion": "Ceviche", "cantidad": 1,
                   "precio_unitario": 118.00, "subtotal": 118.00}],
    )


def test_sin_configurar_la_url_avisa_en_vez_de_fallar_raro():
    with _config(url=""):
        with pytest.raises(SunatCloudError):
            _emitir()


def test_si_el_servicio_no_responde_la_boleta_queda_reintentable():
    """Un corte de red NO puede marcar la boleta como rechazada: el
    comprobante está bien y hay que poder reintentarlo con el mismo número."""
    with _config(), patch("httpx.post", side_effect=httpx.ConnectError("sin ruta")):
        with pytest.raises(SunatCloudError):
            _emitir()


def test_un_500_del_servicio_tambien_es_reintentable():
    resp = httpx.Response(500, json={"detail": "boom"}, request=httpx.Request("POST", "http://x"))
    with _config(), patch("httpx.post", return_value=resp):
        with pytest.raises(SunatCloudError):
            _emitir()


def test_falta_de_certificado_se_reporta_claro_y_no_como_error_de_red():
    """412 = configuración pendiente, no un fallo transitorio. Reintentarlo
    en bucle no lo arregla: hay que cargar el certificado."""
    resp = httpx.Response(
        412,
        json={"detail": {"error_codigo": "SIN_CERTIFICADO", "error_mensaje": "Falta el certificado"}},
        request=httpx.Request("POST", "http://x"),
    )
    with _config(), patch("httpx.post", return_value=resp):
        r = _emitir()
    assert r.exito is False
    assert r.error_codigo == "SIN_CERTIFICADO"
    assert r.reintentable is False


def test_un_rechazo_de_sunat_no_se_marca_reintentable():
    """Reintentar el mismo contenido daría el mismo rechazo."""
    resp = httpx.Response(
        200,
        json={"exito": False, "error_codigo": "RECHAZO_SUNAT",
              "error_mensaje": "El RUC no está activo"},
        request=httpx.Request("POST", "http://x"),
    )
    with _config(), patch("httpx.post", return_value=resp):
        r = _emitir()
    assert r.exito is False
    assert r.reintentable is False


def test_una_caida_de_sunat_si_se_marca_reintentable():
    resp = httpx.Response(
        200,
        json={"exito": False, "error_codigo": "TRANSPORTE",
              "error_mensaje": "No se pudo contactar a SUNAT"},
        request=httpx.Request("POST", "http://x"),
    )
    with _config(), patch("httpx.post", return_value=resp):
        r = _emitir()
    assert r.reintentable is True


def test_una_boleta_aceptada_devuelve_el_cdr():
    resp = httpx.Response(
        200,
        json={"exito": True, "estado": "accepted", "codigo": "0",
              "descripcion": "La Boleta numero B001-1, ha sido aceptada",
              "cdr_xml": "<ApplicationResponse/>"},
        request=httpx.Request("POST", "http://x"),
    )
    with _config(), patch("httpx.post", return_value=resp):
        r = _emitir()
    assert r.exito is True
    assert r.cdr_xml == "<ApplicationResponse/>"


def test_el_token_del_servicio_viaja_en_la_cabecera():
    """Sin esto el micro-servicio rechaza el pedido — y si alguien quita la
    cabecera 'para simplificar', la emisión deja de funcionar entera."""
    capturado = {}

    def fake_post(url, **kw):
        capturado.update(kw)
        return httpx.Response(200, json={"exito": True}, request=httpx.Request("POST", url))

    with _config(token="secreto-123"), patch("httpx.post", side_effect=fake_post):
        _emitir()

    assert capturado["headers"]["X-Sunat-Token"] == "secreto-123"


def test_nunca_se_mandan_las_credenciales_sol_desde_restomind():
    """
    Las credenciales SOL las lee el micro-servicio del mismo volumen que el
    certificado. RestoMind no las conoce, y no debe empezar a conocerlas:
    así no aparecen en su base de datos, sus backups ni sus logs.
    """
    capturado = {}

    def fake_post(url, **kw):
        capturado.update(kw)
        return httpx.Response(200, json={"exito": True}, request=httpx.Request("POST", url))

    with _config(), patch("httpx.post", side_effect=fake_post):
        _emitir()

    enviado = capturado["json"]
    assert "sol_usuario" not in enviado
    assert "sol_clave" not in enviado


# ============ DETECCIÓN DE DESVÍO POR REDONDEO ============

def test_detecta_cuando_la_boleta_declararia_distinto_de_lo_cobrado():
    """
    S/ 120.00 es el caso patológico: no existe ninguna base imponible que,
    con el redondeo a céntimos que aplica SUNAT por línea, dé exactamente
    120.00 — salta de 119.99 a 120.01.

    No es algo que se arregle con más decimales: RestoMind saca el IGV desde
    el total y SUNAT desde la base, y las dos cuentas no siempre pueden
    coincidir. Lo que este código garantiza es que el desvío quede
    DETECTADO y anotado en la Factura, en vez de emitirse en silencio.
    """
    detalles = [{"plato_id": 1, "descripcion": "Menu", "cantidad": 1,
                 "precio_unitario": 120.00, "subtotal": 120.00}]
    assert total_que_declarara_sunat(detalles) == Decimal("119.99")
    assert diferencia_contra_lo_cobrado(detalles, 120.00) == Decimal("-0.01")


def test_cuando_cuadra_el_desvio_es_cero():
    detalles = [{"plato_id": 1, "descripcion": "Ceviche", "cantidad": 2,
                 "precio_unitario": 45.00, "subtotal": 90.00}]
    assert diferencia_contra_lo_cobrado(detalles, 90.00) == Decimal("0")
