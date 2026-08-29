"""
Fixtures compartidas para tests
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from backend.database import Base
from backend.models import Cliente, Plato, Mesa

TEST_CLIENTE_ID = "test-cliente-001"


@pytest.fixture
def test_db():
    """Crea una BD en memoria para tests.

    StaticPool es obligatorio aquí: sin él, cada conexión que SQLAlchemy
    abre desde el pool (p.ej. al ejecutarse en el threadpool de FastAPI)
    apunta a una base ':memory:' NUEVA y vacía, y las tablas 'desaparecen'.
    """
    engine = create_engine(
        'sqlite:///:memory:',
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()

    yield db

    db.close()


@pytest.fixture
def test_client(test_db):
    """Cliente de test FastAPI, aislado de la BD real y fijado a TEST_CLIENTE_ID."""
    from fastapi.testclient import TestClient
    from backend.app import app
    from backend.database import get_db
    from backend.dependencies import get_cliente_id

    def override_get_db():
        yield test_db

    def override_get_cliente_id():
        return TEST_CLIENTE_ID

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_cliente_id] = override_get_cliente_id

    client = TestClient(app)
    yield client

    app.dependency_overrides.clear()


@pytest.fixture
def test_cliente(test_db):
    """Crea cliente de test en BD"""
    cliente = Cliente(
        id=TEST_CLIENTE_ID,
        nombre='Test Restaurant',
        email='test@restaurant.com',
        pais='Perú',
        moneda='PEN'
    )
    test_db.add(cliente)
    test_db.commit()
    return cliente


@pytest.fixture
def test_platos(test_db, test_cliente):
    """Crea platos de test"""
    platos = [
        Plato(
            cliente_id=test_cliente.id,
            nombre='Ceviche Clásico',
            categoria='Cebiches',
            precio_venta=45.00,
            estado='activo'
        ),
        Plato(
            cliente_id=test_cliente.id,
            nombre='Jugo de Naranja',
            categoria='Bebidas',
            precio_venta=5.00,
            estado='activo'
        )
    ]
    for plato in platos:
        test_db.add(plato)
    test_db.commit()
    return platos


@pytest.fixture
def test_mesas(test_db, test_cliente):
    """Crea mesas de test"""
    mesas = [
        Mesa(cliente_id=test_cliente.id, numero=1, estado='disponible'),
        Mesa(cliente_id=test_cliente.id, numero=2, estado='disponible'),
        Mesa(cliente_id=test_cliente.id, numero=5, estado='disponible')
    ]
    for mesa in mesas:
        test_db.add(mesa)
    test_db.commit()
    return mesas
