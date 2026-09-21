"""
Los parámetros `desde`/`hasta` del dashboard, y el signo del arqueo.

POR QUÉ IMPORTA
---------------
Los dos endpoints del dashboard (`/resumen` y `/reporte-excel`) reciben un
rango de fechas que hasta ahora NADIE validaba. Medido contra el servidor real
antes del arreglo:

    ?desde=basura&hasta=2026-01-01          -> HTTP 500
    ?desde=2030-01-01&hasta=2020-01-01      -> HTTP 200, totales en cero
    ?desde=1900-01-01&hasta=2100-01-01      -> 73.050 días, 5,6 MB de JSON
                                               y 13,7 s para el Excel

El último es el peligroso, y no por el tamaño: esta app corre con UN solo
worker de uvicorn, así que esos 13,7 segundos son 13,7 segundos en los que
NADIE del restaurante puede tomar un pedido ni cobrar. No hace falta mala
intención — alcanza con un dedo torpe en el selector de fechas.

El del medio es el más traicionero de los tres: no falla. Devuelve 200 con
todo en cero, y el dueño lo lee como "no vendí nada en ese período" cuando en
realidad pidió mal el período. No tiene forma de notar la diferencia.
"""

import pytest


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


RUTAS = ["/api/dashboard/resumen", "/api/dashboard/reporte-excel"]


# ---------------------------------------------------------------------------
# Fechas mal escritas
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("ruta", RUTAS)
@pytest.mark.parametrize("desde", ["basura", "2026-13-45", "21/09/2026", "", "2026-09-99"])
def test_una_fecha_invalida_da_400_y_no_revienta(test_client, test_platos, test_mesas, ruta, desde):
    """400, nunca 500.

    Un 500 se ve como "el sistema se rompió" y se reporta como tal; un 400 con
    el formato esperado dice qué corregir. La diferencia la paga soporte.
    """
    r = test_client.get(f"{ruta}?desde={desde}&hasta=2026-09-21")

    assert r.status_code != 500, f"{ruta} con desde={desde!r} devolvió 500"
    # Una cadena vacía cae al camino de `dias` (no hay rango a medida), que es
    # correcto: el parámetro se considera ausente.
    assert r.status_code in (200, 400)
    if r.status_code == 400:
        assert "AAAA-MM-DD" in r.json()["detail"]


@pytest.mark.parametrize("ruta", RUTAS)
def test_la_fecha_de_fin_tambien_se_valida(test_client, test_platos, test_mesas, ruta):
    r = test_client.get(f"{ruta}?desde=2026-09-01&hasta=no-es-fecha")
    assert r.status_code == 400
    assert "AAAA-MM-DD" in r.json()["detail"]


# ---------------------------------------------------------------------------
# Rango al revés
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("ruta", RUTAS)
def test_un_rango_al_reves_se_rechaza_en_vez_de_mentir(test_client, test_platos, test_mesas, ruta):
    """EL MÁS TRAICIONERO: antes devolvía 200 con todo en cero.

    "No vendiste nada" y "pediste mal las fechas" son respuestas muy distintas,
    y el dueño no tenía forma de distinguirlas.
    """
    r = test_client.get(f"{ruta}?desde=2026-09-30&hasta=2026-09-01")

    assert r.status_code == 400
    assert "posterior" in r.json()["detail"]


@pytest.mark.parametrize("ruta", RUTAS)
def test_un_solo_dia_sigue_siendo_valido(test_client, test_platos, test_mesas, ruta):
    """desde == hasta es un rango legítimo: "cuánto vendí HOY"."""
    r = test_client.get(f"{ruta}?desde=2026-09-21&hasta=2026-09-21")
    assert r.status_code == 200


# ---------------------------------------------------------------------------
# Rango gigante
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("ruta", RUTAS)
def test_un_rango_de_siglos_se_rechaza(test_client, test_platos, test_mesas, ruta):
    r = test_client.get(f"{ruta}?desde=1900-01-01&hasta=2100-01-01")

    assert r.status_code == 400
    assert "366" in r.json()["detail"]


@pytest.mark.parametrize("ruta", RUTAS)
def test_un_anio_entero_sigue_entrando(test_client, test_platos, test_mesas, ruta):
    """El caso real que hay que NO romper: "todo el año pasado, para el contador".

    Si el tope dejara afuera un año completo, el arreglo sería peor que el
    problema.
    """
    r = test_client.get(f"{ruta}?desde=2026-01-01&hasta=2026-12-31")
    assert r.status_code == 200, r.text


