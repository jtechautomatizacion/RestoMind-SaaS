"""
Interruptor de facturación por restaurante (Cliente.usar_sunat).

EL PROBLEMA QUE RESUELVE
------------------------
Antes, "¿este restaurante emite boletas?" se deducía de "¿tiene RUC?". Eso
mezcla dos cosas que no son la misma: tener RUC es un dato tributario del
negocio; emitir desde ESTA app es una decisión operativa que además cambia
con el tiempo — se vende desde el primer día y el Facturador se configura
después.

Con la lógica vieja, un restaurante sin RUC recibía un toast rojo en CADA
cobro ("Cobro OK, pero la boleta NO se emitió") y se le llenaba
Admin > Boletas de pendientes que nadie iba a emitir jamás.
"""

import pytest

from backend.models import Cliente


@pytest.fixture
def cliente_con_ruc(test_db, test_cliente):
    test_cliente.ruc = "10200812234"
    test_cliente.razon_social = "Pollería Fogones"
    test_db.commit()
    return test_cliente


def _crear_y_cobrar_mesa(test_client, test_platos, numero_mesa=5):
    resp = test_client.post("/api/comandas", json={
        "numero_mesa": numero_mesa,
        "platos": [{"plato_id": test_platos[0].id, "cantidad": 2}],
    })
    comanda_id = resp.json()["id"]
    test_client.patch(f"/api/comandas/{comanda_id}/estado", json={"estado": "entregado"})
    mesa = next(m for m in test_client.get("/api/mesas").json() if m["numero"] == numero_mesa)
    return test_client.post(f"/api/mesas/{mesa['id']}/cobrar").json()


# ---------- Valor por defecto y compatibilidad ----------

def test_un_restaurante_nuevo_no_emite_boletas(test_client, test_cliente):
    """Default False a propósito: se vende desde el día uno, SUNAT se
    configura después. Lo contrario obliga a configurar el Facturador
    antes de poder cobrar la primera mesa."""
    cfg = test_client.get("/api/configuracion").json()
    assert cfg["usar_sunat"] is False
    assert cfg["tiene_ruc"] is False


def test_la_sesion_informa_si_el_restaurante_emite(test_client_real_auth, test_cliente, test_db):
    """El frontend decide con este dato si intentar emitir tras cobrar —
    sin él volvería el toast rojo en cada venta."""
    from tests.conftest import TEST_USUARIO_EMAIL, TEST_USUARIO_PASSWORD
    login = test_client_real_auth.post("/api/auth/login", json={
        "email": TEST_USUARIO_EMAIL, "password": TEST_USUARIO_PASSWORD,
    })
    assert login.json()["usuario"]["cliente_usar_sunat"] is False

    test_cliente.ruc = "10200812234"
    test_cliente.usar_sunat = True
    test_db.commit()

    login2 = test_client_real_auth.post("/api/auth/login", json={
        "email": TEST_USUARIO_EMAIL, "password": TEST_USUARIO_PASSWORD,
    })
    assert login2.json()["usuario"]["cliente_usar_sunat"] is True


# ---------- Reglas del interruptor ----------

def test_no_se_puede_activar_sin_ruc(test_client, test_cliente):
    """Sin RUC no hay comprobante posible: dejar prenderlo solo llevaría al
    mismo error en cada cobro, pero ahora sin explicación."""
    resp = test_client.patch("/api/configuracion", json={"usar_sunat": True})
    assert resp.status_code == 400
    # El mensaje ya no dice "cargá el RUC": con el flujo nuevo lo que falta
    # es el certificado, que es lo que de verdad habilita emitir.
    assert "certificado" in resp.json()["detail"]


def test_con_ruc_se_puede_activar_y_desactivar(test_client, cliente_con_ruc):
    activado = test_client.patch("/api/configuracion", json={"usar_sunat": True})
    assert activado.status_code == 200
    assert activado.json()["usar_sunat"] is True

    apagado = test_client.patch("/api/configuracion", json={"usar_sunat": False})
    assert apagado.status_code == 200
    assert apagado.json()["usar_sunat"] is False


def test_el_cambio_queda_auditado(test_client, test_db, cliente_con_ruc):
    from backend.models import AuditLog

    test_client.patch("/api/configuracion", json={"usar_sunat": True})

    evento = (
        test_db.query(AuditLog)
        .filter(AuditLog.accion == "cambiar_configuracion")
        .order_by(AuditLog.id.desc())
        .first()
    )
    assert evento is not None
    assert "False -> True" in evento.detalle


def test_reenviar_el_mismo_valor_no_genera_evento(test_client, test_db, cliente_con_ruc):
    """El frontend puede reenviar el estado actual; eso no es un cambio y
    no debe ensuciar la auditoría."""
    from backend.models import AuditLog

    test_client.patch("/api/configuracion", json={"usar_sunat": False})
    eventos = test_db.query(AuditLog).filter(AuditLog.accion == "cambiar_configuracion").count()
    assert eventos == 0


