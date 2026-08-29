"""
Datos semilla para desarrollo/demo.

Se ejecuta una sola vez: si ya existe al menos un cliente en la BD,
no hace nada (idempotente). Pensado para que al clonar el repo y
levantar el servidor, la demo ya tenga mesas y una carta cargada.
"""

from sqlalchemy.orm import Session
from backend.models import Cliente, Mesa, Plato

CLIENTE_DEMO_ID = "rest-001"

PLATOS_DEMO = [
    ("Ceviche Clásico", "Cebiches", 45.00, "Pescado fresco, leche de tigre, cebolla morada y camote"),
    ("Ceviche Mixto", "Cebiches", 55.00, "Pescado, pulpo, camarón y conchas negras"),
    ("Tiradito en Leche de Tigre", "Cebiches", 48.00, "Finas láminas de pescado bañadas en leche de tigre picante"),
    ("Causa Limeña", "Piqueos", 22.00, "Papa amarilla rellena de pollo o atún"),
    ("Chicharrón de Pescado", "Piqueos", 38.00, "Trozos de pescado crocante con salsa criolla"),
    ("Jalea Mixta", "Piqueos", 58.00, "Mariscos y pescado apanados para compartir"),
    ("Arroz con Mariscos", "Fondos", 42.00, "Arroz al estilo norteño con mixtura de mariscos"),
    ("Chaufa de Mariscos", "Fondos", 40.00, "Arroz chaufa con langostinos y calamar"),
    ("Chicha Morada", "Bebidas", 8.00, "Jarra personal"),
    ("Limonada Frozen", "Bebidas", 10.00, "Limonada helada"),
    ("Inca Kola 500ml", "Bebidas", 6.00, None),
    ("Suspiro a la Limeña", "Postres", 14.00, None),
]


def seed_if_empty(db: Session) -> None:
    if db.query(Cliente).first():
        return

    cliente = Cliente(
        id=CLIENTE_DEMO_ID,
        nombre="La Marisquería del Chef",
        email="admin@lamarisqueria.pe",
        telefono="+51 999 999 999",
        pais="Perú",
        moneda="PEN",
    )
    db.add(cliente)

    for numero in range(1, 9):
        db.add(Mesa(cliente_id=cliente.id, numero=numero, capacidad=4))

    for nombre, categoria, precio, descripcion in PLATOS_DEMO:
        db.add(Plato(
            cliente_id=cliente.id,
            nombre=nombre,
            categoria=categoria,
            precio_venta=precio,
            descripcion=descripcion,
        ))

    db.commit()
