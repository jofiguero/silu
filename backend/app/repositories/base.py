"""Base común de los repositorios."""

from typing import Generic, TypeVar

from sqlalchemy.orm import Session

from app.db.models import Base

ModelT = TypeVar("ModelT", bound=Base)


class BaseRepository(Generic[ModelT]):
    """Acceso a datos de un modelo.

    Un repositorio traduce entre el lenguaje del dominio y SQLAlchemy, y no hace
    commit: quien controla la transacción es el servicio, para que varias
    operaciones puedan confirmarse juntas.
    """

    model: type[ModelT]

    def __init__(self, session: Session) -> None:
        self.session = session
