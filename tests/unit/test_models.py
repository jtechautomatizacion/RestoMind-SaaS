"""
Tests unitarios para modelos
"""

import pytest
from backend.models import Plato, Comanda, ComandaPlato


def test_plato_creacion(test_db, test_cliente):
    """Test crear plato"""
    plato = Plato(
        cliente_id=test_cliente.id,
        nombre='Causa Limeña',
        categoria='Entradas',
        precio_venta=15.00,
        estado='activo'
    )
    test_db.add(plato)
    test_db.commit()

    retrieved = test_db.query(Plato).filter(Plato.nombre == 'Causa Limeña').first()
    assert retrieved is not None
    assert retrieved.precio_venta == 15.00
    assert retrieved.estado == 'activo'


def test_multi_tenant_isolation(test_db, test_cliente):
    """Test aislamiento multi-tenant"""
    otro_cliente_id = 'test-cliente-002'

    # Crear platos para diferentes clientes
    plato1 = Plato(
        cliente_id=test_cliente.id,
        nombre='Ceviche',
        categoria='Cebiches',
        precio_venta=45.00
    )
    plato2 = Plato(
        cliente_id=otro_cliente_id,
        nombre='Otro Plato',
        categoria='Otro',
        precio_venta=30.00
    )

    test_db.add(plato1)
    test_db.add(plato2)
    test_db.commit()

    # Query solo para cliente 1
    platos_cliente1 = test_db.query(Plato).filter(
        Plato.cliente_id == test_cliente.id
    ).all()

    assert len(platos_cliente1) == 1
    assert platos_cliente1[0].nombre == 'Ceviche'
