"""
Estructura de los archivos planos del Facturador SUNAT.

Todas las posiciones de acá salen del Anexo I de SUNAT (el archivo
docs/sunat/AnexosIyII_Formato1.3.xlsx, hoja "Factura y boleta 2.1"),
leído campo por campo. En un archivo de palotes la POSICIÓN define el campo: un campo
de más o de menos corre todo lo que sigue, y SUNAT rechaza el comprobante
con un error que no apunta a la causa. Por eso estos tests verifican
posiciones concretas y no solo "el archivo existe".

Los índices de las listas son la posición del Anexo MENOS UNO (campo 1 del
Anexo = índice 0).
"""

import pytest

from backend.config import settings
from backend.utils import sfs_export
from backend.utils.sfs_export import (
    CAMPOS_CAB,
    CAMPOS_DET,
    CAMPOS_LEY,
    CAMPOS_TRI,
    SfsExportError,
    exportar_comprobante,
    monto_en_letras,
)


@pytest.fixture
def carpeta_sfs(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "sfs_export_dir", str(tmp_path))
    return tmp_path


def _exportar(carpeta, **overrides):
    """Boleta de ejemplo: 1 ceviche de S/45 + 2 jugos de S/22.50 = S/90."""
    datos = dict(
        ruc_emisor="10200812234",
        razon_social_emisor="Cevicheria de Prueba",
        tipo_comprobante="03",
        serie="B001",
        numero_correlativo=1,
        fecha_emision="2026-09-01",
        hora_emision="13:45:00",
        subtotal=76.27,
        igv=13.73,
        total=90.00,
        detalles=[
            {"plato_id": 101, "descripcion": "Ceviche Clásico", "cantidad": 1,
             "precio_unitario": 45.00, "subtotal": 45.00},
            {"plato_id": 105, "descripcion": "Jugo de Naranja", "cantidad": 2,
             "precio_unitario": 22.50, "subtotal": 45.00},
        ],
        tipo_documento_comprador="1",
        numero_documento_comprador="45678912",
        nombre_comprador="JUAN PEREZ",
    )
    datos.update(overrides)
    return exportar_comprobante(**datos)


def _lineas(ruta):
    """Lee el archivo y devuelve una lista de listas de campos.

    Lee BYTES y decodifica a mano: read_text() traduce el CRLF a \\n
    (universal newlines) y entonces no se puede verificar que el archivo
    lleve el CRLF que el formato exige.
    """
    from pathlib import Path
    crudo = Path(ruta).read_bytes().decode(settings.sfs_export_encoding)
    # El último token de cada línea es el vacío que deja el pipe final.
    return [linea.split("|")[:-1] for linea in crudo.rstrip("\r\n").split("\r\n")]


# ---------- Cantidad de campos ----------

def test_se_generan_los_cuatro_archivos_obligatorios(carpeta_sfs):
    """El Anexo agrupa .cab/.det/.tri/.ley bajo "Archivos Obligatorios".
    Durante mucho tiempo el exportador escribía solo los dos primeros."""
    r = _exportar(carpeta_sfs)
    for ruta in (r.archivo_cab, r.archivo_det, r.archivo_tri, r.archivo_ley):
        assert (carpeta_sfs / ruta.split("\\")[-1].split("/")[-1]).exists()


def test_cabecera_tiene_18_campos(carpeta_sfs):
    campos = _lineas(_exportar(carpeta_sfs).archivo_cab)[0]
    assert len(campos) == CAMPOS_CAB == 18


def test_detalle_tiene_36_campos_por_item(carpeta_sfs):
    """36, no 14. Los campos 8-14 son el bloque de IGV y ahí termina lo que
    un restaurante usa, pero el Anexo sigue con ISC, Otros e ICBPER, y
    recién DESPUÉS vienen los campos 34 y 35, que son obligatorios."""
    lineas = _lineas(_exportar(carpeta_sfs).archivo_det)
    assert len(lineas) == 2  # una por plato
    for campos in lineas:
        assert len(campos) == CAMPOS_DET == 36


def test_tributos_tiene_5_campos_y_leyendas_2(carpeta_sfs):
    r = _exportar(carpeta_sfs)
    assert len(_lineas(r.archivo_tri)[0]) == CAMPOS_TRI == 5
    assert len(_lineas(r.archivo_ley)[0]) == CAMPOS_LEY == 2


