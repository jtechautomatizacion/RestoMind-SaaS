"""
Fixtures compartidas para tests
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from backend.auth import hash_password
from backend.database import Base
from backend.models import Cliente, Plato, Mesa, Usuario, SuperAdmin

TEST_CLIENTE_ID = "test-cliente-001"
TEST_USUARIO_EMAIL = "admin@test.local"
TEST_USUARIO_PASSWORD = "secreta123"
TEST_SUPERADMIN_EMAIL = "dueno@resto-mind.com"
TEST_SUPERADMIN_PASSWORD = "superclave123"


@pytest.fixture(autouse=True)
def _reset_rate_limit_login():
    """El rate-limiter de login cuenta intentos por IP, pero Starlette's
    TestClient siempre usa el mismo host falso ("testclient") — sin este
    reset, los 401 esperados en un test de credenciales inválidas se
    acumularían con los de otro test y dispararían un 429 que no tiene
    nada que ver con lo que ese test está probando."""
    from backend.utils import rate_limit
    rate_limit._fallos.clear()
    yield
    rate_limit._fallos.clear()


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
    from backend.dependencies import get_cliente_id, get_usuario_actual

    def override_get_db():
        yield test_db

    def override_get_cliente_id():
        return TEST_CLIENTE_ID

    def override_get_usuario_actual():
        return TEST_USUARIO_EMAIL

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_cliente_id] = override_get_cliente_id
    app.dependency_overrides[get_usuario_actual] = override_get_usuario_actual

    client = TestClient(app)
    yield client

    app.dependency_overrides.clear()


@pytest.fixture
def test_client_real_auth(test_db):
    """
    Cliente de test SIN los overrides de get_cliente_id/get_usuario_actual:
    a diferencia de test_client (que bypasea el JWT por completo para no
    tener que loguearse en cada test de negocio), este ejercita la cadena
    real de autenticación — para probar login y que un token inválido/
    ausente efectivamente bloquea el acceso.
    """
    from fastapi.testclient import TestClient
    from backend.app import app
    from backend.database import get_db

    def override_get_db():
        yield test_db

    app.dependency_overrides[get_db] = override_get_db

    client = TestClient(app)
    yield client

    app.dependency_overrides.clear()


@pytest.fixture
def test_client_real_auth_sa(test_db, test_superadmin):
    """
    Cliente de test con autenticación SUPERADMIN real (con JWT).
    Se loguea automáticamente y devuelve un cliente que incluye el token
    en todas las solicitudes.
    """
    from fastapi.testclient import TestClient
    from backend.app import app
    from backend.database import get_db

    def override_get_db():
        yield test_db

    app.dependency_overrides[get_db] = override_get_db

    client = TestClient(app)

    # Login del superadmin
    resp = client.post('/api/superadmin/login', json={
        "email": TEST_SUPERADMIN_EMAIL,
        "password": TEST_SUPERADMIN_PASSWORD
    })
    assert resp.status_code == 200
    token = resp.json()["access_token"]

    # Inyectar el token en todas las solicitudes
    client.headers.update({"Authorization": f"Bearer {token}"})

    yield client

    app.dependency_overrides.clear()


@pytest.fixture
def test_cliente(test_db):
    """Crea cliente de test + usuario admin en BD"""
    cliente = Cliente(
        id=TEST_CLIENTE_ID,
        nombre='Test Restaurant',
        email='test@restaurant.com',
        pais='Perú',
        moneda='PEN'
    )
    test_db.add(cliente)
    test_db.commit()

    usuario = Usuario(
        id='usr-admin-001',
        cliente_id=TEST_CLIENTE_ID,
        nombre='Admin',
        email=TEST_USUARIO_EMAIL,
        password_hash=hash_password(TEST_USUARIO_PASSWORD),
        rol='admin',
        estado='activo'
    )
    test_db.add(usuario)
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
def test_superadmin(test_db):
    """Crea una cuenta de superadmin de test."""
    admin = SuperAdmin(
        id='super-test',
        nombre='Dueño',
        email=TEST_SUPERADMIN_EMAIL,
        password_hash=hash_password(TEST_SUPERADMIN_PASSWORD),
    )
    test_db.add(admin)
    test_db.commit()
    return admin


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
