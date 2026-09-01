"""
Facturación electrónica SUNAT (boletas) — dos formas de emitir, elegidas
por backend.config.settings.emisor_facturacion:

  "sfs_local" (default, costo S/ 0): escribe .cab/.det en la carpeta que
  vigila el Facturador SUNAT instalado en la PC de la caja (ver
  backend/utils/sfs_export.py). RestoMind NO sabe si SUNAT terminó
  aceptando el comprobante — eso pasa dentro del Facturador, después de
  que este endpoint termina. El estado resultante es 'generado_localmente',
  distinto de 'enviada_sunat' a propósito: no mentir sobre una confirmación
  que este sistema no tiene.

  "facturacion_pe" (de pago, ver backend/utils/facturacion_pe.py): API
  externa que sí confirma en el momento si SUNAT aceptó o rechazó.

Regla central de este módulo, que no debe romperse nunca sea cual sea el
emisor activo: la boleta se arma leyendo lo que el sistema ya registró
como vendido (ComandaPlato de comandas en estado 'cobrado'), nunca de un
array de platos que mande el frontend. Si se aceptara eso último,
cualquiera con el token de un mozo podría pedir una boleta por productos
que nunca se sirvieron.

Flujo (ver backend/services.py:cobrar_mesa):
    1. Mozo cobra la mesa -> POST /mesas/{id}/cobrar (ya existente, sin
       tocar). Devuelve comanda_ids de lo que se acaba de cerrar.
    2. Frontend llama POST /facturas/generar con esos comanda_ids.
    3. Este endpoint arma el detalle desde la BD y despacha al emisor
       configurado — nunca se pierde el intento, incluso si falla.
"""

from datetime import datetime, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.config import settings
from backend.database import get_db
from backend.dependencies import get_cliente_id, get_tz_offset, get_usuario_actual
from backend.models import Cliente, Comanda, Factura, FacturaComanda
from backend.schemas import (
    FacturaDetalleItem,
    FacturaGenerarRequest,
    FacturaListItem,
    FacturaPendienteItem,
    FacturaResponse,
    FacturasPendientesResponse,
    VentaSinBoletaItem,
)
from backend.utils.facturacion_pe import FacturacionPeError, generar_boleta
from backend.utils.security import validar_admin
from backend.utils.sfs_export import SfsExportError, exportar_comprobante

router = APIRouter()

IGV_TASA = 0.18

# Estados que significan "el intento terminó bien" para el emisor que
# corresponda — 'enviada_sunat' (facturacion_pe, confirmado por SUNAT) y
# 'generado_localmente' (sfs_local, depositado para que el Facturador lo
# procese) NO son intercambiables en significado, pero ambos representan
# "no hace falta reintentar".
ESTADOS_OK = {"enviada_sunat", "generado_localmente"}


def _numero_boleta(factura: Factura) -> str:
    return f"{factura.serie}-{factura.numero_correlativo:08d}"


def _factura_to_response(factura: Factura, cliente: Cliente, detalles: list) -> FacturaResponse:
    return FacturaResponse(
        id=factura.id,
        numero_mesa=factura.numero_mesa,
        serie=factura.serie,
        numero_correlativo=factura.numero_correlativo,
        numero_boleta=_numero_boleta(factura),
        subtotal=factura.subtotal,
        igv=factura.igv,
        total=factura.total,
        pdf_url=factura.pdf_url,
        qr_code=factura.qr_code,
        archivo_local=factura.archivo_local,
        estado=factura.estado,
        error_mensaje=factura.error_mensaje,
        creado_en=factura.creado_en,
        fecha_emision_local=factura.fecha_emision_local,
        hora_emision_local=factura.hora_emision_local,
        ruc_emisor=cliente.ruc or "",
        razon_social_emisor=cliente.razon_social or cliente.nombre,
        nombre_emisor=cliente.nombre,
        direccion_emisor=cliente.direccion,
        email_emisor=cliente.email,
        tipo_documento_comprador=factura.tipo_documento_comprador or "0",
        numero_documento_comprador=factura.numero_documento_comprador or "00000000",
        nombre_comprador=factura.nombre_comprador or "CLIENTES VARIOS",
        detalles=[
            FacturaDetalleItem(
                descripcion=item["descripcion"],
                cantidad=item["cantidad"],
                precio_unitario=item["precio_unitario"],
                subtotal=item["subtotal"],
            )
            for item in detalles
        ],
    )


