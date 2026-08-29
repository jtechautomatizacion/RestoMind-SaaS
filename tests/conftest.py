"""
Fixtures compartidas para tests
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from backend.database import Base
from backend.models import Cliente, Plato, Mesa


@pytest.fixture
def test_db():
    """Crea una BD en memoria para tests"""
    engine = create_engine('sqlite:///:memory:')
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()

    yield db

    db.close()


@pytest.fixture
def test_client(test_db):
    """Cliente de test FastAPI"""
    from fastapi.testclient import TestClient
    from backend.app import app
    from backend.database import get_db

    def override_get_db():
        return test_db

    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app)


@pytest.fixture
def test_cliente(test_db):
    """Crea cliente de test en BD"""
    cliente = Cliente(
        id='test-cliente-001',
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
