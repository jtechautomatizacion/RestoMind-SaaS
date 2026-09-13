"""
Script de migración: agregar columnas 'celular' a tabla usuarios
y hacer email nullable para permitir staff sin email.
"""

import sqlite3
from pathlib import Path

from backend.config import settings


def _ruta_bd() -> str:
    """Ruta del archivo SQLite, sacada de DATABASE_URL.

    Antes esto era la constante "restomind.db" hardcodeada, y eso silenciaba
    migraciones de la peor forma posible: si DATABASE_URL apuntaba a otra
    ruta (el VPS, una copia para pruebas), migrate() abría un archivo
    distinto del que la app iba a usar — o no encontraba ninguno y devolvía
    "BD no existe todavía" sin migrar nada, mientras la app arrancaba contra
    una base con columnas viejas y reventaba en la primera consulta.

    Devuelve "" si DATABASE_URL no es SQLite: las migraciones de este
    archivo usan sintaxis específica de SQLite (PRAGMA table_info, recrear
    tablas) y no aplican a otro motor.
    """
    url = settings.database_url
    if not url.startswith("sqlite"):
        return ""
    # sqlite:///./restomind.db -> ./restomind.db ; sqlite:////abs/ruta.db -> /abs/ruta.db
    return url.split("///", 1)[-1] if "///" in url else ""


