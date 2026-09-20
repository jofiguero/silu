"""Registra (o borra) el webhook del bot de PROMPTS.

Es el segundo bot, distinto del de tickets. Se ejecuta dentro del contenedor:

    docker compose run --rm backend python scripts/set_prompts_webhook.py
    docker compose run --rm backend python scripts/set_prompts_webhook.py --info
    docker compose run --rm backend python scripts/set_prompts_webhook.py --delete
"""

import argparse
import sys

import httpx

from app.core.config import get_settings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--url",
        default="https://silu.jofiguero.cl/api/v1/prompts/telegram/webhook",
        help="URL publica del webhook de prompts",
    )
    parser.add_argument("--delete", action="store_true", help="Elimina el webhook")
    parser.add_argument("--info", action="store_true", help="Muestra el estado actual")
    args = parser.parse_args()

    settings = get_settings()
    if not settings.telegram_prompts_bot_token:
        print("Falta TELEGRAM_PROMPTS_BOT_TOKEN en el .env", file=sys.stderr)
        return 1

    api = f"https://api.telegram.org/bot{settings.telegram_prompts_bot_token}"

    with httpx.Client(timeout=30.0) as client:
        if args.info:
            respuesta = client.get(f"{api}/getWebhookInfo")
        elif args.delete:
            respuesta = client.post(
                f"{api}/deleteWebhook", json={"drop_pending_updates": True}
            )
        else:
            if not settings.telegram_prompts_webhook_secret:
                print("Falta TELEGRAM_PROMPTS_WEBHOOK_SECRET", file=sys.stderr)
                return 1
            respuesta = client.post(
                f"{api}/setWebhook",
                json={
                    "url": args.url,
                    "secret_token": settings.telegram_prompts_webhook_secret,
                    "allowed_updates": ["message", "edited_message"],
                    "drop_pending_updates": True,
                },
            )

    payload = respuesta.json()
    print(payload)
    return 0 if payload.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
