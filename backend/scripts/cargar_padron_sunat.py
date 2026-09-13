"""
Construye la base local de consulta de RUC desde el Padrón Reducido oficial
de SUNAT.

    python -m backend.scripts.cargar_padron_sunat            # descarga y carga
    python -m backend.scripts.cargar_padron_sunat --archivo padron.zip
    python -m backend.scripts.cargar_padron_sunat --limite 100000   # prueba

QUÉ ES ESTA FUENTE
------------------
https://www.sunat.gob.pe/descargaPRR/mrc137_padron_reducido.html
SUNAT publica el padrón para descarga pública, precisamente para que los
contribuyentes puedan validar a sus contrapartes. Usarlo para completar la
razón social de un comprobante es el uso para el que existe.

Formato verificado sobre el archivo real (no supuesto):
  - ZIP -> padron_reducido_ruc.txt, 1.5 GB sin comprimir
  - separado por "|", con un pipe SOBRANTE al final de cada línea
  - codificado en LATIN-1, no UTF-8 (un decode('utf-8') revienta)
  - primera línea de cabecera
  - 15 columnas; los campos vacíos vienen como "-"

DATOS PERSONALES — LEER ANTES DE CAMBIAR NADA
---------------------------------------------
Los RUC que empiezan en 10, 15, 16 y 17 son PERSONAS NATURALES: su "razón
social" es el nombre y apellidos de una persona real. Eso es dato personal
bajo la Ley N° 29733.

Procesarlo es lícito porque proviene de una fuente de acceso público
(Art. 14), pero eso NO habilita cualquier uso. Dos consecuencias concretas
que están implementadas y no hay que aflojar:

  1. Solo se guardan los 4 campos que hacen falta para emitir un
     comprobante (ruc, nombre, estado, condición). Las 11 columnas de
     domicilio se descartan: una boleta no las necesita, y guardar el
     domicilio de 10 millones de personas sin usarlo es exactamente el
     tipo de acumulación que la ley busca evitar. De paso, la base baja
     de ~2.5 GB a ~800 MB.
  2. La consulta NUNCA se expone sin autenticar (ver backend/routes/ruc.py).
     Un endpoint público sobre esta base es una API de divulgación masiva
     de datos personales y un imán de scraping.

POR QUÉ SE CONSTRUYE APARTE Y SE INTERCAMBIA AL FINAL
-----------------------------------------------------
La carga tarda minutos y reescribe millones de filas. Hacerla sobre el
archivo que la app está consultando dejaría las búsquedas lentas o rotas
todo ese rato. Se construye en un archivo temporal y recién al terminar se
reemplaza de un golpe (os.replace es atómico): las consultas en vuelo
siguen con la base vieja hasta el instante del cambio.
"""

from __future__ import annotations

import argparse
import os
import sqlite3
import struct
import sys
import time
import zlib
from pathlib import Path
from typing import Iterable, Iterator

URL_PADRON = "http://www2.sunat.gob.pe/padron_reducido_ruc.zip"

# 50k filas por transacción. Con lotes mucho más chicos el costo por commit
# domina; con lotes mucho más grandes la transacción pendiente crece en
# memoria, que es justo lo que no sobra en un VPS de 2 GB.
TAM_LOTE = 50_000

# Cuánto se lee del stream por vez. 1 MB comprimido rinde ~4 MB de texto:
# suficiente para avanzar rápido sin inflar la memoria.
TROZO_DESCARGA = 1024 * 1024

RUTA_POR_DEFECTO = Path("data/sunat_padron.db")


# ============ LECTURA EN STREAMING ============

