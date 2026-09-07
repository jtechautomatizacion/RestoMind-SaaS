"""
Los dos bloqueadores de seguridad del Validador de Caja que la auditoría
pre-producción dejó abiertos (ver claude.md).

Cada test de acá reproduce el ataque/escenario concreto, no solo "el
endpoint responde 200". Sin el fix correspondiente, fallan.
"""

import datetime as _dt
from datetime import datetime, timedelta
from unittest.mock import patch

import pytest

from backend.models import CierreCaja
from tests.conftest import TEST_CLIENTE_ID, TEST_USUARIO_EMAIL

# Mediodía UTC: con el reloj congelado acá, la ventana del restaurante
# (UTC-5 -> 07:00, mismo día) y la que fabricaría un atacante con el offset
# opuesto (UTC+14 -> 02:00 del día SIGUIENTE) caen en fechas distintas
# SIEMPRE. Sin congelar el reloj el test es una moneda al aire: el desfase
# entre ambas zonas es de 19h, así que solo cruza la medianoche según la
# hora a la que se corra la suite — y un test de seguridad que a veces no
# detecta el agujero es peor que no tenerlo.
_AHORA_FIJO = _dt.datetime(2026, 9, 1, 12, 0, 0)


class _RelojCongelado(_dt.datetime):
    @classmethod
    def utcnow(cls):
        return _AHORA_FIJO


def _abrir_caja(client, saldo=100.0, tz_offset=300):
    return client.post(
        '/api/caja/abrir',
        json={"saldo_inicial": saldo},
        headers={"X-TZ-Offset": str(tz_offset)},
    )


# ---------- Bloqueador 2: X-TZ-Offset manipulable ----------

def test_un_mozo_no_puede_forzar_el_cierre_de_la_caja_del_admin(test_client, test_cliente, test_db):
    """EL ataque del bloqueador #2.

    /caja/gate no exige admin (mozo y cocina necesitan saber si pueden
    operar) y dispara el auto-cierre de turnos vencidos. Cuando ese
    auto-cierre calculaba "qué día es hoy" con el header X-TZ-Offset de
    QUIEN CONSULTA, un mozo mandando un offset extremo adelantaba el día y
    el turno que el admin tenía abierto se cerraba solo, con
    saldo_contado = saldo_esperado: el admin perdía su conteo real y en la
    auditoría quedaba como actor "sistema", sin nadie a quien imputarlo.
    """
    with patch('backend.routes.caja.datetime', _RelojCongelado):
        # El admin abre su turno desde Lima (UTC-5).
        assert _abrir_caja(test_client, saldo=250.0, tz_offset=300).status_code == 201

        # El mozo consulta el semáforo con un offset falso de la otra punta
        # del mundo (UTC+14) para hacer creer que ya es "mañana".
        resp = test_client.get('/api/caja/gate', headers={"X-TZ-Offset": "-840"})
        assert resp.status_code == 200

    caja = db_caja(test_db)
    assert caja.estado == "abierto", "un offset falso cerró la caja del admin"
    assert caja.saldo_contado is None, "se le inventó un conteo físico al admin"
    # Y el gate sigue diciendo la verdad: hay turno abierto, se puede operar.
    assert resp.json()["hay_caja_abierta"] is True


def test_el_auto_cierre_sigue_funcionando_con_un_turno_de_ayer(test_client, test_cliente, test_db):
    """Contracara: blindar el auto-cierre contra el header NO puede haberlo
    roto. Un turno que de verdad quedó de ayer se sigue cerrando solo — si
    no, Mesas y Cocina quedarían bloqueadas todo el día siguiente.

    Reloj congelado por el mismo motivo que el resto del archivo: "ayer" en
    UTC crudo y "hoy" en hora de Lima (UTC-5) NO son siempre el mismo
    desfase de un día — en la ventana 00:00-05:00 UTC caen en la MISMA
    fecha de calendario, y el turno "envejecido" por el test terminaba sin
    verse vencido de verdad. Sin el reloj fijo, este test pasaba o fallaba
    según la hora a la que se corriera la suite."""
    with patch('backend.routes.caja.datetime', _RelojCongelado):
        _abrir_caja(test_client, saldo=100.0, tz_offset=300)

        # Se envejece el turno: se lo manda a ayer, como si el admin se
        # hubiera olvidado de cerrar anoche.
        caja = db_caja(test_db)
        ayer = _AHORA_FIJO - timedelta(days=1)
        caja.fecha = ayer.date().isoformat()
        caja.abierto_en = ayer
        test_db.commit()

        test_client.get('/api/caja/gate', headers={"X-TZ-Offset": "300"})

    caja = db_caja(test_db)
    assert caja.estado == "cerrado_automatico"
    # Nunca 'cuadrado': ese cierre no lo validó un conteo real.
    assert caja.estado != "cuadrado"
    assert caja.cerrado_por == "sistema (cierre automático)"