# ---------- Posiciones concretas ----------

def test_cabecera_deja_vacia_la_fecha_de_vencimiento(carpeta_sfs):
    """Campo 4 del Anexo. Es condicional y una boleta de restaurante se
    paga en el momento — pero el campo TIENE que estar, aunque vacío: sin
    él, todo lo que sigue (del 5 al 18) queda corrido una posición. Ese era
    exactamente el estado anterior del exportador."""
    campos = _lineas(_exportar(carpeta_sfs).archivo_cab)[0]
    assert campos[3] == ""
    assert campos[4] == "0000"   # 5. codLocalEmisor, en su lugar
    assert campos[16] == "2.1"   # 17. ublVersionId
    assert campos[17] == "2.0"   # 18. customizationId


def test_detalle_bloque_igv_usa_los_codigos_de_catalogo(carpeta_sfs):
    """Campos 8-14. Los valores salen de los catálogos del mismo Anexo:
    5 (tributos), 7 (afectación al IGV)."""
    campos = _lineas(_exportar(carpeta_sfs).archivo_det)[0]
    assert campos[7] == "1000"    # 8.  codTriIGV
    assert campos[10] == "IGV"    # 11. nomTributoIgvItem
    assert campos[11] == "VAT"    # 12. codTipTributoIgvItem
    assert campos[12] == "10"     # 13. tipAfeIGV (Gravado - Operación Onerosa)
    assert campos[13] == "18.00"  # 14. porIgvItem


def test_los_campos_34_y_35_llegan_a_su_posicion(carpeta_sfs):
    """EL test que justifica emitir los bloques vacíos de ISC/Otros/ICBPER.

    mtoPrecioVentaUnitario (34) y mtoValorVentaItem (35) son obligatorios y
    viven DESPUÉS de esos tres bloques. Si el detalle se cortara en 14
    campos —como decía la descripción inicial del formato— nunca llegarían
    a su posición y SUNAT rechazaría el comprobante.
    """
    campos = _lineas(_exportar(carpeta_sfs).archivo_det)[0]
    assert campos[33] == "45.00"  # 34. precio de venta unitario (con IGV)
    assert campos[34] == "38.14"  # 35. valor de venta del ítem (sin IGV)
    # Y los bloques del medio están presentes pero vacíos.
    assert all(c == "" for c in campos[14:33]), "los bloques ISC/Otros/ICBPER deben ir vacíos"


def test_tributos_desglosa_el_igv_declarado_en_la_cabecera(carpeta_sfs):
    """El .tri es lo que justifica el campo "Sumatoria Tributos" de la
    cabecera: la base imponible y el monto tienen que ser los mismos."""
    r = _exportar(carpeta_sfs)
    cab = _lineas(r.archivo_cab)[0]
    tri = _lineas(r.archivo_tri)[0]

    assert tri[0] == "1000"   # ideTributo
    assert tri[1] == "IGV"    # nomTributo
    assert tri[2] == "VAT"    # codTipTributo
    assert tri[3] == cab[10]  # mtoBaseImponible == sumTotValVenta
    assert tri[4] == cab[9]   # mtoTributo == sumTotTributos


def test_leyenda_lleva_el_monto_en_letras(carpeta_sfs):
    campos = _lineas(_exportar(carpeta_sfs).archivo_ley)[0]
    assert campos[0] == "1000"  # Catálogo 52: Monto en Letras
    assert campos[1] == "SON NOVENTA CON 00/100 SOLES"


# ---------- Serialización ----------

def test_las_lineas_terminan_en_crlf_sin_duplicar_el_retorno(carpeta_sfs):
    """Cada línea se arma con "\\r\\n" a mano. Si el archivo se abriera en
    modo texto sin newline="", Windows traduciría el "\\n" a "\\r\\n" y
    quedaría "\\r\\r\\n" — líneas rotas para cualquier parser que espere
    CRLF puro."""
    from pathlib import Path
    for ruta in _exportar(carpeta_sfs).__dict__.values():
        crudo = Path(ruta).read_bytes()
        assert crudo.endswith(b"\r\n")
        assert b"\r\r" not in crudo


