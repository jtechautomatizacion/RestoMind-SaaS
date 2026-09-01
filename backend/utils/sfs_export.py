"""
Exportador local para el Facturador SUNAT (SFS), formato de archivos planos.

Costo S/ 0: en vez de mandar la boleta por API a un proveedor de pago
(ver backend/utils/facturacion_pe.py, que sigue existiendo para cuando
convenga volver a esa opción), se escriben archivos de texto plano con
formato de palotes ('|') en una carpeta que el Facturador SUNAT vigila.
El propio Facturador —no RestoMind— es quien arma el XML UBL 2.1, lo
firma y lo manda a SUNAT.

FUENTE DE LA ESTRUCTURA
-----------------------
Los campos y su orden salen del Anexo I de SUNAT (el archivo
docs/sunat/AnexosIyII_Formato1.3.xlsx, hoja "Factura y boleta 2.1"),
leído campo por campo — no de una interpretación. Cada bloque de abajo
lleva el número de campo del Anexo y el nombre de atributo que usa ahí,
para que cualquiera pueda cotejarlo contra el mismo documento.

SON CUATRO ARCHIVOS, NO DOS. El Anexo los agrupa bajo "*Archivos
Obligatorios" y marca todos sus campos como M (mandatorio) para boleta:

  .cab  18 campos   Cabecera del comprobante
  .det  36 campos   Una línea por ítem
  .tri   5 campos   Tributos generales (justifica "Sumatoria Tributos"
                    de la cabecera)
  .ley   2 campos   Leyendas; el "MONTO EN LETRAS" (código 1000) es
                    obligatorio en todo comprobante

POR QUÉ EL DETALLE LLEVA 36 CAMPOS Y NO 14
------------------------------------------
Los campos 8-14 son el bloque de IGV, y ahí termina lo que un restaurante
realmente usa. Pero el Anexo sigue: 15-21 ISC, 22-27 Otros Tributos,
28-33 ICBPER (bolsas plásticas), y recién después vienen los campos 34
(mtoPrecioVentaUnitario) y 35 (mtoValorVentaItem), AMBOS obligatorios.

En un archivo de palotes la POSICIÓN define el campo. Si se cortara en 14,
los campos 34 y 35 nunca llegarían a su lugar y SUNAT rechazaría el
comprobante. Por eso los bloques de ISC/Otros/ICBPER se emiten VACÍOS
(un restaurante no los usa) pero CON sus separadores.

DOS VALORES QUE CONVIENE COTEJAR CONTRA EL MANUAL DEL FACTURADOR
----------------------------------------------------------------
El Anexo define los campos pero no todos los detalles de serialización:
  - el encoding del archivo (se usa settings.sfs_export_encoding,
    latin-1 por defecto, la convención habitual de los planos de SUNAT)
  - si cada línea lleva '|' final (se agrega; ver _linea)
Ambos se cambian en un solo lugar si el Facturador los rechaza.

La extensión va en minúsculas. El Anexo la escribe ".CAB", pero ahí todo
el nombre está en mayúsculas como notación de placeholder
(RRRRRRRRRRR-CC-XXXX-999999999.CAB), y el Facturador corre sobre Windows,
cuyo sistema de archivos no distingue mayúsculas.

Distinción importante de estado: escribir estos archivos NO significa que
SUNAT aceptó el comprobante. Solo significa que RestoMind depositó la
solicitud; la aceptación ocurre después, dentro del Facturador, fuera del
alcance de este sistema. Por eso el estado resultante es
'generado_localmente', nunca 'enviada_sunat' (ver backend/routes/facturas.py).
"""

from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from backend.config import settings

IGV_TASA = 0.18

