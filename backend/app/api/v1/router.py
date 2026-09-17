"""Ensamblado de la versión 1 de la API."""

from fastapi import APIRouter

from app.api.v1 import agent, auth, categories, health, telegram, tickets

api_router = APIRouter()

# Públicos: salud (monitoreo) y login. El webhook se protege con su propio
# secreto compartido con Telegram, no con la sesión de la web app.
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(telegram.router)

# Requieren sesión.
api_router.include_router(tickets.router)
api_router.include_router(categories.router)
api_router.include_router(agent.router)
