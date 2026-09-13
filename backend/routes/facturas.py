"""
Facturación electrónica SUNAT — 100% en la nube.

El comprobante se firma y se envía a SUNAT desde el servidor, vía el
micro-servicio de sunat-service/ (librería sunat-py). No hace falta ninguna
PC con Windows en el restaurante: un local que trabaja solo con tablets
factura igual.

QUÉ COMPROBANTE SE EMITE — lo decide el servidor, no el frontend
-----------------------------------------------------------------
Según lo que el cajero tipee en un único campo (ver _resolver_comprobante):

    vacío, total < S/ 700   -> Boleta  03 / B001, Público General
    vacío, total >= S/ 700  -> 400: SUNAT exige identificar al comprador
    8 dígitos (DNI)         -> Boleta  03 / B001
    11 dígitos (RUC)        -> FACTURA 01 / F001 si el restaurante puede
                               facturar; si no (Nuevo RUS), BOLETA 03 / B001
                               con el RUC como documento del adquiriente

Cada serie lleva su propio correlativo (ver models.py:Cliente): compartir
uno dejaría huecos en ambas, y SUNAT las exige consecutivas.

Regla central que no debe romperse: el comprobante se arma leyendo lo que
el sistema ya registró como vendido (ComandaPlato de comandas en estado
'cobrado'), nunca de un array de platos que mande el frontend. Si se
aceptara eso último, cualquiera con el token de un mozo podría pedir un
comprobante por productos que nunca se sirvieron.

Flujo:
    1. Mozo cobra la mesa -> POST /mesas/{id}/cobrar. Devuelve comanda_ids.
    2. Frontend llama POST /facturas/generar con esos comanda_ids.
    3. Este endpoint arma el detalle desde la BD y lo manda a emitir —
       nunca se pierde el intento, incluso si falla.
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
from backend.models import Cliente, Comanda, Factura, FacturaComanda, Usuario
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
from backend.utils.sunat_cloud import (
    SunatCloudError,
    diferencia_contra_lo_cobrado as diferencia_redondeo,
    emitir_boleta as emitir_boleta_cloud,
)
from backend.utils.padron import PadronNoDisponible, consultar as consultar_padron
from backend.utils.security import validar_admin

router = APIRouter()

IGV_TASA = 0.18

# Estados que significan "el intento terminó bien".
#
# 'generado_localmente' ya NO se produce (el emisor local se eliminó), pero
# sigue listado a propósito: hay comprobantes REALES emitidos así que
# quedaron con ese estado. Sacarlo de acá los mostraría como pendientes y
# el restaurante intentaría reemitir algo que SUNAT ya tiene.
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
        cajero_nombre=factura.cajero_nombre,
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


def _emitir_sunat_cloud(factura: Factura, cliente: Cliente, detalles: list) -> None:
    """
    Firma y envía el comprobante a SUNAT desde el servidor, vía el
    micro-servicio de sunat-service/ (ver backend/utils/sunat_cloud.py).

    Distingue "no se pudo intentar" de "SUNAT dijo que no", porque se
    resuelven distinto:
      - transporte/servicio caído  -> 'pendiente': el mismo comprobante sirve,
        /facturas/{id}/reintentar lo retoma SIN consumir otro correlativo.
      - rechazo de SUNAT           -> 'error': reintentar igual daría lo mismo,
        hay que corregir algo antes.
    """
    try:
        resultado = emitir_boleta_cloud(
            cliente_id=cliente.id,
            ruc_emisor=cliente.ruc,
            razon_social_emisor=cliente.razon_social or cliente.nombre,
            direccion_emisor=cliente.direccion,
            serie=factura.serie,
            numero_correlativo=factura.numero_correlativo,
            # La fecha congelada al crear la Factura, no "hoy": un reintento
            # al día siguiente NO debe cambiar la fecha de emisión declarada.
            fecha_emision=factura.fecha_emision_local,
            detalles=detalles,
            tipo_documento_comprador=factura.tipo_documento_comprador,
            numero_documento_comprador=factura.numero_documento_comprador,
            nombre_comprador=factura.nombre_comprador,
        )
    except SunatCloudError as exc:
        factura.estado = "pendiente"
        factura.error_mensaje = str(exc)
        return

    if not resultado.exito:
        # Reintentable = el comprobante está bien, falló el camino. Se deja
        # 'pendiente' para que el reintento lo retome con el mismo número.
        factura.estado = "pendiente" if resultado.reintentable else "error"
        factura.error_mensaje = resultado.error_mensaje or resultado.descripcion
        return

    factura.estado = "enviada_sunat"
    factura.cdr_xml = resultado.cdr_xml
    factura.codigo_hash = resultado.codigo
    factura.enviado_en = datetime.utcnow()

    # La boleta salió, pero puede declarar hasta un céntimo distinto de lo
    # cobrado: RestoMind saca el IGV desde el total y SUNAT desde la base, y
    # con ciertos precios las dos cuentas no pueden coincidir (ver
    # sunat_cloud.total_que_declarara_sunat). Queda anotado en la Factura en
    # vez de pasar desapercibido — sin esto, la caja no cuadraría contra los
    # comprobantes al cierre de mes y nadie sabría por qué.
    desvio = diferencia_redondeo(detalles, factura.total)
    factura.error_mensaje = (
        None if desvio == 0
        else f"Aviso: la boleta declara S/ {desvio:+} respecto de lo cobrado (redondeo del IGV)."
    )


def _emitir(factura: Factura, cliente: Cliente, detalles: list) -> None:
    """Punto único de despacho entre emisores — actualiza la Factura in-place.
    El llamador hace commit/refresh después."""
    if settings.emisor_facturacion == "facturacion_pe":
        # Proveedor de pago, ya integrado — se conserva como alternativa
        # para quien prefiera no administrar su propio certificado.
        _emitir_facturacion_pe(factura, cliente, detalles)
    else:
        _emitir_sunat_cloud(factura, cliente, detalles)


# Desde S/ 700, SUNAT exige identificar al comprador en una boleta de venta.
# Por debajo se puede emitir a "Público General" sin documento.
UMBRAL_IDENTIFICAR_COMPRADOR = 700.00


def _resolver_comprobante(
    documento: Optional[str],
    total: float,
    razon_social_manual: Optional[str],
    emite_facturas: bool = False,
) -> tuple:
    """
    Decide QUÉ comprobante corresponde según lo que tipeó el cajero.

    Devuelve (tipo_comprobante, serie, tipo_doc, numero_doc, nombre).

        vacío y total < 700   -> Boleta 03/B001, doc "0"/"00000000", Público General
        vacío y total >= 700  -> 400: SUNAT exige identificar al comprador
        8 dígitos             -> Boleta 03/B001, doc "1" (DNI)
        11 dígitos            -> FACTURA 01/F001, doc "6" (RUC) + razón social real

    El tipo de comprobante lo decide el SERVIDOR y no el frontend, por el
    mismo motivo que el detalle se arma desde la BD: es la regla fiscal, y
    tener dos versiones (una en JS, otra acá) es garantía de que algún día
    divergan.

    Un RUC SIEMPRE produce factura, nunca boleta: quien da su RUC lo hace
    para sustentar gasto o crédito fiscal, y una boleta no le sirve para
    eso. Cambiarle el tipo de comprobante por nuestra cuenta le crea un
    problema comercial al restaurante.
    """
    if not documento:
        if total >= UMBRAL_IDENTIFICAR_COMPRADOR:
            # EL COBRO NO SE TOCA. Esto corre DESPUÉS de /mesas/{id}/cobrar:
            # la plata ya cambió de mano, la mesa ya se liberó y la venta ya
            # está registrada en la caja. Lo único que no se puede emitir es
            # el comprobante, y queda esperando en Admin > Boletas
            # (ventas_sin_boleta) hasta que alguien agregue el documento.
            #
            # NO se crea una Factura con el correlativo reservado, a
            # propósito: si nadie completa el dato, ese número queda
            # consumido y abre un HUECO PERMANENTE en la serie B001 — y SUNAT
            # las exige consecutivas. La recuperación por ventas_sin_boleta
            # da lo mismo sin ese riesgo.
            #
            # El detalle va estructurado (no texto suelto) para que el
            # frontend distinga ESTE caso de cualquier otro fallo de emisión
            # y pueda pedir el documento en el momento, con el cliente
            # todavía enfrente.
            raise HTTPException(
                status_code=400,
                detail={
                    "codigo": "IDENTIFICAR_COMPRADOR",
                    "mensaje": (
                        f"Cobro registrado. Desde S/ {UMBRAL_IDENTIFICAR_COMPRADOR:.0f} "
                        "SUNAT exige identificar al cliente: pedile el DNI (8 dígitos) "
                        "o el RUC (11 dígitos) para emitir el comprobante."
                    ),
                    "total": total,
                    "umbral": UMBRAL_IDENTIFICAR_COMPRADOR,
                },
            )
        return "03", "B001", "0", "00000000", "CLIENTES VARIOS"

    if len(documento) == 8:
        # El nombre del titular de un DNI no se consulta: RENIEC no es una
        # fuente disponible acá y una boleta es válida sin él.
        return "03", "B001", "1", documento, "-"

    # ---- 11 dígitos: RUC ----
    #
    # Solo se convierte en FACTURA si el restaurante puede emitirlas. Un
    # contribuyente del NUEVO RUS tiene PROHIBIDO facturar: emite boletas y
    # tickets, nada más. Para él, un comensal con RUC igual recibe BOLETA,
    # llevando su RUC como documento del adquiriente — el catálogo 06 de
    # SUNAT admite RUC en una boleta.
    #
    # Emitir una factura sin poder hacerlo no es un detalle de formato: es
    # una infracción del emisor, y le da al comprador un crédito fiscal que
    # no corresponde.
    if not emite_facturas:
        # La razón social se busca igual que para una factura: que el
        # comprobante sea boleta no vuelve anónimo al comprador. Si el
        # padrón no la tiene, se emite igual con "-" — a diferencia de la
        # factura, una boleta es válida sin el nombre del adquiriente, así
        # que un padrón sin instalar no puede frenar la venta.
        nombre_boleta = (razon_social_manual or "").strip()
        if not nombre_boleta:
            nombre_boleta = _razon_social_del_padron(documento) or ""
        return "03", "B001", "6", documento, nombre_boleta or "-"

    # Factura. SUNAT no acepta una factura sin razón social, así que hay que
    # conseguirla sí o sí.
    nombre = (razon_social_manual or "").strip()
    if not nombre:
        nombre = _razon_social_del_padron(documento)

    if not nombre:
        raise HTTPException(
            status_code=400,
            detail=(
                f"No encontramos el RUC {documento} en el padrón de SUNAT. "
                "Revisá el número, o escribí la razón social a mano para emitir igual."
            ),
        )

    return "01", "F001", "6", documento, nombre


def _nombre_del_cajero(db: Session, comandas: List[Comanda], cliente_id: str) -> Optional[str]:
    """
    Quién atendió la venta, para el papel que recibe el cliente.

    Sale de Comanda.creado_por —quien tomó el pedido—, no de quien está
    logueado al emitir: son la misma persona en un restaurante que atiende
    solo, pero no cuando el mozo toma la mesa y el admin cobra, y el nombre
    que corresponde en el tique es el de quien atendió.

    creado_por guarda el 'sub' del JWT, que es el email del admin pero el
    código de acceso del staff, así que hay que resolverlo contra las dos
    columnas de Usuario —siempre acotado al cliente_id— igual que en
    movimientos.py y push_notifications.py. Si esa cuenta ya no existe
    (alguien la eliminó), se devuelve None y el tique imprime "-" en vez
    de un código de seis dígitos sin significado.
    """
    subs = [c.creado_por for c in comandas if c.creado_por]
    if not subs:
        return None
    # La primera comanda de la mesa: quien abrió la atención.
    sub = subs[0]
    usuario = db.query(Usuario).filter(
        Usuario.cliente_id == cliente_id,
        (Usuario.email == sub) | (Usuario.celular == sub),
    ).first()
    return usuario.nombre if usuario else None


def _razon_social_del_padron(ruc: str) -> Optional[str]:
    """
    Busca la razón social en la copia local del padrón.

    Que el padrón no esté instalado NO es un error de esta operación: se
    trata igual que "no lo encontré", y el cajero resuelve escribiendo el
    nombre a mano. Así un restaurante que todavía no cargó el padrón de
    1,6 GB puede facturar igual desde el primer día.
    """
    try:
        contribuyente = consultar_padron(ruc, settings.padron_db_path)
    except PadronNoDisponible:
        return None
    except Exception:  # noqa: BLE001 — un fallo del padrón no puede tumbar una venta
        return None
    return contribuyente.nombre if contribuyente else None


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

    # QUÉ comprobante corresponde se decide ANTES de tocar ningún
    # correlativo: si esto rechaza (sin documento por encima de S/ 700, o un
    # RUC sin razón social), no se puede haber consumido un número. Un
    # correlativo gastado por un intento fallido deja un hueco permanente en
    # la serie, y SUNAT exige que sean consecutivas.
    tipo_comprobante, serie, tipo_doc, numero_doc, nombre_comprador = _resolver_comprobante(
        payload.documento_comprador, total, payload.razon_social_manual,
        emite_facturas=bool(cliente.emite_facturas),
    )

    # Reserva atómica del correlativo: se incrementa y se lee en la misma
    # transacción de SQLAlchemy antes del commit. El UNIQUE(cliente_id,
    # serie, numero_correlativo) en Factura es la red de seguridad si dos
    # cobros concurrentes llegaran a pisarse este valor.
    #
    # Cada serie lleva SU PROPIO contador: compartir uno dejaría huecos en
    # ambas (ver models.py:Cliente.factura_correlativo_actual).
    if serie == "F001":
        cliente.factura_correlativo_actual += 1
        numero_correlativo = cliente.factura_correlativo_actual
    else:
        cliente.boleta_correlativo_actual += 1
        numero_correlativo = cliente.boleta_correlativo_actual

    # Hora LOCAL del restaurante, no del servidor — mismo criterio que
    # dashboard/compras (ver backend/dependencies.py:get_tz_offset). Se
    # congela en la Factura porque un reintento no debe correr la fecha de
    # emisión del comprobante a "ahora".
    ahora_local = datetime.utcnow() - timedelta(minutes=tz_offset)

    factura = Factura(
        cliente_id=cliente_id,
        numero_mesa=comandas[0].numero_mesa,
        subtotal=subtotal,
        igv=igv,
        total=total,
        tipo_comprobante=tipo_comprobante,
        serie=serie,
        numero_correlativo=numero_correlativo,
        fecha_emision_local=ahora_local.date().isoformat(),
        hora_emision_local=ahora_local.strftime("%H:%M:%S"),
        tipo_documento_comprador=tipo_doc,
        numero_documento_comprador=numero_doc,
        nombre_comprador=nombre_comprador,
        cajero_nombre=_nombre_del_cajero(db, comandas, cliente_id),
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

    # Un restaurante que no emite desde acá NO tiene ventas "pendientes de
    # boleta": tiene ventas, a secas. Sin este corte, cada cobro se sumaba
    # a una lista de pendientes que crecía para siempre y que nadie iba a
    # resolver nunca — ruido que además esconde un pendiente de verdad el
    # día que sí se active la facturación.
    cliente_actual = db.query(Cliente).filter(Cliente.id == cliente_id).first()
    if not cliente_actual or not cliente_actual.usar_sunat:
        return FacturasPendientesResponse(facturas_con_error=[], ventas_sin_boleta=[])

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
