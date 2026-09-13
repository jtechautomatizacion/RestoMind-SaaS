"""
Consulta de RUC contra la copia local del Padrón Reducido de SUNAT.

Dos cosas se protegen acá, y ninguna es "que devuelva el nombre":

  1. QUE NO SE CONVIERTA EN UNA API PÚBLICA DE DATOS PERSONALES.
     Detrás hay ~19 millones de contribuyentes y los RUC 10/15/16/17 son
     personas naturales: su "razón social" es el nombre de alguien. Sin
     sesión y sin cuota, esto es un servicio de descarga masiva de datos
     personales montado sobre el servidor del restaurante.

  2. QUE NO SE RECHACEN RUC VÁLIDOS.
     La validación vieja aceptaba solo prefijos 10 y 20; en el padrón real
     el 7,4% empieza en 15 o 17. A esos clientes no se les podía facturar.
"""

import sqlite3

import pytest

from backend.config import settings
from backend.utils.padron import (
    cerrar_conexion_del_hilo,
    digito_verificador_ok,
    formato_valido,
)
from backend.utils.rate_limit import limpiar_limites_por_volumen

# RUC reales del padrón de SUNAT (dígito verificador válido, verificado).
RUC_PERSONA = "10452159428"
RUC_EMPRESA = "20123456786"
RUC_PREFIJO_17 = "17537127422"


@pytest.fixture(autouse=True)
def _limpiar_cuota():
    """TestClient siempre reporta la misma IP falsa, así que sin esto un
    test gastaría la cuota del siguiente y vería un 429 que no tiene nada
    que ver con lo que prueba."""
    limpiar_limites_por_volumen()
    yield
    limpiar_limites_por_volumen()
    cerrar_conexion_del_hilo()


@pytest.fixture
def padron(tmp_path, monkeypatch):
    """Un padrón chico con la misma forma que el real."""
    ruta = tmp_path / "padron.db"
    conn = sqlite3.connect(ruta)
    conn.execute("CREATE TABLE padron (ruc TEXT, nombre TEXT, estado TEXT, condicion TEXT)")
    conn.executemany("INSERT INTO padron VALUES (?,?,?,?)", [
        (RUC_PERSONA, "GARCIA CHANCO CARLOS AUGUSTO", "ACTIVO", "HABIDO"),
        (RUC_EMPRESA, "MI RESTO SAC", "ACTIVO", "HABIDO"),
        (RUC_PREFIJO_17, "SUCESION INDIVISA PEREZ", "BAJA DE OFICIO", "NO HABIDO"),
    ])
    conn.execute("CREATE UNIQUE INDEX idx_ruc ON padron(ruc)")
    conn.commit()
    conn.close()

    cerrar_conexion_del_hilo()
    monkeypatch.setattr(settings, "padron_db_path", str(ruta))
    yield ruta
    cerrar_conexion_del_hilo()


# ============ LO QUE MÁS IMPORTA: NO EXPONER DATOS PERSONALES ============

def test_sin_sesion_no_se_puede_consultar_ningun_ruc(test_client_real_auth, padron):
    """
    Si este test empieza a fallar, alguien volvió pública una consulta sobre
    19 millones de nombres de personas. No se arregla el test: se arregla el
    endpoint.
    """
    assert test_client_real_auth.get(f"/api/ruc/{RUC_EMPRESA}").status_code == 401


def test_hay_un_tope_de_consultas_para_frenar_la_extraccion_masiva(
    test_client, test_cliente, padron, monkeypatch
):
    """Un uso normal (unas pocas facturas por turno) nunca llega al tope;
    un script que quiera bajarse el padrón, sí, en segundos."""
    monkeypatch.setattr("backend.routes.ruc.MAX_CONSULTAS", 5)

    for _ in range(5):
        assert test_client.get(f"/api/ruc/{RUC_EMPRESA}").status_code == 200

    assert test_client.get(f"/api/ruc/{RUC_EMPRESA}").status_code == 429


def test_un_ruc_invalido_no_llega_a_consultar_la_base(test_client, test_cliente, padron):
    """Se rechaza por formato antes de tocar el disco: no gasta consulta ni
    cuota en un número que no puede existir."""
    assert test_client.get("/api/ruc/12345678901").status_code == 400
    assert test_client.get("/api/ruc/hola").status_code == 400
    # Dígito verificador equivocado (el resto del número es válido):
    assert test_client.get("/api/ruc/20123456789").status_code == 400


# ============ CONSULTA ============

def test_devuelve_la_razon_social_de_una_empresa(test_client, test_cliente, padron):
    r = test_client.get(f"/api/ruc/{RUC_EMPRESA}")
    assert r.status_code == 200
    d = r.json()
    assert d["encontrado"] is True
    assert d["nombre"] == "MI RESTO SAC"
    assert d["persona_natural"] is False
    assert d["puede_facturarse"] is True
    assert d["advertencia"] is None


