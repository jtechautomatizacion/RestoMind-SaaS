"""
Categorías de la carta (Cebiches, Bebidas, Postres, etc.).

No estaba contemplado en el diseño original: la categoría de un plato era
texto libre, así que "Cebiches", "cebiches" y "Cebiche" convivían como tres
categorías distintas en la carta. Se agrega como catálogo propio para que
el admin las defina una vez y el formulario de platos elija de una lista,
no que las reescriba a mano cada vez.
"""

from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from backend.database import get_db
from backend.dependencies import get_cliente_id, get_usuario_actual
from backend.models import Categoria, Plato
from backend.schemas import CategoriaCreate, CategoriaResponse
from backend.utils.security import validar_admin

router = APIRouter()


@router.get("/categorias", response_model=List[CategoriaResponse])
def listar_categorias(
    db: Session = Depends(get_db),
    cliente_id: str = Depends(get_cliente_id),
):
    return db.query(Categoria).filter(Categoria.cliente_id == cliente_id).order_by(Categoria.nombre).all()


@router.post("/categorias", response_model=CategoriaResponse, status_code=201)
def crear_categoria(
    payload: CategoriaCreate,
    db: Session = Depends(get_db),
    cliente_id: str = Depends(get_cliente_id),
    usuario: str = Depends(get_usuario_actual),
):
    validar_admin(db, usuario, cliente_id)

    nombre = payload.nombre.strip()
    existe = db.query(Categoria).filter(Categoria.cliente_id == cliente_id, Categoria.nombre == nombre).first()
    if existe:
        raise HTTPException(status_code=400, detail=f"La categoría '{nombre}' ya existe")

    categoria = Categoria(cliente_id=cliente_id, nombre=nombre, icono=payload.icono)
    db.add(categoria)
    db.commit()
    db.refresh(categoria)
    return categoria


@router.delete("/categorias/{categoria_id}", status_code=204)
def eliminar_categoria(
    categoria_id: int,
    db: Session = Depends(get_db),
    cliente_id: str = Depends(get_cliente_id),
    usuario: str = Depends(get_usuario_actual),
):
    validar_admin(db, usuario, cliente_id)

    categoria = db.query(Categoria).filter(
        Categoria.id == categoria_id, Categoria.cliente_id == cliente_id
    ).first()
    if not categoria:
        raise HTTPException(status_code=404, detail="Categoría no encontrada")

    en_uso = db.query(Plato).filter(
        Plato.cliente_id == cliente_id, Plato.categoria == categoria.nombre
    ).first()
    if en_uso:
        raise HTTPException(
            status_code=400,
            detail="Esta categoría tiene platos asignados. Cámbialos de categoría antes de eliminarla.",
        )

    db.delete(categoria)
    db.commit()
    return None
