"""
Inventario básico: stock de insumos del almacén (pescado, limón, ají...).

Deliberadamente DESACOPLADO de Compras: registrar un gasto no mueve el
stock y mover el stock no registra un gasto. Ver el docstring del modelo
Insumo (backend/models.py) para el porqué.

Admin-only en escritura, igual que Carta y Gastos: el stock del almacén es
información de gestión, no algo que un mozo deba poder cambiar desde su
celular a mitad de un turno.
"""

from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from backend.database import get_db
from backend.dependencies import get_cliente_id, get_usuario_actual
from backend.models import Insumo
from backend.schemas import InsumoCreate, InsumoUpdate, InsumoResponse
from backend.utils.security import validar_admin

router = APIRouter()


def _estado(cantidad_actual: float, cantidad_minima: float) -> str:
    """
    Semáforo del stock. El umbral crítico es la MITAD del mínimo (no el
    mínimo mismo) para que queden dos avisos distintos: "bajo" da tiempo a
    incluirlo en la próxima compra, "crítico" significa que puede faltar
    hoy. Con un solo umbral, el admin ve la misma alerta cuando le queda
    justo lo del día que cuando ya no le alcanza para el almuerzo.
    """
    if cantidad_actual <= cantidad_minima * 0.5:
        return "critico"
    if cantidad_actual < cantidad_minima:
        return "bajo"
    return "ok"


def _serializar(insumo: Insumo) -> dict:
    return {
        "id": insumo.id,
        "cliente_id": insumo.cliente_id,
        "nombre": insumo.nombre,
        "unidad": insumo.unidad,
        "cantidad_actual": insumo.cantidad_actual,
        "cantidad_minima": insumo.cantidad_minima,
        "estado": _estado(insumo.cantidad_actual, insumo.cantidad_minima),
        "creado_en": insumo.creado_en,
    }


def _buscar_o_404(db: Session, insumo_id: int, cliente_id: str) -> Insumo:
    insumo = db.query(Insumo).filter(
        Insumo.id == insumo_id,
        Insumo.cliente_id == cliente_id,
    ).first()
    if not insumo:
        raise HTTPException(status_code=404, detail="Insumo no encontrado")
    return insumo


@router.get("/insumos", response_model=List[InsumoResponse])
def listar_insumos(
    db: Session = Depends(get_db),
    cliente_id: str = Depends(get_cliente_id),
):
    # Lectura abierta a propósito (a diferencia de las escrituras de abajo,
    # que sí son admin-only): saber qué hay en stock le sirve a la cocina
    # durante el turno. Ver test_insumos_requieren_rol_admin.
    insumos = db.query(Insumo).filter(Insumo.cliente_id == cliente_id).order_by(Insumo.nombre).all()
    return [_serializar(i) for i in insumos]


@router.post("/insumos", response_model=InsumoResponse, status_code=201)
def crear_insumo(
    payload: InsumoCreate,
    db: Session = Depends(get_db),
    cliente_id: str = Depends(get_cliente_id),
    usuario: str = Depends(get_usuario_actual),
):
    validar_admin(db, usuario, cliente_id)

    nombre = payload.nombre.strip()
    existe = db.query(Insumo).filter(
        Insumo.cliente_id == cliente_id,
        Insumo.nombre == nombre,
    ).first()
    if existe:
        raise HTTPException(status_code=400, detail=f"El insumo '{nombre}' ya está registrado")

    insumo = Insumo(
        cliente_id=cliente_id,
        nombre=nombre,
        unidad=payload.unidad,
        cantidad_actual=payload.cantidad_actual,
        cantidad_minima=payload.cantidad_minima,
    )
    db.add(insumo)
    db.commit()
    db.refresh(insumo)
    return _serializar(insumo)


@router.patch("/insumos/{insumo_id}", response_model=InsumoResponse)
def editar_insumo(
    insumo_id: int,
    payload: InsumoUpdate,
    db: Session = Depends(get_db),
    cliente_id: str = Depends(get_cliente_id),
    usuario: str = Depends(get_usuario_actual),
):
    validar_admin(db, usuario, cliente_id)
    insumo = _buscar_o_404(db, insumo_id, cliente_id)

    datos = payload.model_dump(exclude_unset=True)

    if "nombre" in datos and datos["nombre"]:
        nombre = datos["nombre"].strip()
        duplicado = db.query(Insumo).filter(
            Insumo.cliente_id == cliente_id,
            Insumo.nombre == nombre,
            Insumo.id != insumo_id,
        ).first()
        if duplicado:
            raise HTTPException(status_code=400, detail=f"El insumo '{nombre}' ya está registrado")
        datos["nombre"] = nombre

    for campo, valor in datos.items():
        setattr(insumo, campo, valor)

    db.commit()
    db.refresh(insumo)
    return _serializar(insumo)


@router.delete("/insumos/{insumo_id}", status_code=204)
def eliminar_insumo(
    insumo_id: int,
    db: Session = Depends(get_db),
    cliente_id: str = Depends(get_cliente_id),
    usuario: str = Depends(get_usuario_actual),
):
    # Sin comprobación de "en uso" (a diferencia de Categoria, que la
    # necesita porque los platos la referencian): nada cuelga de un insumo,
    # así que borrarlo no deja filas huérfanas ni rompe historial.
    validar_admin(db, usuario, cliente_id)
    insumo = _buscar_o_404(db, insumo_id, cliente_id)

    db.delete(insumo)
    db.commit()
    return None
