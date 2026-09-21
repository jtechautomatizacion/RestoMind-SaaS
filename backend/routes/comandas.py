"""
CU-02 y CU-03: Gestión de Comandas
- CU-02: Registro y Envío de Comandas Express (Mozo)
- CU-03: Monitor de Cocina en Tiempo Real
"""

from collections import OrderedDict
from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy import and_, or_
from sqlalchemy.orm import Session
from backend.database import get_db
from backend.dependencies import get_cliente_id, get_usuario_actual
from backend.models import Comanda, ComandaPlato, Mesa, Plato
from backend.schemas import (
    ComandaCreate,
    ComandaResponse,
    ComandaEstadoUpdate,
    MonitorComandaItem,
    MonitorPlatoItem,
)
from backend.services import comanda_to_response, actualizar_estado_comanda
from backend.utils.push_notifications import notificar_nueva_comanda

router = APIRouter()


@router.get("/comandas", response_model=List[ComandaResponse])
def listar_comandas(
    estado: Optional[str] = None,
    numero_mesa: Optional[int] = None,
    db: Session = Depends(get_db),
    cliente_id: str = Depends(get_cliente_id),
):
    query = db.query(Comanda).filter(Comanda.cliente_id == cliente_id)
    if estado:
        query = query.filter(Comanda.estado == estado)
    if numero_mesa is not None:
        query = query.filter(Comanda.numero_mesa == numero_mesa)

    comandas = query.order_by(Comanda.creado_en.desc()).all()
    return [comanda_to_response(c) for c in comandas]


