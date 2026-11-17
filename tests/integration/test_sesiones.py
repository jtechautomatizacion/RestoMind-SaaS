"""
Sesión de la app web: access token corto en memoria + refresh rotativo en
cookie HttpOnly (backend/sesiones.py). Mismo contrato que Sac-Geo.

La cookie es `Secure`, y el TestClient habla por http://testserver: su jar no
la guardaría ni la reenviaría. Por eso cada test la lee del Set-Cookie y la
manda a mano en la cabecera Cookie, igual que haría el navegador.
"""

from datetime import datetime, timedelta

from backend.auth import decodificar_token
from backend.models import SesionRefresh, Usuario
from backend.sesiones import COOKIE_REFRESH, RUTA_COOKIE
from tests.conftest import TEST_USUARIO_EMAIL, TEST_USUARIO_PASSWORD

MODO_WEB = {"X-Sesion": "cookie"}


def _cookie(resp) -> str | None:
    for linea in resp.headers.get_list("set-cookie"):
        if linea.startswith(f"{COOKIE_REFRESH}="):
            return linea.split(";", 1)[0].split("=", 1)[1].strip('"') or None
    return None


def _atributos(resp) -> str:
    return next(l for l in resp.headers.get_list("set-cookie") if l.startswith(COOKIE_REFRESH)).lower()


def _login_web(client):
    r = client.post("/api/auth/login", json={"email": TEST_USUARIO_EMAIL, "password": TEST_USUARIO_PASSWORD}, headers=MODO_WEB)
    assert r.status_code == 200, r.text
    return r


def _refresh(client, cookie):
    return client.post("/api/auth/sesion/refresh", headers={"Cookie": f"{COOKIE_REFRESH}={cookie}"})


def test_login_web_entrega_cookie_httponly_secure_strict_y_token_corto(test_client_real_auth, test_cliente):
    r = _login_web(test_client_real_auth)
    attrs = _atributos(r)
    assert "httponly" in attrs and "secure" in attrs and "samesite=strict" in attrs
    assert f"path={RUTA_COOKIE}" in attrs
    payload = decodificar_token(r.json()["access_token"])
    assert payload["sid"]
    assert payload["exp"] - payload["iat"] <= 15 * 60
    # El refresh NUNCA viaja en el cuerpo
    assert _cookie(r) not in r.text


def test_login_sin_modo_web_sigue_como_siempre_para_el_apk(test_client_real_auth, test_cliente):
    r = test_client_real_auth.post("/api/auth/login", json={"email": TEST_USUARIO_EMAIL, "password": TEST_USUARIO_PASSWORD})
    assert r.status_code == 200
    assert _cookie(r) is None
    payload = decodificar_token(r.json()["access_token"])
    assert "sid" not in payload
    assert payload["exp"] - payload["iat"] == 12 * 3600


def test_refresh_rota_la_cookie_y_devuelve_identidad(test_client_real_auth, test_cliente):
    c1 = _cookie(_login_web(test_client_real_auth))
    r = _refresh(test_client_real_auth, c1)
    assert r.status_code == 200
    c2 = _cookie(r)
    assert c2 and c2 != c1
    assert r.json()["usuario"]["email"] == TEST_USUARIO_EMAIL
    token = r.json()["access_token"]
    assert test_client_real_auth.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"}).status_code == 200


def test_reusar_un_refresh_ya_rotado_revoca_la_sesion_entera(test_client_real_auth, test_cliente, test_db):
    c1 = _cookie(_login_web(test_client_real_auth))
    c2 = _cookie(_refresh(test_client_real_auth, c1))
    # Alguien presenta el viejo: es reuso
    r = _refresh(test_client_real_auth, c1)
    assert r.status_code == 401
    # ...y el legítimo tampoco sirve más
    assert _refresh(test_client_real_auth, c2).status_code == 401
    sesion = test_db.query(SesionRefresh).one()
    assert sesion.motivo_revocacion == "reuso"


def test_logout_revoca_y_borra_la_cookie(test_client_real_auth, test_cliente):
    c1 = _cookie(_login_web(test_client_real_auth))
    r = test_client_real_auth.post("/api/auth/sesion/logout", headers={"Cookie": f"{COOKIE_REFRESH}={c1}"})
    assert r.status_code == 204
    assert "max-age=0" in _atributos(r)
    assert _refresh(test_client_real_auth, c1).status_code == 401


def test_logout_sin_cookie_es_idempotente(test_client_real_auth, test_cliente):
    assert test_client_real_auth.post("/api/auth/sesion/logout").status_code == 204


def test_refresh_sin_cookie_o_basura_da_401(test_client_real_auth, test_cliente):
    assert test_client_real_auth.post("/api/auth/sesion/refresh").status_code == 401
    assert _refresh(test_client_real_auth, "no-es-un-token").status_code == 401
    assert _refresh(test_client_real_auth, "00000000-0000-0000-0000-000000000000.x").status_code == 401


def test_sesion_expirada_no_se_renueva(test_client_real_auth, test_cliente, test_db):
    c1 = _cookie(_login_web(test_client_real_auth))
    sesion = test_db.query(SesionRefresh).one()
    sesion.expira_en = datetime.utcnow() - timedelta(seconds=1)
    test_db.commit()
    assert _refresh(test_client_real_auth, c1).status_code == 401


def test_cuenta_desactivada_no_renueva(test_client_real_auth, test_cliente, test_db):
    c1 = _cookie(_login_web(test_client_real_auth))
    usuario = test_db.query(Usuario).filter(Usuario.email == TEST_USUARIO_EMAIL).one()
    usuario.estado = "inactivo"
    test_db.commit()
    assert _refresh(test_client_real_auth, c1).status_code == 401


def test_cambiar_la_contrasena_cierra_las_sesiones_web(test_client_real_auth, test_cliente):
    r = _login_web(test_client_real_auth)
    c1, token = _cookie(r), r.json()["access_token"]
    cambio = test_client_real_auth.patch(
        "/api/usuarios/me/password",
        json={"password_actual": TEST_USUARIO_PASSWORD, "nueva_password": "otraclave99"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert cambio.status_code == 200, cambio.text
    assert _refresh(test_client_real_auth, c1).status_code == 401


def test_staff_tambien_abre_sesion_web(test_client_real_auth, test_cliente):
    admin = test_client_real_auth.post("/api/auth/login", json={"email": TEST_USUARIO_EMAIL, "password": TEST_USUARIO_PASSWORD})
    auth = {"Authorization": f"Bearer {admin.json()['access_token']}"}
    creado = test_client_real_auth.post("/api/usuarios/staff", json={"nombre": "Rosa", "password": "clave123", "roles": ["mozo"]}, headers=auth)
    assert creado.status_code in (200, 201), creado.text
    codigo = creado.json()["celular"]
    r = test_client_real_auth.post("/api/auth/login-staff", json={"celular": codigo, "password": "clave123"}, headers=MODO_WEB)
    assert r.status_code == 200
    c1 = _cookie(r)
    renovado = _refresh(test_client_real_auth, c1)
    assert renovado.status_code == 200
    assert renovado.json()["usuario"]["nombre"] == "Rosa"
