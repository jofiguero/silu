"""Configuración de la aplicación.

Toda la configuración entra por variables de entorno y se valida con
pydantic-settings al arrancar: si falta una credencial o un valor tiene el tipo
equivocado, la aplicación falla de inmediato y con un mensaje claro, en vez de
romperse más tarde en medio de una petición.
"""

from functools import lru_cache
from typing import Literal

from pydantic import Field, computed_field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- Aplicación ---
    app_name: str = "Silu"
    environment: Literal["dev", "prod"] = "prod"
    api_prefix: str = "/api/v1"

    # --- Base de datos ---
    postgres_user: str
    postgres_password: str
    postgres_db: str
    postgres_host: str = "db"
    postgres_port: int = 5432

    # Rol con el que se conecta la aplicación para atender peticiones. Es
    # DISTINTO del dueño de las tablas a propósito: en Postgres el dueño se
    # salta las políticas de seguridad por fila, así que si la app entrara con
    # él, RLS no protegería nada. Las migraciones sí usan el dueño, porque
    # necesitan crear tablas y tocar filas de todos.
    #
    # Sin configurar, la app entra como el dueño y RLS queda inerte. Se avisa
    # al arrancar en vez de fallar: así un despliegue a medio configurar sigue
    # funcionando mientras se arregla.
    app_db_user: str | None = None
    app_db_password: str | None = None

    # --- Paginación ---
    default_page_size: int = Field(default=50, ge=1, le=200)
    max_page_size: int = Field(default=200, ge=1, le=1000)

    # --- Autenticación de la web app ---
    # Un solo usuario: una contraseña y un secreto para firmar la sesión.
    # Sin ambos, la API queda cerrada por completo en vez de abierta.
    app_password: str | None = None
    session_secret: str | None = None
    session_days: int = Field(default=30, ge=1, le=365)

    # --- Telegram ---
    # Opcionales: si faltan, la app arranca igual y el webhook responde 503.
    # Así el backend sigue sirviendo la API aunque el bot no esté configurado.
    telegram_bot_token: str | None = None
    # Secreto que Telegram devuelve en cada webhook. Es lo único que distingue
    # una petición legítima de cualquiera que adivine la URL.
    telegram_webhook_secret: str | None = None
    # Solo este usuario puede crear tickets. Sin la restricción, cualquiera que
    # encuentre el bot llena la bandeja y gasta créditos de transcripción.
    telegram_allowed_user_id: int | None = None

    # --- Bot de prompts ---
    # Bot separado del de tickets: son dos flujos distintos y mezclarlos
    # obligaría a adivinar en cuál de los dos va cada audio.
    telegram_prompts_bot_token: str | None = None
    telegram_prompts_webhook_secret: str | None = None

    # --- OpenAI ---
    # Transcripción y LLM comparten cuenta, API key y saldo: se cargan créditos
    # en un solo lugar y se descuentan de ahí para ambos.
    openai_api_key: str | None = None
    openai_base_url: str = "https://api.openai.com/v1"

    # --- Transcripción ---
    transcription_model: str = "gpt-4o-mini-transcribe"
    transcription_language: str = "es"

    # --- LLM ---
    llm_model: str = "gpt-5-nano"
    # El agente elige qué acciones ejecutar sobre los tickets, que es bastante
    # más exigente que redactar un resumen. Va en su propia variable para poder
    # subirlo sin tocar el de los resúmenes.
    agent_model: str = "gpt-5-nano"
    agent_max_steps: int = Field(default=6, ge=1, le=20)
    # Ordenar una divagación sin agregarle ni quitarle nada exige seguir la
    # instrucción con disciplina: un modelo chico se pone creativo y completa
    # lo que cree que falta. Por eso va uno mayor que el de los resúmenes.
    prompt_model: str = "gpt-5-mini"
    prompt_timeout_seconds: float = 120.0
    llm_timeout_seconds: float = 60.0
    # Algunos modelos de razonamiento solo aceptan la temperatura por defecto.
    # None significa no enviar el parámetro.
    llm_temperature: float | None = None
    # Overrides opcionales: permiten mover SOLO el LLM a otro gateway que hable
    # el protocolo de OpenAI, sin tocar la transcripción.
    llm_api_key: str | None = None
    llm_base_url: str | None = None

    # --- CORS ---
    # Orígenes permitidos para la web app. En producción se restringe al
    # dominio real; vacío significa que no se permite ningún origen cruzado.
    cors_origins: list[str] = []

    @model_validator(mode="before")
    @classmethod
    def treat_blanks_as_missing(cls, data: object) -> object:
        """Una variable vacía en el .env es una variable sin configurar.

        Las plantillas de .env dejan las claves declaradas y vacías, y sin esto
        un `TELEGRAM_ALLOWED_USER_ID=` hace fallar el arranque completo al
        intentar leer "" como entero.
        """
        if isinstance(data, dict):
            return {
                key: (None if isinstance(value, str) and not value.strip() else value)
                for key, value in data.items()
            }
        return data

    @computed_field  # type: ignore[prop-decorator]
    @property
    def database_url(self) -> str:
        """Conexión como dueño. La usan Alembic y los scripts de mantención."""
        return self._url(self.postgres_user, self.postgres_password)

    @property
    def app_database_url(self) -> str:
        """Conexión de la aplicación, sometida a las políticas por fila."""
        if self.app_db_user and self.app_db_password:
            return self._url(self.app_db_user, self.app_db_password)
        return self.database_url

    @property
    def rls_activo(self) -> bool:
        return bool(self.app_db_user and self.app_db_password)

    def _url(self, usuario: str, clave: str) -> str:
        return (
            f"postgresql+psycopg://{usuario}:{clave}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @computed_field  # type: ignore[prop-decorator]
    @property
    def is_dev(self) -> bool:
        return self.environment == "dev"

    @computed_field  # type: ignore[prop-decorator]
    @property
    def auth_configured(self) -> bool:
        return bool(self.app_password and self.session_secret)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def prompts_bot_configured(self) -> bool:
        return bool(
            self.telegram_prompts_bot_token and self.telegram_prompts_webhook_secret
        )

    @computed_field  # type: ignore[prop-decorator]
    @property
    def resolved_llm_api_key(self) -> str | None:
        return self.llm_api_key or self.openai_api_key

    @computed_field  # type: ignore[prop-decorator]
    @property
    def resolved_llm_base_url(self) -> str:
        return self.llm_base_url or self.openai_base_url

    @computed_field  # type: ignore[prop-decorator]
    @property
    def telegram_configured(self) -> bool:
        """Basta el token y el secreto para atender el webhook.

        La restricción de acceso se aplica dentro del servicio, no aquí: si el
        webhook exigiera `telegram_allowed_user_id`, no habría forma de usar
        /id para averiguar ese id la primera vez.
        """
        return bool(self.telegram_bot_token and self.telegram_webhook_secret)


@lru_cache
def get_settings() -> Settings:
    """Instancia única de la configuración.

    Cacheada porque leer y validar el entorno en cada petición sería gasto puro,
    y porque permite sobrescribirla en tests con `get_settings.cache_clear()`.
    """
    return Settings()  # type: ignore[call-arg]