# Valores de catálogo de SUNAT usados en cada comprobante. Salen del mismo
# Anexo (hoja "Catálogos"); se nombran acá para que un cambio de catálogo
# no obligue a cazar literales sueltos entre los campos.
CAT51_VENTA_INTERNA = "0101"      # Catálogo 51: tipo de operación
CAT5_IGV_ID = "1000"              # Catálogo 5: código de tributo IGV
CAT5_IGV_NOMBRE = "IGV"           # Catálogo 5, columna "Nombre"
CAT5_IGV_TIPO = "VAT"             # Catálogo 5, columna "Código internacional"
CAT7_GRAVADO_ONEROSA = "10"       # Catálogo 7: afectación "Gravado - Operación Onerosa"
CAT52_MONTO_EN_LETRAS = "1000"    # Catálogo 52: leyenda "Monto en Letras"
UNIDAD_MEDIDA_ITEM = "NIU"        # Catálogo 3 (UN/ECE rec. 20): unidad de bien

# Cantidad de campos de cada archivo, según el Anexo. Se usan para
# verificar en tiempo de ejecución que ninguna línea salga corrida — un
# campo de más o de menos desplaza todo lo que sigue y el comprobante se
# rechaza sin un error que apunte a la causa.
CAMPOS_CAB = 18
CAMPOS_DET = 36
CAMPOS_TRI = 5
CAMPOS_LEY = 2


class SfsExportError(Exception):
    """No se pudo escribir el archivo (carpeta no configurada/no existe,
    sin permisos de escritura, disco lleno). Siempre reintentable una vez
    corregida la causa — nunca implica que el comprobante en sí sea inválido.
    """


@dataclass
class SfsExportResultado:
    archivo_cab: str
    archivo_det: str
    archivo_tri: str
    archivo_ley: str


def _nombre_base(ruc_emisor: str, tipo_comprobante: str, serie: str, numero_correlativo: int) -> str:
    # Convención estándar de SUNAT para el nombre de un CPE (la misma que
    # usa el XML UBL: RUC-tipoDoc-serie-correlativo).
    return f"{ruc_emisor}-{tipo_comprobante}-{serie}-{numero_correlativo:08d}"


def _monto(valor: float) -> str:
    """Formatea un importe con exactamente 2 decimales — nunca vía f-string
    directo sobre un float sin pasar antes por round(), porque un valor
    como 2.005 puede imprimir "2.00" o "2.01" según el redondeo binario del
    float en vez del redondeo decimal que se hizo más arriba al calcularlo."""
    return f"{round(valor, 2):.2f}"


def _linea(*campos, esperados: int) -> str:
    """Une campos con '|' y agrega un '|' final.

    `esperados` no es decorativo: si un bloque de campos queda corrido (uno
    de más o de menos), todo lo que sigue cae en la posición equivocada y
    SUNAT rechaza el comprobante con un error que no apunta a la causa.
    Mejor reventar acá, con el número de campos a la vista.
    """
    if len(campos) != esperados:
        raise SfsExportError(
            f"Se armó una línea con {len(campos)} campos y el formato exige "
            f"{esperados} — revisar contra el Anexo I de SUNAT."
        )
    return "|".join("" if c is None else str(c) for c in campos) + "|"


# ============ MONTO EN LETRAS (archivo .ley) ============

_UNIDADES = (
    "", "UNO", "DOS", "TRES", "CUATRO", "CINCO", "SEIS", "SIETE", "OCHO", "NUEVE",
    "DIEZ", "ONCE", "DOCE", "TRECE", "CATORCE", "QUINCE", "DIECISÉIS", "DIECISIETE",
    "DIECIOCHO", "DIECINUEVE", "VEINTE", "VEINTIUNO", "VEINTIDÓS", "VEINTITRÉS",
    "VEINTICUATRO", "VEINTICINCO", "VEINTISÉIS", "VEINTISIETE", "VEINTIOCHO", "VEINTINUEVE",
)
_DECENAS = ("", "", "VEINTE", "TREINTA", "CUARENTA", "CINCUENTA", "SESENTA", "SETENTA", "OCHENTA", "NOVENTA")
_CENTENAS = (
    "", "CIENTO", "DOSCIENTOS", "TRESCIENTOS", "CUATROCIENTOS", "QUINIENTOS",
    "SEISCIENTOS", "SETECIENTOS", "OCHOCIENTOS", "NOVECIENTOS",
)
_NOMBRE_MONEDA = {"PEN": "SOLES", "USD": "DÓLARES AMERICANOS"}


