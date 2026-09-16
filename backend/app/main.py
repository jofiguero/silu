"""Punto de entrada de la API de Silu."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.api.errors import register_exception_handlers
from app.api.v1.router import api_router
from app.core.config import Settings, get_settings
from app.db.session import engine

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
)

# httpx registra la URL completa de cada petición, y el token del bot viaja
# dentro de la URL de la API de Telegram. A nivel INFO eso deja la credencial
# escrita en los logs del servidor.
logging.getLogger("httpx").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Comprueba la base al arrancar y libera el pool al terminar.

    Fallar aquí es preferible a arrancar "sano" y devolver errores 500 en la
    primera petición real.
    """
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))
    logger.info("Conexión a la base de datos verificada")

    yield

    engine.dispose()
    logger.info("Pool de conexiones cerrado")


def create_app(settings: Settings | None = None) -> FastAPI:
    """Fábrica de la aplicación.

    Construirla en una función, en vez de a nivel de módulo, permite crear
    instancias con configuración distinta en los tests sin tocar el entorno.
    """
    settings = settings or get_settings()

    app = FastAPI(
        title=settings.app_name,
        description="Sistema personal de tickets: captura por voz, revisión en web.",
        version="0.1.0",
        lifespan=lifespan,
        docs_url=f"{settings.api_prefix}/docs",
        openapi_url=f"{settings.api_prefix}/openapi.json",
    )

    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    register_exception_handlers(app)
    app.include_router(api_router, prefix=settings.api_prefix)

    return app


app = create_app()
