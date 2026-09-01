"""
Entradas y salidas de stock: el extracto que explica Insumo.cantidad_actual.

Manual a propósito, no derivado de las comandas. Descontar automáticamente
según lo que se vende exigiría una receta por plato (400g de pescado por
ceviche), y ese número es teórico: en una cocina real hay mermas, porciones
que salen más generosas y platos que se rehacen. El stock que sirve es el
que el admin cuenta, y esta tabla registra por qué cambió.

Escritura admin-only (mismo criterio que Insumo); lectura abierta a
cualquier rol autenticado, para que en cocina se pueda mirar el historial
sin poder tocarlo.
"""

from datetime import date, datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.dependencies import get_cliente_id, get_usuario_actual
from backend.models import Insumo, MovimientoInsumo, Usuario
from backend.routes.insumos import _buscar_o_404, _estado
from backend.schemas import MovimientoCreate, MovimientoResponse
from backend.utils.auditoria import registrar_evento
from backend.utils.security import validar_admin

router = APIRouter()

# Nombre de la razón que pone el sistema al deshacer un movimiento. No está
# en RAZONES_VALIDAS: el admin no puede elegirla al crear, solo se genera acá.
RAZON_REVERSION = "reversion"


def _resolver_usuario(db: Session, sub: str, cliente_id: str) -> Optional[Usuario]:
    """
    El 'sub' del JWT es el email para admin pero el código de acceso para el
    staff, así que hay que probar contra las dos columnas — siempre acotado
    al cliente_id del token (ver la lección de push_subscriptions en CLAUDE.md).
    """
    return db.query(Usuario).filter(
        Usuario.cliente_id == cliente_id,
        (Usuario.email == sub) | (Usuario.celular == sub),
    ).first()


def _serializar(mov: MovimientoInsumo) -> dict:
    return {
        "id": mov.id,
        "insumo_id": mov.insumo_id,
        "tipo": mov.tipo,
        "cantidad": mov.cantidad,
        "razon": mov.razon,
        "saldo_despues": mov.saldo_despues,
        "fecha": mov.fecha,
        "usuario_nombre": mov.usuario_nombre,
        "creado_en": mov.creado_en,
        "revertido": mov.revertido,
    }


def _aplicar(insumo: Insumo, tipo: str, cantidad: float) -> float:
    """
    Devuelve el saldo que quedaría, o lanza 400 si la salida no alcanza.

    Se rechaza el stock negativo en vez de dejarlo pasar porque un negativo
    no significa nada físicamente —no hay -2kg de pescado en la cámara— y
    convierte el semáforo en ruido: todo insumo en negativo queda 'critico'
    para siempre hasta que alguien lo note.
    """
    delta = cantidad if tipo == "entrada" else -cantidad
    saldo = round(insumo.cantidad_actual + delta, 4)
    if saldo < 0:
        raise HTTPException(
            status_code=400,
            detail=(
                f"No hay suficiente stock: quedan {_fmt(insumo.cantidad_actual)} "
                f"{insumo.unidad} y quieres sacar {_fmt(cantidad)}"
            ),
        )
    return saldo


def _fmt(n: float) -> str:
    """20.0 se lee '20'; 0.5 sigue siendo '0.5'."""
    return str(int(n)) if float(n).is_integer() else str(round(n, 2))


def _alertar_si_cruza_umbral(
    db: Session, cliente_id: str, insumo: Insumo, estado_anterior: str
) -> None:
    """
    Registra la alerta solo al CRUZAR el umbral, no en cada movimiento por
    debajo de él: avisando siempre, sacar 5 veces del mismo insumo bajo
    generaría 5 alertas idénticas y el admin dejaría de mirarlas.

    Se llama DESPUÉS del commit del movimiento: registrar_evento hace su
    propio commit, así que invocarlo antes confirmaría a medias los cambios
    de stock todavía pendientes. Nunca propaga errores (registrar_evento ya
    los traga): un fallo del registro no puede deshacer un movimiento real.
    """
    estado_nuevo = _estado(insumo.cantidad_actual, insumo.cantidad_minima)
    if estado_nuevo == estado_anterior or estado_nuevo not in ("bajo", "critico"):
        return
    registrar_evento(
        db=db,
        actor="sistema",
        accion="alerta_insumo",
        entidad="insumo",
        entidad_id=str(insumo.id),
        cliente_id=cliente_id,
        detalle=(
            f"{insumo.nombre} pasó a {estado_nuevo}: quedan "
            f"{_fmt(insumo.cantidad_actual)} {insumo.unidad} "
            f"(mínimo {_fmt(insumo.cantidad_minima)})"
        ),
    )


@router.get("/insumos/{insumo_id}/movimientos", response_model=List[MovimientoResponse])
def listar_movimientos(
    insumo_id: int,
    limite: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    cliente_id: str = Depends(get_cliente_id),
):
    # Valida de paso que el insumo sea de este cliente: sin esto, un id de
    # otro restaurante devolvería una lista vacía (200) en vez de 404,
    # confirmando que el insumo no existe... o que no es tuyo.
    _buscar_o_404(db, insumo_id, cliente_id)

    movimientos = (
        db.query(MovimientoInsumo)
        .filter(
            MovimientoInsumo.cliente_id == cliente_id,
            MovimientoInsumo.insumo_id == insumo_id,
        )
        .order_by(MovimientoInsumo.fecha.desc(), MovimientoInsumo.id.desc())
        .offset(offset)
        .limit(limite)
        .all()
    )
    return [_serializar(m) for m in movimientos]