# ---------- Efecto sobre Admin > Boletas ----------

def test_sin_emitir_no_hay_ventas_pendientes_de_boleta(
    test_client, test_cliente, test_platos, test_mesas
):
    """EL bug: cada cobro se sumaba a una lista de pendientes que crecía
    para siempre y que nadie iba a resolver — ruido que además esconde un
    pendiente de verdad el día que sí se active la facturación."""
    _crear_y_cobrar_mesa(test_client, test_platos)

    pendientes = test_client.get("/api/facturas/pendientes").json()
    assert pendientes["ventas_sin_boleta"] == []
    assert pendientes["facturas_con_error"] == []


def test_al_activar_la_facturacion_las_ventas_si_aparecen_como_pendientes(
    test_client, test_db, cliente_con_ruc, test_platos, test_mesas
):
    """Contracara: apagar el interruptor no puede volverse una forma de
    esconder boletas que sí había que emitir."""
    cliente_con_ruc.usar_sunat = True
    test_db.commit()

    _crear_y_cobrar_mesa(test_client, test_platos)

    pendientes = test_client.get("/api/facturas/pendientes").json()
    assert len(pendientes["ventas_sin_boleta"]) == 1


# ---------- Permisos ----------

def test_solo_el_admin_toca_la_configuracion(test_client_real_auth, test_cliente):
    from tests.integration.test_endpoints import _crear_staff_y_loguear

    _, token = _crear_staff_y_loguear(test_client_real_auth, "Pedro Mozo", ["mozo"])
    headers = {"Authorization": f"Bearer {token}"}

    assert test_client_real_auth.get("/api/configuracion", headers=headers).status_code == 403
    assert test_client_real_auth.patch(
        "/api/configuracion", json={"usar_sunat": True}, headers=headers,
    ).status_code == 403


def test_sin_sesion_no_se_puede_leer_ni_cambiar(test_client_real_auth, test_cliente):
    assert test_client_real_auth.get("/api/configuracion").status_code == 401
    assert test_client_real_auth.patch(
        "/api/configuracion", json={"usar_sunat": True},
    ).status_code == 401


# ============ ACTIVACIÓN DEL MODO FORMAL (certificado + SOL) ============
#
# Lo que se protege acá no es "que el archivo se guarde": es que un .pfx
# —que permite emitir comprobantes a nombre del restaurante— no termine en
# manos equivocadas, y que la facturación NUNCA quede activada a medias.

# Un .pfx real es una estructura DER, que siempre arranca con SEQUENCE (0x30).
PFX_FALSO = b"\x30\x82\x04\x00" + b"contenido de prueba"
SOL_USUARIO = "MIUSUARIO"
SOL_CLAVE = "miclavesol"
RUC_VALIDO = "10200812234"


def _activar(test_client, pfx=PFX_FALSO, password="clave-secreta",
             sol_usuario=SOL_USUARIO, sol_clave=SOL_CLAVE,
             ruc=RUC_VALIDO, direccion="Av. Lima 123", razon_social=None):
    return test_client.post(
        "/api/configuracion/subir-certificado",
        files={"file": ("certificado.pfx", pfx, "application/x-pkcs12")},
        data={
            "ruc": ruc, "password": password, "direccion_fiscal": direccion,
            "sol_usuario": sol_usuario, "sol_clave": sol_clave,
            **({"razon_social_manual": razon_social} if razon_social is not None else {}),
        },
    )


@pytest.fixture
def certs_tmp(tmp_path, monkeypatch):
    from backend.config import settings
    monkeypatch.setattr(settings, "certs_dir", str(tmp_path))
    return tmp_path


def test_se_guardan_los_TRES_archivos_que_necesita_la_firma(
    test_client, test_db, cliente_con_ruc, certs_tmp
):
    """
    sunat-service necesita certificado.pfx, clave.txt Y sol.txt. Si faltara
    cualquiera, el restaurante quedaría "activado" y fallando en cada cobro
    con SIN_CREDENCIALES_SOL — el escenario de emisiones rotas que esta
    pantalla existe para evitar.
    """
    resp = _activar(test_client)
    assert resp.status_code == 200, resp.text
    assert resp.json()["usar_sunat"] is True

    destino = certs_tmp / cliente_con_ruc.id
    assert (destino / "certificado.pfx").read_bytes() == PFX_FALSO
    assert (destino / "clave.txt").read_text(encoding="utf-8") == "clave-secreta"
    # sol.txt con el formato exacto que espera el contenedor: usuario en la
    # primera línea, clave en la segunda.
    assert (destino / "sol.txt").read_text(encoding="utf-8") == "MIUSUARIO\nmiclavesol\n"

    test_db.refresh(cliente_con_ruc)
    assert cliente_con_ruc.usar_sunat is True


