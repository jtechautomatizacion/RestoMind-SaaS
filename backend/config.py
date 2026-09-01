from pydantic import model_validator
from pydantic_settings import BaseSettings
from typing import List

_CORS_ORIGINS_DEFAULT = ["http://localhost:3000", "http://localhost:8000"]


class Settings(BaseSettings):
    # Environment
    environment: str = "development"
    debug: bool = True

    # Sin default a propósito: si SECRET_KEY no está en el entorno/.env, la
    # app debe fallar al arrancar, no firmar tokens JWT con un valor público
    # que cualquiera puede leer en el código fuente. Un despliegue nuevo sin
    # este valor configurado emitiría tokens de admin/superadmin forjables.
    secret_key: str

    # Database
    database_url: str = "sqlite:///./restomind.db"
    database_echo: bool = False

    # Multi-tenant (MVP: sin login todavía, cliente por defecto)
    default_cliente_id: str = "rest-001"

    # CORS
    cors_origins: List[str] = list(_CORS_ORIGINS_DEFAULT)

    # Server
    host: str = "0.0.0.0"
    port: int = 8000

    # Claude API (futuro)
    anthropic_api_key: str = ""

    # Facturación electrónica SUNAT — dos formas de emitir, elegidas por
    # 'emisor_facturacion'. Es config de ESTA instalación física (qué hay
    # en la PC de la caja), no del tenant en la nube — a diferencia del RUC
    # (que sí vive en Cliente.ruc porque cada restaurante tiene el suyo),
    # esto puede ser distinto en cada máquina donde corra RestoMind.
    #
    # "sfs_local" (default, costo S/ 0): el Facturador SUNAT oficial (u
    # homólogo) corre en la misma PC, vigilando una carpeta. RestoMind
    # escribe ahí los archivos .cab/.det; el propio Facturador es quien
    # habla con SUNAT — RestoMind NO se entera si SUNAT aceptó o rechazó
    # (ver backend/utils/sfs_export.py y el estado 'generado_localmente').
    #
    # "facturacion_pe" (de pago, S/ 0.20/boleta): integración por API ya
    # implementada (backend/utils/facturacion_pe.py) — queda lista para
    # cuando el volumen justifique confirmación automática de SUNAT en
    # vez de depender del Facturador local.
    emisor_facturacion: str = "sfs_local"

    # Carpeta local donde el Facturador SUNAT (SFS) vigila archivos nuevos.
    # Sin valor, /api/facturas/generar debe rechazar con error claro antes
    # de intentar escribir en ningún lado — nunca asumir una ruta por
    # defecto tipo "C:/sfs/DATA", porque escribir en el lugar equivocado
    # en silencio es peor que fallar ruidosamente.
    sfs_export_dir: str = ""
    # Los formatos planos de SUNAT (ej. PLE) tradicionalmente usan Latin-1,
    # no UTF-8 — CONFIRMAR contra el manual del Facturador que estés usando
    # antes de ir a producción; un encoding equivocado corrompe tildes/ñ.
    sfs_export_encoding: str = "latin-1"

    facturacion_pe_api_key: str = ""
    facturacion_pe_url: str = "https://api.facturacion.pe/v1"

    # Notificaciones push (Firebase Cloud Messaging) — avisan a jefe_cocina
    # cuando entra una comanda nueva, incluso con la app minimizada.
    # firebase_credentials_json: ruta al archivo de credenciales de cuenta de
    # servicio que se descarga desde Firebase Console > Configuración del
    # proyecto > Cuentas de servicio > "Generar nueva clave privada".
    # Sin este valor, el envío de notificaciones se salta en silencio (ver
    # utils/push_notifications.py) — la app funciona igual, solo sin avisos.
    firebase_credentials_json: str = ""
    # firebase_vapid_key: la "Clave pública" que Firebase Console genera en
    # Configuración del proyecto > Cloud Messaging > Certificados push web.
    # No es secreta (se sirve al navegador), pero vive en el backend para no
    # tener que tocar el HTML/JS del frontend al configurarla.
    firebase_vapid_key: str = ""

    # SMTP (para envío de emails)
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from_email: str = ""
    smtp_from_name: str = "RestoMind"
    app_url: str = "http://localhost:8000"

    class Config:
        env_file = ".env"
        case_sensitive = False

    @model_validator(mode="after")
    def _validar_produccion(self) -> "Settings":
        """En producción, un CORS mal configurado es tan grave como un
        SECRET_KEY hardcodeado: "*" o los orígenes de desarrollo por defecto
        dejarían que cualquier sitio web llame a la API usando el token que
        el navegador de la víctima tiene guardado. Igual que con SECRET_KEY,
        preferimos que la app no arranque a que arranque insegura."""
        if self.environment != "production":
            return self

        if self.debug:
            raise ValueError(
                "DEBUG no puede estar activo en producción (expone stack traces detallados)."
            )
        if not self.cors_origins or "*" in self.cors_origins:
            raise ValueError(
                "CORS_ORIGINS debe listar los dominios reales del frontend en producción, no '*'."
            )
        if self.cors_origins == _CORS_ORIGINS_DEFAULT:
            raise ValueError(
                "CORS_ORIGINS sigue en los valores de desarrollo (localhost) — "
                "configura los dominios reales en el .env de producción."
            )
        return self


settings = Settings()
