"""Tests del webhook y del pipeline de captura.

Los servicios externos (Telegram, Whisper, el LLM) se reemplazan por dobles: lo
que se prueba aquí es la lógica de Silu —autorización, limpieza del texto,
degradación cuando el modelo falla—, no que las APIs ajenas funcionen.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.deps import get_session_factory
from app.core.config import Settings, get_settings
from app.db.session import get_session
from app.integrations.llm import LLMError, TicketDraft
from app.main import create_app
from app.db.models import Ticket
from app.schemas.telegram import TelegramUpdate
from app.services import capture as capture_module
from app.services.capture import CaptureService

ALLOWED_USER = 42
TEST_EMAIL = "pruebas@example.com"
OTHER_USER = 999
SECRET = "un-secreto-de-pruebas"


# --- Dobles de los servicios externos ---


class _NonClosingSession:
    """Envuelve la sesión del test para que el código bajo prueba pueda usarla
    como contexto sin cerrarla: el cierre y el rollback los maneja la fixture."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def __enter__(self) -> Session:
        return self._session

    def __exit__(self, *_exc: object) -> None:
        return None


class FakeTelegram:
    """Registra los mensajes enviados en vez de llamar a Telegram."""

    def __init__(self, *_args, **_kwargs) -> None:
        self.sent: list[tuple[int, str]] = []
        self.audio = b"audio-falso"

    def send_message(self, chat_id: int, text: str) -> None:
        self.sent.append((chat_id, text))

    def download_file(self, file_id: str) -> bytes:
        return self.audio

    @property
    def texts(self) -> list[str]:
        return [text for _, text in self.sent]


class FakeTranscriber:
    def __init__(self, *_args, **_kwargs) -> None:
        pass

    def transcribe(self, audio: bytes, filename: str = "audio.ogg") -> str:
        return "Gaste 1000 pesos en un helado"


class FakeDrafter:
    def __init__(self, *_args, **_kwargs) -> None:
        pass

    def draft(self, raw_text: str, **_kwargs) -> TicketDraft:
        return TicketDraft(title="Gasto: helado", summary="Compra de un helado.")


class UrgentDrafter:
    """Devuelve urgencia, como cuando la persona la dicta."""

    def __init__(self, *_args, **_kwargs) -> None:
        pass

    def draft(self, raw_text: str, **_kwargs) -> TicketDraft:
        return TicketDraft(
            title="Llamar al dentista",
            summary="Pedir hora al dentista.",
            urgent=True,
        )


class BrokenDrafter:
    def __init__(self, *_args, **_kwargs) -> None:
        pass

    def draft(self, raw_text: str, **_kwargs) -> TicketDraft:
        raise LLMError("el modelo no respondió")


# --- Fixtures ---


@pytest.fixture
def bot_settings() -> Settings:
    return get_settings().model_copy(
        update={
            "telegram_bot_token": "token-de-pruebas",
            "telegram_webhook_secret": SECRET,
            "telegram_allowed_user_id": ALLOWED_USER,
            "openai_api_key": "key-falsa",
            "app_password": "contrasena-de-pruebas",
            "session_secret": "secreto-de-pruebas",
        }
    )


@pytest.fixture
def fake_telegram(monkeypatch: pytest.MonkeyPatch) -> FakeTelegram:
    client = FakeTelegram()
    monkeypatch.setattr(capture_module, "TelegramClient", lambda *a, **k: client)
    monkeypatch.setattr(capture_module, "Transcriber", FakeTranscriber)
    monkeypatch.setattr(capture_module, "TicketDrafter", FakeDrafter)
    return client


def make_update(
    *,
    user_id: int = ALLOWED_USER,
    text: str | None = None,
    voice: bool = False,
) -> TelegramUpdate:
    message: dict = {
        "message_id": 1,
        "chat": {"id": 555},
        "from": {"id": user_id, "first_name": "Joaquin"},
    }
    if text is not None:
        message["text"] = text
    if voice:
        message["voice"] = {"file_id": "file-123", "duration": 4}

    return TelegramUpdate.model_validate({"update_id": 1, "message": message})


# --- Webhook ---



