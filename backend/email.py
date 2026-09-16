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

        html = f"""
        <html>
            <body style="font-family: Arial, sans-serif; color: #333;">
                <div style="max-width: 600px; margin: 0 auto;">
                    <h2 style="color: #FF5722;">Bienvenido a RestoMind</h2>
                    <p>¡Hola <strong>{nombre_admin}</strong>!</p>
                    <p>Se ha creado tu cuenta de administrador para <strong>{nombre_restaurante}</strong>.</p>

                    <div style="background: #f5f5f5; padding: 20px; border-radius: 8px; margin: 20px 0;">
                        <h3 style="margin-top: 0;">Tu usuario de acceso:</h3>
                        <p><code style="background: #e0e0e0; padding: 4px 8px; border-radius: 4px;">{email_login}</code></p>
                        <p style="margin-bottom: 0; color: #666; font-size: 14px;">
                            La contraseña te la entrega por separado quien creó tu cuenta.
                            Nunca la enviamos por correo.
                        </p>
                    </div>

                    <p>
                        <a href="{settings.app_url}/" style="display: inline-block; background: #FF5722; color: white; padding: 12px 24px; border-radius: 4px; text-decoration: none; font-weight: bold;">
                            Acceder a RestoMind
                        </a>
                    </p>

                    <hr style="border: none; border-top: 1px solid #ddd; margin: 30px 0;">
                    <p style="color: #999; font-size: 12px;">
                        Si no solicitaste este acceso, contacta al administrador del sistema.
                    </p>
                </div>
            </body>
        </html>
        """

        msg.attach(MIMEText(html, "html"))

        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as server:
            server.starttls()
            server.login(settings.smtp_user, settings.smtp_password)
            server.send_message(msg)

        return True

    except Exception as e:
        logger.error("[EMAIL] No se pudo enviar a %s: %s", destinatario, e)
        return False