def _fuente_bytes(archivo: str | None) -> Iterator[bytes]:
    """Entrega el ZIP por trozos, desde disco o directo de la red.

    Nunca se guarda el .txt de 1.5 GB en disco: se descomprime al vuelo y
    solo sobrevive la base final.
    """
    if archivo:
        with open(archivo, "rb") as fh:
            while trozo := fh.read(TROZO_DESCARGA):
                yield trozo
        return

    import httpx

    print(f"Descargando {URL_PADRON} ...")
    # Sin timeout de lectura total: son ~374 MB y una conexión lenta puede
    # tardar bastante. El timeout de conexión sí se acota.
    with httpx.stream("GET", URL_PADRON, timeout=httpx.Timeout(30.0, read=None),
                      follow_redirects=True) as resp:
        resp.raise_for_status()
        total = int(resp.headers.get("content-length", 0))
        bajado = 0
        ultimo_aviso = 0.0
        for trozo in resp.iter_bytes(TROZO_DESCARGA):
            bajado += len(trozo)
            ahora = time.time()
            if total and ahora - ultimo_aviso > 3:
                ultimo_aviso = ahora
                print(f"  {bajado/1048576:7.1f} / {total/1048576:.1f} MB "
                      f"({100*bajado/total:.0f}%)", flush=True)
            yield trozo


def _lineas_del_zip(trozos: Iterable[bytes]) -> Iterator[str]:
    """
    Descomprime el ZIP sobre la marcha y entrega líneas de texto.

    Se parsea el encabezado local del ZIP a mano en vez de usar zipfile
    porque zipfile necesita poder posicionarse (seek) sobre el archivo
    completo — lee el directorio central, que está AL FINAL. Con un stream
    de red eso obligaría a bajar los 374 MB a disco antes de empezar.
    El padrón trae un único archivo dentro, así que alcanza con leer su
    encabezado y descomprimir el resto como un stream deflate crudo.
    """
    it = iter(trozos)
    buffer = b""

    # El encabezado local mide 30 bytes fijos + nombre + extra.
    while len(buffer) < 30:
        buffer += next(it)
    if buffer[:4] != b"PK\x03\x04":
        raise SystemExit("El archivo no parece un ZIP válido de SUNAT.")

    metodo = struct.unpack("<H", buffer[8:10])[0]
    nlen, elen = struct.unpack("<HH", buffer[26:30])
    while len(buffer) < 30 + nlen + elen:
        buffer += next(it)

    nombre = buffer[30:30 + nlen].decode("latin-1")
    print(f"Archivo dentro del ZIP: {nombre}")
    if metodo != 8:
        raise SystemExit(f"Compresión inesperada ({metodo}); se esperaba deflate.")

    # -15 = deflate crudo, sin la cabecera zlib que el ZIP no incluye.
    descompresor = zlib.decompressobj(-15)
    resto = buffer[30 + nlen + elen:]
    pendiente = b""

    def procesar(datos: bytes) -> Iterator[str]:
        nonlocal pendiente
        texto = descompresor.decompress(datos)
        if not texto:
            return
        pendiente += texto
        # La última línea del bloque casi siempre queda cortada: se guarda
        # para pegarla con el bloque siguiente. Sin esto se perderían (o
        # se partirían) filas justo en los bordes de cada trozo.
        *completas, pendiente = pendiente.split(b"\n")
        for linea in completas:
            yield linea.decode("latin-1")

    yield from procesar(resto)
    for trozo in it:
        yield from procesar(trozo)

    cola = pendiente + descompresor.flush()
    for linea in cola.split(b"\n"):
        if linea.strip():
            yield linea.decode("latin-1")


def filas_del_padron(trozos: Iterable[bytes], limite: int | None = None) -> Iterator[tuple]:
    """Generador de (ruc, nombre, estado, condicion) ya limpios."""
    entregadas = 0
    for numero, linea in enumerate(_lineas_del_zip(trozos)):
        if numero == 0:
            continue  # cabecera
        if not linea.strip():
            continue

        campos = linea.split("|")
        if len(campos) < 4:
            continue

        ruc = campos[0].strip()
        # Se descarta lo que no tenga forma de RUC en vez de cortar la
        # carga: el padrón es un archivo de 10 millones de filas y una
        # línea rara no puede tirar abajo el proceso entero.
        if len(ruc) != 11 or not ruc.isdigit():
            continue

        nombre = campos[1].strip()
        estado = campos[2].strip()
        condicion = campos[3].strip()
        # SUNAT usa "-" para vacío; guardarlo así obligaría a que cada
        # consumidor lo traduzca.
        yield (
            ruc,
            nombre if nombre != "-" else "",
            estado if estado != "-" else "",
            condicion if condicion != "-" else "",
        )

        entregadas += 1
        if limite and entregadas >= limite:
            return


