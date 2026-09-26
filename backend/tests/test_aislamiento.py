"""Que una cuenta no vea ni toque lo de otra.

Es el test más importante del proyecto: todo lo demás que falle molesta, esto
sería mostrarle a alguien lo que escribió otra persona.
"""

from datetime import date

import pytest
from sqlalchemy.orm import Session

from app.db.models import ExpenseSubcategory
from app.db.session import declarar_dueno
from app.schemas.expense import EtiquetaCreate, ExpenseCreate
from app.schemas.prompt import ProjectCreate, PromptCreate
from app.schemas.thread import TaskCreate, ThreadCreate
from app.schemas.ticket import TicketCreate
from app.services.auth import AuthService
from app.services.expense import ExpenseService
from app.services.prompt import ProjectService, PromptService
from app.services.thread import ThreadService
from app.services.ticket import TicketService

ANA = "ana@example.com"
BETO = "beto@example.com"
CLAVE = "una-contrasena-larga"


@pytest.fixture
def dos_cuentas(db_session: Session):
    auth = AuthService(db_session)
    return auth.crear_usuario(ANA, CLAVE), auth.crear_usuario(BETO, CLAVE)


def como(session: Session, usuario):
    """Pasa a atender la petición como esa cuenta."""
    declarar_dueno(session, usuario.id)


class TestBandeja:
    def test_no_se_ven_los_tickets_del_otro(
        self, db_session: Session, dos_cuentas
    ) -> None:
        ana, beto = dos_cuentas
        servicio = TicketService(db_session)

        como(db_session, ana)
        servicio.create(
            TicketCreate(raw_text="algo de Ana", title="De Ana", summary="x")
        )

        como(db_session, beto)
        assert servicio.list() == []

    def test_no_se_alcanza_el_ticket_ajeno_ni_por_id(
        self, db_session: Session, dos_cuentas
    ) -> None:
        """Pedir por id se salta cualquier filtro de lista."""
        from app.core.exceptions import TicketNotFoundError

        ana, beto = dos_cuentas
        servicio = TicketService(db_session)

        como(db_session, ana)
        suyo = servicio.create(
            TicketCreate(raw_text="algo", title="De Ana", summary="x")
        )

        como(db_session, beto)
        with pytest.raises(TicketNotFoundError):
            servicio.get(suyo.id)


class TestTareas:
    def test_no_se_ven_los_threads_del_otro(
        self, db_session: Session, dos_cuentas
    ) -> None:
        ana, beto = dos_cuentas
        servicio = ThreadService(db_session)

        como(db_session, ana)
        servicio.create(ThreadCreate(name="ICAI"))

        como(db_session, beto)
        assert [t.name for t in servicio.list()] == []

    def test_dos_cuentas_pueden_tener_un_thread_con_el_mismo_nombre(
        self, db_session: Session, dos_cuentas
    ) -> None:
        """Antes el nombre era único en toda la base."""
        ana, beto = dos_cuentas
        servicio = ThreadService(db_session)

        como(db_session, ana)
        servicio.create(ThreadCreate(name="SILU"))

        como(db_session, beto)
        assert servicio.create(ThreadCreate(name="SILU")).name == "SILU"

    def test_no_se_agregan_tareas_al_thread_ajeno(
        self, db_session: Session, dos_cuentas
    ) -> None:
        from app.core.exceptions import ThreadNotFoundError

        ana, beto = dos_cuentas
        servicio = ThreadService(db_session)

        como(db_session, ana)
        suyo = servicio.create(ThreadCreate(name="ICAI"))

        como(db_session, beto)
        with pytest.raises(ThreadNotFoundError):
            servicio.add_task(suyo.id, TaskCreate(text="colarse"))

    def test_el_historico_es_de_cada_uno(
        self, db_session: Session, dos_cuentas
    ) -> None:
        ana, beto = dos_cuentas
        servicio = ThreadService(db_session)

        como(db_session, ana)
        thread = servicio.create(ThreadCreate(name="ICAI"))
        servicio.add_task(thread.id, TaskCreate(text="De Ana"))

        como(db_session, beto)
        datos = servicio.history(date.today(), date.today())
        assert datos["creadas"] == 0


class TestGastos:
    def test_las_taxonomias_son_de_cada_uno(
        self, db_session: Session, dos_cuentas
    ) -> None:
        """Las categorías son datos del usuario, no una tabla compartida."""
        ana, beto = dos_cuentas
        gastos = ExpenseService(db_session)

        como(db_session, ana)
        gastos.categories.create(EtiquetaCreate(name="Alimento"))

        como(db_session, beto)
        assert gastos.categories.list_con_usos() == []
        # Y puede crear una con el mismo nombre.
        creada = gastos.categories.create(EtiquetaCreate(name="Alimento"))
        assert creada.name == "Alimento"

    def test_no_se_ven_los_gastos_del_otro(
        self, db_session: Session, dos_cuentas
    ) -> None:
        ana, beto = dos_cuentas
        gastos = ExpenseService(db_session)
        hoy = date.today()

        como(db_session, ana)
        categoria = gastos.categories.create(EtiquetaCreate(name="Alimento"))
        # La subcategoría se crea directo: el servicio de etiquetas no lleva
        # la categoría, la pone el endpoint. Lo que importa aquí es el dueño.
        sub = ExpenseSubcategory(name="Restaurant", category_id=categoria.id)
        db_session.add(sub)
        db_session.commit()
        medio = gastos.methods.create(EtiquetaCreate(name="Débito"))
        gastos.create(
            ExpenseCreate(
                amount=5000,
                spent_on=hoy,
                category_id=categoria.id,
                subcategory_id=sub.id,
                payment_method_id=medio.id,
            )
        )

        como(db_session, beto)
        assert gastos.list(desde=hoy, hasta=hoy) == []
        assert gastos.resumen(desde=hoy, hasta=hoy).total == 0


class TestPrompts:
    def test_no_se_ven_los_prompts_del_otro(
        self, db_session: Session, dos_cuentas
    ) -> None:
        ana, beto = dos_cuentas
        prompts = PromptService(db_session)

        como(db_session, ana)
        prompts.create(PromptCreate(title="De Ana", content="x"))

        como(db_session, beto)
        assert prompts.list() == []

    def test_no_se_ven_los_proyectos_del_otro(
        self, db_session: Session, dos_cuentas
    ) -> None:
        ana, beto = dos_cuentas
        proyectos = ProjectService(db_session)

        como(db_session, ana)
        proyectos.create(ProjectCreate(name="Silu"))

        como(db_session, beto)
        assert proyectos.list() == []


class TestSinDueno:
    def test_una_consulta_sin_dueno_declarado_se_corta(
        self, db_session: Session, dos_cuentas
    ) -> None:
        """Preferible un error ruidoso a devolver lo de todos.

        Si un camino nuevo olvidara declarar de quién es la petición, esto lo
        hace explotar en vez de dejarlo listar la base entera.
        """
        db_session.info.pop("user_id", None)

        with pytest.raises(RuntimeError, match="no declaró"):
            TicketService(db_session).list()
