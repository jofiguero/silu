"""Tests de proyectos y prompts."""

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.exceptions import (
    ProjectNameTakenError,
    ProjectNotFoundError,
    PromptNotFoundError,
)
from app.db.session import get_session
from app.integrations.redaccion import PromptDraft, RedaccionError, Redactor
from app.main import create_app
from app.schemas.prompt import (
    ProjectCreate,
    ProjectUpdate,
    PromptCreate,
    PromptUpdate,
)
from app.schemas.telegram import TelegramUpdate
from app.services import prompt as prompt_module
from app.services.auth import AuthService
from app.services.prompt import (
    ProjectService,
    PromptCaptureService,
    PromptService,
)

ALLOWED_USER = 42
TEST_EMAIL = "prompts@example.com"
# La que crea db_session, y que es dueña de lo que escriben los tests.
CUENTA_DEL_TEST = "pruebas@example.com"
TEST_PASSWORD = "contrasena-de-pruebas"
SECRET = "secreto-de-prompts"


@pytest.fixture
def proyectos(db_session: Session) -> ProjectService:
    return ProjectService(db_session)


@pytest.fixture
def prompts(db_session: Session) -> PromptService:
    return PromptService(db_session)


@pytest.fixture
def chilean(proyectos: ProjectService):
    return proyectos.create(
        ProjectCreate(
            name="Chilean2Sign",
            description_md="Traductor de lengua de señas chilena. Python + PyTorch.",
        )
    )


# --- Dobles ---


class FakeTelegram:
    def __init__(self, *_args, **_kwargs) -> None:
        self.sent: list[tuple[int, str]] = []

    def send_message(self, chat_id: int, text: str) -> None:
        self.sent.append((chat_id, text))

    def download_file(self, file_id: str) -> bytes:
        return b"audio"

    @property
    def texts(self) -> list[str]:
        return [t for _, t in self.sent]


class FakeTranscriber:
    def __init__(self, *_args, **_kwargs) -> None:
        pass

    def transcribe(self, audio: bytes, filename: str = "audio.ogg") -> str:
        return "Para Chilean2Sign necesito que agreguemos un endpoint de salud"


class FakeRedactor:
    """Devuelve la transcripción ya ordenada."""

    def __init__(self, *_args, **_kwargs) -> None:
        pass

    def draft(self, raw_text: str, proyectos) -> PromptDraft:
        return PromptDraft(
            title="Endpoint de salud",
            content="Agregar un endpoint de salud al backend.",
        )


class BrokenRedactor:
    def __init__(self, *_args, **_kwargs) -> None:
        pass

    def draft(self, raw_text: str, proyectos) -> PromptDraft:
        raise RedaccionError("el modelo no respondió")


@pytest.fixture
def bot_settings() -> Settings:
    return get_settings().model_copy(
        update={
            "telegram_prompts_bot_token": "token-prompts",
            "telegram_prompts_webhook_secret": SECRET,
            "telegram_allowed_user_id": ALLOWED_USER,
            "openai_api_key": "key-falsa",
            "app_password": "contrasena-de-pruebas",
            "session_secret": "secreto-de-pruebas",
        }
    )


@pytest.fixture
def fake_bot(monkeypatch: pytest.MonkeyPatch) -> FakeTelegram:
    cliente = FakeTelegram()
    monkeypatch.setattr(prompt_module, "TelegramClient", lambda *a, **k: cliente)
    monkeypatch.setattr(prompt_module, "Transcriber", FakeTranscriber)
    monkeypatch.setattr(prompt_module, "Redactor", FakeRedactor)
    return cliente


def make_update(*, user_id: int = ALLOWED_USER, text=None, voice=False):
    message: dict = {
        "message_id": 1,
        "chat": {"id": 555},
        "from": {"id": user_id, "first_name": "Joaquin"},
    }
    if text is not None:
        message["text"] = text
    if voice:
        message["voice"] = {"file_id": "file-1", "duration": 9}
    return TelegramUpdate.model_validate({"update_id": 1, "message": message})



@pytest.fixture(autouse=True)
def telegram_vinculado(db_session: Session):
    """Vincula la cuenta del test al Telegram que usan los updates de prueba.

    El bot ya no atiende por lista de ids permitidos sino por vínculo, así que
    sin esto ninguna captura llegaría a ninguna bandeja.
    """
    from app.services.auth import AuthService, TelegramService

    usuario = AuthService(db_session).buscar_por_email(CUENTA_DEL_TEST)
    telegram = TelegramService(db_session)
    telegram.vincular(telegram.generar_codigo(usuario).code, ALLOWED_USER)
    return usuario


