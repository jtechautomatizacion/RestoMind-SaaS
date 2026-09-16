"""
Envío de emails via SMTP (Gmail).

Dos reglas de seguridad que conviene no perder de vista:

1. NUNCA se manda una contraseña por email. El correo queda para siempre en
   la bandeja del destinatario y en "Enviados" del remitente, viaja entre
   servidores sin cifrado extremo a extremo, y —lo que se ve poco— si el
   mensaje REBOTA, el aviso de rebote incluye una copia del original: la
   contraseña termina también en la bandeja de quien envió. Además no
   aportaba nada: el superadmin ESCRIBE esa contraseña en el formulario al
   dar de alta el restaurante, así que ya la conoce y puede comunicarla por
   donde prefiera. Era riesgo puro sin beneficio.

2. Fuera de producción no se envía nada de verdad: se registra en el log.
   Dar de alta restaurantes de prueba con dominios inventados
   (carlos@buensabor.pe) generaba rebotes reales contra la cuenta de Gmail,
   y una tasa alta de rebotes es una de las señales que usa Google para
   limitar o suspender el envío de una cuenta. En desarrollo no hay ninguna
   razón para tocar la red.
"""

import logging
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from backend.config import settings

logger = logging.getLogger(__name__)

# Paleta del tema claro de la app (frontend/css/style.css). Los correos se
# abren mayormente en clientes con fondo claro, así que el mensaje usa esa
# variante para que se reconozca como la misma marca que la app.
_AZUL = "#1B5EA8"
_TEXTO = "#161D26"
_SUAVE = "#5C6773"
_BORDE = "#DCE3EA"
_FONDO = "#F4F6F8"


def _boton(url: str, etiqueta: str, fondo: str, color_texto: str, borde: str = "") -> str:
    """Botón a prueba de Outlook.

    Un `<a>` con padding alcanza en casi todos los clientes, pero Outlook de
    escritorio usa el motor de Word: ignora el padding de un inline-block y
    deja el color de fondo pegado al texto, sin forma de botón. La tabla de
    una celda con `bgcolor` sí la respeta, y en el resto de los clientes se
    ve igual.
    """
    estilo_borde = f"border: 1px solid {borde};" if borde else ""
    return f"""
    <table role="presentation" cellpadding="0" cellspacing="0" border="0">
        <tr>
            <td align="center" bgcolor="{fondo}"
                style="border-radius: 8px; {estilo_borde}">
                <a href="{url}" target="_blank"
                   style="display: inline-block; padding: 14px 28px;
                          font-family: -apple-system, 'Segoe UI', Roboto, Arial, sans-serif;
                          font-size: 15px; font-weight: 700; line-height: 1;
                          color: {color_texto}; text-decoration: none;">{etiqueta}</a>
            </td>
        </tr>
    </table>"""


