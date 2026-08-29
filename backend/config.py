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
