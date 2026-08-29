from pydantic_settings import BaseSettings
from typing import List


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
    cors_origins: List[str] = ["http://localhost:3000", "http://localhost:8000"]

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


settings = Settings()