def test_un_sol_incompleto_no_activa_nada(test_client, test_db, cliente_con_ruc, certs_tmp):
    """Unas credenciales SOL incompletas, descubiertas recien al cobrar,
    comprobante con el cliente en la puerta. Se valida acá, que es cuando hay
    alguien mirando la pantalla para corregirlo."""
    resp = _activar(test_client, sol_clave="   ")

    assert resp.status_code == 400
    assert "clave SOL" in resp.json()["detail"]
    test_db.refresh(cliente_con_ruc)
    assert cliente_con_ruc.usar_sunat is False
    # Nada a medias: no quedó ni el certificado suelto.
    assert not list(certs_tmp.iterdir())


def test_sin_datos_fiscales_no_se_acepta_el_certificado(test_client, test_cliente, certs_tmp, monkeypatch):
    """
    Regla estricta: sin RUC resoluble no se activa nada.

    Aceptarlo dejaría al restaurante emitiendo con datos de emisor vacíos.
    Acá el padrón no está disponible y el cliente no tiene razón social, así
    que no hay de dónde sacarla.
    """
    from backend.config import settings
    from backend.utils.padron import cerrar_conexion_del_hilo
    cerrar_conexion_del_hilo()
    monkeypatch.setattr(settings, "padron_db_path", "/no/existe/padron.db")

    resp = _activar(test_client)

    assert resp.status_code == 400
    assert "padrón" in resp.json()["detail"]
    assert not list(certs_tmp.iterdir())


def test_no_se_puede_cambiar_el_RUC_de_un_restaurante_ya_registrado(
    test_client, cliente_con_ruc, certs_tmp
):
    """El certificado se emite A NOMBRE de un RUC: aceptar otro acá dejaría
    los comprobantes firmados por un contribuyente distinto del que declaran."""
    resp = _activar(test_client, ruc="20123456786")

    assert resp.status_code == 400
    assert cliente_con_ruc.ruc in resp.json()["detail"]
    assert not list(certs_tmp.iterdir())


def test_el_certificado_NUNCA_se_guarda_en_la_base_de_datos(
    test_client, test_db, cliente_con_ruc, certs_tmp
):
    """Si alguien se lleva un backup de la BD, no debe llevarse con qué
    facturar. El .pfx, su clave y las credenciales SOL viven solo en el
    volumen de certificados."""
    assert _activar(test_client).status_code == 200

    import sqlalchemy
    filas = test_db.execute(sqlalchemy.text("SELECT * FROM clientes")).mappings().all()
    volcado = str([dict(f) for f in filas])
    assert "clave-secreta" not in volcado
    assert "miclavesol" not in volcado
    assert "contenido de prueba" not in volcado


def test_un_archivo_que_no_es_certificado_se_rechaza(test_client, cliente_con_ruc, certs_tmp):
    """No se confía en la extensión ni en el content-type: los dos los elige
    quien sube el archivo. Se mira la firma binaria."""
    resp = _activar(test_client, pfx=b"<html>esto no es un pfx</html>")

    assert resp.status_code == 400
    assert "certificado" in resp.json()["detail"].lower()
    assert not list(certs_tmp.iterdir())


def test_sin_la_clave_no_se_acepta(test_client, cliente_con_ruc, certs_tmp):
    """Un .pfx sin su clave no sirve para firmar: guardarlo dejaría la
    facturación activada y rota.

    Dos formas de no mandarla, con dos rechazos distintos y ambos correctos:
    el campo ausente lo frena FastAPI (422) y el de puros espacios lo frena
    la ruta (400) — este último NO lo atrapa un simple `if not password`.
    """
    assert _activar(test_client, password="").status_code == 422
    assert _activar(test_client, password="   ").status_code == 400
    assert not list(certs_tmp.iterdir())


def test_sin_sesion_no_se_puede_activar_la_facturacion(test_client_real_auth, certs_tmp):
    resp = test_client_real_auth.post(
        "/api/configuracion/subir-certificado",
        files={"file": ("c.pfx", PFX_FALSO, "application/x-pkcs12")},
        data={"ruc": RUC_VALIDO, "password": "x",
              "sol_usuario": SOL_USUARIO, "sol_clave": SOL_CLAVE},
    )
    assert resp.status_code == 401


def test_el_certificado_va_a_la_carpeta_DEL_TOKEN_no_a_otra(
    test_client, test_db, cliente_con_ruc, certs_tmp
):
    """El cliente_id sale del JWT, nunca del cuerpo: si viniera del payload,
    un admin podría pisarle el certificado a otro restaurante."""
    otro = Cliente(id="otro-restaurante", nombre="Ajeno", email="a@b.com", ruc="20123456786")
    test_db.add(otro)
    test_db.commit()

    assert _activar(test_client).status_code == 200

    assert (certs_tmp / cliente_con_ruc.id / "certificado.pfx").exists()
    assert not (certs_tmp / "otro-restaurante").exists()


