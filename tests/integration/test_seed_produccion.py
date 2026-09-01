"""
seed_if_empty() crea un restaurante y un admin de PRUEBA con contraseña
"admin123" — pública, está en el código fuente (backend/seed.py). Corría en
CADA arranque de la app, sin importar el entorno. En un VPS recién
levantado, antes de correr backend/scripts/crear_cliente.py, esa habría
sido la ÚNICA cuenta del sistema — y el código de este proyecto es público,
así que cualquiera podría haber sabido las credenciales sin adivinar nada.

Se prueba con un subproceso real (no solo llamando a la función) porque la
guarda vive a nivel de MÓDULO en backend/app.py, ejecutándose al importar
— la única forma de probarla de verdad es importar el módulo tal como lo
hace uvicorn al arrancar, con ENVIRONMENT=production puesto de antemano.
"""

import os
import sqlite3
import subprocess
import sys
from pathlib import Path



def _arrancar_e_inspeccionar(tmp_path, environment: str) -> list:
    """Arranca backend.app en un subproceso contra una BD nueva y devuelve
    las filas de la tabla clientes al terminar de importar (donde vive el
    seed). No levanta un servidor de verdad: alcanza con importar el
    módulo, que es exactamente cuando corre seed_if_empty()."""
    db_path = tmp_path / "boot.db"
    env = {
        **os.environ,
        "DATABASE_URL": f"sqlite:///{db_path}",
        "SECRET_KEY": "test-secret-para-boot-" + environment,
        "ENVIRONMENT": environment,
        "DEBUG": "false" if environment == "production" else "true",
    }
    if environment == "production":
        env["CORS_ORIGINS"] = '["https://app.test.com"]'

    codigo = "import backend.app"
    resultado = subprocess.run(
        [sys.executable, "-c", codigo],
        cwd=Path(__file__).resolve().parents[2],
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert resultado.returncode == 0, f"el import falló:\n{resultado.stderr}"

    conn = sqlite3.connect(db_path)
    try:
        return conn.execute("SELECT id, email FROM clientes").fetchall()
    finally:
        conn.close()


def test_produccion_arranca_sin_el_restaurante_de_prueba(tmp_path):
    clientes = _arrancar_e_inspeccionar(tmp_path, "production")
    assert clientes == [], (
        "seed_if_empty() creó un restaurante de prueba en producción — "
        "eso deja una cuenta admin con contraseña pública ('admin123', "
        "ver backend/seed.py) en el único sistema que existe hasta que "
        "alguien corra crear_cliente.py."
    )


def test_desarrollo_sigue_arrancando_con_el_restaurante_de_prueba(tmp_path):
    """Contracara: la guarda no puede haber apagado el seed también para
    desarrollo — ahí sigue haciendo falta para probar la app a mano sin
    tener que dar de alta un cliente primero."""
    clientes = _arrancar_e_inspeccionar(tmp_path, "development")
    assert len(clientes) == 1
    assert clientes[0][1] == "admin@lamarisqueria.pe"
