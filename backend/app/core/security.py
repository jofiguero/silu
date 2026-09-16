"""Sesiones firmadas.

Un solo usuario, una sola contraseña. La sesión es un token firmado con HMAC
que viaja en una cookie: el servidor no guarda estado, y alterar el contenido
del token invalida la firma.

Se usa la biblioteca estándar en vez de JWT porque aquí no hay nada que
negociar entre servicios: es el mismo proceso firmando y verificando.
"""

import base64
import hashlib
import hmac
import json
import logging
import secrets
import time

logger = logging.getLogger(__name__)

SESSION_COOKIE = "silu_session"


def _b64encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _b64decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


def verify_password(candidate: str, expected: str) -> bool:
    """Comparación en tiempo constante.

    Con `==`, el tiempo que tarda en fallar revela cuántos caracteres iniciales
    acertó quien lo intenta.
    """
    return hmac.compare_digest(candidate.encode(), expected.encode())


def create_session_token(secret: str, *, ttl_seconds: int) -> str:
    payload = {
        "exp": int(time.time()) + ttl_seconds,
        # Identificador único por sesión: permite distinguir dispositivos en los
        # logs sin guardar nada del usuario.
        "jti": secrets.token_hex(8),
    }
    body = _b64encode(json.dumps(payload, separators=(",", ":")).encode())
    signature = _sign(secret, body)
    return f"{body}.{signature}"


def verify_session_token(token: str, secret: str) -> bool:
    try:
        body, signature = token.split(".", 1)
    except ValueError:
        return False

    if not hmac.compare_digest(signature, _sign(secret, body)):
        return False

    try:
        payload = json.loads(_b64decode(body))
    except (ValueError, json.JSONDecodeError):
        return False

    return int(payload.get("exp", 0)) > time.time()


def _sign(secret: str, body: str) -> str:
    digest = hmac.new(secret.encode(), body.encode(), hashlib.sha256).digest()
    return _b64encode(digest)
