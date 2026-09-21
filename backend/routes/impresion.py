"""
Cola de impresión: los aparatos vienen a buscar trabajo acá.

Ver backend/utils/impresion.py para el porqué de la cola y las tres reglas
que impiden que un papel se duplique o se pierda.

QUIÉN PUEDE USAR ESTOS ENDPOINTS
--------------------------------
Cualquier rol del restaurante, NO solo admin. El aparato de la cocina se
loguea con una cuenta de cocina, y el del mozo con una de mozo: si esto fuera
admin-only, la cola no le serviría a nadie más que al dueño, que es justo
quien menos la necesita.

Todo va acotado al `cliente_id` del token, como el resto de la app: un
restaurante no puede reclamar ni confirmar los papeles de otro.
"""

from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.dependencies import get_cliente_id
from backend.models import TrabajoImpresion
from backend.schemas import (
    ReclamarImpresionRequest,
    TrabajoImpresionResponse,
    ResultadoImpresionRequest,
    ReimprimirRequest,
)
from backend.utils.impresion import (
    reclamar_trabajos,
    confirmar_resultado,
    reimprimir,
)

router = APIRouter()

# Dónde sale cada papel cuando se pide a mano. El de cocina vuelve a la
# cocina; los del comensal, al mostrador. Se resuelve en el SERVIDOR y no se
# acepta del cliente: si el frontend pudiera elegir la estación, un botón mal
# cableado mandaría el ticket de cocina a la impresora del mostrador y el
# síntoma sería "sale en el lugar equivocado", de lo más difícil de rastrear.
_ESTACION_DE_TIPO = {
    "cocina": "cocina",
    "precuenta": "mostrador",
    "preventa": "mostrador",
}


@router.post("/impresion/reclamar", response_model=List[TrabajoImpresionResponse])
def reclamar(
    payload: ReclamarImpresionRequest,
    db: Session = Depends(get_db),
    cliente_id: str = Depends(get_cliente_id),
):
    """Este aparato pide los papeles pendientes de las estaciones que atiende.

    Devuelve también los que este mismo aparato ya tenía tomados y no
    confirmó: si la app se recargó justo después de reclamar pero antes de
    imprimir, esos papeles vuelven a aparecer sin esperar a que venza nada.
    """
    return reclamar_trabajos(
        db,
        cliente_id=cliente_id,
        estaciones=payload.estaciones,
        device_id=payload.device_id,
        limite=payload.limite,
    )


@router.post("/impresion/{trabajo_id}/resultado", response_model=TrabajoImpresionResponse)
def resultado(
    trabajo_id: int,
    payload: ResultadoImpresionRequest,
    db: Session = Depends(get_db),
    cliente_id: str = Depends(get_cliente_id),
):
    """Confirma si el papel salió. Solo lo puede cerrar el aparato que lo tomó.

    Un 404 acá casi siempre significa que el reclamo venció y otro aparato se
    llevó el trabajo — no es un error que haya que mostrarle a nadie: el papel
    ya está en manos de otra impresora.
    """
    trabajo = confirmar_resultado(
        db,
        cliente_id=cliente_id,
        trabajo_id=trabajo_id,
        device_id=payload.device_id,
        salio=payload.salio,
        error=payload.error,
    )
    if not trabajo:
        raise HTTPException(
            status_code=404,
            detail="Ese trabajo no existe, o ya no lo tiene este aparato",
        )
    return trabajo


@router.post("/impresion/reimprimir", response_model=TrabajoImpresionResponse, status_code=201)
def pedir_reimpresion(
    payload: ReimprimirRequest,
    db: Session = Depends(get_db),
    cliente_id: str = Depends(get_cliente_id),
):
    """Vuelve a pedir un papel de un pedido que ya existe.

    Cubre los tres casos que pasan de verdad en un turno: el aparato de la
    cocina estaba apagado cuando entró el pedido, la impresora estaba trabada,
    o el papel salió y se perdió entre el movimiento.

    Entra como un trabajo NUEVO (no reabre el original) para que el historial
    pueda decir cuántas veces salió algo — que es exactamente el dato que se
    busca cuando alguien pregunta "¿esto ya se imprimió?".
    """
    trabajo = reimprimir(
        db,
        cliente_id=cliente_id,
        comanda_id=payload.comanda_id,
        tipo_documento=payload.tipo_documento,
        estacion=_ESTACION_DE_TIPO[payload.tipo_documento],
    )
    if not trabajo:
        raise HTTPException(status_code=404, detail="Esa comanda no existe en este restaurante")
    return trabajo