@pytest.fixture(autouse=True)
def telegram_vinculado(db_session: Session):
    """Vincula la cuenta del test al Telegram que usan los updates de prueba.

    El bot ya no atiende por lista de ids permitidos sino por vínculo, así que
    sin esto ninguna captura llegaría a ninguna bandeja.
    """
    from app.services.auth import AuthService, TelegramService

    usuario = AuthService(db_session).buscar_por_email(TEST_EMAIL)
    telegram = TelegramService(db_session)
    telegram.vincular(telegram.generar_codigo(usuario).code, ALLOWED_USER)
    return usuario


class TestWebhook:
    @pytest.fixture
    def client(self, db_session: Session, bot_settings: Settings):
        app = create_app()
        app.dependency_overrides[get_session] = lambda: db_session
        app.dependency_overrides[get_settings] = lambda: bot_settings
        # La tarea en segundo plano abre su propia sesión. Sin sustituir también
        # la fábrica, escribiría en la base real en vez de en la de pruebas.
        app.dependency_overrides[get_session_factory] = lambda: (
            lambda: _NonClosingSession(db_session)
        )
        yield TestClient(app, base_url="https://testserver")
        app.dependency_overrides.clear()

    def test_rechaza_sin_secreto(self, client: TestClient) -> None:
        response = client.post(
            "/api/v1/telegram/webhook",
            json=make_update(text="hola").model_dump(by_alias=True),
        )

        assert response.status_code == 403

    def test_rechaza_secreto_incorrecto(self, client: TestClient) -> None:
        response = client.post(
            "/api/v1/telegram/webhook",
            json=make_update(text="hola").model_dump(by_alias=True),
            headers={"X-Telegram-Bot-Api-Secret-Token": "secreto-equivocado"},
        )

        assert response.status_code == 403

    def test_acepta_con_el_secreto_correcto(
        self, client: TestClient, fake_telegram: FakeTelegram
    ) -> None:
        response = client.post(
            "/api/v1/telegram/webhook",
            json=make_update(text="hola").model_dump(by_alias=True),
            headers={"X-Telegram-Bot-Api-Secret-Token": SECRET},
        )

        assert response.status_code == 200
        assert response.json() == {"ok": True}

    def test_el_trabajo_en_segundo_plano_usa_la_sesion_del_test(
        self, client: TestClient, db_session: Session, fake_telegram: FakeTelegram
    ) -> None:
        # Regresión: antes la tarea en segundo plano importaba SessionFactory
        # directamente, así que los tests creaban tickets en la base real.
        antes = db_session.query(Ticket).count()

        client.post(
            "/api/v1/telegram/webhook",
            json=make_update(text="comprar pan").model_dump(by_alias=True),
            headers={"X-Telegram-Bot-Api-Secret-Token": SECRET},
        )

        assert db_session.query(Ticket).count() == antes + 1

    def test_responde_503_si_el_bot_no_esta_configurado(
        self, db_session: Session
    ) -> None:
        # La configuración se fija explícitamente: el contenedor ya tiene el
        # bot configurado y heredarla haría que el test dependiera de eso.
        sin_bot = Settings(
            postgres_user="u",
            postgres_password="p",
            postgres_db="d",
            telegram_bot_token=None,
            telegram_webhook_secret=None,
        )
        app = create_app()
        app.dependency_overrides[get_session] = lambda: db_session
        app.dependency_overrides[get_settings] = lambda: sin_bot
        client = TestClient(app, base_url="https://testserver")

        response = client.post(
            "/api/v1/telegram/webhook",
            json=make_update(text="hola").model_dump(by_alias=True),
            headers={"X-Telegram-Bot-Api-Secret-Token": SECRET},
        )

        assert response.status_code == 503
        app.dependency_overrides.clear()

    def test_ignora_updates_con_forma_desconocida(self, client: TestClient) -> None:
        # Telegram agrega tipos de evento con frecuencia; uno desconocido no
        # debe romper el webhook.
        response = client.post(
            "/api/v1/telegram/webhook",
            json={"update_id": 7, "poll_answer": {"poll_id": "x"}},
            headers={"X-Telegram-Bot-Api-Secret-Token": SECRET},
        )

        assert response.status_code == 200


# --- Pipeline de captura ---


