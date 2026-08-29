"""
Tests de integración para endpoints API
"""

import pytest


def test_health_endpoint(test_client):
    """Test endpoint de health check"""
    response = test_client.get('/health')
    assert response.status_code == 200
    data = response.json()
    assert data['status'] == 'ok'
    assert 'version' in data


def test_root_endpoint(test_client):
    """Test endpoint raíz"""
    response = test_client.get('/')
    assert response.status_code == 200
    data = response.json()
    assert 'message' in data
    assert 'docs' in data


# TODO: Tests para endpoints de platos, comandas, compras, mesas
# def test_get_platos(test_client, test_platos):
#     response = test_client.get('/api/platos')
#     assert response.status_code == 200

# def test_post_comanda(test_client, test_platos, test_mesas):
#     data = {
#         "numero_mesa": 1,
#         "platos": [
#             {"plato_id": test_platos[0].id, "cantidad": 1}
#         ]
#     }
#     response = test_client.post('/api/comandas', json=data)
#     assert response.status_code == 200
