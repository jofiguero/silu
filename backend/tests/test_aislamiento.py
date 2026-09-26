"""Que una cuenta no vea ni toque lo de otra.

Es el test más importante del proyecto: todo lo demás que falle molesta, esto
sería mostrarle a alguien lo que escribió otra persona.
"""

from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db.session import declarar_dueno
from app.schemas.expense import EtiquetaCreate, ExpenseCreate
from app.schemas.prompt import ProjectCreate, PromptCreate
from app.schemas.thread import TaskCreate, ThreadCreate
from app.schemas.ticket import TicketCreate
from app.services.auth import (
    CUOTA_DIARIA,
    AuthService,
    CuotaAgotada,
    SinVinculo,
    TelegramService,
)
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
        assert servicio.list() == ([], 0)

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
    @staticmethod
    def _categoria(gastos, nombre):
        return next(
            c for c, _ in gastos.categories.list_con_usos() if c.name == nombre
        )

    def test_no_se_ven_las_categorias_del_otro(
        self, db_session: Session, dos_cuentas
    ) -> None:
        """Cada cuenta nace con su taxonomía y edita la suya."""
        ana, beto = dos_cuentas
        gastos = ExpenseService(db_session)

        como(db_session, ana)
        gastos.categories.create(EtiquetaCreate(name="Asado"))

        como(db_session, beto)
        suyas = [c.name for c, _ in gastos.categories.list_con_usos()]
        assert "Asado" not in suyas
        # Y las sembradas al crear la cuenta sí están.
        assert "Alimento" in suyas

    def test_dos_cuentas_pueden_tener_la_misma_categoria(
        self, db_session: Session, dos_cuentas
    ) -> None:
        ana, beto = dos_cuentas
        gastos = ExpenseService(db_session)

        como(db_session, ana)
        gastos.categories.create(EtiquetaCreate(name="Asado"))

        como(db_session, beto)
        assert gastos.categories.create(EtiquetaCreate(name="Asado")).name == "Asado"

    def test_no_se_ven_los_gastos_del_otro(
        self, db_session: Session, dos_cuentas
    ) -> None:
        ana, beto = dos_cuentas
        gastos = ExpenseService(db_session)
        hoy = date.today()

        como(db_session, ana)
        categoria = self._categoria(gastos, "Alimento")
        sub = next(iter(categoria.subcategories))
        medio = next(m for m, _ in gastos.methods.list_con_usos())
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


class TestSeguridadPorFila:
    """Que la base también lo impida, no solo el código.

    Estos tests consultan saltándose los repositorios: van directo con SQL,
    como lo haría un camino nuevo mal escrito. Si pasan, es Postgres el que
    está protegiendo.
    """

    def test_un_select_crudo_no_ve_lo_ajeno(
        self, db_session: Session, dos_cuentas
    ) -> None:
        ana, beto = dos_cuentas

        como(db_session, ana)
        TicketService(db_session).create(
            TicketCreate(raw_text="algo", title="De Ana", summary="x")
        )

        como(db_session, beto)
        titulos = db_session.execute(text("SELECT title FROM tickets")).scalars().all()
        assert "De Ana" not in titulos

    def test_no_se_puede_escribir_a_nombre_de_otro(
        self, db_session: Session, dos_cuentas
    ) -> None:
        """WITH CHECK: insertar una fila ajena tampoco se puede."""
        ana, beto = dos_cuentas

        como(db_session, beto)
        with pytest.raises(Exception) as caido:
            db_session.execute(
                text(
                    "INSERT INTO tickets (raw_text, title, summary, user_id) "
                    "VALUES ('x', 'Colado', 'x', :ajeno)"
                ),
                {"ajeno": ana.id},
            )
            db_session.flush()

        assert "row-level security" in str(caido.value).lower()

    def test_sin_declarar_dueno_no_se_ve_nada(
        self, db_session: Session, dos_cuentas
    ) -> None:
        """Una sesión que no dice quién es no ve todo: no ve nada."""
        ana, _ = dos_cuentas

        como(db_session, ana)
        TicketService(db_session).create(
            TicketCreate(raw_text="algo", title="De Ana", summary="x")
        )

        db_session.execute(text("SELECT set_config('silu.user_id', '', true)"))
        assert db_session.execute(text("SELECT count(*) FROM tickets")).scalar() == 0