class TestCaptura:
    def test_texto_crea_ticket(
        self, db_session: Session, bot_settings: Settings, fake_telegram: FakeTelegram
    ) -> None:
        service = CaptureService(db_session, bot_settings)

        ticket = service.handle(make_update(text="Comprar pan manana"))

        assert ticket is not None
        assert ticket.title == "Gasto: helado"
        assert ticket.raw_text == "Comprar pan manana"

    def test_audio_se_transcribe(
        self, db_session: Session, bot_settings: Settings, fake_telegram: FakeTelegram
    ) -> None:
        service = CaptureService(db_session, bot_settings)

        ticket = service.handle(make_update(voice=True))

        assert ticket is not None
        assert ticket.raw_text == "Gaste 1000 pesos en un helado"

    def test_avisa_al_recibir_y_al_terminar(
        self, db_session: Session, bot_settings: Settings, fake_telegram: FakeTelegram
    ) -> None:
        service = CaptureService(db_session, bot_settings)

        service.handle(make_update(voice=True))

        assert len(fake_telegram.sent) == 2
        assert "Escuchando" in fake_telegram.texts[0]
        assert "Gasto: helado" in fake_telegram.texts[1]

    @pytest.mark.parametrize(
        "mensaje",
        [
            "Silu, generame un ticket sobre comprar pan",
            "Oye Silu, anotame que hay que comprar pan",
            "silu: comprar pan",
        ],
    )
    def test_limpia_la_muletilla_de_dictado(
        self,
        db_session: Session,
        bot_settings: Settings,
        fake_telegram: FakeTelegram,
        mensaje: str,
    ) -> None:
        service = CaptureService(db_session, bot_settings)

        ticket = service.handle(make_update(text=mensaje))

        assert ticket is not None
        assert "silu" not in ticket.raw_text.lower()
        assert "comprar pan" in ticket.raw_text.lower()

    def test_un_telegram_sin_vincular_no_deja_nada(
        self, db_session: Session, bot_settings: Settings, fake_telegram: FakeTelegram
    ) -> None:
        """Se le avisa, pero no se procesa: sin saber de quién es el audio no
        hay bandeja a la que mandarlo."""
        service = CaptureService(db_session, bot_settings)

        ticket = service.handle(make_update(user_id=OTHER_USER, text="hola"))

        assert ticket is None
        assert "vinculado" in fake_telegram.sent[-1][1]

    def test_comando_id_responde_a_cualquiera(
        self, db_session: Session, bot_settings: Settings, fake_telegram: FakeTelegram
    ) -> None:
        # Es la unica forma de conocer el propio id para configurar el acceso.
        service = CaptureService(db_session, bot_settings)

        service.handle(make_update(user_id=OTHER_USER, text="/id"))

        assert str(OTHER_USER) in fake_telegram.texts[0]

    def test_mensaje_sin_texto_ni_audio_avisa(
        self, db_session: Session, bot_settings: Settings, fake_telegram: FakeTelegram
    ) -> None:
        service = CaptureService(db_session, bot_settings)

        ticket = service.handle(make_update())

        assert ticket is None
        assert "voz y texto" in fake_telegram.texts[0]


class TestDegradacion:
    """Si el LLM falla, la captura no se pierde: se guarda sin procesar."""

    @pytest.fixture
    def broken_llm(
        self, monkeypatch: pytest.MonkeyPatch, fake_telegram: FakeTelegram
    ) -> FakeTelegram:
        monkeypatch.setattr(capture_module, "TicketDrafter", BrokenDrafter)
        return fake_telegram

    def test_guarda_el_ticket_igual(
        self, db_session: Session, bot_settings: Settings, broken_llm: FakeTelegram
    ) -> None:
        service = CaptureService(db_session, bot_settings)

        ticket = service.handle(make_update(text="Comprar pan manana"))

        assert ticket is not None
        assert ticket.raw_text == "Comprar pan manana"
        assert ticket.summary == "Comprar pan manana"

    def test_avisa_que_quedo_sin_procesar(
        self, db_session: Session, bot_settings: Settings, broken_llm: FakeTelegram
    ) -> None:
        service = CaptureService(db_session, bot_settings)

        service.handle(make_update(text="Comprar pan manana"))

        assert "no pude procesarlo" in broken_llm.texts[-1]


