"""
Cliente HTTP del proveedor de facturación electrónica (Facturación.pe).

Aislado en su propio módulo — no vive dentro de routes/facturas.py — por
dos razones:
1. Testear el endpoint de facturas no debería requerir pegarle a la red
   real; este módulo es el único punto a mockear.
2. Si el día de mañana se cambia de proveedor (otro que también genere
   XML UBL 2.1 y hable con SUNAT), solo hay que reescribir este archivo,
   no tocar la lógica de negocio en routes/facturas.py.

Este cliente NUNCA lanza excepción por un rechazo de SUNAT/proveedor (RUC
inválido, IGV mal calculado, etc.) — eso es un resultado esperado del
negocio, no un bug, y se devuelve como FacturacionPeResultado con
exito=False. Solo lanza si la llamada de red en sí falla (timeout, DNS,
proveedor caído) — ver FacturacionPeError.
"""

from dataclasses import dataclass
from typing import Optional

import httpx

from backend.config import settings


class FacturacionPeError(Exception):
    """La llamada de red al proveedor falló (timeout, caído, sin credenciales).

    Distinto de un rechazo de SUNAT: esto significa que ni siquiera hubo
    respuesta que interpretar. El llamador debe tratarlo como "reintentable
    más tarde", nunca como "la boleta era inválida".
    """


@dataclass
class FacturacionPeResultado:
    exito: bool
    numero_boleta_proveedor: Optional[str] = None
    pdf_url: Optional[str] = None
    qr_code: Optional[str] = None
    codigo_hash: Optional[str] = None
    error_mensaje: Optional[str] = None


def _construir_payload(
    *,
    ruc_emisor: str,
    razon_social_emisor: str,
    serie: str,
    numero_correlativo: int,
    subtotal: float,
    igv: float,
    total: float,
    detalles: list,
    tipo_documento_comprador: Optional[str],
    numero_documento_comprador: Optional[str],
    nombre_comprador: Optional[str],
) -> dict:
    return {
        "tipo_comprobante": "03",  # Boleta de venta
        "serie": serie,
        "numero": numero_correlativo,
        "ruc_emisor": ruc_emisor,
        "razon_social_emisor": razon_social_emisor,
        "moneda": "PEN",
        # "Público General" es una boleta válida en Perú: sin documento
        # y con "-" como nombre, tal como sale en la pre-cuenta no fiscal.
        "tipo_documento_cliente": tipo_documento_comprador or "0",
        "numero_documento_cliente": numero_documento_comprador or "00000000",
        "nombre_cliente": nombre_comprador or "CLIENTES VARIOS",
        "subtotal": subtotal,
        "igv": igv,
        "total": total,
        "detalles": detalles,
    }


def generar_boleta(
    *,
    ruc_emisor: str,
    razon_social_emisor: str,
    serie: str,
    numero_correlativo: int,
    subtotal: float,
    igv: float,
    total: float,
    detalles: list,
    tipo_documento_comprador: Optional[str] = None,
    numero_documento_comprador: Optional[str] = None,
    nombre_comprador: Optional[str] = None,
) -> FacturacionPeResultado:
    """
    Envía una boleta a Facturación.pe, que arma el XML UBL 2.1, lo firma y
    lo manda por SOAP a SUNAT. Devuelve el resultado ya interpretado.
    """
    if not settings.facturacion_pe_api_key:
        raise FacturacionPeError(
            "SUNAT no está configurado en este servidor (falta FACTURACION_PE_API_KEY)"
        )

    payload = _construir_payload(
        ruc_emisor=ruc_emisor,
        razon_social_emisor=razon_social_emisor,
        serie=serie,
        numero_correlativo=numero_correlativo,
        subtotal=subtotal,
        igv=igv,
        total=total,
        detalles=detalles,
        tipo_documento_comprador=tipo_documento_comprador,
        numero_documento_comprador=numero_documento_comprador,
        nombre_comprador=nombre_comprador,
    )

    try:
        respuesta = httpx.post(
            f"{settings.facturacion_pe_url}/facturas",
            json=payload,
            headers={
                "Authorization": f"Bearer {settings.facturacion_pe_api_key}",
                "Content-Type": "application/json",
            },
            timeout=30.0,
        )
    except httpx.HTTPError as exc:
        raise FacturacionPeError(f"No se pudo contactar a Facturación.pe: {exc}") from exc

    if respuesta.status_code >= 500:
        # Error del lado del proveedor/SUNAT, no del payload — reintentable.
        raise FacturacionPeError(
            f"Facturación.pe respondió {respuesta.status_code}: servicio no disponible"
        )

    data = respuesta.json() if respuesta.content else {}

    if respuesta.status_code != 200:
        # Rechazo de negocio (RUC inválido, datos mal formados, etc.) — no
        # es un fallo de red, es un resultado. No reintentar sin corregir.
        return FacturacionPeResultado(
            exito=False,
            error_mensaje=data.get("mensaje") or respuesta.text or "Rechazado por SUNAT",
        )

    return FacturacionPeResultado(
        exito=True,
        numero_boleta_proveedor=data.get("numero_comprobante"),
        pdf_url=data.get("pdf_url"),
        qr_code=data.get("qr_code"),
        codigo_hash=data.get("hash") or data.get("codigo_hash"),
    )