def _apocopar(texto: str) -> str:
    """"UNO" pasa a "UN" delante de un sustantivo masculino (MIL, MILLONES):
    se dice "VEINTIÚN MIL", no "VEINTIUNO MIL". Sin esto el monto en letras
    queda mal escrito en un documento tributario."""
    if texto.endswith("VEINTIUNO"):
        return texto[: -len("VEINTIUNO")] + "VEINTIÚN"
    if texto.endswith("UNO"):
        return texto[:-3] + "UN"
    return texto


def _menor_a_cien(n: int) -> str:
    if n < 30:
        return _UNIDADES[n]
    decena, unidad = divmod(n, 10)
    if unidad == 0:
        return _DECENAS[decena]
    return f"{_DECENAS[decena]} Y {_UNIDADES[unidad]}"


def _menor_a_mil(n: int) -> str:
    # 100 exacto es "CIEN"; de 101 en adelante es "CIENTO ..." — una de las
    # irregularidades del español que un f-string genérico se come.
    if n == 100:
        return "CIEN"
    centena, resto = divmod(n, 100)
    partes = []
    if centena:
        partes.append(_CENTENAS[centena])
    if resto:
        partes.append(_menor_a_cien(resto))
    return " ".join(partes)


def _entero_a_letras(n: int) -> str:
    if n == 0:
        return "CERO"
    partes = []
    millones, resto = divmod(n, 1_000_000)
    if millones:
        partes.append("UN MILLÓN" if millones == 1 else f"{_apocopar(_entero_a_letras(millones))} MILLONES")
    miles, unidades = divmod(resto, 1000)
    if miles:
        # 1000 es "MIL" a secas, nunca "UN MIL".
        partes.append("MIL" if miles == 1 else f"{_apocopar(_menor_a_mil(miles))} MIL")
    if unidades:
        partes.append(_menor_a_mil(unidades))
    return " ".join(partes)


def monto_en_letras(monto: float, moneda: str = "PEN") -> str:
    """Importe escrito en palabras, en el formato que usan los comprobantes
    peruanos: "SON CIENTO VEINTITRÉS CON 50/100 SOLES".

    Es obligatorio en todo comprobante (leyenda 1000 del Catálogo 52), y va
    en el archivo .ley.
    """
    # Se pasa a centavos enteros ANTES de separar, para que un float como
    # 123.50 (que en binario es 123.50000000000001) no termine dando 49
    # centavos por truncamiento.
    total_centavos = int(round(monto * 100))
    entero, centavos = divmod(abs(total_centavos), 100)
    nombre = _NOMBRE_MONEDA.get(moneda, moneda)
    return f"SON {_entero_a_letras(entero)} CON {centavos:02d}/100 {nombre}"


# ============ ARCHIVO .cab (18 campos) ============