# ============ CONSTRUCCIÓN DE LA BASE ============

DDL = """
CREATE TABLE padron (
    ruc       TEXT NOT NULL,
    nombre    TEXT NOT NULL,
    estado    TEXT,
    condicion TEXT
);
"""


def _conectar_para_carga(ruta: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(ruta)
    # PRAGMAs SOLO para la carga masiva. Son inseguros ante un corte de luz
    # (journal_mode=OFF significa que no hay cómo revertir una transacción a
    # medias), y acá eso es aceptable: si se corta, se descarta el temporal
    # y se vuelve a cargar. La base EN USO nunca corre con estos valores.
    conn.execute("PRAGMA journal_mode = OFF")
    conn.execute("PRAGMA synchronous = OFF")
    conn.execute("PRAGMA temp_store = FILE")
    # 64 MB de caché: acelera mucho la creación del índice sin comprometer
    # la memoria de un VPS chico (el resto del sistema sigue necesitando RAM).
    conn.execute("PRAGMA cache_size = -64000")
    return conn


def construir(destino: Path, archivo: str | None, limite: int | None) -> None:
    destino.parent.mkdir(parents=True, exist_ok=True)
    temporal = destino.with_suffix(".db.construyendo")
    if temporal.exists():
        temporal.unlink()

    conn = _conectar_para_carga(temporal)
    conn.executescript(DDL)

    inicio = time.time()
    total = 0
    lote: list[tuple] = []

    try:
        for fila in filas_del_padron(_fuente_bytes(archivo), limite):
            lote.append(fila)
            if len(lote) >= TAM_LOTE:
                conn.executemany("INSERT INTO padron VALUES (?,?,?,?)", lote)
                conn.commit()
                total += len(lote)
                lote.clear()
                print(f"  {total:>10,} filas  ({total/(time.time()-inicio):,.0f}/s)", flush=True)

        if lote:
            conn.executemany("INSERT INTO padron VALUES (?,?,?,?)", lote)
            conn.commit()
            total += len(lote)

        if total == 0:
            raise SystemExit("No se cargó ninguna fila; se aborta sin tocar la base actual.")

        # El índice se crea AL FINAL, no antes: mantenerlo actualizado
        # durante 10 millones de INSERT cuesta muchísimo más que ordenarlo
        # una sola vez al terminar.
        print(f"Creando índice sobre {total:,} filas (este paso tarda)...", flush=True)
        conn.execute("CREATE UNIQUE INDEX idx_ruc ON padron(ruc)")
        conn.commit()

        # ANALYZE deja estadísticas para que el planificador elija el índice
        # con certeza en vez de estimarlo.
        conn.execute("ANALYZE")
        # Recién ahora se pasa a WAL, que es el modo con el que la app la
        # va a LEER: permite lecturas concurrentes sin bloqueos.
        conn.execute("PRAGMA journal_mode = WAL")
        conn.commit()
    finally:
        conn.close()

    tam = temporal.stat().st_size / 1048576

    # Cambio atómico: hasta esta línea, las consultas siguen usando la base
    # anterior. os.replace no deja un instante en que el archivo no exista.
    os.replace(temporal, destino)
    # El WAL de la base vieja quedaría huérfano y confundiría a SQLite.
    for sufijo in ("-wal", "-shm"):
        viejo = Path(str(destino) + sufijo)
        if viejo.exists():
            viejo.unlink()

    minutos = (time.time() - inicio) / 60
    print()
    print(f"[OK] {total:,} contribuyentes en {destino}")
    print(f"     {tam:,.0f} MB  ·  {minutos:.1f} minutos")


def main() -> None:
    p = argparse.ArgumentParser(description="Carga el Padrón Reducido de SUNAT.")
    p.add_argument("--archivo", help="ZIP ya descargado (si no, se baja de SUNAT)")
    p.add_argument("--destino", default=str(RUTA_POR_DEFECTO))
    p.add_argument("--limite", type=int, help="Cargar solo N filas (para probar)")
    args = p.parse_args()

    construir(Path(args.destino), args.archivo, args.limite)


if __name__ == "__main__":
    main()
