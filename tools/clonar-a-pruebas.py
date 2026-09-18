"""
Copia tus datos reales a la base de PRUEBAS.

    .venv/Scripts/python.exe tools/clonar-a-pruebas.py

POR QUÉ EXISTE
--------------
Sin esto, la base de pruebas arranca con el restaurante de demostración ("La
Marisquería del Chef"): tus usuarios no existen, tus platos no existen, tus
mesas no existen. Probar ahí obliga a crear todo de nuevo a mano — y esa
fricción es la razón por la que uno termina probando en producción, que es
justo lo que no hay que hacer.

Con los datos copiados, la app de pruebas es la tuya: entrás con tu mismo
usuario, ves tu misma carta, tus mismas mesas. La única diferencia es que lo
que hagas ahí no le pasa a nadie.

VA EN UN SOLO SENTIDO, SIEMPRE
------------------------------
De `restomind.db` (tus datos) HACIA `restomind-testing.db` (pruebas), nunca al
revés. Un script que pudiera copiar en las dos direcciones es un script que
algún día, con un argumento mal puesto, le va a escribir encima a los datos
reales del restaurante. Acá el destino está fijo en el código.

Se usa la copia de seguridad de SQLite en vez de copiar el archivo: si el
servidor está corriendo, copiar el .db a mano puede llevarse una base a medio
escribir. La API de backup toma el bloqueo correcto y espera.
"""

import sqlite3
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
ORIGEN = RAIZ / "restomind.db"          # tus datos
DESTINO = RAIZ / "restomind-testing.db"  # pruebas — SIEMPRE este, nunca otro


def resumen(ruta: Path) -> str:
    if not ruta.exists():
        return "no existe"
    con = sqlite3.connect(f"file:{ruta}?mode=ro", uri=True)
    try:
        fila = con.execute("SELECT nombre FROM clientes LIMIT 1").fetchone()
        n = {t: con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
             for t in ("usuarios", "platos", "mesas", "comandas")}
        return (f"{fila[0] if fila else '(sin restaurante)'} — "
                f"{n['usuarios']} usuarios, {n['platos']} platos, "
                f"{n['mesas']} mesas, {n['comandas']} comandas")
    except sqlite3.Error as e:
        return f"ilegible ({e})"
    finally:
        con.close()


def main() -> None:
    if not ORIGEN.exists():
        raise SystemExit(f"No encuentro {ORIGEN.name}. ¿Corriste el servidor de desarrollo alguna vez?")

    print(f"\n  DE:     {ORIGEN.name}")
    print(f"          {resumen(ORIGEN)}")
    print(f"\n  HACIA:  {DESTINO.name}   (se reemplaza)")
    print(f"          {resumen(DESTINO)}")

    if "--si" not in sys.argv:
        print("\n  Esto BORRA lo que haya en la base de pruebas.")
        print("  Para confirmar:  ... tools/clonar-a-pruebas.py --si\n")
        return

    origen = sqlite3.connect(f"file:{ORIGEN}?mode=ro", uri=True)
    destino = sqlite3.connect(DESTINO)
    try:
        origen.backup(destino)
        # Consolidar el WAL dentro del .db antes de soltarlo.
        #
        # Sin esto, todo lo copiado queda en el archivo `-wal` de al lado y el
        # .db principal se queda en 4 KB. SQLite lo lee bien —junta los dos—
        # así que la app funciona y nada avisa. El problema aparece después:
        # copiar o respaldar "la base de datos" sin llevarse también el -wal
        # da una base VACÍA, y eso se descubre cuando ya es tarde.
        destino.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    finally:
        destino.close()
        origen.close()

    print(f"\n  Listo: {resumen(DESTINO)}")
    print("  Entrá con tu usuario de siempre. Lo que hagas acá no sale de tu PC.\n")


if __name__ == "__main__":
    main()
