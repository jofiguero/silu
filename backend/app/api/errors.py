"""Traducción de errores del dominio a respuestas HTTP.

Registrar los manejadores aquí mantiene los endpoints limpios: ninguno necesita
try/except, porque un TicketNotFoundError lanzado en cualquier capa ya sabe
llegar al cliente como un 404 con la forma de ErrorResponse.
"""

import logging

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from app.core.exceptions import (
    CategoryInUseError,
    CategoryNameTakenError,
    CategoryNotFoundError,
    InvalidTicketTransitionError,
    ProtectedCategoryError,
    SiluError,
    TicketNotFoundError,
)

logger = logging.getLogger(__name__)


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(TicketNotFoundError)
    async def _not_found(_: Request, exc: TicketNotFoundError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"detail": exc.message},
        )

    @app.exception_handler(InvalidTicketTransitionError)
    async def _invalid_transition(
        _: Request, exc: InvalidTicketTransitionError
    ) -> JSONResponse:
        # 409: la petición es válida, pero choca con el estado actual del recurso.
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={"detail": exc.message},
        )

    @app.exception_handler(CategoryNotFoundError)
    async def _category_not_found(
        _: Request, exc: CategoryNotFoundError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND, content={"detail": exc.message}
        )

    @app.exception_handler(CategoryNameTakenError)
    @app.exception_handler(ProtectedCategoryError)
    @app.exception_handler(CategoryInUseError)
    async def _category_conflict(_: Request, exc: SiluError) -> JSONResponse:
        # 409: la petición es válida pero choca con el estado actual.
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT, content={"detail": exc.message}
        )

    @app.exception_handler(SiluError)
    async def _domain_error(_: Request, exc: SiluError) -> JSONResponse:
        logger.exception("Error de dominio no contemplado: %s", exc.message)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"detail": "Error interno"},
        )