def test_el_auto_cierre_usa_la_zona_horaria_del_turno_no_la_del_visitante(test_client, test_cliente, test_db):
    """El turno guarda la zona horaria del dispositivo del admin al abrirse.
    Ese es el dato que manda, venga quien venga a consultar después."""
    _abrir_caja(test_client, saldo=100.0, tz_offset=300)

    caja = db_caja(test_db)
    assert caja.tz_offset == 300, "la zona horaria del admin no quedó guardada en el turno"


# ---------- Bloqueador 3: dos turnos abiertos a la vez ----------

def test_no_se_pueden_abrir_dos_turnos_a_la_vez(test_client, test_cliente, test_db):
    """El camino normal: el segundo intento recibe un error legible."""
    assert _abrir_caja(test_client).status_code == 201

    segundo = _abrir_caja(test_client)
    assert segundo.status_code == 400
    assert "abierto" in segundo.json()["detail"].lower()

    abiertos = test_db.query(CierreCaja).filter(
        CierreCaja.cliente_id == TEST_CLIENTE_ID, CierreCaja.estado == "abierto",
    ).count()
    assert abiertos == 1


def test_la_bd_impide_dos_turnos_abiertos_aunque_se_salte_la_validacion(test_client, test_cliente, test_db):
    """EL escenario del bloqueador #3.

    POST /caja/abrir hacía check-then-insert sin lock: con dos requests
    simultáneos (doble clic del admin, o dos pestañas) los dos pasaban el
    chequeo y se insertaban dos turnos abiertos. Con dos, .first() elige
    uno cualquiera y las MISMAS ventas se cuentan en ambos turnos: la caja
    no vuelve a cuadrar nunca.

    Insertar directo en la BD simula esa carrera sin depender de hilos (que
    en SQLite en memoria darían falsos negativos). El índice único parcial
    es lo único que puede impedirlo de verdad.
    """
    from sqlalchemy.exc import IntegrityError

    assert _abrir_caja(test_client).status_code == 201

    test_db.add(CierreCaja(
        cliente_id=TEST_CLIENTE_ID,
        fecha=datetime.utcnow().date().isoformat(),
        saldo_inicial=50.0,
        abierto_en=datetime.utcnow(),
        abierto_por=TEST_USUARIO_EMAIL,
        tz_offset=300,
        estado="abierto",
    ))
    with pytest.raises(IntegrityError):
        test_db.commit()
    test_db.rollback()


def test_varios_turnos_cerrados_el_mismo_dia_siguen_permitidos(test_client, test_cliente, test_db):
    """El índice es PARCIAL (solo sobre estado='abierto') justamente para no
    romper los turnos múltiples por día — mañana y tarde comparten fecha.

    Reloj congelado: `caja.fecha` la calcula el backend en hora LOCAL
    (utcnow - tz_offset), no en UTC crudo. Comparar contra
    datetime.utcnow().date() sin ajustar por el offset fallaba en la
    ventana 00:00-05:00 UTC, donde el día UTC ya avanzó pero el de Lima
    (UTC-5) todavía no — el mismo desfase que ya rompía el test vecino."""
    with patch('backend.routes.caja.datetime', _RelojCongelado):
        assert _abrir_caja(test_client, saldo=100.0).status_code == 201
        cerrar = test_client.post('/api/caja/cerrar', json={"saldo_contado": 100.0})
        assert cerrar.status_code == 200

        assert _abrir_caja(test_client, saldo=80.0).status_code == 201, "no se pudo abrir el segundo turno del día"

    hoy = _AHORA_FIJO.date().isoformat()
    del_dia = test_db.query(CierreCaja).filter(
        CierreCaja.cliente_id == TEST_CLIENTE_ID, CierreCaja.fecha == hoy,
    ).count()
    assert del_dia == 2


