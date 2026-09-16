"""Registra (o borra) el webhook de Telegram.

Se ejecuta dentro del contenedor, que ya tiene las credenciales:

    docker compose run --rm backend python scripts/set_webhook.py
    docker compose run --rm backend python scripts/set_webhook.py --delete
    docker compose run --rm backend python scripts/set_webhook.py --info
"""

import argparse
import sys

import httpx

from app.core.config import get_settings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--url",
        default="https://silu.jofiguero.cl/api/v1/telegram/webhook",
        help="URL pública del webhook",
    )
    parser.add_argument("--delete", action="store_true", help="Elimina el webhook")
    parser.add_argument("--info", action="store_true", help="Muestra el estado actual")
    args = parser.parse_args()

    settings = get_settings()
    if not settings.telegram_bot_token:
        print("Falta TELEGRAM_BOT_TOKEN en el .env", file=sys.stderr)
        return 1

    api = f"https://api.telegram.org/bot{settings.telegram_bot_token}"

    with httpx.Client(timeout=30.0) as client:
        if args.info:
            response = client.get(f"{api}/getWebhookInfo")
        elif args.delete:
            response = client.post(
                f"{api}/deleteWebhook", json={"drop_pending_updates": True}
            )
        else:
            if not settings.telegram_webhook_secret:
                print("Falta TELEGRAM_WEBHOOK_SECRET en el .env", file=sys.stderr)
                return 1
            response = client.post(
                f"{api}/setWebhook",
                json={
                    "url": args.url,
                    "secret_token": settings.telegram_webhook_secret,
                    # Solo interesan los mensajes; el resto de eventos es ruido.
                    "allowed_updates": ["message", "edited_message"],
                    "drop_pending_updates": True,
                },
            )

    payload = response.json()
    print(payload)
    return 0 if payload.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