class TestConfiguracionInicial:
    """El /id tiene que funcionar antes de que exista la lista de permitidos,
    o no hay forma de conocer el propio id para configurarla."""

    def test_el_webhook_opera_sin_lista_de_permitidos(
        self, db_session: Session, bot_settings: Settings, fake_telegram: FakeTelegram
    ) -> None:
        sin_allowlist = bot_settings.model_copy(
            update={"telegram_allowed_user_id": None}
        )
        assert sin_allowlist.telegram_configured is True

        service = CaptureService(db_session, sin_allowlist)
        service.handle(make_update(user_id=OTHER_USER, text="/id"))

        assert str(OTHER_USER) in fake_telegram.texts[0]

    def test_sin_allowlist_no_se_crean_tickets(
        self, db_session: Session, bot_settings: Settings, fake_telegram: FakeTelegram
    ) -> None:
        sin_allowlist = bot_settings.model_copy(
            update={"telegram_allowed_user_id": None}
        )

        ticket = CaptureService(db_session, sin_allowlist).handle(
            make_update(text="comprar pan")
        )

        assert ticket is None


class TestVariablesVacias:
    def test_una_variable_vacia_equivale_a_no_configurada(self) -> None:
        # Las plantillas de .env dejan las claves declaradas y vacias; sin este
        # manejo, TELEGRAM_ALLOWED_USER_ID= tumbaba el arranque completo.
        settings = Settings(
            postgres_user="u",
            postgres_password="p",
            postgres_db="d",
            telegram_allowed_user_id="",
            telegram_bot_token="   ",
        )

        assert settings.telegram_allowed_user_id is None
        assert settings.telegram_bot_token is None


class TestCredencialesCentralizadas:
    """Transcripción y LLM comparten cuenta y saldo en OpenAI."""

    def _base(self, **extra) -> Settings:
        # Los overrides se fijan explícitamente: el entorno del contenedor
        # define estas variables y filtrarlas haría que el test dependiera de
        # cómo esté configurado el servidor donde corre.
        defaults = {
            "openai_base_url": "https://api.openai.com/v1",
            "llm_api_key": None,
            "llm_base_url": None,
        }
        return Settings(
            postgres_user="u",
            postgres_password="p",
            postgres_db="d",
            **{**defaults, **extra},
        )

    def test_el_llm_hereda_la_key_de_openai(self) -> None:
        settings = self._base(openai_api_key="sk-comun")

        assert settings.resolved_llm_api_key == "sk-comun"
        assert settings.resolved_llm_base_url == "https://api.openai.com/v1"

    def test_se_puede_mover_solo_el_llm_a_otro_gateway(self) -> None:
        # La transcripción sigue en OpenAI y el LLM se va a otro proveedor,
        # sin tocar código.
        settings = self._base(
            openai_api_key="sk-openai",
            llm_api_key="otro-token",
            llm_base_url="https://gateway.ejemplo/v1",
        )

        assert settings.openai_api_key == "sk-openai"
        assert settings.resolved_llm_api_key == "otro-token"
        assert settings.resolved_llm_base_url == "https://gateway.ejemplo/v1"

    def test_la_temperatura_no_se_envia_por_defecto(self) -> None:
        # Varios modelos de razonamiento rechazan una temperatura distinta de
        # la por defecto; omitirla evita un 400 innecesario.
        assert self._base().llm_temperature is None


class TestUrgenciaDesdeElAudio:
    """La persona marca la urgencia al dictar; el sistema no la infiere."""

    def test_sin_instruccion_no_queda_urgente(
        self, db_session: Session, bot_settings: Settings, fake_telegram: FakeTelegram
    ) -> None:
        ticket = CaptureService(db_session, bot_settings).handle(
            make_update(text="Gaste 1000 pesos en un helado")
        )

        assert ticket is not None
        assert ticket.urgent is False

    def test_con_instruccion_queda_urgente(
        self,
        db_session: Session,
        bot_settings: Settings,
        fake_telegram: FakeTelegram,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(capture_module, "TicketDrafter", UrgentDrafter)

        ticket = CaptureService(db_session, bot_settings).handle(
            make_update(text="Esto es urgente: llamar al dentista")
        )

        assert ticket is not None
        assert ticket.urgent is True

    def test_el_bot_avisa_que_quedo_urgente(
        self,
        db_session: Session,
        bot_settings: Settings,
        fake_telegram: FakeTelegram,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        # Si el modelo lo interpretó mal, se nota al instante.
        monkeypatch.setattr(capture_module, "TicketDrafter", UrgentDrafter)

        CaptureService(db_session, bot_settings).handle(make_update(text="algo"))

        assert "URGENTE" in fake_telegram.texts[-1]