def _construir_cabecera(
    *,
    fecha_emision: str,  # YYYY-MM-DD, hora LOCAL del restaurante — ver nota en routes/facturas.py
    hora_emision: str,  # HH:MM:SS, hora LOCAL
    tipo_documento_comprador: str,
    numero_documento_comprador: str,
    nombre_comprador: str,
    moneda: str,
    subtotal: float,  # Total valor de venta (sin IGV)
    igv: float,  # Sumatoria de tributos
    total: float,  # Importe total de la venta
) -> str:
    return _linea(
        CAT51_VENTA_INTERNA,        # 1.  tipOperacion
        fecha_emision,              # 2.  fecEmision
        hora_emision,               # 3.  horEmision
        "",                         # 4.  fecVencimiento — vacío: una boleta de
                                    #     restaurante se paga en el momento, no
                                    #     tiene vencimiento (campo condicional).
        "0000",                     # 5.  codLocalEmisor (domicilio fiscal principal)
        tipo_documento_comprador,   # 6.  tipDocUsuario
        numero_documento_comprador, # 7.  numDocUsuario
        nombre_comprador,           # 8.  rznSocialUsuario
        moneda,                     # 9.  tipMoneda
        _monto(igv),                # 10. sumTotTributos
        _monto(subtotal),           # 11. sumTotValVenta
        _monto(total),              # 12. sumPrecioVenta
        "0.00",                     # 13. sumDescTotal (sin soporte de descuentos aún)
        "0.00",                     # 14. sumOtrosCargos
        "0.00",                     # 15. sumTotalAnticipos
        _monto(total),              # 16. sumImpVenta
        "2.1",                      # 17. ublVersionId
        "2.0",                      # 18. customizationId
        esperados=CAMPOS_CAB,
    )


# ============ ARCHIVO .det (36 campos) ============

def _desglosar_linea(cantidad: int, subtotal_con_igv: float) -> tuple:
    """Descompone el subtotal (con IGV) de UNA línea en valor de venta + IGV,
    con el mismo criterio "IGV primero, subtotal por resta" que evita
    descuadres de un céntimo (ver routes/facturas.py:_calcular_montos)."""
    valor_venta_sin_redondear = subtotal_con_igv / (1 + IGV_TASA)
    igv_item = round(subtotal_con_igv - valor_venta_sin_redondear, 2)
    valor_venta_item = round(subtotal_con_igv - igv_item, 2)
    cantidad_segura = cantidad or 1  # ComandaPlatoCreate exige cantidad > 0; defensivo nomás
    valor_unitario_sin_igv = round(valor_venta_item / cantidad_segura, 2)
    return valor_venta_item, igv_item, valor_unitario_sin_igv


def _construir_detalle_lineas(*, detalles: List[dict], subtotal_cabecera: float, igv_cabecera: float) -> List[str]:
    """Una línea de 36 campos por plato. Al final, ajusta la ÚLTIMA línea si
    la suma de "Valor de venta del ítem"/"Monto de tributo" de todas las
    líneas no cuadra centavo a centavo con los totales de la cabecera — un
    redondeo por línea independiente puede desviarse un céntimo del total ya
    redondeado, y el Facturador valida que cabecera y detalle sumen igual."""
    calculadas = []  # (item, valor_venta_item, igv_item, valor_unitario_sin_igv)
    for item in detalles:
        valor_venta_item, igv_item, valor_unitario_sin_igv = _desglosar_linea(
            item["cantidad"], item["subtotal"]
        )
        calculadas.append([item, valor_venta_item, igv_item, valor_unitario_sin_igv])

    if calculadas:
        diff_valor_venta = round(subtotal_cabecera - sum(c[1] for c in calculadas), 2)
        diff_igv = round(igv_cabecera - sum(c[2] for c in calculadas), 2)
        if diff_valor_venta or diff_igv:
            calculadas[-1][1] = round(calculadas[-1][1] + diff_valor_venta, 2)
            calculadas[-1][2] = round(calculadas[-1][2] + diff_igv, 2)

    porcentaje_igv = f"{IGV_TASA * 100:.2f}"

    lineas = []
    for item, valor_venta_item, igv_item, valor_unitario_sin_igv in calculadas:
        lineas.append(_linea(
            UNIDAD_MEDIDA_ITEM,              # 1.  codUnidadMedida
            item["cantidad"],                # 2.  ctdUnidadItem
            item["plato_id"],                # 3.  codProducto (id interno del plato)
            "",                              # 4.  codProductoSUNAT (condicional, sin usar)
            item["descripcion"],             # 5.  desItem
            _monto(valor_unitario_sin_igv),  # 6.  mtoValorUnitario (sin IGV)
            _monto(igv_item),                # 7.  sumTotTributosItem

            # --- Bloque IGV (campos 8-14), "Mandatorio en conjunto" ---
            CAT5_IGV_ID,                     # 8.  codTriIGV
            _monto(igv_item),                # 9.  mtoIgvItem
            _monto(valor_venta_item),        # 10. mtoBaseIgvItem
            CAT5_IGV_NOMBRE,                 # 11. nomTributoIgvItem
            CAT5_IGV_TIPO,                   # 12. codTipTributoIgvItem
            CAT7_GRAVADO_ONEROSA,            # 13. tipAfeIGV
            porcentaje_igv,                  # 14. porIgvItem

            # --- Bloque ISC (15-21): vacío, un restaurante no vende bienes
            #     afectos al Impuesto Selectivo al Consumo. Los separadores
            #     igual tienen que estar: si no, los campos 34 y 35 (que sí
            #     son obligatorios) caerían en la posición equivocada.
            "", "", "", "", "", "", "",

            # --- Bloque Otros Tributos 9999 (22-27): vacío ---
            "", "", "", "", "", "",

            # --- Bloque ICBPER 7152 (28-33): vacío. Es el impuesto a las
            #     bolsas plásticas; si algún día se cobran bolsas, se llena
            #     este bloque en vez de dejarlo en blanco.
            "", "", "", "", "", "",

            _monto(item["precio_unitario"]),  # 34. mtoPrecioVentaUnitario (con IGV)
            _monto(valor_venta_item),         # 35. mtoValorVentaItem
            "",                               # 36. mtoValorReferencialUnitario
                                              #     (condicional: solo ítems gratuitos)
            esperados=CAMPOS_DET,
        ))
    return lineas


