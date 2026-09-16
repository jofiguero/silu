"""Motor y sesiones de SQLAlchemy."""

from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings

settings = get_settings()

engine = create_engine(
    settings.database_url,
    # Verifica la conexión antes de usarla: evita el error clásico de conexión
    # muerta cuando el contenedor de Postgres se reinicia.
    pool_pre_ping=True,
    echo=settings.is_dev,
)

SessionFactory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_session() -> Iterator[Session]:
    """Sesión por petición, cerrada siempre al terminar.

    No hace commit: eso es responsabilidad de la capa de servicio, que es la que
    sabe dónde empieza y termina una operación de negocio.
    """
    session = SessionFactory()
    try:
        yield session
    finally:
        session.close()