def migrate():
    """Ejecutar migraciones necesarias."""
    db_path = _ruta_bd()
    if not db_path:
        print("[OK] DATABASE_URL no es SQLite, se omiten las migraciones de este archivo")
        return

    if not Path(db_path).exists():
        # Base nueva: create_all() la crea completa, con todas las columnas
        # que estas migraciones agregarían. No hay nada que migrar.
        print("[OK] BD no existe todavía, se creará automáticamente")
        return

    conn = sqlite3.connect(db_path)
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

        # Datos tributarios del restaurante (RUC/razón social) para poder
        # emitir boletas SUNAT — no existían en el esquema original.
        cursor.execute("PRAGMA table_info(clientes)")
        columns_clientes = [row[1] for row in cursor.fetchall()]

        if "ruc" not in columns_clientes:
            print("Agregando columna 'ruc' a clientes...")
            cursor.execute("ALTER TABLE clientes ADD COLUMN ruc VARCHAR DEFAULT NULL")
            conn.commit()
            print("[OK] Columna 'ruc' agregada")
        else:
            print("[OK] Columna 'ruc' ya existe")

        if "razon_social" not in columns_clientes:
            print("Agregando columna 'razon_social' a clientes...")
            cursor.execute("ALTER TABLE clientes ADD COLUMN razon_social VARCHAR DEFAULT NULL")
            conn.commit()
            print("[OK] Columna 'razon_social' agregada")
        else:
            print("[OK] Columna 'razon_social' ya existe")

        if "direccion" not in columns_clientes:
            print("Agregando columna 'direccion' a clientes...")
            cursor.execute("ALTER TABLE clientes ADD COLUMN direccion VARCHAR DEFAULT NULL")
            conn.commit()
            print("[OK] Columna 'direccion' agregada")
        else:
            print("[OK] Columna 'direccion' ya existe")

        if "boleta_correlativo_actual" not in columns_clientes:
            print("Agregando columna 'boleta_correlativo_actual' a clientes...")
            cursor.execute("ALTER TABLE clientes ADD COLUMN boleta_correlativo_actual INTEGER DEFAULT 0")
            conn.commit()
            print("[OK] Columna 'boleta_correlativo_actual' agregada")
        else:
            print("[OK] Columna 'boleta_correlativo_actual' ya existe")

        # La tabla 'facturas' es nueva: en una instalación que arranca por
        # primera vez con esta versión, create_all() ya la crea completa y
        # este bloque no tiene nada que hacer (el PRAGMA da lista vacía y
        # el 'if cursor.fetchone()' de abajo corta antes de tocar nada).
        # Solo hace falta ALTER TABLE acá para una instalación (como esta
        # misma máquina de desarrollo) que ya había creado 'facturas' con
        # una versión anterior del modelo, sin estas columnas.
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='facturas'")
        if cursor.fetchone():
            cursor.execute("PRAGMA table_info(facturas)")
            columns_facturas = [row[1] for row in cursor.fetchall()]

            for columna, ddl in (
                ("archivo_local", "VARCHAR DEFAULT NULL"),
                ("fecha_emision_local", "VARCHAR DEFAULT NULL"),
                ("hora_emision_local", "VARCHAR DEFAULT NULL"),
            ):
                if columna not in columns_facturas:
                    print(f"Agregando columna '{columna}' a facturas...")
                    cursor.execute(f"ALTER TABLE facturas ADD COLUMN {columna} {ddl}")
                    conn.commit()
                    print(f"[OK] Columna '{columna}' agregada")
                else:
                    print(f"[OK] Columna '{columna}' ya existe")

        # cierres_caja se creó con UNIQUE(cliente_id, fecha) — bloqueaba
        # tener más de un turno (mañana/tarde) el mismo día. Se decidió
        # permitir varios turnos por día (ver CLAUDE.md "Validador de
        # Caja"), así que ese índice sobra y hay que quitarlo. SQLite no
        # soporta "DROP CONSTRAINT": hay que recrear la tabla, mismo patrón
        # que la migración de 'usuarios.email' más arriba.
        cursor.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='cierres_caja'")
        tabla_cierres_caja = cursor.fetchone()
        if tabla_cierres_caja:
            # El UNIQUE inline queda como CONSTRAINT dentro del propio SQL de
            # creación de la tabla — SQLite le pone un nombre de ÍNDICE
            # autogenerado (sqlite_autoindex_...) que NO es el nombre que se
            # le dio al constraint, así que buscarlo por nombre de índice no
            # sirve: hay que mirar el texto de la definición de la tabla.
            if "uq_cliente_fecha_caja" in tabla_cierres_caja[0]:
                print("Quitando UNIQUE(cliente_id, fecha) de cierres_caja (permite varios turnos por día)...")
                cursor.execute("PRAGMA foreign_keys=off")
                cursor.execute("""
                    CREATE TABLE cierres_caja_new (
                        id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
                        cliente_id VARCHAR NOT NULL,
                        fecha VARCHAR NOT NULL,
                        saldo_inicial FLOAT NOT NULL,
                        abierto_en DATETIME NOT NULL,
                        abierto_por VARCHAR NOT NULL,
                        ventas_cobradas FLOAT,
                        gastos_efectivo FLOAT,
                        retiros_personales FLOAT,
                        saldo_esperado FLOAT,
                        saldo_contado FLOAT,
                        diferencia FLOAT,
                        variacion_pct FLOAT,
                        razon_discrepancia VARCHAR,
                        cerrado_en DATETIME,
                        cerrado_por VARCHAR,
                        estado VARCHAR NOT NULL,
                        FOREIGN KEY(cliente_id) REFERENCES clientes (id)
                    )
                """)
                cursor.execute("""
                    INSERT INTO cierres_caja_new
                        (id, cliente_id, fecha, saldo_inicial, abierto_en, abierto_por,
                         ventas_cobradas, gastos_efectivo, retiros_personales,
                         saldo_esperado, saldo_contado, diferencia, variacion_pct,
                         razon_discrepancia, cerrado_en, cerrado_por, estado)
                    SELECT id, cliente_id, fecha, saldo_inicial, abierto_en, abierto_por,
                           ventas_cobradas, gastos_efectivo, retiros_personales,
                           saldo_esperado, saldo_contado, diferencia, variacion_pct,
                           razon_discrepancia, cerrado_en, cerrado_por, estado
                    FROM cierres_caja
                """)
                cursor.execute("DROP TABLE cierres_caja")
                cursor.execute("ALTER TABLE cierres_caja_new RENAME TO cierres_caja")
                cursor.execute("CREATE INDEX ix_cierres_caja_cliente_id ON cierres_caja (cliente_id)")
                cursor.execute("PRAGMA foreign_keys=on")
                conn.commit()
                print("[OK] cierres_caja ahora permite varios turnos por día")
            else:
                print("[OK] cierres_caja ya permite varios turnos por día")

        # push_subscriptions: la primera versión vinculaba el token al 'sub'
        # del JWT en una columna `usuario_email`. Ese valor es el email para
        # admin pero el CÓDIGO DE ACCESO para el staff, y las cuentas de
        # staff tienen email=NULL — o sea que jefe_cocina, el rol para el que
        # existe el feature, nunca recibía nada. Ahora el vínculo es
        # usuario_id (FK real). Se recrea la tabla en vez de migrar datos: un
        # token FCM viejo no se puede reasociar de forma confiable (el 'sub'
        # guardado puede no resolver a ningún usuario), y volver a
        # registrarlo es automático la próxima vez que el navegador abre la
        # app — no se pierde nada que el cliente note.
        cursor.execute("PRAGMA table_info(push_subscriptions)")
        cols_push = [row[1] for row in cursor.fetchall()]
        if cols_push and "usuario_email" in cols_push:
            print("Recreando push_subscriptions con usuario_id (FK)...")
            cursor.execute("DROP TABLE push_subscriptions")
            conn.commit()
            print("[OK] push_subscriptions recreada (init_db la crea con el esquema nuevo)")
        elif cols_push:
            print("[OK] push_subscriptions ya usa usuario_id")

        # cierres_caja.tz_offset: el auto-cierre de turnos vencidos calculaba
        # "qué día es hoy" con el header X-TZ-Offset de QUIEN CONSULTA, y
        # /caja/gate lo consulta cualquier rol — así que un mozo con un
        # offset falso podía adelantar el "hoy" y forzar el cierre automático
        # del turno que el admin tenía abierto. Ahora la zona horaria se
        # captura del dispositivo del admin AL ABRIR y vive en el turno.
        if cols_cierres := [row[1] for row in cursor.execute("PRAGMA table_info(cierres_caja)").fetchall()]:
            if "tz_offset" not in cols_cierres:
                print("Agregando columna 'tz_offset' a cierres_caja...")
                cursor.execute("ALTER TABLE cierres_caja ADD COLUMN tz_offset INTEGER NOT NULL DEFAULT 0")
                conn.commit()
                print("[OK] Columna 'tz_offset' agregada")
            else:
                print("[OK] Columna 'tz_offset' ya existe")

            # Índice único parcial: un solo turno ABIERTO por restaurante.
            # Cierra la carrera del check-then-insert de POST /caja/abrir
            # (doble clic o dos pestañas dejaban dos turnos abiertos, y las
            # mismas ventas se contaban en los dos).
            cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='index' "
                "AND name='ix_cierres_caja_un_turno_abierto'"
            )
            if not cursor.fetchone():
                # Si ya hay duplicados de antes, el índice no se puede crear:
                # se cierran los sobrantes dejando el más reciente abierto.
                cursor.execute("""
                    SELECT cliente_id, COUNT(*) FROM cierres_caja
                    WHERE estado='abierto' GROUP BY cliente_id HAVING COUNT(*) > 1
                """)
                for cliente_id, cuantos in cursor.fetchall():
                    print(f"  Ojo: {cuantos} turnos abiertos en '{cliente_id}' — cerrando los antiguos")
                    cursor.execute("""
                        UPDATE cierres_caja SET estado='cerrado_automatico',
                            razon_discrepancia='Cerrado por migración: había más de un turno abierto a la vez (bug de concurrencia). Revisar manualmente.'
                        WHERE cliente_id=? AND estado='abierto' AND id NOT IN (
                            SELECT id FROM cierres_caja WHERE cliente_id=? AND estado='abierto'
                            ORDER BY abierto_en DESC LIMIT 1
                        )
                    """, (cliente_id, cliente_id))

                print("Creando índice único de turno abierto en cierres_caja...")
                cursor.execute(
                    "CREATE UNIQUE INDEX ix_cierres_caja_un_turno_abierto "
                    "ON cierres_caja (cliente_id) WHERE estado = 'abierto'"
                )
                conn.commit()
                print("[OK] Índice único de turno abierto creado")
            else:
                print("[OK] Índice único de turno abierto ya existe")

        # facturas.descargado_en: cuándo el agente de la PC del restaurante
        # confirmó que los cuatro archivos llegaron al Facturador. Las
        # boletas que ya existían quedan en NULL, o sea "pendientes de
        # entregar" — correcto: se generaron cuando RestoMind corría en la
        # misma máquina que el Facturador, así que nunca pasaron por el
        # agente. Si alguna vez se apunta el agente a esta base, las va a
        # bajar de nuevo; son 18 archivos, y el Facturador ignora lo que ya
        # procesó.
        if cols_facturas := [row[1] for row in cursor.execute("PRAGMA table_info(facturas)").fetchall()]:
            if "descargado_en" not in cols_facturas:
                print("Agregando columna 'descargado_en' a facturas...")
                cursor.execute("ALTER TABLE facturas ADD COLUMN descargado_en DATETIME")
                conn.commit()
                print("[OK] Columna 'descargado_en' agregada")
            else:
                print("[OK] Columna 'descargado_en' ya existe")

        # cierres_caja.nombre_turno: etiqueta opcional ("Mañana"/"Tarde"/
        # "Noche") para distinguir turnos en el historial sin calcular a
        # qué hora empezó cada uno. Turnos ya cerrados quedan en NULL — el
        # frontend cae de vuelta a "Turno N de hoy" cuando no hay etiqueta.
        if cols_cierres_nombre := [row[1] for row in cursor.execute("PRAGMA table_info(cierres_caja)").fetchall()]:
            if "nombre_turno" not in cols_cierres_nombre:
                print("Agregando columna 'nombre_turno' a cierres_caja...")
                cursor.execute("ALTER TABLE cierres_caja ADD COLUMN nombre_turno TEXT")
                conn.commit()
                print("[OK] Columna 'nombre_turno' agregada")
            else:
                print("[OK] Columna 'nombre_turno' ya existe")

        # clientes.usar_sunat: si este restaurante emite boletas desde
        # RestoMind. Los que ya existen arrancan en 0 (False) EXCEPTO los que
        # ya tienen RUC cargado: esos venían emitiendo con el
        # comportamiento anterior ("hay RUC -> se emite"), y ponerlos en
        # False les apagaría la facturación de un día para el otro sin que
        # nadie lo pida. Preservar lo que estaban haciendo es lo correcto.
        if cols_clientes := [row[1] for row in cursor.execute("PRAGMA table_info(clientes)").fetchall()]:
            if "usar_sunat" not in cols_clientes:
                print("Agregando columna 'usar_sunat' a clientes...")
                cursor.execute("ALTER TABLE clientes ADD COLUMN usar_sunat BOOLEAN NOT NULL DEFAULT 0")
                cursor.execute("UPDATE clientes SET usar_sunat = 1 WHERE ruc IS NOT NULL AND ruc != ''")
                migrados = cursor.rowcount
                conn.commit()
                print(f"[OK] Columna 'usar_sunat' agregada ({migrados} con RUC quedaron emitiendo)")
            else:
                print("[OK] Columna 'usar_sunat' ya existe")

        # facturas.cdr_xml: la Constancia de Recepción que devuelve SUNAT al
        # aceptar un comprobante, con el emisor "sunat_cloud".
        #
        # Se guarda entera y no solo su hash porque es LA prueba de que SUNAT
        # aceptó: ante una fiscalización, un hash no demuestra nada por sí
        # solo. Nullable sin default: las boletas ya emitidas por los otros
        # dos emisores (sfs_local / facturacion_pe) nunca tuvieron CDR, y
        # NULL dice exactamente eso — no se inventa un valor.
        cols_facturas_cdr = [row[1] for row in cursor.execute("PRAGMA table_info(facturas)").fetchall()]
        if cols_facturas_cdr:
            if "cdr_xml" not in cols_facturas_cdr:
                print("Agregando columna 'cdr_xml' a facturas...")
                cursor.execute("ALTER TABLE facturas ADD COLUMN cdr_xml TEXT")
                conn.commit()
                print("[OK] Columna 'cdr_xml' agregada")
            else:
                print("[OK] Columna 'cdr_xml' ya existe")

        # clientes.factura_correlativo_actual: numeración de la serie F001,
        # separada de la de boletas (B001). Ver el comentario extenso en
        # models.py:Cliente — compartir un contador entre dos series deja a
        # las DOS con huecos, y SUNAT exige que cada una sea correlativa.
        #
        # Arranca en 0 para todos, incluidos los clientes que ya existen: hasta
        # hoy NADIE emitió facturas (solo boletas B001), así que 0 es el valor
        # correcto y no hay que deducirlo de los datos históricos.
        cols_clientes_fact = [row[1] for row in cursor.execute("PRAGMA table_info(clientes)").fetchall()]
        if cols_clientes_fact:
            if "factura_correlativo_actual" not in cols_clientes_fact:
                print("Agregando columna 'factura_correlativo_actual' a clientes...")
                cursor.execute(
                    "ALTER TABLE clientes ADD COLUMN factura_correlativo_actual INTEGER NOT NULL DEFAULT 0"
                )
                conn.commit()
                print("[OK] Columna 'factura_correlativo_actual' agregada")
            else:
                print("[OK] Columna 'factura_correlativo_actual' ya existe")

        # clientes.emite_facturas: si el restaurante puede emitir facturas o
        # solo boletas. Ver el comentario en models.py:Cliente.
        #
        # TODOS arrancan en 0 (solo boletas), incluidos los que ya existen: es
        # el valor seguro. Hasta hoy el sistema solo emitía boletas B001, así
        # que 0 describe exactamente lo que venían haciendo — y si alguno está
        # en Régimen General, activarlo es un clic del superadmin, mientras
        # que lo contrario (facturar sin poder) es una infracción.
        cols_clientes_fact2 = [row[1] for row in cursor.execute("PRAGMA table_info(clientes)").fetchall()]
        if cols_clientes_fact2:
            if "emite_facturas" not in cols_clientes_fact2:
                print("Agregando columna 'emite_facturas' a clientes...")
                cursor.execute(
                    "ALTER TABLE clientes ADD COLUMN emite_facturas BOOLEAN NOT NULL DEFAULT 0"
                )
                conn.commit()
                print("[OK] Columna 'emite_facturas' agregada (todos en 'solo boletas')")
            else:
                print("[OK] Columna 'emite_facturas' ya existe")

        print("[OK] Migración completada")
    except Exception as e:
        print(f"[ERROR] Error en migración: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    migrate()