def _detalles_guardados(db: Session, factura: Factura) -> list:
    """Reconstruye el detalle de una Factura ya creada, leyendo las
    comandas vinculadas vía FacturaComanda — usado por /reintentar y por
    GET /facturas/{id}, que no reciben 'detalles' como parámetro porque la
    Factura ya existe de una llamada anterior."""
    comanda_ids = [
        row[0] for row in
        db.query(FacturaComanda.comanda_id).filter(FacturaComanda.factura_id == factura.id).all()
    ]
    comandas = db.query(Comanda).filter(Comanda.id.in_(comanda_ids)).all()
    return _detalles_de(comandas)


def _calcular_montos(total: float) -> tuple:
    """Descompone un total (que ya incluye IGV) en subtotal + IGV.

    Redondea de forma que subtotal + igv == total exactamente (calcula el
    IGV primero y el subtotal por resta) — sumar dos redondeos
    independientes puede descuadrar el total en un céntimo, y SUNAT rechaza
    boletas donde subtotal + igv != total.
    """
    subtotal_sin_redondear = total / (1 + IGV_TASA)
    igv = round(total - subtotal_sin_redondear, 2)
    subtotal = round(total - igv, 2)
    return subtotal, igv


def _emitir_sfs_local(factura: Factura, cliente: Cliente, detalles: list) -> None:
    try:
        resultado = exportar_comprobante(
            ruc_emisor=cliente.ruc,
            razon_social_emisor=cliente.razon_social or cliente.nombre,
            tipo_comprobante=factura.tipo_comprobante,
            serie=factura.serie,
            numero_correlativo=factura.numero_correlativo,
            # Congeladas al crear la Factura (no factura.creado_en, que es
            # UTC) — un reintento horas después no debe correr la fecha de
            # emisión del comprobante. Ver el comentario en models.py:Factura.
            fecha_emision=factura.fecha_emision_local,
            hora_emision=factura.hora_emision_local,
            subtotal=factura.subtotal,
            igv=factura.igv,
            total=factura.total,
            detalles=detalles,
            tipo_documento_comprador=factura.tipo_documento_comprador,
            numero_documento_comprador=factura.numero_documento_comprador,
            nombre_comprador=factura.nombre_comprador,
        )
    except SfsExportError as exc:
        # 'error' (no 'pendiente'): a diferencia de un proveedor HTTP
        # caído, esto casi siempre es una causa local corregible ahora
        # mismo (carpeta mal configurada, sin permisos) — vale la pena
        # que se note como error activo, no como "ya va a resolverse solo".
        factura.estado = "error"
        factura.error_mensaje = str(exc)
        return

    factura.estado = "generado_localmente"
    factura.archivo_local = resultado.archivo_cab
    factura.pdf_url = None  # El Facturador local genera su propio PDF/impresión, fuera de RestoMind
    factura.qr_code = None
    factura.codigo_hash = None
    factura.error_mensaje = None
    factura.enviado_en = datetime.utcnow()


def _emitir_facturacion_pe(factura: Factura, cliente: Cliente, detalles: list) -> None:
    """No relanza FacturacionPeError: la Factura queda en 'pendiente' (ya
    persistida con su número reservado) para que /facturas/{id}/reintentar
    la retome sin volver a consumir un correlativo nuevo.
    """
    try:
        resultado = generar_boleta(
            ruc_emisor=cliente.ruc,
            razon_social_emisor=cliente.razon_social or cliente.nombre,
            serie=factura.serie,
            numero_correlativo=factura.numero_correlativo,
            subtotal=factura.subtotal,
            igv=factura.igv,
            total=factura.total,
            detalles=detalles,
            tipo_documento_comprador=factura.tipo_documento_comprador,
            numero_documento_comprador=factura.numero_documento_comprador,
            nombre_comprador=factura.nombre_comprador,
        )
    except FacturacionPeError as exc:
        factura.estado = "pendiente"
        factura.error_mensaje = str(exc)
        return

    if not resultado.exito:
        factura.estado = "error"
        factura.error_mensaje = resultado.error_mensaje
        return

    factura.estado = "enviada_sunat"
    factura.pdf_url = resultado.pdf_url
    factura.qr_code = resultado.qr_code
    factura.codigo_hash = resultado.codigo_hash
    factura.error_mensaje = None
    factura.enviado_en = datetime.utcnow()


