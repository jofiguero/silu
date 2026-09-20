"""Ensamblado de la versión 1 de la API."""

from fastapi import APIRouter

from app.api.v1 import (
    agent,
    auth,
    expenses,
    health,
    prompts,
    telegram,
    threads,
    tickets,
)

api_router = APIRouter()

# Públicos: salud (monitoreo) y login. El webhook se protege con su propio
# secreto compartido con Telegram, no con la sesión de la web app.
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(telegram.router)
# El webhook de prompts tambien se protege con su propio secreto.
api_router.include_router(prompts.webhook_router)

# Requieren sesión.
api_router.include_router(tickets.router)
api_router.include_router(threads.router)
api_router.include_router(expenses.router)
api_router.include_router(prompts.router)
api_router.include_router(agent.router)