def _armar_html(nombre_admin: str, email_login: str, nombre_restaurante: str) -> str:
    """
    El cuerpo del correo.

    Va TODO en tablas y con estilos EN LÍNEA a propósito: Gmail descarta los
    bloques `<style>` en buena parte de sus vistas, y Outlook de escritorio
    renderiza con Word — sin flexbox, sin grid, sin hojas externas. Un
    maquetado moderno se ve perfecto en la prueba y descuadrado justo en el
    cliente que usa el contador del restaurante.
    """
    # La sección del APK aparece solo si hay enlace configurado: sin esto,
    # un restaurante dado de alta antes de que exista el instalable recibiría
    # un botón que lleva a una carpeta vacía.
    bloque_apk = ""
    if settings.apk_url:
        bloque_apk = f"""
            <tr>
                <td style="padding: 0 32px 8px 32px;">
                    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"
                           style="border: 1px solid {_BORDE}; border-radius: 10px;">
                        <tr>
                            <td style="padding: 20px 22px;">
                                <p style="margin: 0 0 6px 0; font-size: 15px; font-weight: 700; color: {_TEXTO};">
                                    Instalar en tu celular o tablet
                                </p>
                                <p style="margin: 0 0 16px 0; font-size: 14px; line-height: 1.5; color: {_SUAVE};">
                                    Para usarla como aplicación, sin abrir el navegador cada vez.
                                </p>
                                {_boton(settings.apk_url, "Descargar la app", "#FFFFFF", _AZUL, _BORDE)}
                            </td>
                        </tr>
                    </table>
                </td>
            </tr>"""

    return f"""<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Acceso a RestoMind</title>
</head>
<body style="margin: 0; padding: 0; background-color: {_FONDO};">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"
       style="background-color: {_FONDO}; padding: 24px 12px;">
    <tr>
        <td align="center">
            <table role="presentation" width="600" cellpadding="0" cellspacing="0" border="0"
                   style="max-width: 600px; width: 100%; background-color: #FFFFFF;
                          border-radius: 14px; overflow: hidden;
                          font-family: -apple-system, 'Segoe UI', Roboto, Arial, sans-serif;">

                <tr>
                    <td bgcolor="{_AZUL}" style="padding: 26px 32px;">
                        <p style="margin: 0; font-size: 20px; font-weight: 800;
                                  letter-spacing: -0.3px; color: #FFFFFF;">RestoMind</p>
                    </td>
                </tr>

                <tr>
                    <td style="padding: 32px 32px 8px 32px;">
                        <p style="margin: 0 0 14px 0; font-size: 19px; font-weight: 700; color: {_TEXTO};">
                            Hola {nombre_admin}
                        </p>
                        <p style="margin: 0 0 24px 0; font-size: 15px; line-height: 1.6; color: {_SUAVE};">
                            Tu cuenta de administrador para
                            <strong style="color: {_TEXTO};">{nombre_restaurante}</strong>
                            ya está lista.
                        </p>
                    </td>
                </tr>

                <tr>
                    <td style="padding: 0 32px 24px 32px;">
                        <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"
                               style="background-color: {_FONDO}; border-radius: 10px;">
                            <tr>
                                <td style="padding: 20px 22px;">
                                    <p style="margin: 0 0 8px 0; font-size: 11px; font-weight: 700;
                                              letter-spacing: 1.2px; text-transform: uppercase; color: {_SUAVE};">
                                        Tu usuario
                                    </p>
                                    <p style="margin: 0 0 16px 0; font-size: 16px; font-weight: 700;
                                              color: {_TEXTO}; word-break: break-all;">
                                        {email_login}
                                    </p>
                                    <p style="margin: 0; font-size: 13px; line-height: 1.55; color: {_SUAVE};
                                              border-top: 1px solid {_BORDE}; padding-top: 14px;">
                                        La contraseña te la entrega por separado quien creó tu cuenta.
                                        Nunca la enviamos por correo.
                                    </p>
                                </td>
                            </tr>
                        </table>
                    </td>
                </tr>

                <tr>
                    <td style="padding: 0 32px 24px 32px;">
                        {_boton(settings.app_url + "/static/index.html", "Entrar a RestoMind", _AZUL, "#FFFFFF")}
                    </td>
                </tr>
{bloque_apk}
                <tr>
                    <td style="padding: 24px 32px 28px 32px; border-top: 1px solid {_BORDE};">
                        <p style="margin: 0; font-size: 12px; line-height: 1.55; color: {_SUAVE};">
                            Si no esperabas este acceso, avisale a quien administra el sistema.
                        </p>
                    </td>
                </tr>

            </table>
        </td>
    </tr>
</table>
</body>
</html>"""


def enviar_email_credenciales(
    destinatario: str,
    nombre_admin: str,
    email_login: str,
    nombre_restaurante: str,
) -> bool:
    """
    Envía el email de bienvenida con el usuario de acceso — NO la contraseña
    (ver regla 1 en el docstring del módulo): esa la comunica el superadmin
    por el canal que elija.

    Returns: True si se envió, False si no (SMTP sin configurar, entorno de
    desarrollo, o error de envío). Nunca lanza: que falle un correo no puede
    tumbar el alta de un restaurante.
    """
    if not settings.smtp_user or not settings.smtp_password:
        # SMTP no configurado — no es un error: el alta del restaurante no
        # depende del correo. Pero en PRODUCCIÓN sí conviene que quede
        # registrado: el envío corre como background task y su resultado se
        # descarta (ver superadmin.py), así que sin esta línea la falta de
        # configuración no deja rastro en ningún lado y el problema recién
        # aparece cuando el cliente avisa que nunca recibió su acceso.
        if settings.environment == "production":
            logger.warning(
                "[EMAIL] NO se envió la bienvenida a %s: faltan SMTP_USER/SMTP_PASSWORD "
                "en el .env. El restaurante quedó creado igual.",
                destinatario,
            )
        return False

    # En desarrollo se registra en el log en vez de enviar: los restaurantes
    # de prueba suelen tener dominios inventados, y cada uno de esos rebotes
    # cuenta contra la reputación de la cuenta que envía (ver regla 2).
    if settings.environment != "production":
        logger.info(
            "[EMAIL] (no enviado: entorno '%s') Bienvenida para %s <%s> — restaurante '%s'",
            settings.environment, nombre_admin, destinatario, nombre_restaurante,
        )
        return False

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"Acceso a RestoMind — {nombre_restaurante}"
        msg["From"] = f"{settings.smtp_from_name} <{settings.smtp_from_email}>"
        msg["To"] = destinatario

        html = _armar_html(nombre_admin, email_login, nombre_restaurante)

        msg.attach(MIMEText(html, "html"))

        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as server:
            server.starttls()
            server.login(settings.smtp_user, settings.smtp_password)
            server.send_message(msg)

        return True

    except Exception as e:
        logger.error("[EMAIL] No se pudo enviar a %s: %s", destinatario, e)
        return False