def test_marca_como_persona_natural_a_los_prefijos_10_15_16_17(test_client, test_cliente, padron):
    """El frontend lo necesita para no rotular como 'razón social' lo que en
    realidad es el nombre y apellidos de una persona."""
    assert test_client.get(f"/api/ruc/{RUC_PERSONA}").json()["persona_natural"] is True
    assert test_client.get(f"/api/ruc/{RUC_PREFIJO_17}").json()["persona_natural"] is True


def test_avisa_antes_de_emitir_si_el_contribuyente_esta_de_baja(test_client, test_cliente, padron):
    """Avisar ANTES sirve; después de emitir, SUNAT ya observó el
    comprobante y corregirlo cuesta mucho más."""
    d = test_client.get(f"/api/ruc/{RUC_PREFIJO_17}").json()
    assert d["puede_facturarse"] is False
    assert "BAJA DE OFICIO" in d["advertencia"]


def test_un_ruc_que_no_esta_en_el_padron_no_es_un_error(test_client, test_cliente, padron):
    """200 con encontrado=False, no 404: puede ser un RUC recién creado o el
    archivo local estar viejo. El cajero igual emite escribiendo el nombre."""
    r = test_client.get("/api/ruc/20100070970")
    assert r.status_code == 200
    assert r.json()["encontrado"] is False


def test_sin_la_base_construida_avisa_que_falta_instalarla(test_client, test_cliente, monkeypatch):
    """503 y no 500: el sistema funciona, falta un paso de instalación. Y el
    resto de la app no se cae por eso."""
    cerrar_conexion_del_hilo()
    monkeypatch.setattr(settings, "padron_db_path", "/no/existe/padron.db")
    r = test_client.get(f"/api/ruc/{RUC_EMPRESA}")
    assert r.status_code == 503
    assert "cargar_padron_sunat" in r.json()["detail"]


def test_el_estado_del_padron_es_solo_para_el_admin(test_client, test_cliente, padron):
    r = test_client.get("/api/ruc-padron/estado")
    assert r.status_code == 200
    assert r.json()["contribuyentes"] == 3


# ============ VALIDACIÓN DE RUC ============

@pytest.mark.parametrize("ruc", [RUC_PERSONA, RUC_EMPRESA, RUC_PREFIJO_17])
def test_acepta_los_prefijos_que_sunat_usa_de_verdad(ruc):
    """15/16/17 son personas naturales con asignación antigua. Aceptar solo
    10 y 20 dejaba fuera al 7,4% de los contribuyentes del padrón real."""
    assert formato_valido(ruc)


def test_el_digito_verificador_atrapa_el_tipeo_del_mostrador():
    """Cambiar UN dígito de un RUC válido lo vuelve inválido: es lo que
    distingue esta validación de solo contar once números."""
    assert digito_verificador_ok(RUC_EMPRESA)
    # mismo número con el último dígito cambiado
    assert not digito_verificador_ok(RUC_EMPRESA[:10] + "9")
    # dos dígitos intercambiados en el medio, el error de tipeo más común
    assert not digito_verificador_ok("20123456876")


@pytest.mark.parametrize("malo", [
    "", "123", "2012345678", "201234567890",       # largo incorrecto
    "2012345678a", "abcdefghijk",                   # no numérico
    "30123456789", "00123456789",                   # prefijo que SUNAT no usa
])
def test_rechaza_lo_que_no_puede_ser_un_ruc(malo):
    assert not formato_valido(malo)


# ============ CONSULTA UNIFICADA: DNI y RUC en un solo campo ============
#
# El cajero tipea un número y no debería tener que saber qué es. Un DNI NO
# está en el Padrón Reducido (que solo tiene RUC), así que se resuelve
# contra el registro propio del restaurante.
#
# Ese registro es datos personales de sus comensales, y a diferencia del
# padrón NO viene de una fuente pública: el aislamiento por cliente_id es
# obligación legal, no una comodidad.

from unittest.mock import patch  # noqa: E402

from backend.models import ClienteFrecuente  # noqa: E402

DNI = "73081441"


def test_un_dni_de_OTRO_restaurante_no_se_filtra(test_client, test_db, test_cliente, padron):
    """
    Lo más importante de esta tabla.

    El mismo DNI puede estar en dos restaurantes: son dos registros
    independientes, cada uno del negocio que atendió a esa persona. Que uno
    vea el del otro sería una cesión de datos personales entre empresas
    distintas.
    """
    test_db.add(ClienteFrecuente(
        cliente_id="otro-restaurante", tipo_documento="1",
        numero_documento=DNI, nombre="JUAN PEREZ", origen="manual",
    ))
    test_db.commit()

    datos = test_client.get(f"/api/documento/{DNI}").json()

    assert datos["encontrado"] is False
    assert datos["nombre"] is None
    assert datos["requiere_nombre_manual"] is True


