from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from backend.config import settings

# SQLite engine con SQLAlchemy
engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False},
    echo=settings.database_echo
)

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
