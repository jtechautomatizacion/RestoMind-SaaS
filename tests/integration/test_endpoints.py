"""
Tests de integración para endpoints API.
Cubren el ciclo completo: Admin crea plato -> Mozo manda comanda ->
Cocina entrega -> Mozo cobra -> Dashboard refleja el dinero.
"""


def test_health_endpoint(test_client):
    response = test_client.get('/health')
    assert response.status_code == 200
    assert response.json()['status'] == 'ok'


def test_root_endpoint(test_client):
    response = test_client.get('/')
    assert response.status_code == 200
    assert 'message' in response.json()


# ============ CU-01: PLATOS ============

def test_crear_y_listar_plato(test_client, test_cliente):
    payload = {"nombre": "Ceviche Clásico", "categoria": "Cebiches", "precio_venta": 45.0}
    resp = test_client.post('/api/platos', json=payload)
    assert resp.status_code == 201
    data = resp.json()
    assert data["nombre"] == "Ceviche Clásico"
    assert data["estado"] == "activo"
    assert data["cliente_id"] == "test-cliente-001"

    resp = test_client.get('/api/platos')
    assert resp.status_code == 200
    assert len(resp.json()) == 1


def test_crear_plato_precio_invalido_falla(test_client, test_cliente):
    resp = test_client.post('/api/platos', json={"nombre": "X", "categoria": "Y", "precio_venta": 0})
    assert resp.status_code == 422


def test_desactivar_plato_no_aparece_en_listado(test_client, test_platos):
    plato_id = test_platos[0].id
    resp = test_client.patch(f'/api/platos/{plato_id}/estado', json={"estado": "inactivo"})
    assert resp.status_code == 200
    assert resp.json()["estado"] == "inactivo"

    resp = test_client.get('/api/platos')
    nombres = [p["nombre"] for p in resp.json()]
    assert test_platos[0].nombre not in nombres


# ============ CU-02: COMANDAS ============

def test_crear_comanda_calcula_total_y_ocupa_mesa(test_client, test_platos, test_mesas):
    payload = {
        "numero_mesa": 1,
        "platos": [
            {"plato_id": test_platos[0].id, "cantidad": 2},  # 45 * 2 = 90
            {"plato_id": test_platos[1].id, "cantidad": 1},  # 5 * 1 = 5
        ],
    }
    resp = test_client.post('/api/comandas', json=payload)
    assert resp.status_code == 201
    data = resp.json()
    assert data["total_cuenta"] == 95.0
    assert data["estado"] == "cocina"
    assert len(data["platos"]) == 2

    mesas = test_client.get('/api/mesas').json()
    mesa1 = next(m for m in mesas if m["numero"] == 1)
    assert mesa1["estado"] == "ocupada"
    assert mesa1["cuenta_actual"] == 95.0


def test_crear_comanda_mesa_inexistente_falla(test_client, test_platos):
    payload = {"numero_mesa": 999, "platos": [{"plato_id": test_platos[0].id, "cantidad": 1}]}
    resp = test_client.post('/api/comandas', json=payload)
    assert resp.status_code == 404


def test_crear_comanda_plato_duplicado_suma_cantidades(test_client, test_platos, test_mesas):
    payload = {
        "numero_mesa": 1,
        "platos": [
            {"plato_id": test_platos[0].id, "cantidad": 1},
            {"plato_id": test_platos[0].id, "cantidad": 2},
        ],
    }
    resp = test_client.post('/api/comandas', json=payload)
    assert resp.status_code == 201
    data = resp.json()
    assert len(data["platos"]) == 1
    assert data["platos"][0]["cantidad"] == 3
    assert data["total_cuenta"] == 135.0


def test_crear_comanda_sin_platos_falla_validacion(test_client, test_mesas):
    resp = test_client.post('/api/comandas', json={"numero_mesa": 1, "platos": []})
    assert resp.status_code == 422


# ============ CU-03: MONITOR DE COCINA ============

def test_monitor_cocina_y_marcar_entregado(test_client, test_platos, test_mesas):
    payload = {"numero_mesa": 2, "platos": [{"plato_id": test_platos[0].id, "cantidad": 1}]}
    comanda = test_client.post('/api/comandas', json=payload).json()

    resp = test_client.get('/api/monitor/cocina')
    assert resp.status_code == 200
    ids = [c["id"] for c in resp.json()]
    assert comanda["id"] in ids

    resp = test_client.patch(f'/api/comandas/{comanda["id"]}/estado', json={"estado": "entregado"})
    assert resp.status_code == 200
    assert resp.json()["estado"] == "entregado"

    # Ya no debe aparecer en cocina
    resp = test_client.get('/api/monitor/cocina')
    ids = [c["id"] for c in resp.json()]
    assert comanda["id"] not in ids


