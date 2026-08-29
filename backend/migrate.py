"""
Script de migración: agregar columnas 'celular' a tabla usuarios
y hacer email nullable para permitir staff sin email.
"""

import sqlite3
from pathlib import Path

DB_PATH = "restomind.db"

def migrate():
    """Ejecutar migraciones necesarias."""
    if not Path(DB_PATH).exists():
        print("✓ BD no existe todavía, se creará automáticamente")
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    try:
        # Verificar si las columnas ya existen
        cursor.execute("PRAGMA table_info(usuarios)")
        columns = [row[1] for row in cursor.fetchall()]

        if "celular" not in columns:
            print("Agregando columna 'celular' a usuarios...")
            cursor.execute("ALTER TABLE usuarios ADD COLUMN celular VARCHAR(20) DEFAULT NULL")
            conn.commit()
            print("✓ Columna 'celular' agregada")
        else:
            print("✓ Columna 'celular' ya existe")

        # Nota: No se puede cambiar constraint UNIQUE en SQLite directamente.
        # Email seguirá siendo UNIQUE, pero NULL no viola el constraint.
        # Staff tendrá email=NULL, admins tendrán email != NULL.

        print("✓ Migración completada")
    except Exception as e:
        print(f"✗ Error en migración: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    migrate()
