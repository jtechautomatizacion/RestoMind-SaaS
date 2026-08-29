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
        print("[OK] BD no existe todavía, se creará automáticamente")
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
            print("[OK] Columna 'celular' agregada")
        else:
            print("[OK] Columna 'celular' ya existe")

        # 'email' se quedó NOT NULL en el esquema físico de una BD creada
        # antes del login por celular (el modelo Python ya dice nullable=True,
        # pero SQLAlchemy solo crea tablas nuevas, no altera las existentes).
        # Sin esto, crear personal con celular fallaba con IntegrityError
        # porque insertaba email=NULL contra esa restricción vieja.
        #
        # SQLite no soporta "ALTER COLUMN ... DROP NOT NULL": hay que
        # recrear la tabla (patrón oficial de SQLite para este caso).
        cursor.execute("PRAGMA table_info(usuarios)")
        email_col = next((row for row in cursor.fetchall() if row[1] == "email"), None)
        if email_col and email_col[3] == 1:  # notnull == 1
            print("Haciendo 'email' nullable en usuarios (staff no tiene email)...")
            cursor.execute("PRAGMA foreign_keys=off")
            cursor.execute("""
                CREATE TABLE usuarios_new (
                    id VARCHAR NOT NULL,
                    cliente_id VARCHAR NOT NULL,
                    nombre VARCHAR NOT NULL,
                    email VARCHAR,
                    password_hash VARCHAR NOT NULL,
                    rol VARCHAR,
                    estado VARCHAR,
                    creado_en DATETIME,
                    celular VARCHAR(20) DEFAULT NULL,
                    PRIMARY KEY (id),
                    FOREIGN KEY(cliente_id) REFERENCES clientes (id),
                    UNIQUE (email)
                )
            """)
            cursor.execute("""
                INSERT INTO usuarios_new
                    (id, cliente_id, nombre, email, password_hash, rol, estado, creado_en, celular)
                SELECT id, cliente_id, nombre, email, password_hash, rol, estado, creado_en, celular
                FROM usuarios
            """)
            cursor.execute("DROP TABLE usuarios")
            cursor.execute("ALTER TABLE usuarios_new RENAME TO usuarios")
            cursor.execute("PRAGMA foreign_keys=on")
            conn.commit()
            print("[OK] 'email' ahora es nullable")
        else:
            print("[OK] 'email' ya es nullable")

        print("[OK] Migración completada")
    except Exception as e:
        print(f"[ERROR] Error en migración: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    migrate()
