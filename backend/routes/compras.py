"""
CU-04: Control de Compras y Caja Chica
Endpoints para registrar gastos diarios.
"""

from datetime import date
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from backend.database import get_db
from backend.dependencies import get_cliente_id, get_usuario_actual
from backend.models import Compra
from backend.schemas import CompraCreate, CompraUpdate, CompraResponse, EstadoUpdate

router = APIRouter()

ESTADOS_COMPRA_VALIDOS = ("registrado", "cancelado")


def _validar_fecha_no_futura(fecha_str: str) -> None:
    try:
        fecha = date.fromisoformat(fecha_str)
    except ValueError:
        raise HTTPException(status_code=400, detail="Fecha inválida, use formato YYYY-MM-DD")
    if fecha > date.today():
        raise HTTPException(status_code=400, detail="La fecha no puede ser futura")


@router.get("/compras", response_model=List[CompraResponse])
def listar_compras(
    fecha: Optional[str] = None,
    categoria: Optional[str] = None,
    db: Session = Depends(get_db),
    cliente_id: str = Depends(get_cliente_id),
):
    query = db.query(Compra).filter(Compra.cliente_id == cliente_id)
    if fecha:
        query = query.filter(Compra.fecha == fecha)
    if categoria:
        query = query.filter(Compra.categoria == categoria)
    return query.order_by(Compra.fecha.desc(), Compra.creado_en.desc()).all()


@router.post("/compras", response_model=CompraResponse, status_code=201)
def crear_compra(
    payload: CompraCreate,
    db: Session = Depends(get_db),
    cliente_id: str = Depends(get_cliente_id),
    usuario: str = Depends(get_usuario_actual),
):
    _validar_fecha_no_futura(payload.fecha)

    compra = Compra(cliente_id=cliente_id, creado_por=usuario, **payload.model_dump())
    db.add(compra)
    db.commit()
    db.refresh(compra)
    return compra


@router.patch("/compras/{compra_id}", response_model=CompraResponse)
def editar_compra(
    compra_id: int,
    payload: CompraUpdate,
    db: Session = Depends(get_db),
    cliente_id: str = Depends(get_cliente_id),
):
    compra = db.query(Compra).filter(Compra.id == compra_id, Compra.cliente_id == cliente_id).first()
    if not compra:
        raise HTTPException(status_code=404, detail="Gasto no encontrado")

    if compra.fecha != date.today().isoformat():
        raise HTTPException(status_code=403, detail="Solo se pueden editar gastos del día de hoy")

    datos = payload.model_dump(exclude_unset=True)
    if "fecha" in datos and datos["fecha"]:
        _validar_fecha_no_futura(datos["fecha"])

    for campo, valor in datos.items():
        setattr(compra, campo, valor)

    db.commit()
    db.refresh(compra)
    return compra


@router.patch("/compras/{compra_id}/estado", response_model=CompraResponse)
def cambiar_estado_compra(
    compra_id: int,
    payload: EstadoUpdate,
    db: Session = Depends(get_db),
    cliente_id: str = Depends(get_cliente_id),
):
    if payload.estado not in ESTADOS_COMPRA_VALIDOS:
        raise HTTPException(status_code=400, detail=f"Estado inválido. Use uno de: {ESTADOS_COMPRA_VALIDOS}")

    compra = db.query(Compra).filter(Compra.id == compra_id, Compra.cliente_id == cliente_id).first()
    if not compra:
        raise HTTPException(status_code=404, detail="Gasto no encontrado")

    compra.estado = payload.estado
    db.commit()
    db.refresh(compra)
    return compra
