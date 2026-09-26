"""Motor y sesiones de SQLAlchemy."""

import uuid
from collections.abc import Iterator

from sqlalchemy import create_engine, event, text
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

# Clave donde cada sesión guarda de quién es la petición que está atendiendo.
DUENO = "user_id"


def declarar_dueno(session: Session, user_id: uuid.UUID) -> None:
    """Deja dicho quién es el dueño de todo lo que se escriba o lea aquí.

    Escribe `silu.user_id` en la transacción de Postgres. De ahí salen dos
    cosas: el valor por defecto de la columna `user_id` al insertar, y —cuando
    esté activo— el filtro de las políticas de seguridad por fila.

    Se guarda además en `session.info` porque `SET LOCAL` muere con la
    transacción: cada commit abre una nueva y hay que volver a declararlo. De
    eso se encarga el escuchador de más abajo.
    """
    session.info[DUENO] = user_id
    _escribir(session, user_id)


def _escribir(session: Session, user_id: uuid.UUID) -> None:
    # set_config(..., true) es SET LOCAL: vive solo dentro de la transacción,
    # así que no se filtra a la siguiente petición que reutilice la conexión.
    session.execute(
        text("SELECT set_config('silu.user_id', :valor, true)"),
        {"valor": str(user_id)},
    )


@event.listens_for(Session, "after_begin")
def _redeclarar(session: Session, transaction, connection) -> None:
    """Vuelve a declarar el dueño en cada transacción nueva.

    Sin esto, el primer commit de la petición borraría la declaración y todo
    lo que viniera después insertaría sin dueño o no vería nada.
    """
    user_id = session.info.get(DUENO)
    if user_id is not None:
        connection.exec_driver_sql(
            "SELECT set_config('silu.user_id', %s, true)", (str(user_id),)
        )


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