# ============ ARCHIVO .tri (5 campos) ============

def _construir_tributos_lineas(*, subtotal: float, igv: float) -> List[str]:
    """Tributos generales del comprobante: una línea por tipo de tributo.

    Es lo que justifica el campo "Sumatoria Tributos" de la cabecera. Un
    restaurante solo tiene IGV, así que sale una sola línea; el día que
    haya operaciones exoneradas o inafectas, van como líneas adicionales
    con su propio código de Catálogo 5.
    """
    return [_linea(
        CAT5_IGV_ID,       # 1. ideTributo
        CAT5_IGV_NOMBRE,   # 2. nomTributo
        CAT5_IGV_TIPO,     # 3. codTipTributo
        _monto(subtotal),  # 4. mtoBaseImponible
        _monto(igv),       # 5. mtoTributo
        esperados=CAMPOS_TRI,
    )]


# ============ ARCHIVO .ley (2 campos) ============

def _construir_leyendas_lineas(*, total: float, moneda: str) -> List[str]:
    """Leyendas del comprobante. La 1000 ("Monto en Letras") es obligatoria
    en todos, y es la única que aplica a una boleta de restaurante."""
    return [_linea(
        CAT52_MONTO_EN_LETRAS,             # 1. codLeyenda
        monto_en_letras(total, moneda),    # 2. desLeyenda
        esperados=CAMPOS_LEY,
    )]


# ============ ESCRITURA ============

