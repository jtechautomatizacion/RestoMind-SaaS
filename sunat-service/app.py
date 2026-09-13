"""
Micro-servicio de emisión SUNAT — envuelve la librería `sunat-py`.

POR QUÉ VIVE EN SU PROPIO CONTENEDOR Y NO DENTRO DE RESTOMIND
-------------------------------------------------------------
`sunat-py` fija `cryptography<45`. RestoMind corre hoy con `cryptography
50.0.1`. Instalarlo junto al backend obligaría a retroceder la librería
criptográfica 22 versiones y 6 versiones mayores (mayo 2025) — justo la que
respalda los JWT de la app y firebase-admin. Aislándolo, cada uno usa la
suya y ese retroceso no toca a RestoMind.

El precio de aislarlo es un salto HTTP dentro de la red de Docker, que no
sale a internet: contra los segundos que tarda SUNAT en responder por SOAP,
es ruido.

QUÉ HACE SIN CERTIFICADO
------------------------
Todo menos firmar y enviar. `POST /previsualizar` arma y valida el XML UBL
2.1 completo, que es donde están la mayoría de los errores de formato — así
se puede desarrollar y probar el circuito entero antes de tener el .pfx.
`POST /emitir` sin certificado responde un error explícito (`SIN_CERTIFICADO`),
nunca un 500 críptico.

LOS CERTIFICADOS NUNCA VAN A LA BASE DE DATOS
---------------------------------------------
Viven en un volumen montado, un directorio por restaurante:

    /app/certs/{cliente_id}/certificado.pfx
    /app/certs/{cliente_id}/clave.txt     (la clave del .pfx, sin salto final)

Ese directorio debe ser 0700 y el volumen se monta de solo lectura. Un
certificado digital tributario permite emitir comprobantes a nombre del
restaurante: quien lo roba puede facturar por él.
"""

from __future__ import annotations

import hmac
import logging
import os
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import List, Optional

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

from sunat_py import (
    CertBundle,
    InvoiceInput,
    InvoiceLine,
    Party,
    SunatError,
    ValidationError,
    build_invoice_xml,
    build_zeep_client,
    compute_totals,
    install_log_redactor,
    load_cert_from_pfx,
    pack_invoice,
    send_bill,
    sign_invoice_xml,
)

# Evita que la librería escriba el XML firmado (que lleva el certificado) o
# las credenciales SOL en los logs del contenedor.
install_log_redactor()

logger = logging.getLogger("sunat-service")

CERTS_DIR = Path(os.getenv("SUNAT_CERTS_DIR", "/app/certs"))
SUNAT_MODE = os.getenv("SUNAT_MODE", "beta")  # "beta" | "prod"
SOAP_TIMEOUT = int(os.getenv("SUNAT_SOAP_TIMEOUT", "30"))
SERVICE_TOKEN = os.getenv("SUNAT_SERVICE_TOKEN", "")

app = FastAPI(title="RestoMind · Emisión SUNAT", docs_url=None, redoc_url=None)


# ============ AUTENTICACIÓN ============

def verificar_token(x_sunat_token: str = Header(default="")) -> None:
    """
    Este servicio solo escucha en la red interna de Docker (no se publica
    ningún puerto al host), pero igual exige token: si mañana alguien expone
    el puerto sin querer, o si un contenedor vecino queda comprometido, esto
    es lo único que separa a un atacante de emitir comprobantes a nombre del
    restaurante.
    """
    if not SERVICE_TOKEN:
        raise HTTPException(500, "SUNAT_SERVICE_TOKEN no está configurado en el servicio")
    # compare_digest y no ==: comparar strings corta en el primer byte
    # distinto, y ese tiempo distinto filtra el token de a un carácter.
    if not hmac.compare_digest(x_sunat_token, SERVICE_TOKEN):
        raise HTTPException(401, "Token inválido")


# ============ CONTRATO ============

class LineaEntrada(BaseModel):
    codigo: str
    descripcion: str
    unidad: str = "NIU"  # NIU = unidad (bien). Un plato es un bien, no un servicio.
    cantidad: Decimal
    # SIN IGV. RestoMind guarda los precios de carta CON IGV incluido (como
    # se usa en Perú); la conversión la hace backend/utils/sunat_cloud.py
    # antes de llamar acá, para que este servicio hable el mismo idioma que
    # sunat-py y no haya dos lugares donde se pueda equivocar el impuesto.
    precio_unitario: Decimal


class PartyEntrada(BaseModel):
    tipo_doc: str
    numero_doc: str
    razon_social: str
    direccion: str = ""
    ubigeo: str = "0000"


class EmitirRequest(BaseModel):
    cliente_id: str = Field(..., min_length=1)
    serie: str
    numero: int
    fecha_emision: date
    moneda: str = "PEN"
    tipo_documento: str = "03"  # 03 = boleta, 01 = factura
    emisor: PartyEntrada
    receptor: PartyEntrada
    lines: List[LineaEntrada] = Field(..., min_length=1)


