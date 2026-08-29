"""
Lógica de negocio compartida entre routers.

Se centraliza aquí para que 'comandas' y 'mesas' no se pisen entre sí
y para que las reglas de transición de estado vivan en un solo lugar.
"""

from typing import List
from sqlalchemy.orm import Session
from backend.models import Comanda, Mesa

# Transiciones válidas de una comanda. 'cobrado' y 'cancelado' son estados terminales.
TRANSICIONES_VALIDAS = {
    "cocina": {"entregado", "cancelado"},
    "entregado": {"cobrado", "cancelado"},
    "cobrado": set(),
    "cancelado": set(),
}

ESTADOS_ACTIVOS = ("cocina", "entregado")


def comanda_to_response(comanda: Comanda) -> dict:
    """Arma el dict de respuesta de una comanda incluyendo el nombre de cada plato."""
    return {
        "id": comanda.id,
        "cliente_id": comanda.cliente_id,
        "numero_mesa": comanda.numero_mesa,
        "estado": comanda.estado,
        "total_cuenta": comanda.total_cuenta,
        "creado_en": comanda.creado_en,
        "platos": [
            {
                "plato_id": cp.plato_id,
                "nombre": cp.plato.nombre if cp.plato else "Plato eliminado",
                "cantidad": cp.cantidad,
                "precio_unitario": cp.precio_unitario,
                "subtotal": cp.subtotal,
            }
            for cp in comanda.comanda_platos
        ],
    }


def get_comandas_activas_mesa(db: Session, cliente_id: str, numero_mesa: int) -> List[Comanda]:
    return (
        db.query(Comanda)
        .filter(
            Comanda.cliente_id == cliente_id,
            Comanda.numero_mesa == numero_mesa,
            Comanda.estado.in_(ESTADOS_ACTIVOS),
        )
        .all()
    )


def _liberar_mesa_si_corresponde(db: Session, cliente_id: str, numero_mesa: int) -> None:
    activas = get_comandas_activas_mesa(db, cliente_id, numero_mesa)
    if activas:
        return
    mesa = db.query(Mesa).filter(Mesa.cliente_id == cliente_id, Mesa.numero == numero_mesa).first()
    if mesa and mesa.estado != "disponible":
        mesa.estado = "disponible"


def actualizar_estado_comanda(db: Session, comanda: Comanda, nuevo_estado: str) -> None:
    """Aplica una transición de estado validando que sea posible.

    Lanza ValueError (el router la traduce a HTTP 400) si la transición no es válida.
    """
    permitidos = TRANSICIONES_VALIDAS.get(comanda.estado, set())
    if nuevo_estado not in permitidos:
        raise ValueError(f"No se puede pasar de '{comanda.estado}' a '{nuevo_estado}'")

    comanda.estado = nuevo_estado

    if nuevo_estado in ("cobrado", "cancelado"):
        _liberar_mesa_si_corresponde(db, comanda.cliente_id, comanda.numero_mesa)


def cobrar_mesa(db: Session, cliente_id: str, mesa: Mesa) -> dict:
    """Cierra la cuenta de una mesa: cobra todas sus comandas activas y la libera.

    Regla de negocio: no se puede cobrar si todavía hay platos en cocina
    (evita cobrar algo que el cliente aún no recibió).
    """
    activas = get_comandas_activas_mesa(db, cliente_id, mesa.numero)
    if not activas:
        raise ValueError("Esta mesa no tiene cuenta activa para cobrar")

    en_cocina = [c for c in activas if c.estado == "cocina"]
    if en_cocina:
        raise ValueError("Aún hay platos en cocina; no se puede cobrar todavía")

    total = 0.0
    for comanda in activas:
        comanda.estado = "cobrado"
        total += comanda.total_cuenta

    mesa.estado = "disponible"

    return {
        "mesa_numero": mesa.numero,
        "total_cobrado": round(total, 2),
        "comandas_cerradas": len(activas),
    }
