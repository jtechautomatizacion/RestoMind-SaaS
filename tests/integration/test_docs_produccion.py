"""
FastAPI publica /docs, /redoc y /openapi.json SIN autenticación, y ahí está el
mapa completo de la API: cada endpoint, cada parámetro, cada schema, los campos
exactos que espera /api/superadmin/login.

Verificado contra el VPS de producción: los tres respondían HTTP 200 a
cualquiera en internet. No es una brecha por sí sola —los endpoints siguen
pidiendo su token— pero le ahorra a un atacante todo el trabajo de
reconocimiento: en vez de adivinar rutas, las lee.

Se prueba con un subproceso real (y no llamando a una función) porque la
decisión vive a nivel de MÓDULO en backend/app.py, al construir el objeto
FastAPI: la única forma de probarla de verdad es importar el módulo tal como lo
hace uvicorn al arrancar, con ENVIRONMENT puesto de antemano.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]

# Se importa la app y se reportan las tres rutas tal como quedaron. El print de
# JSON es el canal de vuelta del subproceso.
CODIGO = (
    "import json, backend.app as a; "
    "print(json.dumps({"
    "'docs': a.app.docs_url, "
    "'redoc': a.app.redoc_url, "
    "'openapi': a.app.openapi_url"
    "}))"
)


def _rutas_de_documentacion(tmp_path, environment: str) -> dict:
    env = {
        **os.environ,
        "DATABASE_URL": f"sqlite:///{tmp_path / ('docs-' + environment + '.db')}",
        "SECRET_KEY": "test-secret-docs-" + environment,
        "ENVIRONMENT": environment,
        "DEBUG": "false" if environment == "production" else "true",
    }
    if environment == "production":
        env["CORS_ORIGINS"] = '["https://app.test.com"]'

    r = subprocess.run(
        [sys.executable, "-c", CODIGO],
        cwd=RAIZ,
        env=env,
        capture_output=True,
        text=True,
        timeout=90,
    )
    assert r.returncode == 0, f"el import falló:\n{r.stderr}"
    # El import escribe logs por stdout, así que se toma la última línea, que
    # es el JSON. Buscar la primera daría el log de la migración.
    ultima = [l for l in r.stdout.strip().splitlines() if l.strip().startswith("{")][-1]
    return json.loads(ultima)


def test_produccion_no_publica_la_documentacion_de_la_api(tmp_path):
    rutas = _rutas_de_documentacion(tmp_path, "production")

    assert rutas["docs"] is None, "/docs quedó expuesto en producción"
    assert rutas["redoc"] is None, "/redoc quedó expuesto en producción"
    assert rutas["openapi"] is None, (
        "/openapi.json quedó expuesto en producción — es el mapa completo de la "
        "API, y apagar solo /docs no alcanza: cualquiera puede leer el JSON y "
        "renderizarlo en su propio Swagger."
    )


def test_en_desarrollo_la_documentacion_sigue_disponible(tmp_path):
    """La contracara: cerrar esto en producción no puede volver inservible la
    herramienta con la que se desarrolla. En local los tres siguen activos."""
    rutas = _rutas_de_documentacion(tmp_path, "development")

    assert rutas["docs"] == "/docs"
    assert rutas["redoc"] == "/redoc"
    assert rutas["openapi"] == "/openapi.json"