def test_al_activar_quedan_bloqueados_los_datos_fiscales(
    test_client, test_db, cliente_con_ruc, certs_tmp
):
    """El frontend usa esto para mostrarlos de solo lectura, en vez de
    ofrecer campos que el backend va a rechazar."""
    assert test_client.get("/api/configuracion").json()["datos_fiscales_bloqueados"] is False

    datos = _activar(test_client).json()
    assert datos["datos_fiscales_bloqueados"] is True
    assert datos["razon_social"] == "Pollería Fogones"
    assert datos["direccion_fiscal"] == "Av. Lima 123"

    # Apagar el interruptor los libera: un candado permanente convertiría un
    # tipeo en un callejón sin salida.
    test_client.patch("/api/configuracion", json={"usar_sunat": False})
    assert test_client.get("/api/configuracion").json()["datos_fiscales_bloqueados"] is False


def test_sin_padron_instalado_se_puede_activar_igual(
    test_client, test_db, test_cliente, certs_tmp, monkeypatch
):
    """
    El padrón son 1,6 GB y varios minutos de carga. Que no esté no puede
    impedir activar la facturación: es un dato de comodidad, no un requisito.

    Antes esto era un callejón sin salida — el formulario consultaba el
    padrón, recibía 503 y no dejaba avanzar, aunque el backend ni siquiera
    necesitaba ese dato.
    """
    from backend.config import settings
    from backend.utils.padron import cerrar_conexion_del_hilo

    cerrar_conexion_del_hilo()
    monkeypatch.setattr(settings, "padron_db_path", "/no/existe/padron.db")
    test_cliente.ruc = RUC_VALIDO          # sin razón social guardada
    test_db.commit()

    resp = _activar(test_client, razon_social="CEVICHERIA EL PUERTO SAC")

    assert resp.status_code == 200, resp.text
    test_db.refresh(test_cliente)
    assert test_cliente.usar_sunat is True
    assert test_cliente.razon_social == "CEVICHERIA EL PUERTO SAC"


def test_el_RUC_FICTICIO_de_BETA_se_puede_activar(
    test_client, test_db, test_cliente, certs_tmp, padron_vacio
):
    """
    20000000001 es el RUC del ambiente de pruebas de SUNAT: es FICTICIO y no
    figura en el padrón real — ni va a figurar nunca, por más veces que se
    cargue el archivo.

    Sin poder escribir la razón social a mano, el tenant de pruebas no se
    podría activar jamás y no habría forma de probar contra BETA.
    """
    test_cliente.ruc = "20000000001"
    test_cliente.razon_social = None
    test_db.commit()

    resp = _activar(test_client, ruc="20000000001",
                    razon_social="EMPRESA DE PRUEBAS SUNAT")

    assert resp.status_code == 200, resp.text
    test_db.refresh(test_cliente)
    assert test_cliente.usar_sunat is True


def test_sin_razon_social_por_ningun_lado_se_rechaza_pidiendola(
    test_client, test_db, test_cliente, certs_tmp, padron_vacio
):
    """SUNAT no acepta un comprobante sin razón social del emisor, así que
    no se puede inventar. El mensaje invita a escribirla."""
    test_cliente.ruc = RUC_VALIDO
    test_cliente.razon_social = None
    test_db.commit()

    resp = _activar(test_client, razon_social="")

    assert resp.status_code == 400
    assert "razón social" in resp.json()["detail"]
    # No se escribió NINGÚN certificado. Se mira la carpeta del tenant y no
    # el directorio entero: padron_vacio comparte tmp_path y deja su propio
    # archivo ahí, que no tiene nada que ver con esto.
    assert not (certs_tmp / test_cliente.id).exists()


@pytest.fixture
def padron_vacio(tmp_path, monkeypatch):
    """Un padrón REAL pero sin el RUC buscado — distinto de 'no instalado'."""
    import sqlite3

    from backend.config import settings
    from backend.utils.padron import cerrar_conexion_del_hilo

    ruta = tmp_path / "padron.db"
    conn = sqlite3.connect(ruta)
    conn.execute("CREATE TABLE padron (ruc TEXT, nombre TEXT, estado TEXT, condicion TEXT)")
    conn.execute("CREATE UNIQUE INDEX idx_ruc ON padron(ruc)")
    conn.commit()
    conn.close()

    cerrar_conexion_del_hilo()
    monkeypatch.setattr(settings, "padron_db_path", str(ruta))
    yield ruta
    cerrar_conexion_del_hilo()
