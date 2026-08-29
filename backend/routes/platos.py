"""
CU-01: Gestión de la Carta Inteligente
Endpoints para crear, actualizar y listar platos del menú.
"""

from pathlib import Path
from typing import List, Optional
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session
from backend.database import get_db
from backend.dependencies import get_cliente_id, get_usuario_actual
from backend.models import ComandaPlato, Plato
from backend.schemas import PlatoCreate, PlatoUpdate, PlatoResponse, EstadoUpdate
from backend.utils.security import validar_admin

router = APIRouter()

ESTADOS_PLATO_VALIDOS = ("activo", "inactivo")

# Carpeta física de las fotos de platos, servida por el mount /static de app.py
# (frontend/ es la raíz de ese mount, así que esto queda en /static/assets/platos/).
CARPETA_IMAGENES = Path("frontend/assets/platos")
MAX_IMAGEN_BYTES = 5 * 1024 * 1024  # 5MB: cubre una foto de celular sin comprimir

# Firmas binarias reales de cada formato. No confiamos en el Content-Type que
# manda el cliente (se falsea trivialmente) ni en la extensión del nombre de
# archivo: si alguien sube un .html o .svg con extensión .png, esto lo rechaza
# antes de que llegue a guardarse como archivo estático.
def _detectar_extension(contenido: bytes) -> Optional[str]:
    if contenido[:3] == b"\xff\xd8\xff":
        return "jpg"
    if contenido[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if contenido[:4] == b"RIFF" and contenido[8:12] == b"WEBP":
        return "webp"
    return None


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
    usuario: str = Depends(get_usuario_actual),
):
    validar_admin(db, usuario, cliente_id)

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
    usuario: str = Depends(get_usuario_actual),
):
    validar_admin(db, usuario, cliente_id)

    plato = db.query(Plato).filter(Plato.id == plato_id, Plato.cliente_id == cliente_id).first()
    if not plato:
        raise HTTPException(status_code=404, detail="Plato no encontrado")

    datos = payload.model_dump(exclude_unset=True)
    for campo, valor in datos.items():
        setattr(plato, campo, valor)

    db.commit()
    db.refresh(plato)
    return plato


@router.delete("/platos/{plato_id}")
def eliminar_plato(
    plato_id: int,
    db: Session = Depends(get_db),
    cliente_id: str = Depends(get_cliente_id),
    usuario: str = Depends(get_usuario_actual),
):
    """
    Borrado real, no un simple 'estado=inactivo': el admin pidió poder
    eliminar platos de verdad, no solo desactivarlos.

    La única excepción es un plato que ya aparece en comandas pasadas
    (ComandaPlato): borrarlo de la BD arrastraría esas filas por el
    cascade definido en Plato.comanda_platos, y con ellas se iría el
    detalle de "platos más vendidos" del dashboard para ventas ya
    cobradas. En ese caso se archiva (estado='inactivo') en su lugar:
    desaparece de la carta igual, pero el historial de ventas queda intacto.
    """
    validar_admin(db, usuario, cliente_id)

    plato = db.query(Plato).filter(Plato.id == plato_id, Plato.cliente_id == cliente_id).first()
    if not plato:
        raise HTTPException(status_code=404, detail="Plato no encontrado")

    tiene_historial = db.query(ComandaPlato).filter(ComandaPlato.plato_id == plato_id).first() is not None

    if tiene_historial:
        plato.estado = "inactivo"
        db.commit()
        return {
            "eliminado": False,
            "detail": "Este plato ya tiene ventas registradas, así que se quitó de la carta sin borrar su historial.",
        }

    for previo in CARPETA_IMAGENES.glob(f"{plato_id}.*"):
        previo.unlink()

    db.delete(plato)
    db.commit()
    return {"eliminado": True, "detail": "Plato eliminado."}


@router.patch("/platos/{plato_id}/estado", response_model=PlatoResponse)
def cambiar_estado_plato(
    plato_id: int,
    payload: EstadoUpdate,
    db: Session = Depends(get_db),
    cliente_id: str = Depends(get_cliente_id),
    usuario: str = Depends(get_usuario_actual),
):
    validar_admin(db, usuario, cliente_id)

    if payload.estado not in ESTADOS_PLATO_VALIDOS:
        raise HTTPException(status_code=400, detail=f"Estado inválido. Use uno de: {ESTADOS_PLATO_VALIDOS}")

    plato = db.query(Plato).filter(Plato.id == plato_id, Plato.cliente_id == cliente_id).first()
    if not plato:
        raise HTTPException(status_code=404, detail="Plato no encontrado")

    plato.estado = payload.estado
    db.commit()
    db.refresh(plato)
    return plato


@router.post("/platos/{plato_id}/imagen", response_model=PlatoResponse)
async def subir_imagen_plato(
    plato_id: int,
    archivo: UploadFile = File(...),
    db: Session = Depends(get_db),
    cliente_id: str = Depends(get_cliente_id),
    usuario: str = Depends(get_usuario_actual),
):
    validar_admin(db, usuario, cliente_id)

    plato = db.query(Plato).filter(Plato.id == plato_id, Plato.cliente_id == cliente_id).first()
    if not plato:
        raise HTTPException(status_code=404, detail="Plato no encontrado")

    contenido = await archivo.read()
    if len(contenido) > MAX_IMAGEN_BYTES:
        raise HTTPException(status_code=400, detail="La imagen no puede pesar más de 5MB")

    extension = _detectar_extension(contenido)
    if not extension:
        raise HTTPException(status_code=400, detail="Formato no soportado. Usa JPG, PNG o WEBP")

    CARPETA_IMAGENES.mkdir(parents=True, exist_ok=True)

    # plato_id es un entero que ya validó FastAPI en la ruta: es seguro usarlo
    # como nombre de archivo. Se limpian versiones previas con otra extensión
    # para no dejar huérfanos cuando se reemplaza la foto de un plato.
    for previo in CARPETA_IMAGENES.glob(f"{plato_id}.*"):
        previo.unlink()

    destino = CARPETA_IMAGENES / f"{plato_id}.{extension}"
    destino.write_bytes(contenido)

    plato.imagen_url = f"/static/assets/platos/{plato_id}.{extension}"
    db.commit()
    db.refresh(plato)
    return plato


@router.delete("/platos/{plato_id}/imagen", response_model=PlatoResponse)
def eliminar_imagen_plato(
    plato_id: int,
    db: Session = Depends(get_db),
    cliente_id: str = Depends(get_cliente_id),
    usuario: str = Depends(get_usuario_actual),
):
    validar_admin(db, usuario, cliente_id)

    plato = db.query(Plato).filter(Plato.id == plato_id, Plato.cliente_id == cliente_id).first()
    if not plato:
        raise HTTPException(status_code=404, detail="Plato no encontrado")

    for previo in CARPETA_IMAGENES.glob(f"{plato_id}.*"):
        previo.unlink()

    plato.imagen_url = None
    db.commit()
    db.refresh(plato)
    return plato