def test_el_limite_esta_justo_donde_dice(test_client, test_platos, test_mesas):
    """366 días pasa, 367 no. Un test de borde para que el tope no se corra
    sin querer al refactorizar."""
    # 2026-01-01 + 365 días = 2026-12-31 -> 365 días contando ambos extremos
    assert test_client.get("/api/dashboard/resumen?desde=2026-01-01&hasta=2026-12-31").status_code == 200
    # 2024 fue bisiesto: 366 días exactos
    assert test_client.get("/api/dashboard/resumen?desde=2024-01-01&hasta=2024-12-31").status_code == 200
    # Un día más que el tope
    assert test_client.get("/api/dashboard/resumen?desde=2024-01-01&hasta=2025-01-01").status_code == 400


def test_sin_rango_a_medida_nada_cambia(test_client, test_platos, test_mesas):
    """El camino de siempre (?dias=N) no se toca."""
    r = test_client.get("/api/dashboard/resumen?dias=7")
    assert r.status_code == 200
    assert r.json()["periodo_dias"] == 7


# ---------------------------------------------------------------------------
# Signo del arqueo con saldo esperado negativo
# ---------------------------------------------------------------------------


def test_si_sobra_plata_el_porcentaje_es_positivo_aunque_lo_esperado_sea_negativo(
    test_client, test_platos, test_mesas
):
    """Un saldo esperado NEGATIVO es alcanzable con datos perfectamente
    válidos: se abre la caja en 0, se paga un gasto del turno y todavía no se
    vendió nada. El sistema entonces "espera" -100, o sea que se sacaron 100
    soles que no había.

    Contar la caja vacía (0) es MÁS que -100, así que sobran 100. Dividir por
    el esperado negativo invertía el signo y el reporte impreso terminaba
    diciendo "sobra" arriba y "-100%" abajo: dos afirmaciones opuestas sobre
    el mismo hecho, en el papel que se firma.

    Nota: `saldo_contado` está limitado a `ge=0` (nadie cuenta billetes
    negativos), así que con un esperado negativo la diferencia SIEMPRE sale
    positiva. Por eso no hay un test espejo de "falta": ese caso no existe.
    """
    test_client.post("/api/caja/abrir", json={"saldo_inicial": 0.0})
    # Un gasto sin ventas deja el esperado en negativo.
    test_client.post("/api/compras", json={
        "descripcion": "Pescado", "categoria": "Insumos", "monto": 100.0, "fecha": "2026-09-21",
    })

    cierre = test_client.post("/api/caja/cerrar", json={"saldo_contado": 0.0})
    assert cierre.status_code == 200, cierre.text
    cierre = cierre.json()

    assert cierre["saldo_esperado"] < 0, "el escenario requiere un esperado negativo"
    assert cierre["diferencia"] > 0, "la caja vacía tiene más que un esperado negativo: sobra"
    assert cierre["variacion_pct"] > 0, (
        f"sobra {cierre['diferencia']} pero el porcentaje dice {cierre['variacion_pct']}% "
        "— el signo está invertido"
    )


def test_con_esperado_positivo_y_faltante_el_porcentaje_es_negativo(
    test_client, test_platos, test_mesas
):
    """Blindar el signo no puede haberlo invertido para el caso normal."""
    test_client.post("/api/caja/abrir", json={"saldo_inicial": 100.0})

    cierre = test_client.post("/api/caja/cerrar", json={"saldo_contado": 60.0}).json()

    assert cierre["saldo_esperado"] == 100.0
    assert cierre["diferencia"] == -40.0, "faltan 40"
    assert cierre["variacion_pct"] == -40.0


def test_con_esperado_positivo_el_signo_sigue_como_siempre(test_client, test_platos, test_mesas):
    """El caso normal no cambia."""
    test_client.post("/api/caja/abrir", json={"saldo_inicial": 100.0})

    cierre = test_client.post("/api/caja/cerrar", json={"saldo_contado": 150.0}).json()

    assert cierre["saldo_esperado"] == 100.0
    assert cierre["diferencia"] == 50.0
    assert cierre["variacion_pct"] == 50.0
