"""
Auditoría del envío de emails al dar de alta un restaurante.

Origen: dando de alta restaurantes de prueba con dominios inventados
(carlos@buensabor.pe) empezaron a llegar rebotes reales a la bandeja de la
cuenta que envía. Al revisarlo apareció algo peor que el rebote: el correo
llevaba la contraseña en texto plano, así que el aviso de rebote —que
incluye una copia del mensaje original— la devolvía también.
"""

from unittest.mock import patch

from backend.config import settings


def _login_superadmin(client):
    from tests.conftest import TEST_SUPERADMIN_EMAIL, TEST_SUPERADMIN_PASSWORD
    resp = client.post('/api/superadmin/login', json={
        "email": TEST_SUPERADMIN_EMAIL, "password": TEST_SUPERADMIN_PASSWORD,
    })
    return resp.json()["access_token"]


def _crear_restaurante(client, token, **overrides):
    payload = {
        "nombre": "Pollería El Buen Sabor",
        "email": "contacto@buensabor.pe",
        "num_mesas": 3,
        "admin_nombre": "Carlos",
        "admin_email": "carlos@buensabor.pe",
        "admin_password": "clave123456",
    }
    payload.update(overrides)
    return client.post(
        '/api/superadmin/clientes',
        headers={"Authorization": f"Bearer {token}"},
        json=payload,
    )


# ---------- La contraseña nunca sale por correo ----------

def test_el_email_de_bienvenida_no_lleva_la_contrasena(monkeypatch):
    """EL hallazgo grave.

    El correo incluía la contraseña en texto plano. Eso queda para siempre
    en la bandeja del destinatario y en 'Enviados' del remitente, viaja sin
    cifrado extremo a extremo y, si el mensaje rebota, el aviso de rebote
    devuelve una copia del original — o sea que la contraseña vuelve a la
    bandeja de quien envió. Y no aportaba nada: el superadmin ESCRIBE esa
    contraseña en el formulario, así que ya la conoce.
    """
    from backend.email import enviar_email_credenciales

    monkeypatch.setattr(settings, "smtp_user", "envia@test.local")
    monkeypatch.setattr(settings, "smtp_password", "secreto-smtp")
    monkeypatch.setattr(settings, "environment", "production")

    with patch('smtplib.SMTP') as mock_smtp:
        enviar_email_credenciales(
            destinatario="carlos@buensabor.pe",
            nombre_admin="Carlos",
            email_login="carlos@buensabor.pe",
            nombre_restaurante="Pollería El Buen Sabor",
        )

    servidor = mock_smtp.return_value.__enter__.return_value
    mensaje = servidor.send_message.call_args[0][0]
    cuerpo = mensaje.as_string()

    assert "carlos@buensabor.pe" in cuerpo, "el correo debe decir cuál es el usuario"
    assert "clave123456" not in cuerpo
    # La firma ya ni siquiera acepta una contraseña: no hay forma de
    # filtrarla por accidente desde un call site nuevo.
    import inspect
    assert "password" not in inspect.signature(enviar_email_credenciales).parameters


# ---------- No se envía nada fuera de producción ----------

def test_en_desarrollo_no_se_envia_ningun_correo(monkeypatch):
    """Cada alta de prueba con un dominio inventado generaba un rebote real
    contra la reputación de la cuenta que envía. En desarrollo no hay razón
    para tocar la red: se registra en el log y listo."""
    from backend.email import enviar_email_credenciales

    monkeypatch.setattr(settings, "smtp_user", "envia@test.local")
    monkeypatch.setattr(settings, "smtp_password", "secreto-smtp")
    monkeypatch.setattr(settings, "environment", "development")

    with patch('smtplib.SMTP') as mock_smtp:
        enviado = enviar_email_credenciales(
            destinatario="carlos@buensabor.pe",
            nombre_admin="Carlos",
            email_login="carlos@buensabor.pe",
            nombre_restaurante="Pollería El Buen Sabor",
        )

    assert enviado is False
    mock_smtp.assert_not_called(), "en desarrollo no se debe abrir conexión SMTP"


def test_sin_smtp_configurado_no_se_intenta_enviar(monkeypatch):
    from backend.email import enviar_email_credenciales

    monkeypatch.setattr(settings, "smtp_user", "")
    monkeypatch.setattr(settings, "smtp_password", "")

    with patch('smtplib.SMTP') as mock_smtp:
        assert enviar_email_credenciales(
            destinatario="x@y.com", nombre_admin="X",
            email_login="x@y.com", nombre_restaurante="R",
        ) is False
    mock_smtp.assert_not_called()


def test_un_fallo_de_smtp_no_tumba_el_alta_del_restaurante(monkeypatch):
    """El correo es un extra: si el servidor SMTP está caído, el restaurante
    se crea igual — mismo criterio que las notificaciones push."""
    from backend.email import enviar_email_credenciales

    monkeypatch.setattr(settings, "smtp_user", "envia@test.local")
    monkeypatch.setattr(settings, "smtp_password", "secreto-smtp")
    monkeypatch.setattr(settings, "environment", "production")

    with patch('smtplib.SMTP', side_effect=OSError("servidor caído")):
        assert enviar_email_credenciales(
            destinatario="x@y.com", nombre_admin="X",
            email_login="x@y.com", nombre_restaurante="R",
        ) is False


# ---------- Un email mal tipeado no llega nunca a SMTP ----------

def test_un_email_de_admin_invalido_se_rechaza_antes_de_enviar(test_client_real_auth, test_superadmin):
    """`admin_email` era un str suelto: cualquier cosa llegaba hasta el
    envío, y un destinatario inválido rebota. Los rebotes son una de las
    señales que usa Google para limitar la cuenta que envía."""
    token = _login_superadmin(test_client_real_auth)

    for invalido in ("sin-arroba", "sin@dominio", "espacio @dominio.com", "@dominio.com"):
        resp = _crear_restaurante(test_client_real_auth, token, admin_email=invalido)
        assert resp.status_code == 422, f"se aceptó el email inválido '{invalido}'"


def test_el_email_del_admin_se_guarda_normalizado(test_client_real_auth, test_superadmin):
    """Mayúsculas y espacios alrededor se limpian, para que el mismo correo
    escrito de dos formas no cree dos cuentas distintas."""
    token = _login_superadmin(test_client_real_auth)
    resp = _crear_restaurante(
        test_client_real_auth, token, admin_email="  Carlos@BuenSabor.PE  ",
    )
    assert resp.status_code == 201

    admin = test_client_real_auth.get(
        f'/api/superadmin/clientes/{resp.json()["id"]}/admin',
        headers={"Authorization": f"Bearer {token}"},
    )
    assert admin.json()["email"] == "carlos@buensabor.pe"
