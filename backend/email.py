"""
Envío de emails via SMTP (Gmail).
"""

import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from backend.config import settings


def enviar_email_credenciales(
    destinatario: str,
    nombre_admin: str,
    email_login: str,
    password: str,
    nombre_restaurante: str,
) -> bool:
    """
    Envía email de bienvenida con credenciales de acceso.

    Returns: True si se envió exitosamente, False si falló (pero no bloquea la creación del restaurante)
    """
    if not settings.smtp_user or not settings.smtp_password:
        # SMTP no configurado — skip silenciosamente
        return False

    try:
        # Crear mensaje
        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"Acceso a RestoMind — {nombre_restaurante}"
        msg["From"] = f"{settings.smtp_from_name} <{settings.smtp_from_email}>"
        msg["To"] = destinatario

        # HTML del email
        html = f"""
        <html>
            <body style="font-family: Arial, sans-serif; color: #333;">
                <div style="max-width: 600px; margin: 0 auto;">
                    <h2 style="color: #FF5722;">Bienvenido a RestoMind</h2>
                    <p>¡Hola <strong>{nombre_admin}</strong>!</p>
                    <p>Se ha creado tu cuenta de administrador para <strong>{nombre_restaurante}</strong>.</p>

                    <div style="background: #f5f5f5; padding: 20px; border-radius: 8px; margin: 20px 0;">
                        <h3 style="margin-top: 0;">Tus credenciales de acceso:</h3>
                        <p><strong>Email:</strong> <code style="background: #e0e0e0; padding: 4px 8px; border-radius: 4px;">{email_login}</code></p>
                        <p><strong>Contraseña:</strong> <code style="background: #e0e0e0; padding: 4px 8px; border-radius: 4px;">{password}</code></p>
                    </div>

                    <p>
                        <a href="{settings.app_url}/" style="display: inline-block; background: #FF5722; color: white; padding: 12px 24px; border-radius: 4px; text-decoration: none; font-weight: bold;">
                            Acceder a RestoMind
                        </a>
                    </p>

                    <hr style="border: none; border-top: 1px solid #ddd; margin: 30px 0;">
                    <p style="color: #999; font-size: 12px;">
                        Por tu seguridad, no compartas estas credenciales. Si no solicitaste este acceso, contacta al administrador del sistema.
                    </p>
                </div>
            </body>
        </html>
        """

        msg.attach(MIMEText(html, "html"))

        # Conectar a Gmail y enviar
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as server:
            server.starttls()
            server.login(settings.smtp_user, settings.smtp_password)
            server.send_message(msg)

        return True

    except Exception as e:
        # Log del error (en producción, usar logging module)
        print(f"[ERROR] No se pudo enviar email a {destinatario}: {str(e)}")
        return False
