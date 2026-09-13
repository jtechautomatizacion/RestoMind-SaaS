"""
Cliente del micro-servicio de emisión SUNAT (ver sunat-service/app.py).

Es el tercer emisor de comprobantes, junto a los dos que ya existían
(`sfs_local` y `facturacion_pe`) — se elige con
`settings.emisor_facturacion = "sunat_cloud"`.

QUÉ RESUELVE
------------
Los otros dos emisores atan el restaurante a una PC con Windows: `sfs_local`
escribe archivos que el Facturador SUNAT de escritorio tiene que leer, y por
eso hizo falta el agente de PowerShell (`agente/`). Con este emisor la boleta
se firma y se envía a SUNAT desde el servidor, así que un restaurante que
opera solo con tablets o celulares puede facturar sin instalar nada.

EL PUNTO DELICADO: EL IGV
-------------------------
RestoMind guarda los precios como los ve el comensal en la carta, es decir
CON IGV incluido (la costumbre en Perú, y lo que asume `_calcular_montos()`
en routes/facturas.py, que descompone el total hacia atrás).

`sunat-py` espera lo contrario: su `InvoiceLine.precio_unitario` es la base
IMPONIBLE, sin IGV — internamente hace `precio_con_igv = precio_unitario *
1.18`. Pasarle el precio de carta tal cual inflaría cada boleta un 18% frente
a lo que el cliente pagó de verdad. La conversión se hace acá, en un solo
lugar, y está cubierta por tests.

Se usa Decimal y no float para esa división: son montos que terminan en un
comprobante tributario, y el redondeo de un float puede dejar la boleta con
un céntimo de diferencia contra lo cobrado.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import List, Optional

import httpx

from backend.config import settings

IGV_TASA = Decimal("0.18")

# CINCO decimales en el precio unitario, como lo hace SUNAT.
#
# Calibrado contra un comprobante REAL (boleta EB01-1297): para un ítem de
# S/ 150.00, el visor oficial de SUNAT declara
#
#     Valor Unitario   127.11864      <- 5 decimales
#     Importe de Venta 149.9999952
#
# y se reproduce exacto con 150 / 1.18 redondeado a 5 decimales. Con menos
# decimales el Valor Unitario impreso ya no coincide con el que emitiría
# SUNAT para el mismo importe.
#
# SUNAT admite hasta 10 decimales en el precio unitario justamente para esto,
# y el XML igual muestra el precio de venta redondeado a dos.
PRECISION_BASE = Decimal("0.00001")

# Códigos de documento de identidad de SUNAT (catálogo 06).
DOC_DNI = "1"
DOC_RUC = "6"
DOC_SIN_DOCUMENTO = "0"

# Comprador por defecto de una boleta cuando el comensal no pide comprobante
# a su nombre. Es lo que SUNAT espera para una venta al público general.
RECEPTOR_GENERICO = {
    "tipo_doc": DOC_SIN_DOCUMENTO,
    "numero_doc": "00000000",
    "razon_social": "PUBLICO GENERAL",
}


class SunatCloudError(Exception):
    """El servicio no respondió (caído, red, timeout). El comprobante en sí
    puede estar perfecto: quien llama debe dejar la Factura reintentable, no
    marcarla como rechazada."""


@dataclass
class SunatCloudResultado:
    exito: bool
    estado: Optional[str] = None
    codigo: Optional[str] = None
    descripcion: Optional[str] = None
    cdr_xml: Optional[str] = None
    nombre_archivo: Optional[str] = None
    error_codigo: Optional[str] = None
    error_mensaje: Optional[str] = None
    # True cuando conviene reintentar tal cual (problema de transporte), False
    # cuando SUNAT rechazó el contenido y reintentar daría el mismo resultado.
    reintentable: bool = False


def precio_sin_igv(precio_con_igv: float | Decimal) -> Decimal:
    """
    Convierte un precio de carta (IGV incluido) a la base imponible.

    Redondea HALF_UP, el criterio tributario — no el "banker's rounding" que
    Python usa por defecto: con ROUND_HALF_EVEN, un valor justo en el medio
    se iría hacia abajo la mitad de las veces y la boleta no cuadraría con
    lo cobrado.

    Sobre la cantidad de decimales, ver PRECISION_BASE arriba: dos no
    alcanzan.
    """
    base = Decimal(str(precio_con_igv)) / (Decimal("1") + IGV_TASA)
    return base.quantize(PRECISION_BASE, rounding=ROUND_HALF_UP)


def total_que_declarara_sunat(detalles: List[dict]) -> Decimal:
    """
    Reproduce EXACTAMENTE la aritmética de `sunat_py.compute_totals` para
    saber, antes de enviar, qué total va a terminar diciendo la boleta.

    Existe porque RestoMind y SUNAT calculan el IGV en direcciones opuestas:

      RestoMind (routes/facturas.py::_calcular_montos)
          parte del TOTAL cobrado y saca el IGV hacia atrás
      SUNAT / sunat-py
          parte de la BASE de cada línea y suma el IGV hacia adelante

    Con ciertos precios las dos cuentas no pueden coincidir. Ejemplo real:
    S/ 120.00 cobrados dan base 101.69 -> IGV 18.30 -> total 119.99; y con
    base 101.70 el total salta a 120.01. NO existe una base que dé 120.00.

    No es un error que se arregle afinando decimales: es una limitación del
    redondeo a céntimos por línea. Lo que sí se puede es DETECTARLO y
    avisar, en vez de emitir en silencio un comprobante que declara un
    importe distinto del que pagó el comensal.
    """
    total = Decimal("0")
    for item in detalles:
        base_linea = (Decimal(str(item["cantidad"])) * precio_sin_igv(item["precio_unitario"]))
        base_linea = base_linea.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        igv_linea = (base_linea * IGV_TASA).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        total += base_linea + igv_linea
    return total


def diferencia_contra_lo_cobrado(detalles: List[dict], total_cobrado: float) -> Decimal:
    """Cuánto se desviaría la boleta del importe realmente cobrado.
    Cero = cuadra exacto. Positivo = la boleta declara de más."""
    return total_que_declarara_sunat(detalles) - Decimal(str(total_cobrado))


def _receptor(
    tipo_documento_comprador: Optional[str],
    numero_documento_comprador: Optional[str],
    nombre_comprador: Optional[str],
) -> dict:
    if not numero_documento_comprador:
        return dict(RECEPTOR_GENERICO)
    return {
        "tipo_doc": tipo_documento_comprador or DOC_DNI,
        "numero_doc": numero_documento_comprador,
        # Sin nombre, SUNAT igual acepta la boleta con el documento; poner
        # algo vacío haría fallar la validación del XML.
        "razon_social": nombre_comprador or "CLIENTE",
    }


def _lineas(detalles: List[dict]) -> List[dict]:
    lineas = []
    for item in detalles:
        lineas.append({
            # El código de producto es obligatorio en el UBL. Se usa el id del
            # plato, que es estable; si el plato fue borrado, un marcador para
            # que la boleta siga siendo emitible.
            "codigo": str(item.get("plato_id") or "SIN-COD"),
            "descripcion": item["descripcion"],
            "unidad": "NIU",
            "cantidad": str(item["cantidad"]),
            "precio_unitario": str(precio_sin_igv(item["precio_unitario"])),
        })
    return lineas


def emitir_boleta(
    *,
    cliente_id: str,
    ruc_emisor: str,
    razon_social_emisor: str,
    direccion_emisor: Optional[str],
    serie: str,
    numero_correlativo: int,
    fecha_emision: str,
    detalles: List[dict],
    tipo_documento_comprador: Optional[str] = None,
    numero_documento_comprador: Optional[str] = None,
    nombre_comprador: Optional[str] = None,
) -> SunatCloudResultado:
    """
    Envía el comprobante al micro-servicio, que lo firma y lo manda a SUNAT.

    Distingue tres desenlaces, porque el llamador tiene que reaccionar
    distinto a cada uno:
      - éxito                      → la Factura queda 'enviada_sunat'
      - rechazo de SUNAT           → 'error', NO reintentar igual
      - servicio/red caídos        → SunatCloudError, dejar reintentable
    """
    if not settings.sunat_service_url:
        raise SunatCloudError("SUNAT_SERVICE_URL no está configurado")

    payload = {
        "cliente_id": cliente_id,
        "serie": serie,
        "numero": numero_correlativo,
        "fecha_emision": fecha_emision,
        "moneda": "PEN",
        "tipo_documento": "03",
        "emisor": {
            "tipo_doc": DOC_RUC,
            "numero_doc": ruc_emisor,
            "razon_social": razon_social_emisor,
            "direccion": direccion_emisor or "",
        },
        "receptor": _receptor(
            tipo_documento_comprador, numero_documento_comprador, nombre_comprador
        ),
        "lines": _lineas(detalles),
    }

    url = settings.sunat_service_url.rstrip("/") + "/emitir"
    try:
        resp = httpx.post(
            url,
            json=payload,
            headers={"X-Sunat-Token": settings.sunat_service_token},
            timeout=settings.sunat_service_timeout,
        )
    except httpx.HTTPError as exc:
        raise SunatCloudError(f"No se pudo contactar al servicio de emisión: {exc}") from exc

    if resp.status_code == 412:
        # Falta el certificado o no se pudo abrir: no es un problema de red,
        # pero tampoco un rechazo de SUNAT. Es configuración pendiente.
        detalle = _detalle(resp)
        return SunatCloudResultado(
            exito=False,
            error_codigo=detalle.get("error_codigo", "SIN_CERTIFICADO"),
            error_mensaje=detalle.get("error_mensaje", "Falta el certificado digital."),
            reintentable=False,
        )

    if resp.status_code >= 500:
        raise SunatCloudError(f"El servicio de emisión respondió {resp.status_code}")

    if resp.status_code != 200:
        detalle = _detalle(resp)
        return SunatCloudResultado(
            exito=False,
            error_codigo=detalle.get("error_codigo", "ERROR"),
            error_mensaje=detalle.get("error_mensaje", f"HTTP {resp.status_code}"),
            reintentable=False,
        )

    data = resp.json()
    return SunatCloudResultado(
        exito=bool(data.get("exito")),
        estado=data.get("estado"),
        codigo=data.get("codigo"),
        descripcion=data.get("descripcion"),
        cdr_xml=data.get("cdr_xml"),
        nombre_archivo=data.get("nombre_archivo"),
        error_codigo=data.get("error_codigo"),
        error_mensaje=data.get("error_mensaje"),
        reintentable=data.get("error_codigo") == "TRANSPORTE",
    )


def _detalle(resp: "httpx.Response") -> dict:
    """El servicio manda sus errores como {"detail": {...}} (FastAPI); un
    proxy intermedio puede devolver HTML. Nunca reventar por eso."""
    try:
        body = resp.json()
    except Exception:
        return {}
    detalle = body.get("detail", body)
    return detalle if isinstance(detalle, dict) else {"error_mensaje": str(detalle)}
