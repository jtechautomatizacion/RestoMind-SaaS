"""
Datos semilla para desarrollo/demo.

Se ejecuta una sola vez: si ya existe al menos un cliente en la BD,
no hace nada (idempotente). Pensado para que al clonar el repo y
levantar el servidor, la demo ya tenga mesas y una carta cargada.
"""

from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from backend.models import Cliente, Usuario, Mesa, Categoria, Plato, Comanda, ComandaPlato, Compra

CLIENTE_DEMO_ID = "rest-001"

# Debe coincidir con el default de get_usuario_actual() (backend/dependencies.py):
# sin login real, todo request sin header X-Usuario se resuelve a este email, y
# las acciones de administrador (crear/editar/eliminar mesas, categorías, gastos)
# validan que exista un Usuario con este email y rol='admin'. Sin esta fila, esas
# acciones fallaban con 403 aunque el frontend mostrara el rol "Admin".
USUARIO_ADMIN_EMAIL = "admin@demo.local"

# Iconos por defecto para categorías conocidas; cualquier nombre fuera de
# esta lista (categorías que el propio admin crea) usa el genérico 🍽️.
ICONOS_CATEGORIA = {
    "Cebiches": "🐟",
    "Piqueos": "🍤",
    "Fondos": "🍚",
    "Bebidas": "🥤",
    "Postres": "🍮",
}
ICONO_DEFECTO = "🍽️"

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


def _asegurar_columna_icono(db: Session) -> None:
    """
    Base.metadata.create_all() crea tablas nuevas pero nunca altera una
    tabla que ya existe: una BD creada antes de que Categoria tuviera
    'icono' se queda sin la columna y cada INSERT/SELECT sobre ella falla.
    ALTER TABLE ADD COLUMN es idempotente aquí porque se ignora el error
    si la columna ya existe (la única razón por la que fallaría).
    """
    from sqlalchemy import text
    from sqlalchemy.exc import OperationalError
    try:
        # Sin DEFAULT: así las filas ya existentes quedan en NULL y el loop
        # de más abajo les asigna el icono correcto por nombre, en vez de que
        # SQLite las llene todas con el genérico antes de que corra ese loop.
        db.execute(text("ALTER TABLE categorias ADD COLUMN icono VARCHAR"))
        db.commit()
    except OperationalError:
        db.rollback()