class TestProyectos:
    def test_crear_con_descriptor(self, proyectos: ProjectService) -> None:
        proyecto = proyectos.create(
            ProjectCreate(name="Silu", description_md="# Silu\n\nSistema personal.")
        )

        assert proyecto.name == "Silu"
        assert "Sistema personal" in proyecto.description_md

    def test_nombre_repetido_falla(
        self, proyectos: ProjectService, chilean
    ) -> None:
        with pytest.raises(ProjectNameTakenError):
            proyectos.create(ProjectCreate(name="Chilean2Sign"))

    def test_editar_el_descriptor(self, proyectos: ProjectService, chilean) -> None:
        actualizado = proyectos.update(
            chilean.id, ProjectUpdate(description_md="Ahora con FastAPI.")
        )

        assert actualizado.description_md == "Ahora con FastAPI."

    def test_resolver_sin_distinguir_mayusculas(
        self, proyectos: ProjectService, chilean
    ) -> None:
        # El modelo puede devolver el nombre en otra caja.
        assert proyectos.resolve("chilean2sign").id == chilean.id

    def test_un_nombre_inventado_no_resuelve(
        self, proyectos: ProjectService, chilean
    ) -> None:
        assert proyectos.resolve("Otro Proyecto") is None

    def test_inexistente_falla(self, proyectos: ProjectService) -> None:
        with pytest.raises(ProjectNotFoundError):
            proyectos.get(uuid.uuid4())

    def test_borrar_deja_los_prompts_sueltos(
        self, proyectos: ProjectService, prompts: PromptService, chilean
    ) -> None:
        # Los prompts no se borran con el proyecto: recuperarlos después es
        # imposible y el trabajo del metaprompter se perdería.
        prompt = prompts.create(
            PromptCreate(title="Algo", content="Contenido", project_id=chilean.id)
        )

        sueltos = proyectos.delete(chilean.id)

        assert sueltos == 1
        assert prompts.get(prompt.id).project_id is None


class TestPrompts:
    def test_crear(self, prompts: PromptService, chilean) -> None:
        prompt = prompts.create(
            PromptCreate(
                title="Endpoint de salud",
                content="## Objetivo\n\nAgregar /health.",
                project_id=chilean.id,
            )
        )

        assert prompt.project_name == "Chilean2Sign"
        assert prompt.edited is False

    def test_editar_el_contenido_lo_marca_retocado(
        self, prompts: PromptService, chilean
    ) -> None:
        # Para que una futura regeneración no pise el trabajo a mano.
        prompt = prompts.create(PromptCreate(title="X", content="Original"))

        editado = prompts.update(prompt.id, PromptUpdate(content="Corregido"))

        assert editado.edited is True

    def test_editar_solo_el_titulo_no_lo_marca(
        self, prompts: PromptService
    ) -> None:
        prompt = prompts.create(PromptCreate(title="X", content="Original"))

        renombrado = prompts.update(prompt.id, PromptUpdate(title="Otro titulo"))

        assert renombrado.edited is False

    def test_guardar_el_mismo_contenido_no_lo_marca(
        self, prompts: PromptService
    ) -> None:
        # Abrir el editor y guardar sin tocar nada no es una edición.
        prompt = prompts.create(PromptCreate(title="X", content="Original"))

        guardado = prompts.update(prompt.id, PromptUpdate(content="Original"))

        assert guardado.edited is False

    def test_asignar_a_un_proyecto(
        self, prompts: PromptService, chilean
    ) -> None:
        prompt = prompts.create(PromptCreate(title="X", content="Y"))

        asignado = prompts.update(prompt.id, PromptUpdate(project_id=chilean.id))

        assert asignado.project_name == "Chilean2Sign"

    def test_filtrar_los_sin_proyecto(
        self, prompts: PromptService, chilean
    ) -> None:
        prompts.create(PromptCreate(title="Con", content="X", project_id=chilean.id))
        suelto = prompts.create(PromptCreate(title="Sin", content="Y"))

        assert [p.id for p in prompts.list(sin_proyecto=True)] == [suelto.id]

    def test_lo_mas_nuevo_primero(self, prompts: PromptService) -> None:
        # Al buscar un prompt, el último que dictaste es el que andas buscando.
        primero = prompts.create(PromptCreate(title="A", content="X"))
        segundo = prompts.create(PromptCreate(title="B", content="Y"))

        assert [p.id for p in prompts.list()] == [segundo.id, primero.id]

    def test_inexistente_falla(self, prompts: PromptService) -> None:
        with pytest.raises(PromptNotFoundError):
            prompts.get(uuid.uuid4())


