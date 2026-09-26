"""Contraseñas y sesiones.

Dos piezas con exigencias opuestas:

- La **contraseña** la elige una persona, así que se puede adivinar. Se guarda
  con argon2id, que es deliberadamente lento y duro en memoria: hace que
  probar millones de candidatas salga caro incluso con una GPU. De paso, esos
  ~200 ms por verificación son el primer freno a la fuerza bruta.

- El **token de sesión** lo generamos nosotros con 256 bits de azar, así que
  no se adivina. Ahí no hace falta un hash lento: se guarda su SHA-256 para
  que leer la tabla no entregue sesiones usables, y listo. Usar argon2 aquí
  costaría 200 ms en cada petición sin comprar nada.
"""

import hashlib
import hmac
import logging
import secrets

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError

logger = logging.getLogger(__name__)

SESSION_COOKIE = "silu_session"

# Los parámetros van dentro de la cadena del hash, así que subirlos después no
# invalida los hashes ya guardados. Estos son los recomendados por la propia
# biblioteca; 64 MB por verificación es holgado en un servidor con 3.7 GB.
_hasher = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=4)

# Hash de una contraseña que nadie usa. Sirve para gastar el mismo tiempo
# cuando el correo no existe: si responder fuera instantáneo en ese caso, el
# tiempo de respuesta revelaría qué cuentas están registradas.
_HASH_SEÑUELO = _hasher.hash("contraseña que no le sirve a nadie")


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerifyMismatchError, InvalidHashError):
        return False


def gastar_tiempo_de_hash() -> None:
    """Verifica contra un hash señuelo, para no delatar cuentas inexistentes."""
    verify_password("da lo mismo", _HASH_SEÑUELO)


def necesita_rehash(password_hash: str) -> bool:
    """Si el hash se hizo con parámetros más débiles que los actuales."""
    try:
        return _hasher.check_needs_rehash(password_hash)
    except InvalidHashError:
        return False


# --- Sesiones ---


def create_session_token() -> str:
    """El valor que viaja en la cookie. Solo se ve una vez: se guarda su hash."""
    return secrets.token_urlsafe(32)


def hash_session_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def tokens_coinciden(a: str, b: str) -> bool:
    """Comparación en tiempo constante.

    Con `==`, lo que tarda en fallar revela cuántos caracteres iniciales
    acertó quien lo intenta.
    """
    return hmac.compare_digest(a, b)
