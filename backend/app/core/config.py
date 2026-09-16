"""Configuración de la aplicación.

Toda la configuración entra por variables de entorno y se valida con
pydantic-settings al arrancar: si falta una credencial o un valor tiene el tipo
equivocado, la aplicación falla de inmediato y con un mensaje claro, en vez de
romperse más tarde en medio de una petición.
"""

from functools import lru_cache
from typing import Literal

from pydantic import Field, computed_field
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

    # --- CORS ---
    # Orígenes permitidos para la web app. En producción se restringe al
    # dominio real; vacío significa que no se permite ningún origen cruzado.
    cors_origins: list[str] = []

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


@lru_cache
def get_settings() -> Settings:
    """Instancia única de la configuración.

    Cacheada porque leer y validar el entorno en cada petición sería gasto puro,
    y porque permite sobrescribirla en tests con `get_settings.cache_clear()`.
    """
    return Settings()  # type: ignore[call-arg]
