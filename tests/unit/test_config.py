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