def exportar_comprobante(
    *,
    ruc_emisor: str,
    razon_social_emisor: str,
    tipo_comprobante: str,
    serie: str,
    numero_correlativo: int,
    fecha_emision: str,
    hora_emision: str,
    subtotal: float,
    igv: float,
    total: float,
    detalles: List[dict],
    tipo_documento_comprador: Optional[str] = None,
    numero_documento_comprador: Optional[str] = None,
    nombre_comprador: Optional[str] = None,
    moneda: str = "PEN",
) -> SfsExportResultado:
    """Escribe los cuatro archivos del comprobante en settings.sfs_export_dir.

    razon_social_emisor no se usa en el cuerpo de ninguno de los archivos
    (el Facturador ya conoce al emisor por su propia configuración); se
    mantiene en la firma, que es compartida con el emisor facturacion_pe
    (que sí lo necesita, porque ahí SÍ hay que declarar quién emite).

    Lanza SfsExportError si la carpeta no está configurada, no existe, o
    falla la escritura — nunca deja un comprobante escrito a medias (ver
    la limpieza más abajo).
    """
    if not settings.sfs_export_dir:
        raise SfsExportError(
            "SFS_EXPORT_DIR no está configurado — indicá la carpeta que vigila "
            "el Facturador SUNAT en el .env de esta PC."
        )

    carpeta = Path(settings.sfs_export_dir)
    if not carpeta.is_dir():
        raise SfsExportError(
            f"La carpeta configurada para el Facturador SUNAT no existe: {carpeta}. "
            "Verificá que el Facturador esté instalado y SFS_EXPORT_DIR apunte a su carpeta DATA."
        )

    nombre_base = _nombre_base(ruc_emisor, tipo_comprobante, serie, numero_correlativo)

    contenido_cab = _construir_cabecera(
        fecha_emision=fecha_emision,
        hora_emision=hora_emision,
        tipo_documento_comprador=tipo_documento_comprador or "0",
        numero_documento_comprador=numero_documento_comprador or "00000000",
        nombre_comprador=nombre_comprador or "CLIENTES VARIOS",
        moneda=moneda,
        subtotal=subtotal,
        igv=igv,
        total=total,
    ) + "\r\n"
    contenido_det = "\r\n".join(
        _construir_detalle_lineas(detalles=detalles, subtotal_cabecera=subtotal, igv_cabecera=igv)
    ) + "\r\n"
    contenido_tri = "\r\n".join(_construir_tributos_lineas(subtotal=subtotal, igv=igv)) + "\r\n"
    contenido_ley = "\r\n".join(_construir_leyendas_lineas(total=total, moneda=moneda)) + "\r\n"

    encoding = settings.sfs_export_encoding

    # El orden importa: el .cab va ÚLTIMO. El Facturador vigila la carpeta y
    # dispara cuando aparece la cabecera, así que si esta se escribiera
    # primero podría levantar el comprobante antes de que existan su detalle,
    # sus tributos o sus leyendas. Escribiendo los complementos primero, para
    # cuando el .cab aparece ya está todo en su lugar.
    #
    # newline="" desactiva la traducción automática de fin de línea que
    # write_text hace en modo texto (en Windows, "\n" -> "\r\n"): sin esto,
    # el "\r\n" que ya se arma a mano en cada línea termina duplicado en
    # "\r\r\n", y el Facturador (o cualquier parser que espere CRLF puro)
    # ve líneas rotas.
    a_escribir = [
        (carpeta / f"{nombre_base}.det", contenido_det),
        (carpeta / f"{nombre_base}.tri", contenido_tri),
        (carpeta / f"{nombre_base}.ley", contenido_ley),
        (carpeta / f"{nombre_base}.cab", contenido_cab),
    ]

    escritos = []
    for ruta, contenido in a_escribir:
        try:
            ruta.write_text(contenido, encoding=encoding, newline="")
            escritos.append(ruta)
        except OSError as exc:
            # Todo o nada: un comprobante incompleto en la carpeta es peor
            # que ninguno, porque el Facturador podría levantarlo igual y
            # emitir algo mal formado.
            for previo in escritos:
                previo.unlink(missing_ok=True)
            raise SfsExportError(f"No se pudo escribir {ruta.name}: {exc}") from exc

    return SfsExportResultado(
        archivo_cab=str(carpeta / f"{nombre_base}.cab"),
        archivo_det=str(carpeta / f"{nombre_base}.det"),
        archivo_tri=str(carpeta / f"{nombre_base}.tri"),
        archivo_ley=str(carpeta / f"{nombre_base}.ley"),
    )
