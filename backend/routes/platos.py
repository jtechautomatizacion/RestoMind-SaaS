"""
CU-01: Gestión de la Carta Inteligente
Endpoints para crear, actualizar y listar platos del menú.
"""

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from backend.database import get_db
from backend.dependencies import get_cliente_id
from backend.models import Plato
from backend.schemas import PlatoCreate, PlatoUpdate, PlatoResponse, EstadoUpdate

router = APIRouter()

ESTADOS_PLATO_VALIDOS = ("activo", "inactivo")


@router.get("/platos", response_model=List[PlatoResponse])
def listar_platos(
    categoria: Optional[str] = None,
    incluir_inactivos: bool = False,
    db: Session = Depends(get_db),
    cliente_id: str = Depends(get_cliente_id),
):
    query = db.query(Plato).filter(Plato.cliente_id == cliente_id)
    if not incluir_inactivos:
        query = query.filter(Plato.estado == "activo")
    if categoria:
        query = query.filter(Plato.categoria == categoria)
    return query.order_by(Plato.categoria, Plato.nombre).all()


@router.post("/platos", response_model=PlatoResponse, status_code=201)
def crear_plato(
    payload: PlatoCreate,
    db: Session = Depends(get_db),
    cliente_id: str = Depends(get_cliente_id),
):
    plato = Plato(cliente_id=cliente_id, **payload.model_dump())
    db.add(plato)
    db.commit()
    db.refresh(plato)
    return plato


@router.patch("/platos/{plato_id}", response_model=PlatoResponse)
def editar_plato(
    plato_id: int,
    payload: PlatoUpdate,
    db: Session = Depends(get_db),
    cliente_id: str = Depends(get_cliente_id),
):
    plato = db.query(Plato).filter(Plato.id == plato_id, Plato.cliente_id == cliente_id).first()
    if not plato:
        raise HTTPException(status_code=404, detail="Plato no encontrado")

    datos = payload.model_dump(exclude_unset=True)
    for campo, valor in datos.items():
        setattr(plato, campo, valor)

    db.commit()
    db.refresh(plato)
    return plato


@router.patch("/platos/{plato_id}/estado", response_model=PlatoResponse)
def cambiar_estado_plato(
    plato_id: int,
    payload: EstadoUpdate,
    db: Session = Depends(get_db),
    cliente_id: str = Depends(get_cliente_id),
):
    if payload.estado not in ESTADOS_PLATO_VALIDOS:
        raise HTTPException(status_code=400, detail=f"Estado inválido. Use uno de: {ESTADOS_PLATO_VALIDOS}")

    plato = db.query(Plato).filter(Plato.id == plato_id, Plato.cliente_id == cliente_id).first()
    if not plato:
        raise HTTPException(status_code=404, detail="Plato no encontrado")

    plato.estado = payload.estado
    db.commit()
    db.refresh(plato)
    return plato