def backfill_clientes_existentes(db: Session) -> None:
    """
    Corre en cada arranque, para bases de datos que ya tenían un Cliente
    antes de existir Usuario/Categoria (seed_if_empty no vuelve a tocarlas
    porque solo actúa sobre una BD vacía). Sin esto, quien ya tenía el
    sistema instalado se queda con:
    - Las acciones de admin (mesas, gastos) fallando con 403 para siempre
      (no había fila de Usuario que validar_admin pudiera encontrar).
    - El selector de categorías del formulario de platos vacío, aunque
      sus platos ya tuvieran categoría asignada como texto.
    Idempotente: cada chequeo es "si no existe, créalo".
    """
    _asegurar_columna_icono(db)

    for cliente in db.query(Cliente).all():
        tiene_admin = db.query(Usuario).filter(
            Usuario.cliente_id == cliente.id, Usuario.rol == "admin"
        ).first()
        if not tiene_admin and not db.query(Usuario).filter(Usuario.email == USUARIO_ADMIN_EMAIL).first():
            db.add(Usuario(
                id=f"usr-admin-{cliente.id}",
                cliente_id=cliente.id,
                nombre="Administrador",
                email=USUARIO_ADMIN_EMAIL,
                password_hash="$2b$12$demo.no.login.todavia",
                rol="admin",
            ))

        tiene_categorias = db.query(Categoria).filter(Categoria.cliente_id == cliente.id).first()
        if not tiene_categorias:
            nombres_en_uso = {
                fila[0] for fila in db.query(Plato.categoria).filter(Plato.cliente_id == cliente.id).distinct()
            }
            for nombre in sorted(nombres_en_uso):
                db.add(Categoria(cliente_id=cliente.id, nombre=nombre, icono=ICONOS_CATEGORIA.get(nombre, ICONO_DEFECTO)))

        # Filas ya existentes de antes de que 'icono' existiera: sin valor,
        # NOT NULL las dejaría rotas en el próximo INSERT/UPDATE.
        for categoria in db.query(Categoria).filter(
            Categoria.cliente_id == cliente.id, Categoria.icono.is_(None)
        ).all():
            categoria.icono = ICONOS_CATEGORIA.get(categoria.nombre, ICONO_DEFECTO)

    db.commit()


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

    # Sin login real todavía (fase 2), pero las validaciones de rol admin sí
    # están activas: sin esta fila, "solo admin puede..." fallaba siempre.
    db.add(Usuario(
        id="usr-admin-demo",
        cliente_id=cliente.id,
        nombre="Administrador",
        email=USUARIO_ADMIN_EMAIL,
        password_hash="$2b$12$demo.no.login.todavia",
        rol="admin",
    ))

    for numero in range(1, 9):
        db.add(Mesa(cliente_id=cliente.id, numero=numero, capacidad=4))

    categorias_demo = sorted({categoria for _, categoria, _, _ in PLATOS_DEMO})
    for nombre in categorias_demo:
        db.add(Categoria(cliente_id=cliente.id, nombre=nombre, icono=ICONOS_CATEGORIA.get(nombre, ICONO_DEFECTO)))

    platos = []
    for nombre, categoria, precio, descripcion in PLATOS_DEMO:
        plato = Plato(
            cliente_id=cliente.id,
            nombre=nombre,
            categoria=categoria,
            precio_venta=precio,
            descripcion=descripcion,
        )
        db.add(plato)
        platos.append(plato)

    db.commit()

    # Usar fecha fija (viernes 28/08/2026) en lugar de utcnow()
    # Evita que la seed cree datos con fecha UTC cuando usuario espera fecha local
    from datetime import date
    hoy = date(2026, 8, 28)
    mesas = [m for m in db.query(Mesa).filter(Mesa.cliente_id == cliente.id).all()]

    # Crear datos demo para los últimos 7 días (exactamente 7 fechas)
    for dias_atras in range(7):
        fecha_date = hoy - timedelta(days=dias_atras)
        # Crear datetime a las 12:00 UTC del día para evitar problemas de zona horaria
        fecha_comanda = datetime.combine(fecha_date, datetime.min.time()).replace(hour=12)

        if dias_atras < 7:
            # 2-3 comandas por día
            for comanda_num in range(2 + (dias_atras % 2)):
                comanda = Comanda(
                    cliente_id=cliente.id,
                    numero_mesa=mesas[(dias_atras + comanda_num) % len(mesas)].numero,
                    total_cuenta=100.00 + (dias_atras * 15) + (comanda_num * 20),
                    estado="cobrado",
                    creado_por="demo@test.local",
                    actualizado_en=fecha_comanda,
                    creado_en=fecha_comanda,
                )
                db.add(comanda)
                db.flush()

                cp1 = ComandaPlato(
                    comanda_id=comanda.id,
                    plato_id=platos[dias_atras % len(platos)].id,
                    cantidad=1,
                    precio_unitario=platos[dias_atras % len(platos)].precio_venta,
                    subtotal=platos[dias_atras % len(platos)].precio_venta,
                )
                cp2 = ComandaPlato(
                    comanda_id=comanda.id,
                    plato_id=platos[(dias_atras + 1) % len(platos)].id,
                    cantidad=1,
                    precio_unitario=platos[(dias_atras + 1) % len(platos)].precio_venta,
                    subtotal=platos[(dias_atras + 1) % len(platos)].precio_venta,
                )
                db.add(cp1)
                db.add(cp2)

        if dias_atras < 5:
            compra = Compra(
                cliente_id=cliente.id,
                descripcion=f"Insumos del día {fecha_date.isoformat()}",
                categoria="Insumos",
                monto=45.00 + (dias_atras * 8),
                fecha=fecha_date.isoformat(),
                estado="registrado",
                creado_por="demo@test.local",
                creado_en=fecha_comanda,
            )
            db.add(compra)

    db.commit()
