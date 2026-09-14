"""
Prepara una base LIMPIA para producción, conservando solo el catálogo.

QUÉ CONSERVA (lo que costó cargar a mano y sigue siendo verdad mañana):

    clientes      la ficha del restaurante: RUC, razón social, dirección,
                  el interruptor usar_sunat, emite_facturas
    usuarios      admin y personal, con sus contraseñas ya hasheadas
    categorias    la organización de la carta
    platos        la carta: nombres, precios, categorías, fotos
    mesas         el salón
    insumos       el catálogo de inventario (nombres, unidades, mínimos)
    superadmins   la cuenta del dueño del sistema

QUÉ BORRA (historia de las pruebas, que en producción sería una mentira):

    comandas / comanda_platos     pedidos de prueba
    compras                       gastos de prueba
    facturas / factura_comandas   comprobantes de prueba
    cierres_caja                  turnos de prueba
    movimientos_insumo            entradas y salidas de prueba
    audit_log                     quién hizo qué DURANTE LAS PRUEBAS
    clientes_frecuentes           DNI y nombres tipeados probando
    push_subscriptions            tokens de dispositivos que no son los reales
    agente_tokens                 del agente eliminado en la v4.0

DOS COSAS QUE NO SON OBVIAS Y SÍ IMPORTAN
-----------------------------------------

1. **Los correlativos vuelven a CERO.** Si no, la primera boleta real de
   producción saldría con el número que dejaron las pruebas (B001-30 en vez
   de B001-1) y la serie arrancaría con un hueco de 29 números que SUNAT
   no tiene cómo explicarse. Se resetean `boleta_correlativo_actual` y
   `factura_correlativo_actual` junto con las facturas que los consumieron:
   son el mismo hecho contado dos veces, y separarlos deja la base
   mintiendo.

2. **`insumos` conserva el catálogo pero pone el stock en 0.** El nombre,
   la unidad y el mínimo de "Arroz" siguen siendo válidos mañana; los 12 kg
   que quedaron de una prueba, no. Arrancar con un stock inventado hace que
   la primera alerta de "queda poco" sea falsa, y una alerta falsa al
   principio es la forma más rápida de que nadie vuelva a mirarlas.

USO
---
    python -m backend.scripts.preparar_produccion --revisar   # solo muestra
    python -m backend.scripts.preparar_produccion --ejecutar

Siempre hace una copia de seguridad antes de tocar nada.
"""

import argparse
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

from backend.config import settings

# Se borran hijos antes que padres para no dejar filas colgando si alguien
# corre esto contra una base con las claves foráneas activadas.
TABLAS_A_VACIAR = (
    "comanda_platos",
    "factura_comandas",
    "comandas",
    "facturas",
    "compras",
    "cierres_caja",
    "movimientos_insumo",
    "audit_log",
    "clientes_frecuentes",
    "push_subscriptions",
    "agente_tokens",
)

TABLAS_A_CONSERVAR = (
    "clientes", "usuarios", "superadmins",
    "categorias", "platos", "mesas", "insumos",
)


def _ruta_db() -> Path:
    url = settings.database_url
    if not url.startswith("sqlite:///"):
        raise SystemExit(f"Este script es solo para SQLite. DATABASE_URL={url}")
    return Path(url.replace("sqlite:///", "", 1)).resolve()


def _existe(cur, tabla: str) -> bool:
    return cur.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (tabla,)
    ).fetchone() is not None


def _contar(cur, tabla: str) -> int:
    if not _existe(cur, tabla):
        return -1
    return cur.execute(f'SELECT COUNT(*) FROM "{tabla}"').fetchone()[0]


def revisar(db: Path) -> None:
    con = sqlite3.connect(db)
    cur = con.cursor()
    print(f"\nBase: {db}\n")
    print("SE CONSERVA")
    for t in TABLAS_A_CONSERVAR:
        n = _contar(cur, t)
        print(f"  {t:22} {n if n >= 0 else '(no existe)'}")
    print("\nSE BORRA")
    total = 0
    for t in TABLAS_A_VACIAR:
        n = _contar(cur, t)
        if n > 0:
            total += n
        print(f"  {t:22} {n if n >= 0 else '(no existe)'}")
    print(f"\n  total de filas a borrar: {total}")

    fila = cur.execute(
        "SELECT id, nombre, boleta_correlativo_actual, factura_correlativo_actual "
        "FROM clientes"
    ).fetchall()
    print("\nCORRELATIVOS (vuelven a 0)")
    for cid, nombre, b, f in fila:
        print(f"  {cid:16} {nombre:28} B001={b}  F001={f}")
    con.close()


def ejecutar(db: Path) -> None:
    marca = datetime.now().strftime("%Y%m%d%H%M%S")
    respaldo = db.with_name(f"{db.name}.antes-de-produccion-{marca}")
    shutil.copy2(db, respaldo)
    print(f"[OK] Respaldo: {respaldo.name}")

    con = sqlite3.connect(db)
    cur = con.cursor()
    try:
        cur.execute("BEGIN")
        borradas = 0
        for t in TABLAS_A_VACIAR:
            if not _existe(cur, t):
                continue
            n = _contar(cur, t)
            cur.execute(f'DELETE FROM "{t}"')
            if n:
                print(f"  {t:22} -{n}")
            borradas += n

        # Los correlativos son parte del mismo hecho que las facturas que se
        # acaban de borrar: dejarlos altos haría que la serie real arranque
        # con un hueco que SUNAT exige que no exista.
        cur.execute(
            "UPDATE clientes SET boleta_correlativo_actual = 0, "
            "factura_correlativo_actual = 0"
        )
        print("  correlativos           -> 0")

        # El catálogo de insumos vale; el stock de las pruebas, no.
        if _existe(cur, "insumos"):
            cur.execute("UPDATE insumos SET cantidad_actual = 0")
            print("  stock de insumos       -> 0")

        con.commit()
    except Exception:
        con.rollback()
        print("\n[!] Falló: no se cambió nada. El respaldo sigue en su lugar.")
        raise
    finally:
        con.close()

    # VACUUM fuera de la transacción: reescribe el archivo y le devuelve al
    # disco el espacio de las filas borradas. Sin esto la base queda del
    # mismo tamaño, llena de páginas vacías.
    con = sqlite3.connect(db)
    con.execute("VACUUM")
    con.close()

    print(f"\n[OK] Base lista para producción ({borradas} filas borradas).")
    print("     Revisá con --revisar antes de desplegar.")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--revisar", action="store_true", help="muestra qué haría, sin tocar nada")
    g.add_argument("--ejecutar", action="store_true", help="borra de verdad (hace respaldo antes)")
    args = p.parse_args()

    db = _ruta_db()
    if not db.exists():
        raise SystemExit(f"No existe la base: {db}")

    if args.revisar:
        revisar(db)
        return

    revisar(db)
    print("\nEsto BORRA ventas, gastos, comprobantes y auditoría de esta base.")
    if input("Escribí 'PRODUCCION' para confirmar: ").strip() != "PRODUCCION":
        print("Cancelado. No se tocó nada.")
        sys.exit(1)
    ejecutar(db)


if __name__ == "__main__":
    main()