@router.get("/monitor/cocina", response_model=List[MonitorComandaItem])
def monitor_cocina(
    db: Session = Depends(get_db),
    cliente_id: str = Depends(get_cliente_id),
):
    # Dos cosas distintas tiene que cocinar el local, y llegan por caminos
    # distintos:
    #
    #   - de MESA: siguen en 'cocina' hasta que se marcan entregadas.
    #   - PARA LLEVAR: nacen ya 'cobrado' (se pagan al pedirlos en el
    #     mostrador), así que filtrar por estado las dejaría invisibles y el
    #     pedido no se prepararía nunca. Para esas manda `entregado_en`: están
    #     pendientes hasta que se le pasan al cliente.
    comandas = (
        db.query(Comanda)
        .filter(
            Comanda.cliente_id == cliente_id,
            or_(
                Comanda.estado == "cocina",
                and_(Comanda.tipo_pedido == "llevar", Comanda.entregado_en.is_(None)),
            ),
        )
        .order_by(Comanda.creado_en.asc())
        .all()
    )

    ahora = datetime.utcnow()
    resultado = []
    for c in comandas:
        minutos = max(int((ahora - c.creado_en).total_seconds() // 60), 0)
        resultado.append(MonitorComandaItem(
            id=c.id,
            numero_mesa=c.numero_mesa,
            estado=c.estado,
            creado_en=c.creado_en,
            minutos_transcurridos=minutos,
            platos=[
                MonitorPlatoItem(nombre=cp.plato.nombre if cp.plato else "Plato eliminado", cantidad=cp.cantidad)
                for cp in c.comanda_platos
            ],
        ))
    return resultado


@router.get("/comandas/{comanda_id}", response_model=ComandaResponse)
def detalle_comanda(
    comanda_id: int,
    db: Session = Depends(get_db),
    cliente_id: str = Depends(get_cliente_id),
):
    comanda = db.query(Comanda).filter(Comanda.id == comanda_id, Comanda.cliente_id == cliente_id).first()
    if not comanda:
        raise HTTPException(status_code=404, detail="Comanda no encontrada")
    return comanda_to_response(comanda)


@router.post("/comandas", response_model=ComandaResponse, status_code=201)
def crear_comanda(
    payload: ComandaCreate,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
    cliente_id: str = Depends(get_cliente_id),
    usuario: str = Depends(get_usuario_actual),
):
    # Un pedido para llevar no tiene mesa que buscar ni que ocupar.
    para_llevar = payload.tipo_pedido == "llevar"
    mesa = None
    if not para_llevar:
        mesa = db.query(Mesa).filter(Mesa.cliente_id == cliente_id, Mesa.numero == payload.numero_mesa).first()
        if not mesa:
            raise HTTPException(status_code=404, detail=f"La mesa {payload.numero_mesa} no existe")

    # Defensa contra plato_id duplicado en el payload: se suman cantidades
    # en vez de crear dos filas para el mismo plato (rompería el total).
    cantidades_por_plato: "OrderedDict[int, int]" = OrderedDict()
    for item in payload.platos:
        cantidades_por_plato[item.plato_id] = cantidades_por_plato.get(item.plato_id, 0) + item.cantidad

    plato_ids = list(cantidades_por_plato.keys())
    platos_db = (
        db.query(Plato)
        .filter(Plato.cliente_id == cliente_id, Plato.id.in_(plato_ids), Plato.estado == "activo")
        .all()
    )
    platos_map = {p.id: p for p in platos_db}

    faltantes = [pid for pid in plato_ids if pid not in platos_map]
    if faltantes:
        raise HTTPException(status_code=400, detail=f"Plato(s) no disponibles: {faltantes}")

    total = 0.0
    detalle = []
    for plato_id, cantidad in cantidades_por_plato.items():
        plato = platos_map[plato_id]
        subtotal = round(plato.precio_venta * cantidad, 2)
        total += subtotal
        detalle.append((plato, cantidad, subtotal))

    comanda = Comanda(
        cliente_id=cliente_id,
        numero_mesa=payload.numero_mesa,
        tipo_pedido=payload.tipo_pedido,
        total_cuenta=round(total, 2),
        # PARA LLEVAR NACE COBRADO: se paga en el mostrador al pedirlo, antes
        # de que cocina empiece. No hay mesa que cerrar después.
        #
        # Que el estado final sea el mismo 'cobrado' de siempre es lo que
        # mantiene esto de bajo riesgo: las tres consultas que calculan
        # ingresos (dashboard y caja) filtran por ese estado y NO se tocan.
        # No se redefine qué es una venta.
        #
        # Cocina igual lo ve: el monitor mira `entregado_en`, no `estado`
        # (ver monitor_cocina más arriba).
        estado="cobrado" if para_llevar else "cocina",
        # Solo para llevar: nace cobrado, así que el método de pago se conoce
        # ya mismo. Una comanda de mesa lo recibe recién al cobrarla.
        metodo_pago=payload.metodo_pago if para_llevar else None,
        creado_por=usuario,
    )
    db.add(comanda)
    db.flush()  # asigna comanda.id sin cerrar la transacción

    for plato, cantidad, subtotal in detalle:
        db.add(ComandaPlato(
            comanda_id=comanda.id,
            plato_id=plato.id,
            cantidad=cantidad,
            precio_unitario=plato.precio_venta,
            subtotal=subtotal,
        ))

    if mesa is not None:
        mesa.estado = "ocupada"

    db.commit()
    db.refresh(comanda)

    # En segundo plano: messaging.send_* es una llamada HTTP bloqueante a
    # Google, y hacerla acá le sumaba ese round-trip a cada pedido que toma
    # el mozo. La comanda ya está creada y visible en cocina por el camino
    # normal — el push es un extra que puede tardar sin afectar a nadie.
    background.add_task(notificar_nueva_comanda, cliente_id, payload.numero_mesa, comanda.id)

    return comanda_to_response(comanda)


@router.patch("/comandas/{comanda_id}/estado", response_model=ComandaResponse)
def cambiar_estado_comanda(
    comanda_id: int,
    payload: ComandaEstadoUpdate,
    db: Session = Depends(get_db),
    cliente_id: str = Depends(get_cliente_id),
):
    comanda = db.query(Comanda).filter(Comanda.id == comanda_id, Comanda.cliente_id == cliente_id).first()
    if not comanda:
        raise HTTPException(status_code=404, detail="Comanda no encontrada")

    try:
        actualizar_estado_comanda(db, comanda, payload.estado)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    db.commit()
    db.refresh(comanda)
    return comanda_to_response(comanda)
