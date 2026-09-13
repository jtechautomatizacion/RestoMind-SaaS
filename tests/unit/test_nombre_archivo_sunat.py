"""
El nombre del archivo que se le manda a SUNAT debe coincidir EXACTAMENTE
con el `cbc:ID` del XML.

POR QUÉ EXISTE ESTE ARCHIVO
---------------------------
Un bug real rechazó todas las emisiones con el error 1036 de SUNAT:

    "Número de documento en el nombre del archivo no coincide con el
     consignado en el contenido del XML
     (nodo: Invoice/cbc:ID valor: B001-28)"

El nombre se armaba con el correlativo relleno a 8 dígitos
(`...-B001-00000028`) mientras la plantilla de sunat-py escribe
`<cbc:ID>{{ serie }}-{{ numero }}</cbc:ID>` —sin relleno—, así que nunca
podían coincidir. Parecía lo correcto: SUNAT sí usa 8 dígitos en OTROS
contextos, y el error no menciona el relleno por ningún lado.

`sunat-service` corre en su propio contenedor y no tiene sus dependencias
instaladas acá (es todo el punto del aislamiento: sunat-py exige
cryptography<45 y RestoMind usa la 50). Por eso el módulo se carga con
`sunat_py` sustituido por un doble: lo único que se prueba es cómo se arma
el nombre, que no necesita nada de la librería real.
"""

import sys
import types
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2]


def _cargar_servicio():
    """Importa sunat-service/app.py con `sunat_py` sustituido."""
    falso = types.ModuleType("sunat_py")
    for nombre in (
        "CertBundle", "InvoiceInput", "InvoiceLine", "Party", "SunatError",
        "ValidationError", "build_invoice_xml", "build_zeep_client",
        "compute_totals", "install_log_redactor", "load_cert_from_pfx",
        "pack_invoice", "send_bill", "sign_invoice_xml",
    ):
        setattr(falso, nombre, type(nombre, (), {}) if nombre[0].isupper() else (lambda *a, **k: None))
    sys.modules["sunat_py"] = falso

    import importlib.util
    ruta = RAIZ / "sunat-service" / "app.py"
    spec = importlib.util.spec_from_file_location("sunat_service_app", ruta)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


@pytest.fixture(scope="module")
def servicio():
    try:
        return _cargar_servicio()
    finally:
        sys.modules.pop("sunat_py", None)


class _Emisor:
    def __init__(self, ruc):
        self.numero_doc = ruc


class _Pedido:
    """Lo mínimo que `_nombre_archivo` lee del request.

    No se construye el EmitirRequest real a propósito: `app.py` usa
    `from __future__ import annotations`, así que cargarlo fuera de su
    contenedor deja los tipos de pydantic sin resolver. Y la función bajo
    prueba no necesita el modelo — solo cuatro atributos.
    """

    def __init__(self, serie="B001", numero=28, ruc="10410827803", tipo="03"):
        self.serie = serie
        self.numero = numero
        self.tipo_documento = tipo
        self.emisor = _Emisor(ruc)


def _pedido(servicio, serie="B001", numero=28, ruc="10410827803", tipo="03"):
    return _Pedido(serie=serie, numero=numero, ruc=ruc, tipo=tipo)


# Lo que la plantilla de sunat-py escribe en <cbc:ID>. Si algún día cambia,
# este test falla y el nombre del archivo tiene que seguirla — no al revés.
def _cbc_id(serie, numero):
    return f"{serie}-{numero}"


def test_el_nombre_del_archivo_termina_igual_que_el_cbc_id(servicio):
    """
    EL test de este archivo. Es la regla que SUNAT verifica con el error
    1036, y la que estuvo rota.
    """
    req = _pedido(servicio)
    nombre = servicio._nombre_archivo(req)

    assert nombre.endswith(_cbc_id("B001", 28))
    assert nombre == "10410827803-03-B001-28"


def test_el_correlativo_NO_va_relleno_con_ceros(servicio):
    """Fija explícitamente el bug: `...-B001-00000028` contra un XML que
    dice `B001-28` es exactamente lo que SUNAT rechaza."""
    nombre = servicio._nombre_archivo(_pedido(servicio, numero=28))

    assert "00000028" not in nombre
    assert nombre.endswith("-28")


@pytest.mark.parametrize("serie, numero, tipo", [
    ("B001", 1, "03"),
    ("B001", 9999, "03"),
    ("F001", 1, "01"),
    ("F001", 12345678, "01"),
])
def test_la_regla_se_cumple_para_cualquier_serie_y_numero(servicio, serie, numero, tipo):
    req = _pedido(servicio, serie=serie, numero=numero, tipo=tipo)
    assert servicio._nombre_archivo(req).endswith(_cbc_id(serie, numero))


def test_el_RUC_del_nombre_es_el_del_EMISOR_no_otro(servicio):
    """
    El RUC del nombre sale del emisor del comprobante, que es el
    restaurante. Si acá se colara otro (el genérico de pruebas, por ejemplo)
    SUNAT rechazaría por identidad cruzada — un error distinto del 1036,
    pero igual de bloqueante.
    """
    nombre = servicio._nombre_archivo(_pedido(servicio, ruc="10410827803"))
    assert nombre.startswith("10410827803-")
    assert "20000000001" not in nombre