def _emitir(factura: Factura, cliente: Cliente, detalles: list) -> None:
    """Punto único de despacho entre emisores — actualiza la Factura in-place.
    El llamador hace commit/refresh después."""
    if settings.emisor_facturacion == "facturacion_pe":
        _emitir_facturacion_pe(factura, cliente, detalles)
    else:
        _emitir_sfs_local(factura, cliente, detalles)


def _resolver_comprador(documento: Optional[str]) -> tuple:
    """Deriva (tipo_documento, numero_documento, nombre) a partir de lo que
    tipeó el cajero en un único campo — regla pensada para no ralentizar la
    caja en hora punta (cero llamadas a RENIEC/SUNAT para autocompletar
    nombre real):

        vacío       -> "0" (No domiciliado/Varios), "00000000", "CLIENTES VARIOS"
        8 dígitos   -> "1" (DNI),  el valor tal cual, "-"
        11 dígitos  -> "6" (RUC),  el valor tal cual, "-"

    documento ya viene validado (vacío, 8 u 11 dígitos) por
    FacturaGenerarRequest — acá no se vuelve a validar formato.

    Nota sobre el caso RUC: reemplazar la razón social real por "-" es una
    decisión de negocio explícita (agilizar la venta), no una limitación
    técnica — un cliente que da su RUC generalmente lo hace para sustentar
    gasto/crédito fiscal, y un "-" en ese campo le deja un comprobante que
    no le sirve para eso. Si el día de mañana se decide pedir la razón
    social real cuando hay RUC, el cambio es local a este bloque.
    """
    if not documento:
        return "0", "00000000", "CLIENTES VARIOS"
    if len(documento) == 8:
        return "1", documento, "-"
    return "6", documento, "-"  # 11 dígitos: único otro caso que el schema permite


def _detalles_de(comandas: List[Comanda]) -> list:
    detalles = []
    for comanda in comandas:
        for cp in comanda.comanda_platos:
            detalles.append({
                "plato_id": cp.plato_id,
                "descripcion": cp.plato.nombre if cp.plato else "Plato eliminado",
                "cantidad": cp.cantidad,
                "precio_unitario": cp.precio_unitario,
                "subtotal": cp.subtotal,
            })
    return detalles


