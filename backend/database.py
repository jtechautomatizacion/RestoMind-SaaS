from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import declarative_base, sessionmaker
from backend.config import settings

# SQLite engine con SQLAlchemy
engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False},
    echo=settings.database_echo
)


@event.listens_for(Engine, "connect")
def _activar_wal(conexion_dbapi, _):
    """Modo WAL de SQLite: los lectores ya no bloquean ni son bloqueados por
    el escritor activo (a diferencia del modo por defecto, "rollback
    journal", donde una escritura bloquea toda lectura concurrente). En
    producción esto es lo que evita que un cierre de caja escribiendo
    choque con alguien mirando el dashboard al mismo tiempo.

    No hace nada en un backend que no sea SQLite (el "PRAGMA" es sintaxis
    propia de SQLite) — el intento de ejecutarlo contra otro motor fallaría,
    así que se filtra por el nombre del dialecto antes de intentarlo.
    """
    if engine.dialect.name != "sqlite":
        return
    cursor = conexion_dbapi.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.close()


SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    """Dependency injection para sesiones de BD en endpoints."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """Crea todas las tablas en la BD."""
    Base.metadata.create_all(bind=engine)
