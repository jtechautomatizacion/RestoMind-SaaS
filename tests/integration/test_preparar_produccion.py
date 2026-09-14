"""
El script que deja la base lista para producción.

Corre UNA vez, sobre datos reales, y borra. No hay segunda oportunidad para
descubrir que se llevó puesta la carta o que dejó los correlativos altos,
así que lo que hace y lo que NO hace se fija acá.
"""

import sqlite3

import pytest

from backend.config import settings
from backend.scripts import preparar_produccion as script


@pytest.fixture
def base(tmp_path, monkeypatch):
    """Una base con la misma forma que la real: catálogo cargado a mano +
    historia de pruebas encima."""
    ruta = tmp_path / "restomind.db"
    con = sqlite3.connect(ruta)
    con.executescript(
        """
        CREATE TABLE clientes (
            id TEXT PRIMARY KEY, nombre TEXT, ruc TEXT,
            boleta_correlativo_actual INTEGER, factura_correlativo_actual INTEGER
        );
        CREATE TABLE usuarios (id TEXT PRIMARY KEY, nombre TEXT, password_hash TEXT);
        CREATE TABLE superadmins (id TEXT PRIMARY KEY, email TEXT);
        CREATE TABLE categorias (id INTEGER PRIMARY KEY, nombre TEXT);
        CREATE TABLE platos (id INTEGER PRIMARY KEY, nombre TEXT, precio_venta REAL);
        CREATE TABLE mesas (id INTEGER PRIMARY KEY, numero INTEGER);
        CREATE TABLE insumos (id INTEGER PRIMARY KEY, nombre TEXT,
                              cantidad_actual REAL, cantidad_minima REAL);

        CREATE TABLE comandas (id INTEGER PRIMARY KEY);
        CREATE TABLE comanda_platos (id INTEGER PRIMARY KEY);
        CREATE TABLE facturas (id INTEGER PRIMARY KEY);
        CREATE TABLE factura_comandas (id INTEGER PRIMARY KEY);
        CREATE TABLE compras (id INTEGER PRIMARY KEY);
        CREATE TABLE cierres_caja (id INTEGER PRIMARY KEY);
        CREATE TABLE movimientos_insumo (id INTEGER PRIMARY KEY);
        CREATE TABLE audit_log (id INTEGER PRIMARY KEY);
        CREATE TABLE clientes_frecuentes (id INTEGER PRIMARY KEY);
        CREATE TABLE push_subscriptions (id INTEGER PRIMARY KEY);

        INSERT INTO clientes VALUES ('rest-1', 'Cevicheria', '10200812234', 30, 4);
        INSERT INTO usuarios VALUES ('u1', 'Susy', 'hash-bcrypt');
        INSERT INTO superadmins VALUES ('sa', 'dueno@sistema.com');
        INSERT INTO categorias VALUES (1, 'Cebiches');
        INSERT INTO platos VALUES (1, 'Ceviche Clasico', 45.0);
        INSERT INTO platos VALUES (2, 'Gaseosa', 3.5);
        INSERT INTO mesas VALUES (1, 1);
        INSERT INTO insumos VALUES (1, 'Arroz', 12.5, 2.0);
        """
    )
    for t in ("comandas", "comanda_platos", "facturas", "factura_comandas",
              "compras", "cierres_caja", "movimientos_insumo", "audit_log",
              "clientes_frecuentes", "push_subscriptions"):
        con.executemany(f"INSERT INTO {t} (id) VALUES (?)", [(i,) for i in range(1, 6)])
    con.commit()
    con.close()

    monkeypatch.setattr(settings, "database_url", f"sqlite:///{ruta}")
    return ruta


def _filas(ruta, tabla):
    con = sqlite3.connect(ruta)
    n = con.execute(f"SELECT COUNT(*) FROM {tabla}").fetchone()[0]
    con.close()
    return n