def test_un_dni_ya_conocido_sale_del_registro_local_sin_gastar_consultas(
    test_client, test_db, test_cliente, padron
):
    """Segunda visita del mismo comensal: gratis e instantánea, sin tocar el
    servicio externo (que cobra por consulta)."""
    test_db.add(ClienteFrecuente(
        cliente_id=test_cliente.id, tipo_documento="1",
        numero_documento=DNI, nombre="MARIA QUISPE", origen="manual",
    ))
    test_db.commit()

    with patch("backend.routes.ruc.consultar_dni_externo") as externo:
        datos = test_client.get(f"/api/documento/{DNI}").json()

    externo.assert_not_called()
    assert datos["encontrado"] is True
    assert datos["nombre"] == "MARIA QUISPE"
    assert datos["origen"] == "local"


def test_un_dni_nuevo_se_guarda_para_que_la_proxima_sea_gratis(
    test_client, test_db, test_cliente, padron
):
    with patch("backend.routes.ruc.consultar_dni_externo", return_value="CARLOS RAMOS"):
        datos = test_client.get(f"/api/documento/{DNI}").json()

    assert datos["encontrado"] is True
    assert datos["origen"] == "api"

    guardado = test_db.query(ClienteFrecuente).filter(
        ClienteFrecuente.cliente_id == test_cliente.id,
        ClienteFrecuente.numero_documento == DNI,
    ).one()
    assert guardado.nombre == "CARLOS RAMOS"

    # La segunda consulta ya no llama a nadie.
    with patch("backend.routes.ruc.consultar_dni_externo") as externo:
        assert test_client.get(f"/api/documento/{DNI}").json()["origen"] == "local"
    externo.assert_not_called()


def test_sin_servicio_externo_configurado_el_cobro_sigue(test_client, test_cliente, padron):
    """El servicio de DNI viene APAGADO por defecto y es de pago. Que no esté
    configurado no puede frenar una venta: el cajero escribe el nombre."""
    datos = test_client.get(f"/api/documento/{DNI}").json()

    assert datos["encontrado"] is False
    assert datos["requiere_nombre_manual"] is True


def test_el_nombre_escrito_a_mano_se_recuerda(test_client, test_db, test_cliente, padron):
    """El trabajo de tipearlo se hace UNA vez."""
    resp = test_client.post(f"/api/documento/{DNI}", json={"nombre": "  ana   torres  "})
    assert resp.status_code == 200
    # Normalizado: lo que va a un comprobante tiene que estar prolijo aunque
    # el cajero tipee de apuro.
    assert resp.json()["nombre"] == "ANA TORRES"

    assert test_client.get(f"/api/documento/{DNI}").json()["nombre"] == "ANA TORRES"


def test_un_ruc_va_al_padron_y_no_al_registro_de_comensales(test_client, test_cliente, padron):
    datos = test_client.get(f"/api/documento/{RUC_EMPRESA}").json()

    assert datos["tipo"] == "RUC"
    assert datos["encontrado"] is True
    assert datos["nombre"] == "MI RESTO SAC"


def test_un_ruc_fuera_del_padron_NO_es_un_error(test_client, test_cliente, padron):
    """
    200 con encontrado=False, no 400.

    Un RUC recién inscrito, o una copia local sin actualizar, son casos
    normales con solución inmediata: el cajero escribe la razón social. Un
    400 le mostraría un error rojo por algo que no hizo mal, justo mientras
    cobra.
    """
    resp = test_client.get("/api/documento/20100070970")

    assert resp.status_code == 200
    datos = resp.json()
    assert datos["encontrado"] is False
    assert datos["requiere_nombre_manual"] is True


def test_solo_se_recuerdan_DNI_no_RUC(test_client, test_cliente, padron):
    """Un RUC sale del padrón: no hay nada que recordar, y guardarlo sería
    duplicar un dato que ya se tiene."""
    resp = test_client.post(f"/api/documento/{RUC_EMPRESA}", json={"nombre": "X SAC"})
    assert resp.status_code == 400


@pytest.mark.parametrize("malo", ["123", "123456789", "abcdefgh"])
def test_un_documento_con_largo_raro_se_rechaza(test_client, test_cliente, padron, malo):
    assert test_client.get(f"/api/documento/{malo}").status_code == 400


def test_sin_sesion_no_se_puede_consultar_ningun_documento(test_client_real_auth, padron):
    """Mismo criterio que /api/ruc: detrás hay datos personales."""
    assert test_client_real_auth.get(f"/api/documento/{DNI}").status_code == 401