class TestVinculoTelegram:
    """Un bot atiende a todos; lo que separa a las personas es el vínculo."""

    def test_un_codigo_vincula_ese_telegram(
        self, db_session: Session, dos_cuentas
    ) -> None:
        ana, _ = dos_cuentas
        telegram = TelegramService(db_session)

        codigo = telegram.generar_codigo(ana)
        vinculado = telegram.vincular(codigo.code, 555)

        assert vinculado.id == ana.id
        assert telegram.usuario_de(555).id == ana.id

    def test_el_codigo_sirve_una_sola_vez(
        self, db_session: Session, dos_cuentas
    ) -> None:
        ana, _ = dos_cuentas
        telegram = TelegramService(db_session)
        codigo = telegram.generar_codigo(ana)
        telegram.vincular(codigo.code, 555)

        with pytest.raises(SinVinculo):
            telegram.vincular(codigo.code, 999)

    def test_un_codigo_vencido_no_sirve(
        self, db_session: Session, dos_cuentas
    ) -> None:
        ana, _ = dos_cuentas
        telegram = TelegramService(db_session)
        codigo = telegram.generar_codigo(ana)
        codigo.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
        db_session.commit()

        with pytest.raises(SinVinculo):
            telegram.vincular(codigo.code, 555)

    def test_pedir_uno_nuevo_invalida_el_anterior(
        self, db_session: Session, dos_cuentas
    ) -> None:
        """Un papel con un código viejo no debería seguir sirviendo."""
        ana, _ = dos_cuentas
        telegram = TelegramService(db_session)
        primero = telegram.generar_codigo(ana)
        codigo_viejo = primero.code
        telegram.generar_codigo(ana)

        with pytest.raises(SinVinculo):
            telegram.vincular(codigo_viejo, 555)

    def test_un_telegram_apunta_a_una_sola_cuenta(
        self, db_session: Session, dos_cuentas
    ) -> None:
        """Si no, el mismo teléfono escribiría en dos bandejas."""
        ana, beto = dos_cuentas
        telegram = TelegramService(db_session)

        telegram.vincular(telegram.generar_codigo(ana).code, 555)
        telegram.vincular(telegram.generar_codigo(beto).code, 555)

        assert telegram.usuario_de(555).id == beto.id
        db_session.refresh(ana)
        assert ana.telegram_id is None

    def test_un_telegram_desconocido_no_es_de_nadie(
        self, db_session: Session, dos_cuentas
    ) -> None:
        """Sin respaldo a "la única cuenta": mandar el audio de alguien a la
        bandeja equivocada es peor que no procesarlo."""
        assert TelegramService(db_session).usuario_de(424242) is None

    def test_una_cuenta_desactivada_deja_de_recibir(
        self, db_session: Session, dos_cuentas
    ) -> None:
        ana, _ = dos_cuentas
        telegram = TelegramService(db_session)
        telegram.vincular(telegram.generar_codigo(ana).code, 555)

        ana.is_active = False
        db_session.commit()

        assert telegram.usuario_de(555) is None


class TestCuotaDelBot:
    def test_cuenta_las_capturas_del_dia(
        self, db_session: Session, dos_cuentas
    ) -> None:
        ana, _ = dos_cuentas
        telegram = TelegramService(db_session)

        assert telegram.consumir_cuota(ana) == 1
        assert telegram.consumir_cuota(ana) == 2

    def test_al_llegar_al_tope_se_corta(
        self, db_session: Session, dos_cuentas
    ) -> None:
        ana, _ = dos_cuentas
        telegram = TelegramService(db_session)
        for _ in range(CUOTA_DIARIA):
            telegram.consumir_cuota(ana)

        with pytest.raises(CuotaAgotada):
            telegram.consumir_cuota(ana)

    def test_la_cuota_es_de_cada_cuenta(
        self, db_session: Session, dos_cuentas
    ) -> None:
        """Que uno gaste la suya no puede dejar al otro sin bot."""
        ana, beto = dos_cuentas
        telegram = TelegramService(db_session)
        for _ in range(CUOTA_DIARIA):
            telegram.consumir_cuota(ana)

        assert telegram.consumir_cuota(beto) == 1