def test_el_catalogo_sobrevive_entero(base):
    """Lo que el dueño cargó a mano —carta, precios, mesas, cuentas— es
    justamente lo que NO se puede perder: volver a tipearlo es horas de
    trabajo y la razón por la que alguien correría este script con miedo."""
    script.ejecutar(base)

    assert _filas(base, "platos") == 2
    assert _filas(base, "categorias") == 1
    assert _filas(base, "mesas") == 1
    assert _filas(base, "usuarios") == 1
    assert _filas(base, "superadmins") == 1
    assert _filas(base, "clientes") == 1
    assert _filas(base, "insumos") == 1

    con = sqlite3.connect(base)
    assert con.execute("SELECT nombre, precio_venta FROM platos WHERE id=1").fetchone() \
        == ("Ceviche Clasico", 45.0)
    # La contraseña ya hasheada sigue sirviendo: nadie tiene que resetearla.
    assert con.execute("SELECT password_hash FROM usuarios").fetchone()[0] == "hash-bcrypt"
    assert con.execute("SELECT ruc FROM clientes").fetchone()[0] == "10200812234"
    con.close()


def test_la_historia_de_pruebas_se_borra_entera(base):
    script.ejecutar(base)
    for t in ("comandas", "comanda_platos", "facturas", "factura_comandas",
              "compras", "cierres_caja", "movimientos_insumo", "audit_log",
              "clientes_frecuentes", "push_subscriptions"):
        assert _filas(base, t) == 0, t


def test_los_correlativos_vuelven_a_cero(base):
    """
    EL test de este archivo.

    Si los correlativos quedaran altos, la primera boleta REAL saldría como
    B001-31 y la serie arrancaría con un hueco de 30 números que SUNAT
    exige que no exista — y que nadie puede explicar después, porque las
    facturas que los consumieron ya no están.
    """
    script.ejecutar(base)
    con = sqlite3.connect(base)
    b, f = con.execute(
        "SELECT boleta_correlativo_actual, factura_correlativo_actual FROM clientes"
    ).fetchone()
    con.close()
    assert (b, f) == (0, 0)


def test_el_stock_arranca_en_cero_pero_el_insumo_queda(base):
    """El nombre, la unidad y el mínimo de "Arroz" siguen siendo válidos
    mañana; los 12,5 kg que quedaron de una prueba, no. Arrancar con un
    stock inventado hace que la primera alerta de "queda poco" sea falsa, y
    una alerta falsa al principio es la forma más rápida de que nadie
    vuelva a mirarlas."""
    script.ejecutar(base)
    con = sqlite3.connect(base)
    nombre, actual, minimo = con.execute(
        "SELECT nombre, cantidad_actual, cantidad_minima FROM insumos"
    ).fetchone()
    con.close()
    assert nombre == "Arroz"
    assert actual == 0
    assert minimo == 2.0, "el mínimo es configuración, no historia: no se toca"


def test_deja_un_respaldo_antes_de_tocar_nada(base):
    """Un script que borra sin red es un script que nadie va a querer
    correr el día del despliegue."""
    script.ejecutar(base)
    respaldos = list(base.parent.glob("restomind.db.antes-de-produccion-*"))
    assert len(respaldos) == 1

    con = sqlite3.connect(respaldos[0])
    assert con.execute("SELECT COUNT(*) FROM comandas").fetchone()[0] == 5
    assert con.execute(
        "SELECT boleta_correlativo_actual FROM clientes"
    ).fetchone()[0] == 30
    con.close()


def test_es_idempotente(base):
    """Correrlo dos veces no puede romper nada: en un despliegue real es
    muy fácil dudar de si ya se ejecutó."""
    script.ejecutar(base)
    script.ejecutar(base)
    assert _filas(base, "platos") == 2
    assert _filas(base, "comandas") == 0


def test_una_tabla_que_no_existe_no_lo_tumba(base):
    """Una base de una versión anterior puede no tener todas las tablas
    (agente_tokens, por ejemplo, es de una arquitectura ya eliminada)."""
    con = sqlite3.connect(base)
    con.execute("DROP TABLE clientes_frecuentes")
    con.commit()
    con.close()

    script.ejecutar(base)  # no debe levantar
    assert _filas(base, "platos") == 2