class EmitirRespuesta(BaseModel):
    exito: bool
    estado: Optional[str] = None       # accepted | accepted_with_obs | rejected
    codigo: Optional[str] = None       # código de respuesta de SUNAT
    descripcion: Optional[str] = None
    cdr_xml: Optional[str] = None
    nombre_archivo: Optional[str] = None
    error_codigo: Optional[str] = None
    error_mensaje: Optional[str] = None


# ============ ARMADO ============

def _a_party(p: PartyEntrada) -> Party:
    return Party(
        tipo_doc=p.tipo_doc,
        numero_doc=p.numero_doc,
        razon_social=p.razon_social,
        direccion=p.direccion,
        ubigeo=p.ubigeo,
    )


def _a_invoice(req: EmitirRequest) -> InvoiceInput:
    return InvoiceInput(
        serie=req.serie,
        numero=req.numero,
        fecha_emision=req.fecha_emision,
        moneda=req.moneda,
        tipo_documento=req.tipo_documento,
        emisor=_a_party(req.emisor),
        receptor=_a_party(req.receptor),
        lines=[
            InvoiceLine(
                codigo=l.codigo,
                descripcion=l.descripcion,
                unidad=l.unidad,
                cantidad=l.cantidad,
                precio_unitario=l.precio_unitario,
            )
            for l in req.lines
        ],
    )


def _nombre_archivo(req: EmitirRequest) -> str:
    """
    RUC-TIPO-SERIE-CORRELATIVO, con el correlativo TAL CUAL, sin rellenar
    con ceros.

    El relleno a 8 dígitos parecía lo correcto y rompía TODAS las emisiones
    con el error 1036 de SUNAT:

        "Número de documento en el nombre del archivo no coincide con el
         consignado en el contenido del XML
         (nodo: Invoice/cbc:ID valor: B001-28)"

    SUNAT compara el nombre del archivo contra el `cbc:ID` del XML y exige
    que sean idénticos. La plantilla de sunat-py escribe
    `<cbc:ID>{{ serie }}-{{ numero }}</cbc:ID>` —sin relleno— así que un
    archivo llamado `...-B001-00000028` contra un XML que dice `B001-28`
    nunca podía coincidir.

    El número lo manda el XML, no este nombre: si algún día la plantilla
    cambiara el formato, esto tiene que seguirla.
    """
    return f"{req.emisor.numero_doc}-{req.tipo_documento}-{req.serie}-{req.numero}"


def _dir_cliente(cliente_id: str) -> Path:
    """
    El cliente_id llega por HTTP, así que se valida contra path traversal
    antes de construir una ruta con él: un "../" permitiría leer archivos
    fuera del volumen de certificados.
    """
    if not cliente_id or "/" in cliente_id or "\\" in cliente_id or ".." in cliente_id:
        raise HTTPException(400, "cliente_id inválido")
    return CERTS_DIR / cliente_id


def _cargar_credenciales_sol(cliente_id: str) -> Optional[tuple[str, str]]:
    """
    Usuario y clave SOL del restaurante, leídos del MISMO volumen que el
    certificado — nunca de la base de datos de RestoMind ni del cuerpo del
    request.

    Es deliberado: así el backend jamás tiene en memoria (ni en su BD, ni en
    un backup, ni en un log de request) las credenciales con las que se
    declara ante SUNAT. El único proceso que las ve es este, que ya necesita
    el certificado de todos modos.

    Formato de sol.txt — dos líneas:
        MIUSUARIO
        miclave
    """
    ruta = _dir_cliente(cliente_id) / "sol.txt"
    if not ruta.exists():
        return None
    lineas = [l.strip() for l in ruta.read_text(encoding="utf-8").splitlines() if l.strip()]
    if len(lineas) < 2:
        return None
    return lineas[0], lineas[1]


def _cargar_certificado(cliente_id: str) -> CertBundle:
    """Un certificado por restaurante."""
    base = _dir_cliente(cliente_id)
    pfx = base / "certificado.pfx"
    clave = base / "clave.txt"

    if not pfx.exists():
        raise HTTPException(
            status_code=412,
            detail={
                "error_codigo": "SIN_CERTIFICADO",
                "error_mensaje": (
                    "Este restaurante todavía no tiene cargado su certificado "
                    "digital de SUNAT. Sin él no se pueden emitir comprobantes."
                ),
            },
        )

    password = clave.read_text(encoding="utf-8").strip() if clave.exists() else None
    try:
        return load_cert_from_pfx(pfx.read_bytes(), password)
    except Exception as exc:
        # Sin el texto de la excepción: puede traer la clave del .pfx.
        logger.error("No se pudo abrir el certificado de %s (%s)", cliente_id, type(exc).__name__)
        raise HTTPException(
            status_code=412,
            detail={
                "error_codigo": "CERTIFICADO_INVALIDO",
                "error_mensaje": "El certificado no se pudo abrir. Revisa que la clave sea la correcta y que no esté vencido.",
            },
        )