class TestCaptura:
    def test_un_audio_genera_el_prompt(
        self, db_session: Session, bot_settings: Settings, fake_bot, chilean
    ) -> None:
        prompt = PromptCaptureService(db_session, bot_settings).handle(
            make_update(voice=True)
        )

        assert prompt is not None
        assert prompt.title == "Endpoint de salud"
        assert prompt.project_id is None
        assert "agreguemos un endpoint" in prompt.raw_text

    def test_avisa_al_recibir_y_al_terminar(
        self, db_session: Session, bot_settings: Settings, fake_bot, chilean
    ) -> None:
        PromptCaptureService(db_session, bot_settings).handle(make_update(voice=True))

        assert len(fake_bot.sent) == 2
        assert "Escuchando" in fake_bot.texts[0]
        assert "Principal" in fake_bot.texts[1]

    def test_todo_llega_a_principal(
        self, db_session: Session, bot_settings: Settings, fake_bot, chilean
    ) -> None:
        """Ya no se clasifica al dictar, aunque el proyecto exista.

        Adivinarlo fallaba seguido, y un prompt en la carpeta equivocada se
        pierde de vista. Desde Principal se arrastra donde corresponde.
        """
        prompt = PromptCaptureService(db_session, bot_settings).handle(
            make_update(text="algo para Chilean2Sign")
        )

        assert prompt is not None
        assert prompt.project_id is None
        assert "Principal" in fake_bot.texts[-1]


    def test_si_falla_el_modelo_no_se_pierde_la_captura(
        self,
        db_session: Session,
        bot_settings: Settings,
        fake_bot,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(prompt_module, "Redactor", BrokenRedactor)

        prompt = PromptCaptureService(db_session, bot_settings).handle(
            make_update(text="una idea larga que no quiero perder")
        )

        assert prompt is not None
        assert prompt.raw_text == "una idea larga que no quiero perder"
        assert prompt.content == "una idea larga que no quiero perder"

    def test_un_telegram_sin_vincular_no_deja_nada(
        self, db_session: Session, bot_settings: Settings, fake_bot
    ) -> None:
        """Se le avisa, pero no se procesa: sin saber de quién es el audio no
        hay a qué cuenta mandarlo. El aviso no cuesta ninguna llamada al
        modelo, así que responder es gratis."""
        prompt = PromptCaptureService(db_session, bot_settings).handle(
            make_update(user_id=999, text="hola")
        )

        assert prompt is None
        assert "vinculado" in fake_bot.texts[-1]


class TestRedactorPrompt:
    def test_el_contexto_lista_los_proyectos(self) -> None:
        texto = Redactor._render(
            [("Silu", "Sistema personal."), ("ICAI", "")]
        )

        assert "### Silu" in texto
        assert "Sistema personal." in texto
        # Un proyecto sin descriptor se nombra igual, para que el modelo pueda
        # asignarlo aunque todavía no esté documentado.
        assert "### ICAI" in texto

    def test_sin_proyectos_no_revienta(self) -> None:
        assert Redactor._render([]) != ""


class TestApi:
    @pytest.fixture
    def cliente(self, db_session: Session, bot_settings: Settings):
        app = create_app()
        app.dependency_overrides[get_session] = lambda: db_session
        app.dependency_overrides[get_settings] = lambda: bot_settings
        test_client = TestClient(app, base_url="https://testserver")
        AuthService(db_session).crear_usuario(TEST_EMAIL, TEST_PASSWORD)
        test_client.post(
            "/api/v1/auth/login",
            json={"email": TEST_EMAIL, "password": TEST_PASSWORD},
        )
        yield test_client
        app.dependency_overrides.clear()

    def test_crear_proyecto(self, cliente: TestClient) -> None:
        respuesta = cliente.post(
            "/api/v1/prompts/projects",
            json={"name": "Silu", "description_md": "# Silu"},
        )

        assert respuesta.status_code == 201
        assert respuesta.json()["prompts_count"] == 0

    def test_campos_desconocidos_dan_422(self, cliente: TestClient) -> None:
        respuesta = cliente.post("/api/v1/prompts/projects", json={"nombre": "typo"})

        assert respuesta.status_code == 422

    def test_el_webhook_rechaza_sin_secreto(self, cliente: TestClient) -> None:
        respuesta = cliente.post(
            "/api/v1/prompts/telegram/webhook",
            json=make_update(text="hola").model_dump(by_alias=True),
        )

        assert respuesta.status_code == 403

    def test_el_webhook_acepta_con_el_secreto(
        self, cliente: TestClient, fake_bot
    ) -> None:
        respuesta = cliente.post(
            "/api/v1/prompts/telegram/webhook",
            json=make_update(text="hola").model_dump(by_alias=True),
            headers={"X-Telegram-Bot-Api-Secret-Token": SECRET},
        )

        assert respuesta.status_code == 200

    def test_sin_sesion_los_prompts_no_se_ven(self, db_session: Session) -> None:
        settings = Settings(
            postgres_user="u",
            postgres_password="p",
            postgres_db="d",
            app_password="x",
            session_secret="y",
        )
        app = create_app()
        app.dependency_overrides[get_session] = lambda: db_session
        app.dependency_overrides[get_settings] = lambda: settings
        sin_sesion = TestClient(app, base_url="https://testserver")

        assert sin_sesion.get("/api/v1/prompts").status_code == 401
        assert sin_sesion.get("/api/v1/prompts/projects").status_code == 401
        app.dependency_overrides.clear()
