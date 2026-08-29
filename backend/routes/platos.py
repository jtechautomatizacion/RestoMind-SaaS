"""
CU-01: Gestión de la Carta Inteligente
Endpoints para crear, actualizar y listar platos del menú.
"""

import io
from pathlib import Path
from typing import List, Optional
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from PIL import Image, UnidentifiedImageError
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

# Límite sobre el archivo CRUDO recibido, antes de recomprimir — solo para
# frenar un archivo absurdamente grande (o una bomba de descompresión) antes
# de gastar CPU abriéndolo con Pillow. No es el límite de lo que queda
# guardado en disco: eso lo fija MAX_LADO_PX + CALIDAD_JPEG más abajo.
MAX_IMAGEN_BYTES = 5 * 1024 * 1024

# El frontend (frontend/js/admin.js) ya redimensiona a 800px/calidad 0.8 antes
# de subir, así que en el uso normal esto no vuelve a tocar la imagen. Pero
# nada impide que alguien llame a este endpoint directo (curl, la app móvil
# del día de mañana, un cliente HTTP cualquiera) saltándose el navegador y
# subiendo una foto de 5MB sin comprimir. Sin esto, el storage del servidor
# crece sin límite con el tiempo en un SaaS multi-tenant — cada restaurante
# nuevo súmando fotos pesadas. Recomprimir siempre en el servidor, sin
# importar de dónde vino el archivo, es lo único que garantiza un tope real.
MAX_LADO_PX = 800
CALIDAD_JPEG = 82

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


def _recomprimir_a_jpeg(contenido: bytes) -> bytes:
    """Reduce cualquier imagen válida a JPEG, máx. MAX_LADO_PX de lado.

    Se guarda SIEMPRE como .jpg sin importar el formato de entrada — no hay
    fotos de platos con transparencia real que se pierda por aplanar PNG/WEBP
    sobre blanco, y unificar el formato es lo que permite garantizar un tope
    de peso consistente para todo lo que hay en disco.
    """
    try:
        imagen = Image.open(io.BytesIO(contenido))
        imagen.load()  # fuerza la decodificación completa acá, no de forma perezosa después
    except UnidentifiedImageError:
        raise HTTPException(status_code=400, detail="No se pudo leer el archivo como imagen")

    if imagen.mode != "RGB":
        # Aplana transparencia (PNG/WEBP con canal alfa) sobre blanco: JPEG
        # no tiene canal alfa, y un plato de comida no lo necesita.
        fondo = Image.new("RGB", imagen.size, (255, 255, 255))
        fondo.paste(imagen, mask=imagen.split()[-1] if imagen.mode in ("RGBA", "LA") else None)
        imagen = fondo

    imagen.thumbnail((MAX_LADO_PX, MAX_LADO_PX), Image.LANCZOS)

    salida = io.BytesIO()
    imagen.save(salida, format="JPEG", quality=CALIDAD_JPEG, optimize=True)
    return salida.getvalue()


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

    if not _detectar_extension(contenido):
        raise HTTPException(status_code=400, detail="Formato no soportado. Usa JPG, PNG o WEBP")

    # El frontend ya manda la imagen liviana en el caso normal; esto es lo
    # que garantiza que quede liviana también si alguien sube directo a la
    # API. Siempre termina como .jpg — ver _recomprimir_a_jpeg.
    contenido_final = _recomprimir_a_jpeg(contenido)

    CARPETA_IMAGENES.mkdir(parents=True, exist_ok=True)

    # plato_id es un entero que ya validó FastAPI en la ruta: es seguro usarlo
    # como nombre de archivo. Se limpian versiones previas (de antes de
    # unificar todo a .jpg pudo haber quedado un .png o .webp) para no dejar
    # huérfanos cuando se reemplaza la foto de un plato.
    for previo in CARPETA_IMAGENES.glob(f"{plato_id}.*"):
        previo.unlink()

    destino = CARPETA_IMAGENES / f"{plato_id}.jpg"
    destino.write_bytes(contenido_final)

    plato.imagen_url = f"/static/assets/platos/{plato_id}.jpg"
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