# ============ RUTAS ============

@app.get("/health")
def health() -> dict:
    """No exige token: lo consulta el healthcheck de Docker, y no revela nada
    sensible — solo si el proceso está vivo y a qué ambiente apunta."""
    return {
        "ok": True,
        "modo": SUNAT_MODE,
        "certs_dir_montado": CERTS_DIR.exists(),
    }


@app.post("/previsualizar", dependencies=[Depends(verificar_token)])
def previsualizar(req: EmitirRequest) -> dict:
    """
    Arma y valida el XML SIN firmarlo ni enviarlo. No necesita certificado.

    Es lo que permite probar la integración completa antes de tener el .pfx:
    la mayoría de los rechazos de SUNAT son de formato o de montos, y todos
    se ven acá.
    """
    try:
        inv = _a_invoice(req)
        xml = build_invoice_xml(inv)
        totales = compute_totals(inv.lines)
    except ValidationError as exc:
        raise HTTPException(422, {"error_codigo": "VALIDACION", "error_mensaje": str(exc)})

    return {
        "nombre_archivo": _nombre_archivo(req),
        "subtotal": str(totales.subtotal),
        "igv": str(totales.igv),
        "total": str(totales.total),
        "xml_bytes": len(xml.encode("utf-8")),
        "xml": xml,
    }


@app.post("/emitir", response_model=EmitirRespuesta, dependencies=[Depends(verificar_token)])
def emitir(req: EmitirRequest) -> EmitirRespuesta:
    """
    Circuito completo: XML → firma → zip → SOAP a SUNAT → CDR.

    Nunca lanza un 500 con el detalle crudo hacia RestoMind: cada modo de
    falla se traduce a un `error_codigo` estable, para que el backend pueda
    decidir si reintentar (problema de red) o no (rechazo de SUNAT) sin
    tener que interpretar un texto libre.
    """
    bundle = _cargar_certificado(req.cliente_id)

    sol = _cargar_credenciales_sol(req.cliente_id)
    if sol is None:
        return EmitirRespuesta(
            exito=False,
            error_codigo="SIN_CREDENCIALES_SOL",
            error_mensaje=(
                "Falta el usuario y la clave SOL del restaurante "
                "(archivo sol.txt junto al certificado)."
            ),
        )
    sol_usuario, sol_clave = sol

    try:
        inv = _a_invoice(req)
        xml = build_invoice_xml(inv)
    except ValidationError as exc:
        return EmitirRespuesta(exito=False, error_codigo="VALIDACION", error_mensaje=str(exc))

    nombre = _nombre_archivo(req)

    try:
        firmado = sign_invoice_xml(xml, bundle)
        zip_bytes = pack_invoice(firmado, nombre)
    except Exception as exc:
        logger.error("Fallo al firmar %s (%s)", nombre, type(exc).__name__)
        return EmitirRespuesta(
            exito=False,
            error_codigo="FIRMA",
            error_mensaje="No se pudo firmar el comprobante con el certificado.",
        )

    try:
        client = build_zeep_client(
            mode=SUNAT_MODE,
            ruc=req.emisor.numero_doc,
            username=sol_usuario,
            password=sol_clave,
            timeout=SOAP_TIMEOUT,
        )
        resultado = send_bill(client, zip_bytes, f"{nombre}.zip")
    except SunatError as exc:
        # SUNAT contestó y rechazó: reintentar el mismo contenido no cambia
        # nada, hay que corregir el comprobante.
        return EmitirRespuesta(
            exito=False,
            error_codigo="RECHAZO_SUNAT",
            error_mensaje=str(exc),
            nombre_archivo=nombre,
        )
    except Exception as exc:
        # Red, timeout, SUNAT caído: el comprobante está bien, conviene
        # reintentarlo más tarde tal cual.
        logger.warning("Error de transporte enviando %s (%s)", nombre, type(exc).__name__)
        return EmitirRespuesta(
            exito=False,
            error_codigo="TRANSPORTE",
            error_mensaje="No se pudo contactar a SUNAT. Se puede reintentar.",
            nombre_archivo=nombre,
        )

    cdr_texto = None
    if getattr(resultado, "cdr_xml", None):
        cdr_texto = resultado.cdr_xml.decode("utf-8", errors="replace")

    return EmitirRespuesta(
        # accepted_with_obs es ACEPTADA: SUNAT la registró y anotó una
        # observación. Tratarla como fallo dejaría al restaurante
        # reintentando un comprobante que ya está aceptado, y el reintento
        # sí sería rechazado por duplicado.
        exito=resultado.status in ("accepted", "accepted_with_obs"),
        estado=resultado.status,
        codigo=resultado.code,
        descripcion=resultado.description,
        cdr_xml=cdr_texto,
        nombre_archivo=nombre,
    )