@router.post("/facturas/generar", response_model=FacturaResponse, status_code=201)
def generar_factura(
    payload: FacturaGenerarRequest,
    db: Session = Depends(get_db),
    cliente_id: str = Depends(get_cliente_id),
    tz_offset: int = Depends(get_tz_offset),
):
    cliente = db.query(Cliente).filter(Cliente.id == cliente_id).first()
    if not cliente:
        raise HTTPException(status_code=404, detail="Restaurante no encontrado")

    if not cliente.ruc:
        raise HTTPException(
            status_code=400,
            detail="Este restaurante todavía no tiene RUC configurado. "
                   "Pídele al dueño del sistema que lo configure antes de emitir boletas.",
        )

    comandas = (
        db.query(Comanda)
        .filter(Comanda.id.in_(payload.comanda_ids), Comanda.cliente_id == cliente_id)
        .all()
    )
    if len(comandas) != len(set(payload.comanda_ids)):
        raise HTTPException(status_code=404, detail="Una o más comandas no existen en este restaurante")

    no_cobradas = [c.id for c in comandas if c.estado != "cobrado"]
    if no_cobradas:
        raise HTTPException(
            status_code=400,
            detail=f"Las comandas {no_cobradas} no están cobradas todavía; cóbralas antes de facturar",
        )

    ya_facturadas = (
        db.query(FacturaComanda.comanda_id)
        .filter(FacturaComanda.comanda_id.in_(payload.comanda_ids))
        .all()
    )
    if ya_facturadas:
        ids_repetidos = [row[0] for row in ya_facturadas]
        raise HTTPException(
            status_code=400,
            detail=f"Las comandas {ids_repetidos} ya tienen una boleta emitida",
        )

    numeros_mesa = {c.numero_mesa for c in comandas}
    if len(numeros_mesa) > 1:
        raise HTTPException(status_code=400, detail="Las comandas seleccionadas son de mesas distintas")

    total = round(sum(c.total_cuenta for c in comandas), 2)
    subtotal, igv = _calcular_montos(total)
    detalles = _detalles_de(comandas)

    # Reserva atómica del correlativo: se incrementa y se lee en la misma
    # transacción de SQLAlchemy antes del commit. El UNIQUE(cliente_id,
    # serie, numero_correlativo) en Factura es la red de seguridad si dos
    # cobros concurrentes llegaran a pisarse este valor.
    cliente.boleta_correlativo_actual += 1
    numero_correlativo = cliente.boleta_correlativo_actual

    # Hora LOCAL del restaurante, no del servidor — mismo criterio que
    # dashboard/compras (ver backend/dependencies.py:get_tz_offset). Se
    # congela en la Factura porque un reintento no debe correr la fecha de
    # emisión del comprobante a "ahora".
    ahora_local = datetime.utcnow() - timedelta(minutes=tz_offset)
    tipo_doc, numero_doc, nombre_comprador = _resolver_comprador(payload.documento_comprador)

    factura = Factura(
        cliente_id=cliente_id,
        numero_mesa=comandas[0].numero_mesa,
        subtotal=subtotal,
        igv=igv,
        total=total,
        serie="B001",
        numero_correlativo=numero_correlativo,
        fecha_emision_local=ahora_local.date().isoformat(),
        hora_emision_local=ahora_local.strftime("%H:%M:%S"),
        tipo_documento_comprador=tipo_doc,
        numero_documento_comprador=numero_doc,
        nombre_comprador=nombre_comprador,
        estado="pendiente",
    )
    db.add(factura)
    db.flush()  # asigna factura.id sin cerrar la transacción

    for comanda in comandas:
        db.add(FacturaComanda(factura_id=factura.id, comanda_id=comanda.id))

    # Confirmar la RESERVA del correlativo ANTES de escribir nada al disco.
    # El orden importa y no es cosmético: si dos cobros concurrentes leyeron
    # el mismo boleta_correlativo_actual, el UNIQUE(cliente_id, serie,
    # numero_correlativo) hace fallar a uno de los dos. Emitiendo antes del
    # commit, ese perdedor ya habría escrito su .cab —pisando el archivo del
    # ganador, que tiene el mismo nombre— y el Facturador terminaría
    # mandando a SUNAT los platos de una venta bajo el número de la otra.
    # Commiteando primero, el perdedor falla sin haber tocado el disco.
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Otro cobro tomó ese número de boleta al mismo tiempo. Reintenta la emisión.",
        )

    _emitir(factura, cliente, detalles)

    db.commit()
    db.refresh(factura)

    if factura.estado not in ESTADOS_OK:
        # La Factura quedó guardada (no se pierde el correlativo ni el
        # intento) pero el cliente HTTP necesita saber que no está lista
        # todavía — el frontend debe leer 'estado' del body en ambos casos.
        raise HTTPException(
            status_code=502,
            detail={
                "mensaje": "La boleta se guardó pero no se pudo generar todavía",
                "factura": _factura_to_response(factura, cliente, detalles).model_dump(mode="json"),
            },
        )

    return _factura_to_response(factura, cliente, detalles)


@router.post("/facturas/{factura_id}/reintentar", response_model=FacturaResponse)
def reintentar_factura(
    factura_id: int,
    db: Session = Depends(get_db),
    cliente_id: str = Depends(get_cliente_id),
):
    factura = db.query(Factura).filter(Factura.id == factura_id, Factura.cliente_id == cliente_id).first()
    if not factura:
        raise HTTPException(status_code=404, detail="Factura no encontrada")

    cliente = db.query(Cliente).filter(Cliente.id == cliente_id).first()
    if not cliente:
        raise HTTPException(status_code=404, detail="Restaurante no encontrado")

    if factura.estado in ESTADOS_OK:
        return _factura_to_response(factura, cliente, _detalles_guardados(db, factura))

    if not cliente.ruc:
        raise HTTPException(status_code=400, detail="Este restaurante no tiene RUC configurado")

    detalles = _detalles_guardados(db, factura)

    _emitir(factura, cliente, detalles)
    db.commit()
    db.refresh(factura)

    if factura.estado not in ESTADOS_OK:
        raise HTTPException(
            status_code=502,
            detail={
                "mensaje": "Sigue sin poder generarse esta boleta",
                "factura": _factura_to_response(factura, cliente, detalles).model_dump(mode="json"),
            },
        )

    return _factura_to_response(factura, cliente, detalles)