def test_transicion_estado_invalida_falla(test_client, test_platos, test_mesas):
    payload = {"numero_mesa": 1, "platos": [{"plato_id": test_platos[0].id, "cantidad": 1}]}
    comanda = test_client.post('/api/comandas', json=payload).json()

    # No se puede pasar de 'cocina' directo a 'cobrado'
    resp = test_client.patch(f'/api/comandas/{comanda["id"]}/estado', json={"estado": "cobrado"})
    assert resp.status_code == 400


# ============ COBRO DE MESA (cierre del ciclo) ============

def test_no_se_puede_cobrar_con_platos_en_cocina(test_client, test_platos, test_mesas):
    payload = {"numero_mesa": 1, "platos": [{"plato_id": test_platos[0].id, "cantidad": 1}]}
    test_client.post('/api/comandas', json=payload)

    mesas = test_client.get('/api/mesas').json()
    mesa1_id = next(m for m in mesas if m["numero"] == 1)["id"]

    resp = test_client.post(f'/api/mesas/{mesa1_id}/cobrar')
    assert resp.status_code == 400


def test_cobrar_mesa_libera_mesa_y_suma_total(test_client, test_platos, test_mesas):
    payload = {"numero_mesa": 1, "platos": [{"plato_id": test_platos[0].id, "cantidad": 2}]}
    comanda = test_client.post('/api/comandas', json=payload).json()
    test_client.patch(f'/api/comandas/{comanda["id"]}/estado', json={"estado": "entregado"})

    mesas = test_client.get('/api/mesas').json()
    mesa1_id = next(m for m in mesas if m["numero"] == 1)["id"]

    resp = test_client.post(f'/api/mesas/{mesa1_id}/cobrar')
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_cobrado"] == 90.0
    assert data["comandas_cerradas"] == 1

    mesas = test_client.get('/api/mesas').json()
    mesa1 = next(m for m in mesas if m["numero"] == 1)
    assert mesa1["estado"] == "disponible"
    assert mesa1["cuenta_actual"] == 0.0


# ============ CU-04: COMPRAS ============

def test_crear_compra_y_editar_mismo_dia(test_client, test_cliente):
    from datetime import date
    payload = {"descripcion": "Pescado rojo", "categoria": "Insumos", "monto": 85.5, "fecha": date.today().isoformat()}
    resp = test_client.post('/api/compras', json=payload)
    assert resp.status_code == 201
    compra_id = resp.json()["id"]

    resp = test_client.patch(f'/api/compras/{compra_id}', json={"monto": 90.0})
    assert resp.status_code == 200
    assert resp.json()["monto"] == 90.0


def test_crear_compra_fecha_futura_falla(test_client, test_cliente):
    payload = {"descripcion": "Insumo", "monto": 10.0, "fecha": "2099-01-01"}
    resp = test_client.post('/api/compras', json=payload)
    assert resp.status_code == 400


def test_cancelar_compra(test_client, test_cliente):
    from datetime import date
    payload = {"descripcion": "Verduras", "monto": 30.0, "fecha": date.today().isoformat()}
    compra_id = test_client.post('/api/compras', json=payload).json()["id"]

    resp = test_client.patch(f'/api/compras/{compra_id}/estado', json={"estado": "cancelado"})
    assert resp.status_code == 200
    assert resp.json()["estado"] == "cancelado"


# ============ CU-05: DASHBOARD ============

def test_dashboard_refleja_venta_cobrada(test_client, test_platos, test_mesas):
    payload = {"numero_mesa": 1, "platos": [{"plato_id": test_platos[0].id, "cantidad": 1}]}
    comanda = test_client.post('/api/comandas', json=payload).json()
    test_client.patch(f'/api/comandas/{comanda["id"]}/estado', json={"estado": "entregado"})

    mesas = test_client.get('/api/mesas').json()
    mesa1_id = next(m for m in mesas if m["numero"] == 1)["id"]
    test_client.post(f'/api/mesas/{mesa1_id}/cobrar')

    resp = test_client.get('/api/dashboard/resumen?dias=7')
    assert resp.status_code == 200
    data = resp.json()
    assert data["totales"]["ventas"] == 45.0
    assert data["totales"]["comandas"] == 1
    assert len(data["top_platos"]) == 1
    assert data["top_platos"][0]["nombre"] == "Ceviche Clásico"


def test_dashboard_sin_ventas_no_falla(test_client, test_cliente):
    resp = test_client.get('/api/dashboard/resumen')
    assert resp.status_code == 200
    data = resp.json()
    assert data["totales"]["ventas"] == 0.0
    assert len(data["serie"]) == 7
