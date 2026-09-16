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

    # --- Paginación ---
    default_page_size: int = Field(default=50, ge=1, le=200)
    max_page_size: int = Field(default=200, ge=1, le=1000)

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
        return (
            f"postgresql+psycopg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @computed_field  # type: ignore[prop-decorator]
    @property
    def is_dev(self) -> bool:
        return self.environment == "dev"

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