@router.get("/facturas/pendientes", response_model=FacturasPendientesResponse)
def listar_pendientes(
    db: Session = Depends(get_db),
    cliente_id: str = Depends(get_cliente_id),
    usuario: str = Depends(get_usuario_actual),
):
    """Todo lo que quedó cobrado pero sin boleta válida — el punto de
    recuperación cuando la emisión falla (Facturador apagado, carpeta mal
    configurada, se cortó la red justo al cobrar).

    OJO CON EL ORDEN: esta ruta debe declararse ANTES que
    GET /facturas/{factura_id}, o FastAPI intenta parsear "pendientes"
    como el int factura_id y responde 422 en vez de entrar acá.

    Dos casos distintos, con arreglos distintos:
      - facturas_con_error: la Factura existe y su correlativo ya está
        reservado -> se reintenta con POST /facturas/{id}/reintentar.
      - ventas_sin_boleta: nunca llegó a crearse la Factura (la petición no
        alcanzó el servidor) -> hay que emitirla de cero con
        POST /facturas/generar sobre esas comandas.
    """
    # Solo la pantalla Admin > Boletas llama a esto, y lo que devuelve
    # (totales por mesa, boletas con error) es la misma clase de dato
    # financiero que el Dashboard — mismo criterio, mismo candado.
    validar_admin(db, usuario, cliente_id)

    facturas_con_error = [
        FacturaPendienteItem(
            id=f.id,
            numero_boleta=_numero_boleta(f),
            numero_mesa=f.numero_mesa,
            total=f.total,
            estado=f.estado,
            error_mensaje=f.error_mensaje,
            creado_en=f.creado_en,
        )
        for f in (
            db.query(Factura)
            .filter(Factura.cliente_id == cliente_id, Factura.estado.notin_(ESTADOS_OK))
            .order_by(Factura.creado_en.desc())
            .all()
        )
    ]

    facturadas = db.query(FacturaComanda.comanda_id).subquery()
    sin_boleta = (
        db.query(Comanda)
        .filter(
            Comanda.cliente_id == cliente_id,
            Comanda.estado == "cobrado",
            Comanda.id.notin_(select(facturadas.c.comanda_id)),
        )
        .order_by(Comanda.actualizado_en.desc())
        .all()
    )

    # Se agrupan por mesa porque así es como se cobran: cobrar_mesa() cierra
    # de una todas las comandas activas de una mesa (ver services.py), así
    # que esas comandas son UNA venta y les corresponde UNA sola boleta.
    por_mesa: dict = {}
    for c in sin_boleta:
        grupo = por_mesa.setdefault(c.numero_mesa, {"comanda_ids": [], "total": 0.0, "creado_en": c.actualizado_en})
        grupo["comanda_ids"].append(c.id)
        grupo["total"] = round(grupo["total"] + c.total_cuenta, 2)

    return FacturasPendientesResponse(
        facturas_con_error=facturas_con_error,
        ventas_sin_boleta=[
            VentaSinBoletaItem(
                numero_mesa=mesa,
                comanda_ids=datos["comanda_ids"],
                total=datos["total"],
                creado_en=datos["creado_en"],
            )
            for mesa, datos in por_mesa.items()
        ],
    )


@router.get("/facturas/{factura_id}", response_model=FacturaResponse)
def obtener_factura(
    factura_id: int,
    db: Session = Depends(get_db),
    cliente_id: str = Depends(get_cliente_id),
    usuario: str = Depends(get_usuario_actual),
):
    """El flujo real de cobro no llama a esto: mozo.js usa directo la
    respuesta de POST /facturas/generar para imprimir. Esta ruta queda para
    consulta administrativa — mismo candado que el resto de lo financiero."""
    validar_admin(db, usuario, cliente_id)

    factura = db.query(Factura).filter(Factura.id == factura_id, Factura.cliente_id == cliente_id).first()
    if not factura:
        raise HTTPException(status_code=404, detail="Factura no encontrada")
    cliente = db.query(Cliente).filter(Cliente.id == cliente_id).first()
    return _factura_to_response(factura, cliente, _detalles_guardados(db, factura))


@router.get("/facturas", response_model=List[FacturaListItem])
def listar_facturas(
    limit: int = 50,
    db: Session = Depends(get_db),
    cliente_id: str = Depends(get_cliente_id),
    usuario: str = Depends(get_usuario_actual),
):
    validar_admin(db, usuario, cliente_id)
    limit = max(1, min(limit, 200))
    facturas = (
        db.query(Factura)
        .filter(Factura.cliente_id == cliente_id)
        .order_by(Factura.creado_en.desc())
        .limit(limit)
        .all()
    )
    return [
        FacturaListItem(
            id=f.id,
            numero_mesa=f.numero_mesa,
            numero_boleta=_numero_boleta(f),
            total=f.total,
            estado=f.estado,
            creado_en=f.creado_en,
        )
        for f in facturas
    ]