# ---------- Serialización de fechas ----------

def test_los_timestamps_salen_marcados_como_utc(test_client, test_cliente):
    """La app guarda los instantes con datetime.utcnow() (naive, pero UTC).
    Si la API los emite sin la marca 'Z', el navegador los lee como hora
    LOCAL —así lo manda el estándar— y en Lima mostraba las 06:36 UTC como
    si fueran las 06:36 de la mañana: cinco horas de más en cada fecha
    visible. El dato viajaba bien; lo ambiguo era cómo leerlo, y por eso no
    lo veía ningún test de backend."""
    _abrir_caja(test_client)
    cerrar = test_client.post('/api/caja/cerrar', json={"saldo_contado": 100.0})
    assert cerrar.status_code == 200

    cuerpo = cerrar.json()
    assert cuerpo["abierto_en"].endswith("Z"), "el navegador leería este instante como hora local"
    assert cuerpo["cerrado_en"].endswith("Z"), "el navegador leería este instante como hora local"


def test_la_fecha_de_negocio_de_un_movimiento_no_lleva_marca_utc(test_client, test_cliente):
    """La contracara: MovimientoInsumo.fecha es el DÍA al que corresponde el
    movimiento (el admin puede fechar hoy una merma de ayer), guardado a
    medianoche. Marcarlo como UTC lo correría un día hacia atrás en Lima —
    el 01/09 a las 00:00 pasaría a mostrarse como 31/08."""
    insumo = test_client.post('/api/insumos', json={
        "nombre": "Pescado", "unidad": "kg", "cantidad_actual": 10, "cantidad_minima": 2,
    }).json()
    mov = test_client.post(f'/api/insumos/{insumo["id"]}/movimientos', json={
        "tipo": "salida", "cantidad": 1, "razon": "merma", "fecha": "2026-09-01",
    })
    assert mov.status_code == 201

    cuerpo = mov.json()
    assert cuerpo["fecha"].startswith("2026-09-01"), "se corrió el día de la merma"
    assert not cuerpo["fecha"].endswith("Z"), "una fecha de calendario no es un instante UTC"
    # El instante en que se tipeó SÍ es UTC.
    assert cuerpo["creado_en"].endswith("Z")


# ---------- Turnos con nombre ----------

def test_el_nombre_del_turno_es_opcional(test_client, test_cliente):
    """Sin nombre, el turno se abre igual — la etiqueta es una comodidad,
    no un requisito (turnos viejos y quien no la usa no deben romperse)."""
    resp = _abrir_caja(test_client, saldo=100.0)
    assert resp.status_code == 201
    assert resp.json()["nombre_turno"] is None


def test_el_nombre_del_turno_viaja_hasta_el_historial(test_client, test_cliente):
    abierto = test_client.post('/api/caja/abrir', json={
        "saldo_inicial": 100.0, "nombre_turno": "Mañana",
    })
    assert abierto.status_code == 201
    assert abierto.json()["nombre_turno"] == "Mañana"

    cerrado = test_client.post('/api/caja/cerrar', json={"saldo_contado": 100.0})
    assert cerrado.json()["nombre_turno"] == "Mañana"

    historial = test_client.get('/api/caja/historial').json()
    assert historial[0]["nombre_turno"] == "Mañana"


def test_un_nombre_de_turno_de_solo_espacios_se_guarda_como_ninguno(test_client, test_cliente):
    resp = test_client.post('/api/caja/abrir', json={
        "saldo_inicial": 100.0, "nombre_turno": "   ",
    })
    assert resp.status_code == 201
    assert resp.json()["nombre_turno"] is None


def db_caja(test_db) -> CierreCaja:
    """El turno más reciente de este restaurante, releído de la BD."""
    test_db.expire_all()
    return (
        test_db.query(CierreCaja)
        .filter(CierreCaja.cliente_id == TEST_CLIENTE_ID)
        .order_by(CierreCaja.id.desc())
        .first()
    )