def test_una_linea_con_campos_de_mas_no_se_escribe(carpeta_sfs):
    """La verificación de cantidad de campos es una red de seguridad para
    el futuro: si alguien agrega o saca un campo de un bloque sin ajustar
    el resto, tiene que reventar acá con el número a la vista, no salir a
    producción como un comprobante corrido."""
    with pytest.raises(SfsExportError, match="17 campos"):
        sfs_export._linea(*range(17), esperados=18)


# ---------- Todo o nada ----------

def test_si_falla_un_archivo_no_queda_ninguno(carpeta_sfs, monkeypatch):
    """Un comprobante a medias en la carpeta es peor que ninguno: el
    Facturador podría levantarlo igual y emitir algo mal formado."""
    from pathlib import Path
    original = Path.write_text
    escrituras = {"n": 0}

    def falla_en_la_tercera(self, *a, **kw):
        escrituras["n"] += 1
        if escrituras["n"] == 3:
            raise OSError("disco lleno")
        return original(self, *a, **kw)

    monkeypatch.setattr(Path, "write_text", falla_en_la_tercera)

    with pytest.raises(SfsExportError):
        _exportar(carpeta_sfs)

    assert list(carpeta_sfs.iterdir()) == [], "quedaron archivos de un comprobante incompleto"


def test_el_cab_se_escribe_ultimo(carpeta_sfs, monkeypatch):
    """El Facturador vigila la carpeta y dispara cuando aparece la
    cabecera. Si el .cab se escribiera primero, podría levantar el
    comprobante antes de que existan su detalle, tributos y leyendas."""
    from pathlib import Path
    orden = []
    original = Path.write_text

    def registrar(self, *a, **kw):
        orden.append(self.suffix)
        return original(self, *a, **kw)

    monkeypatch.setattr(Path, "write_text", registrar)
    _exportar(carpeta_sfs)

    assert orden[-1] == ".cab", f"el .cab tiene que ir último, orden real: {orden}"


# ---------- Monto en letras (archivo .ley) ----------

@pytest.mark.parametrize("monto,esperado", [
    (0.00, "SON CERO CON 00/100 SOLES"),
    (1.00, "SON UNO CON 00/100 SOLES"),
    (15.00, "SON QUINCE CON 00/100 SOLES"),
    (16.00, "SON DIECISÉIS CON 00/100 SOLES"),
    (22.00, "SON VEINTIDÓS CON 00/100 SOLES"),
    (31.00, "SON TREINTA Y UNO CON 00/100 SOLES"),
    # "CIEN" exacto vs "CIENTO ..." es una irregularidad del español que un
    # generador ingenuo se come.
    (100.00, "SON CIEN CON 00/100 SOLES"),
    (101.00, "SON CIENTO UNO CON 00/100 SOLES"),
    (123.50, "SON CIENTO VEINTITRÉS CON 50/100 SOLES"),
    (500.00, "SON QUINIENTOS CON 00/100 SOLES"),
    (700.00, "SON SETECIENTOS CON 00/100 SOLES"),
    (900.00, "SON NOVECIENTOS CON 00/100 SOLES"),
    # "MIL", nunca "UN MIL".
    (1000.00, "SON MIL CON 00/100 SOLES"),
    (2000.00, "SON DOS MIL CON 00/100 SOLES"),
    # Apócope: "VEINTIÚN MIL", no "VEINTIUNO MIL".
    (21000.00, "SON VEINTIÚN MIL CON 00/100 SOLES"),
    (31000.50, "SON TREINTA Y UN MIL CON 50/100 SOLES"),
    (1000000.00, "SON UN MILLÓN CON 00/100 SOLES"),
    (2000000.00, "SON DOS MILLONES CON 00/100 SOLES"),
])
def test_monto_en_letras(monto, esperado):
    assert monto_en_letras(monto) == esperado


def test_monto_en_letras_no_pierde_centavos_por_el_float(carpeta_sfs):
    """123.50 en binario es 123.50000000000001. Restando el entero y
    multiplicando por 100 se puede terminar con 49 centavos por
    truncamiento — por eso se pasa a centavos enteros ANTES de separar."""
    for monto in (123.50, 0.07, 45.90, 8.29, 1.10):
        centavos_esperados = f"{round(monto * 100) % 100:02d}"
        assert f"CON {centavos_esperados}/100" in monto_en_letras(monto)


def test_monto_en_letras_en_dolares():
    assert monto_en_letras(123.45, "USD") == "SON CIENTO VEINTITRÉS CON 45/100 DÓLARES AMERICANOS"
