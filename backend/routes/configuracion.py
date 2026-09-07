"""
Configuración operativa del restaurante que el propio admin puede cambiar
(a diferencia de los datos tributarios —RUC, razón social— que los carga
el superadmin al dar de alta el cliente).

Hoy tiene un solo interruptor: si este restaurante emite boletas
electrónicas desde RestoMind. Antes eso se deducía de "¿tiene RUC?", y eso
mezclaba dos cosas distintas: tener RUC es un dato del negocio, emitir
desde ESTA app es una decisión operativa que además cambia con el tiempo
(se vende desde el día uno, el Facturador se configura después).
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.dependencies import get_cliente_id, get_usuario_actual
from backend.models import Cliente
from backend.schemas import ConfiguracionResponse, ConfiguracionUpdateRequest
from backend.utils.auditoria import registrar_evento
from backend.utils.security import validar_admin

router = APIRouter()


@router.get("/configuracion", response_model=ConfiguracionResponse)
def obtener_configuracion(
    db: Session = Depends(get_db),
    cliente_id: str = Depends(get_cliente_id),
    usuario: str = Depends(get_usuario_actual),
):
    validar_admin(db, usuario, cliente_id)

    cliente = db.query(Cliente).filter(Cliente.id == cliente_id).first()
    if not cliente:
        raise HTTPException(status_code=404, detail="Restaurante no encontrado")

    return ConfiguracionResponse(
        usar_sunat=bool(cliente.usar_sunat),
        tiene_ruc=bool(cliente.ruc),
        ruc=cliente.ruc,
    )


@router.patch("/configuracion", response_model=ConfiguracionResponse)
def actualizar_configuracion(
    payload: ConfiguracionUpdateRequest,
    db: Session = Depends(get_db),
    cliente_id: str = Depends(get_cliente_id),
    usuario: str = Depends(get_usuario_actual),
):
    """Solo el admin del restaurante. El cliente_id sale del token, nunca
    del cuerpo: si viniera del payload, cualquiera podría apagarle la
    facturación a otro restaurante."""
    validar_admin(db, usuario, cliente_id)

    cliente = db.query(Cliente).filter(Cliente.id == cliente_id).first()
    if not cliente:
        raise HTTPException(status_code=404, detail="Restaurante no encontrado")

    if payload.usar_sunat and not cliente.ruc:
        # Sin RUC no hay comprobante posible: dejar prender el interruptor
        # solo llevaría al mismo toast rojo en cada cobro que este campo
        # existe para evitar, pero ahora sin explicación.
        raise HTTPException(
            status_code=400,
            detail="Para emitir boletas primero hay que cargar el RUC del restaurante. "
                   "Pedíselo a quien te dio de alta el sistema.",
        )

    anterior = bool(cliente.usar_sunat)
    cliente.usar_sunat = payload.usar_sunat
    db.commit()

    # Solo se audita el cambio real: un PATCH que deja todo igual (el
    # frontend puede reenviar el estado actual) no es un evento.
    if anterior != payload.usar_sunat:
        registrar_evento(
            db, actor=usuario, accion="cambiar_configuracion", entidad="cliente",
            entidad_id=cliente_id, cliente_id=cliente_id,
            detalle=f"usar_sunat: {anterior} -> {payload.usar_sunat}",
        )

    return ConfiguracionResponse(
        usar_sunat=bool(cliente.usar_sunat),
        tiene_ruc=bool(cliente.ruc),
        ruc=cliente.ruc,
    )
