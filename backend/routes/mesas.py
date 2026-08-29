"""
Soporte: Gestión de Mesas + Cobro de Cuenta.

El cobro de mesa no estaba contemplado en la especificación original,
pero sin él las mesas quedaban 'ocupadas' para siempre y el dinero
nunca se reflejaba en ningún lado. Se agrega aquí como cierre natural
del ciclo: Mozo abre mesa -> Cocina entrega -> Mozo cobra -> Mesa libre.
"""

from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from backend.database import get_db
from backend.dependencies import get_cliente_id
from backend.models import Mesa
from backend.schemas import MesaCreate, MesaResponse, EstadoUpdate, CobroResponse
from backend.services import get_comandas_activas_mesa, cobrar_mesa

router = APIRouter()

ESTADOS_MESA_VALIDOS = ("disponible", "ocupada")


def _to_response(db: Session, cliente_id: str, mesa: Mesa) -> MesaResponse:
    activas = get_comandas_activas_mesa(db, cliente_id, mesa.numero)
    cuenta_actual = round(sum(c.total_cuenta for c in activas), 2)
    return MesaResponse(
        id=mesa.id,
        cliente_id=mesa.cliente_id,
        numero=mesa.numero,
        capacidad=mesa.capacidad,
        ubicacion=mesa.ubicacion,
        estado=mesa.estado,
        creado_en=mesa.creado_en,
        cuenta_actual=cuenta_actual,
    )


@router.get("/mesas", response_model=List[MesaResponse])
def listar_mesas(
    db: Session = Depends(get_db),
    cliente_id: str = Depends(get_cliente_id),
):
    mesas = db.query(Mesa).filter(Mesa.cliente_id == cliente_id).order_by(Mesa.numero).all()
    return [_to_response(db, cliente_id, mesa) for mesa in mesas]


@router.post("/mesas", response_model=MesaResponse, status_code=201)
def crear_mesa(
    payload: MesaCreate,
    db: Session = Depends(get_db),
    cliente_id: str = Depends(get_cliente_id),
):
    existe = db.query(Mesa).filter(Mesa.cliente_id == cliente_id, Mesa.numero == payload.numero).first()
    if existe:
        raise HTTPException(status_code=400, detail=f"La mesa {payload.numero} ya existe")

    mesa = Mesa(cliente_id=cliente_id, **payload.model_dump())
    db.add(mesa)
    db.commit()
    db.refresh(mesa)
    return _to_response(db, cliente_id, mesa)


@router.patch("/mesas/{mesa_id}/estado", response_model=MesaResponse)
def cambiar_estado_mesa(
    mesa_id: int,
    payload: EstadoUpdate,
    db: Session = Depends(get_db),
    cliente_id: str = Depends(get_cliente_id),
):
    if payload.estado not in ESTADOS_MESA_VALIDOS:
        raise HTTPException(status_code=400, detail=f"Estado inválido. Use uno de: {ESTADOS_MESA_VALIDOS}")

    mesa = db.query(Mesa).filter(Mesa.id == mesa_id, Mesa.cliente_id == cliente_id).first()
    if not mesa:
        raise HTTPException(status_code=404, detail="Mesa no encontrada")

    mesa.estado = payload.estado
    db.commit()
    db.refresh(mesa)
    return _to_response(db, cliente_id, mesa)


@router.post("/mesas/{mesa_id}/cobrar", response_model=CobroResponse)
def cobrar(
    mesa_id: int,
    db: Session = Depends(get_db),
    cliente_id: str = Depends(get_cliente_id),
):
    mesa = db.query(Mesa).filter(Mesa.id == mesa_id, Mesa.cliente_id == cliente_id).first()
    if not mesa:
        raise HTTPException(status_code=404, detail="Mesa no encontrada")

    try:
        resultado = cobrar_mesa(db, cliente_id, mesa)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    db.commit()
    return resultado