@router.post("/insumos/{insumo_id}/movimientos", response_model=MovimientoResponse, status_code=201)
def crear_movimiento(
    insumo_id: int,
    payload: MovimientoCreate,
    db: Session = Depends(get_db),
    cliente_id: str = Depends(get_cliente_id),
    usuario: str = Depends(get_usuario_actual),
):
    validar_admin(db, usuario, cliente_id)
    insumo = _buscar_o_404(db, insumo_id, cliente_id)

    estado_anterior = _estado(insumo.cantidad_actual, insumo.cantidad_minima)
    saldo = _aplicar(insumo, payload.tipo, payload.cantidad)

    autor = _resolver_usuario(db, usuario, cliente_id)
    fecha = payload.fecha or date.today()

    mov = MovimientoInsumo(
        cliente_id=cliente_id,
        insumo_id=insumo.id,
        tipo=payload.tipo,
        cantidad=payload.cantidad,
        razon=payload.razon,
        saldo_despues=saldo,
        fecha=datetime.combine(fecha, datetime.min.time()),
        usuario_id=autor.id if autor else None,
        usuario_nombre=autor.nombre if autor else usuario,
    )
    # El saldo del insumo y su movimiento se guardan en el mismo commit: si
    # se separaran, un fallo entre ambos dejaría el stock movido sin nada
    # que lo explique (o al revés).
    insumo.cantidad_actual = saldo
    db.add(mov)
    db.commit()
    db.refresh(mov)

    signo = "+" if mov.tipo == "entrada" else "-"
    registrar_evento(
        db=db,
        actor=usuario,
        accion="movimiento_insumo",
        entidad="insumo",
        entidad_id=str(insumo.id),
        cliente_id=cliente_id,
        detalle=(
            f"{insumo.nombre}: {signo}{_fmt(mov.cantidad)} {insumo.unidad} "
            f"({mov.razon}) → {_fmt(mov.saldo_despues)} {insumo.unidad}"
        ),
    )
    _alertar_si_cruza_umbral(db, cliente_id, insumo, estado_anterior)
    return _serializar(mov)


@router.delete("/insumos/{insumo_id}/movimientos/{movimiento_id}", response_model=MovimientoResponse)
def revertir_movimiento(
    insumo_id: int,
    movimiento_id: int,
    db: Session = Depends(get_db),
    cliente_id: str = Depends(get_cliente_id),
    usuario: str = Depends(get_usuario_actual),
):
    """
    Deshace un movimiento sin borrarlo: deja el original y agrega uno
    inverso que lo referencia.

    Borrar la fila haría desaparecer justamente lo que hay que auditar —el
    error y quién lo cometió— y dejaría el historial mostrando un ajuste
    suelto que no explica nada. Un asiento contable tampoco se borra: se
    contra-asienta.
    """
    validar_admin(db, usuario, cliente_id)
    insumo = _buscar_o_404(db, insumo_id, cliente_id)

    original = db.query(MovimientoInsumo).filter(
        MovimientoInsumo.id == movimiento_id,
        MovimientoInsumo.insumo_id == insumo_id,
        MovimientoInsumo.cliente_id == cliente_id,
    ).first()
    if not original:
        raise HTTPException(status_code=404, detail="Movimiento no encontrado")

    # Sin esta guarda, dos clicks al botón de deshacer descuentan el doble y
    # dejan el stock peor que el error que se quería corregir.
    if original.revertido:
        raise HTTPException(status_code=400, detail="Este movimiento ya fue revertido")
    if original.razon == RAZON_REVERSION:
        raise HTTPException(status_code=400, detail="No se puede revertir una reversión")

    tipo_inverso = "salida" if original.tipo == "entrada" else "entrada"
    estado_anterior = _estado(insumo.cantidad_actual, insumo.cantidad_minima)
    # Puede fallar con 400: deshacer una entrada de 10kg cuando ya solo
    # quedan 3 dejaría el stock en negativo. El admin tiene que ajustar a
    # mano en ese caso, porque el resto ya se consumió de verdad.
    saldo = _aplicar(insumo, tipo_inverso, original.cantidad)

    autor = _resolver_usuario(db, usuario, cliente_id)
    inverso = MovimientoInsumo(
        cliente_id=cliente_id,
        insumo_id=insumo.id,
        tipo=tipo_inverso,
        cantidad=original.cantidad,
        razon=RAZON_REVERSION,
        saldo_despues=saldo,
        fecha=datetime.combine(date.today(), datetime.min.time()),
        usuario_id=autor.id if autor else None,
        usuario_nombre=autor.nombre if autor else usuario,
        revierte_a_id=original.id,
    )
    original.revertido = True
    insumo.cantidad_actual = saldo
    db.add(inverso)
    db.commit()
    db.refresh(inverso)

    registrar_evento(
        db=db,
        actor=usuario,
        accion="revertir_movimiento_insumo",
        entidad="movimiento_insumo",
        entidad_id=str(original.id),
        cliente_id=cliente_id,
        detalle=(
            f"{insumo.nombre}: se deshizo {original.tipo} de "
            f"{_fmt(original.cantidad)} {insumo.unidad} → {_fmt(saldo)} {insumo.unidad}"
        ),
    )
    # Deshacer una entrada también puede dejar el stock bajo el mínimo.
    _alertar_si_cruza_umbral(db, cliente_id, insumo, estado_anterior)
    return _serializar(inverso)
