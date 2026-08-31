"""
Exportador local para el Facturador SUNAT (SFS v1.3.2, oficial de la web
de SUNAT) instalado en la PC de caja.

Costo S/ 0: en vez de mandar la boleta por API a un proveedor de pago
(ver backend/utils/facturacion_pe.py, que sigue existiendo para cuando
convenga volver a esa opción), se escriben dos archivos de texto plano
con formato de palotes ('|') en una carpeta que el Facturador SUNAT
vigila. El propio Facturador —no RestoMind— es quien arma el XML UBL
2.1, lo firma y lo manda a SUNAT.

El orden de campos de CABECERA (17) y DETALLE (12) de acá abajo viene
confirmado por el usuario contra el manual real del SFS v1.3.2 — no es
un placeholder. Lo que SIGUE sin confirmar (el usuario no lo especificó):
encoding exacto del archivo y si cada línea lleva '|' final — se dejaron
las convenciones más comunes en formatos planos de SUNAT (Latin-1,
pipe final), configurable/ajustable en un solo lugar si hace falta
cambiarlas.

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


class SfsExportError(Exception):
    """No se pudo escribir el archivo (carpeta no configurada/no existe,
    sin permisos de escritura, disco lleno). Siempre reintentable una vez
    corregida la causa — nunca implica que el comprobante en sí sea inválido.
    """


@dataclass
class SfsExportResultado:
    archivo_cab: str
    archivo_det: str


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


def _linea(*campos) -> str:
    """Une campos con '|' y agrega un '|' final — convención común en los
    formatos planos de SUNAT (ej. PLE). Sin confirmar contra el manual
    específico del SFS v1.3.2: si tu Facturador rechaza el pipe final,
    sacá el '+ "|"' de acá nomás — es el único lugar que lo agrega."""
    return "|".join(str(c) for c in campos) + "|"


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
    total: float,  # Total precio de venta / Importe total de la venta
) -> str:
    return _linea(
        "0101",                            # 1.  Tipo de operación: venta interna
        fecha_emision,                     # 2.  Fecha de emisión
        hora_emision,                      # 3.  Hora de emisión
        "0000",                            # 4.  Código de domicilio fiscal (principal)
        tipo_documento_comprador,          # 5.  Tipo de documento del cliente
        numero_documento_comprador,        # 6.  Número de documento del cliente
        nombre_comprador,                  # 7.  Apellidos y nombres / razón social del cliente
        moneda,                            # 8.  Tipo de moneda
        _monto(igv),                       # 9.  Sumatoria de tributos
        _monto(subtotal),                  # 10. Total valor de venta
        _monto(total),                     # 11. Total precio de venta
        "0.00",                            # 12. Total descuentos (sin soporte de descuentos aún)
        "0.00",                            # 13. Sumatoria de otros cargos
        "0.00",                            # 14. Total anticipos
        _monto(total),                     # 15. Importe total de la venta
        "2.1",                             # 16. Versión UBL
        "2.0",                             # 17. Versión de la estructura del documento
    )


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
    """Una línea por plato. Al final, ajusta la ÚLTIMA línea si la suma de
    "Valor de venta del ítem"/"Monto de tributo" de todas las líneas no
    cuadra centavo a centavo con los totales de la cabecera — un redondeo
    por línea independiente puede desviarse un céntimo del total ya
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

    lineas = []
    for item, valor_venta_item, igv_item, valor_unitario_sin_igv in calculadas:
        lineas.append(_linea(
            "NIU",                                          # 1.  Unidad de medida
            item["cantidad"],                                # 2.  Cantidad
            item["plato_id"],                                # 3.  Código de producto (ID interno)
            "-",                                              # 4.  Código de producto SUNAT
            item["descripcion"],                             # 5.  Descripción del plato
            _monto(valor_unitario_sin_igv),                  # 6.  Valor unitario por ítem (sin IGV)
            _monto(igv_item),                                # 7.  Sumatoria de tributos por ítem
            "10",                                             # 8.  Código de afectación IGV: Gravado
            _monto(igv_item),                                # 9.  Monto de tributo por ítem
            "-",                                              # 10. Tipo de sistema de ISC
            _monto(item["precio_unitario"]),                 # 11. Precio unitario por ítem (con IGV)
            _monto(valor_venta_item),                        # 12. Valor de venta del ítem
        ))
    return lineas


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
    """Escribe {nombre}.cab y {nombre}.det en settings.sfs_export_dir.

    razon_social_emisor no se usa en el cuerpo de ninguno de los dos
    archivos (el spec de SFS v1.3.2 no lo pide — el Facturador ya conoce
    los datos del emisor porque están configurados en la instalación local
    del propio software, se identifica solo por el RUC en el nombre del
    archivo). Se recibe igual para no romper la firma de _emitir() en
    routes/facturas.py, que es compartida con el emisor facturacion_pe
    (que sí lo necesita, porque ahí SÍ hay que declarar quién emite).

    Lanza SfsExportError si la carpeta no está configurada, no existe, o
    falla la escritura — nunca escribe "a medias" (si falla el .det
    después de escribir el .cab, se borra el .cab, para que el Facturador
    nunca vea una cabecera sin su detalle).
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
    ruta_cab = carpeta / f"{nombre_base}.cab"
    ruta_det = carpeta / f"{nombre_base}.det"

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
    )
    lineas_det = _construir_detalle_lineas(detalles=detalles, subtotal_cabecera=subtotal, igv_cabecera=igv)
    contenido_det = "\r\n".join(lineas_det) + "\r\n"

    encoding = settings.sfs_export_encoding

    # newline="" desactiva la traducción automática de fin de línea que
    # write_text hace en modo texto (en Windows, "\n" -> "\r\n"): sin esto,
    # el "\r\n" que ya se arma a mano en cada línea termina duplicado en
    # "\r\r\n", y el Facturador (o cualquier parser que espere CRLF puro)
    # ve líneas rotas.
    try:
        ruta_cab.write_text(contenido_cab + "\r\n", encoding=encoding, newline="")
    except OSError as exc:
        raise SfsExportError(f"No se pudo escribir {ruta_cab.name}: {exc}") from exc

    try:
        ruta_det.write_text(contenido_det, encoding=encoding, newline="")
    except OSError as exc:
        # No dejar un .cab huérfano: el Facturador podría levantarlo sin
        # su detalle si justo escanea la carpeta en este instante.
        ruta_cab.unlink(missing_ok=True)
        raise SfsExportError(f"No se pudo escribir {ruta_det.name}: {exc}") from exc

    return SfsExportResultado(archivo_cab=str(ruta_cab), archivo_det=str(ruta_det))
