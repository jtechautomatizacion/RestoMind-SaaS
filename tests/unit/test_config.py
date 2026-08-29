"""
Tests unitarios para la configuración de la app.
"""

import pytest
from pydantic import ValidationError

from backend.config import Settings


def test_settings_falla_sin_secret_key(monkeypatch):
    """La app no debe poder arrancar con el secreto JWT hardcodeado que
    tenía antes por defecto — si SECRET_KEY no está en el entorno, debe
    fallar al instanciar Settings(), no caer en un valor público conocido."""
    monkeypatch.delenv("SECRET_KEY", raising=False)
    monkeypatch.delenv("secret_key", raising=False)

    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_produccion_falla_con_debug_activo(monkeypatch):
    """DEBUG=true en producción expondría stack traces con detalles internos
    a cualquier visitante que provoque un error 500."""
    monkeypatch.setenv("SECRET_KEY", "un-secreto-de-prueba")
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("DEBUG", "true")
    monkeypatch.setenv("CORS_ORIGINS", '["https://app.turestaurante.com"]')

    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_produccion_falla_con_cors_wildcard(monkeypatch):
    """"*" en CORS_ORIGINS dejaría que cualquier sitio web llame a la API
    usando el token que el navegador de la víctima tiene guardado."""
    monkeypatch.setenv("SECRET_KEY", "un-secreto-de-prueba")
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("DEBUG", "false")
    monkeypatch.setenv("CORS_ORIGINS", '["*"]')

    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_produccion_falla_con_cors_de_desarrollo(monkeypatch):
    """Si nadie tocó CORS_ORIGINS al desplegar, sigue apuntando a localhost
    — la app no debe arrancar así en producción sin que alguien lo note."""
    monkeypatch.setenv("SECRET_KEY", "un-secreto-de-prueba")
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("DEBUG", "false")
    monkeypatch.delenv("CORS_ORIGINS", raising=False)

    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_produccion_arranca_con_configuracion_correcta(monkeypatch):
    """Con SECRET_KEY, DEBUG=false y un dominio real en CORS_ORIGINS, la app
    sí debe poder arrancar en producción."""
    monkeypatch.setenv("SECRET_KEY", "un-secreto-de-prueba")
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("DEBUG", "false")
    monkeypatch.setenv("CORS_ORIGINS", '["https://app.turestaurante.com"]')

    settings = Settings(_env_file=None)
    assert settings.cors_origins == ["https://app.turestaurante.com"]
