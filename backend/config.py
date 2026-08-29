from pydantic_settings import BaseSettings
from typing import List


class Settings(BaseSettings):
    # Environment
    environment: str = "development"
    debug: bool = True
    secret_key: str = "your-secret-key-change-in-production"

    # Database
    database_url: str = "sqlite:///./restomind.db"
    database_echo: bool = True

    # CORS
    cors_origins: List[str] = ["http://localhost:3000", "http://localhost:8000"]

    # Server
    host: str = "0.0.0.0"
    port: int = 8000

    # Claude API (futuro)
    anthropic_api_key: str = ""

    class Config:
        env_file = ".env"
        case_sensitive = False


settings = Settings()
