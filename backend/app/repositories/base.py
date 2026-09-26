"""Base común de los repositorios."""

import uuid
from typing import Generic, TypeVar

from sqlalchemy.orm import Session
from sqlalchemy.sql import Select

from app.db.models import Base
from app.db.session import DUENO

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

    @property
    def dueno(self) -> uuid.UUID:
        """De quién es la petición que se está atendiendo.

        Lo declara `declarar_dueno` al resolver la sesión. Si falta, se corta
        en vez de devolver datos: una consulta sin dueño o no devuelve nada o
        los devuelve todos, y la segunda posibilidad es inaceptable.
        """
        user_id = self.session.info.get(DUENO)
        if user_id is None:
            raise RuntimeError(
                "La sesión no declaró de quién es. Falta declarar_dueno()."
            )
        return user_id

    def mios(self, stmt: Select) -> Select:
        """Acota una consulta a lo del dueño de la sesión."""
        return stmt.where(self.model.user_id == self.dueno)

    def mio(self, fila):
        """Devuelve la fila solo si es del dueño de la sesión.

        `session.get` busca por clave primaria y se salta cualquier filtro, así
        que pedir por id es el camino por el que se escaparía un dato ajeno.
        """
        if fila is None or fila.user_id != self.dueno:
            return None
        return fila
