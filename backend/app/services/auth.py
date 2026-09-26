"""Cuentas, sesiones y freno a la fuerza bruta."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.security import (
    create_session_token,
    gastar_tiempo_de_hash,
    hash_password,
    hash_session_token,
    necesita_rehash,
    verify_password,
)
from app.db.models import LoginAttempt, User, UserSession

# Ventana en la que se cuentan los fallos.
VENTANA = timedelta(minutes=15)

# Tope por IP. Es la defensa que de verdad para a un bot: viene de una
# dirección y se queda sin intentos rápido.
FALLOS_POR_IP = 10

# Tope por cuenta, para el caso de un ataque repartido entre muchas IP contra
# un solo correo. Va alto a propósito: cualquiera puede gastar los intentos de
# otro con solo saber su correo, y prefiero que eso cueste 20 peticiones y
# dure 15 minutos antes que dejar a alguien afuera por media hora.
FALLOS_POR_CUENTA = 20


class CredencialesInvalidas(Exception):
    """Correo o contraseña que no calzan, o cuenta desactivada.

    Una sola excepción para los tres casos: distinguirlos en la respuesta le
    diría a quien prueba cuáles correos existen.
    """


class DemasiadosIntentos(Exception):
    def __init__(self, segundos: int) -> None:
        self.segundos = segundos
        super().__init__("Demasiados intentos")


class SinUsuarios(Exception):
    """No hay ninguna cuenta todavía; hay que crearla desde el servidor."""


class AuthService:
    def __init__(self, session: Session) -> None:
        self.session = session

    # --- Cuentas ---

    def crear_usuario(self, email: str, password: str, *, rol: str = "usuario") -> User:
        limpio = email.strip().lower()
        if self.buscar_por_email(limpio) is not None:
            raise ValueError(f"Ya existe una cuenta con el correo {limpio}")
        if rol not in {"admin", "usuario"}:
            raise ValueError("El rol tiene que ser 'admin' o 'usuario'")

        usuario = User(email=limpio, password_hash=hash_password(password), role=rol)
        self.session.add(usuario)
        self.session.commit()
        self.session.refresh(usuario)
        return usuario

    def buscar_por_email(self, email: str) -> User | None:
        stmt = select(User).where(func.lower(User.email) == email.strip().lower())
        return self.session.execute(stmt).scalar_one_or_none()

    def hay_usuarios(self) -> bool:
        return self.session.execute(select(func.count(User.id))).scalar_one() > 0

    def listar(self) -> Sequence[User]:
        return (
            self.session.execute(select(User).order_by(User.created_at))
            .scalars()
            .all()
        )

    def cambiar_password(self, usuario: User, password: str) -> User:
        """Cambia la contraseña y cierra todas las sesiones abiertas.

        Si alguien más la tenía, cambiarla lo tiene que dejar afuera. Sin
        cerrar las sesiones, su cookie seguiría sirviendo.
        """
        usuario.password_hash = hash_password(password)
        usuario.password_changed_at = datetime.now(timezone.utc)
        for sesion in usuario.sessions:
            self.session.delete(sesion)
        self.session.commit()
        self.session.refresh(usuario)
        return usuario

    # --- Entrar ---

    def login(
        self,
        email: str,
        password: str,
        *,
        ip: str,
        user_agent: str | None = None,
        dias: int = 30,
    ) -> tuple[User, str]:
        """Devuelve el usuario y el token de sesión, en claro por única vez."""
        if not self.hay_usuarios():
            raise SinUsuarios()

        self._revisar_limites(email, ip)

        usuario = self.buscar_por_email(email)
        if usuario is None:
            # Se gasta el mismo tiempo que en una verificación real: responder
            # al instante delataría que ese correo no está registrado.
            gastar_tiempo_de_hash()
            self._anotar(email, ip, ok=False)
            raise CredencialesInvalidas()

        if not verify_password(password, usuario.password_hash):
            self._anotar(email, ip, ok=False)
            raise CredencialesInvalidas()

        if not usuario.is_active:
            self._anotar(email, ip, ok=False)
            raise CredencialesInvalidas()

        # Si los parámetros de argon2 subieron desde que se guardó, se
        # aprovecha que tenemos la contraseña en la mano para rehashear.
        if necesita_rehash(usuario.password_hash):
            usuario.password_hash = hash_password(password)

        usuario.last_login_at = datetime.now(timezone.utc)
        token = self._abrir_sesion(usuario, ip=ip, user_agent=user_agent, dias=dias)
        self._anotar(email, ip, ok=True)
        self.session.commit()
        return usuario, token

    def _abrir_sesion(
        self, usuario: User, *, ip: str, user_agent: str | None, dias: int
    ) -> str:
        token = create_session_token()
        self.session.add(
            UserSession(
                user_id=usuario.id,
                token_hash=hash_session_token(token),
                expires_at=datetime.now(timezone.utc) + timedelta(days=dias),
                ip=ip,
                # Se recorta: un User-Agent puede venir larguísimo y esto es
                # solo para reconocer el dispositivo de un vistazo.
                user_agent=(user_agent or "")[:300] or None,
            )
        )
        return token

    def usuario_de_sesion(self, token: str) -> User | None:
        """El dueño de una sesión vigente, o None.

        Se busca por el hash del token. Una sesión vencida no se acepta y se
        borra de paso, así la tabla no acumula basura.
        """
        stmt = select(UserSession).where(
            UserSession.token_hash == hash_session_token(token)
        )
        sesion = self.session.execute(stmt).scalar_one_or_none()
        if sesion is None:
            return None

        ahora = datetime.now(timezone.utc)
        if sesion.expires_at <= ahora:
            self.session.delete(sesion)
            self.session.commit()
            return None

        usuario = sesion.user
        if not usuario.is_active:
            return None

        # Una sesión abierta antes del último cambio de contraseña no vale:
        # cambiarla tiene que echar a quien la tuviera.
        if sesion.created_at < usuario.password_changed_at:
            self.session.delete(sesion)
            self.session.commit()
            return None

        sesion.last_seen_at = ahora
        self.session.commit()
        return usuario

    def cerrar_sesion(self, token: str) -> None:
        stmt = select(UserSession).where(
            UserSession.token_hash == hash_session_token(token)
        )
        sesion = self.session.execute(stmt).scalar_one_or_none()
        if sesion is not None:
            self.session.delete(sesion)
            self.session.commit()

    # --- Límites ---

    def _revisar_limites(self, email: str, ip: str) -> None:
        desde = datetime.now(timezone.utc) - VENTANA

        por_ip = self._fallos(desde, ip=ip)
        if por_ip >= FALLOS_POR_IP:
            raise DemasiadosIntentos(int(VENTANA.total_seconds()))

        por_cuenta = self._fallos(desde, email=email)
        if por_cuenta >= FALLOS_POR_CUENTA:
            raise DemasiadosIntentos(int(VENTANA.total_seconds()))

    def _fallos(
        self, desde: datetime, *, ip: str | None = None, email: str | None = None
    ) -> int:
        stmt = select(func.count(LoginAttempt.id)).where(
            LoginAttempt.at >= desde, LoginAttempt.ok.is_(False)
        )
        if ip is not None:
            stmt = stmt.where(LoginAttempt.ip == ip)
        if email is not None:
            stmt = stmt.where(func.lower(LoginAttempt.email) == email.strip().lower())
        return int(self.session.execute(stmt).scalar_one())

    def _anotar(self, email: str, ip: str, *, ok: bool) -> None:
        self.session.add(
            LoginAttempt(email=email.strip().lower()[:320], ip=ip, ok=ok)
        )
        self.session.commit()

    def purgar(self, dias: int = 30) -> int:
        """Borra intentos viejos y sesiones vencidas. Para correr por cron."""
        limite = datetime.now(timezone.utc) - timedelta(days=dias)
        borrados = 0
        for intento in (
            self.session.execute(select(LoginAttempt).where(LoginAttempt.at < limite))
            .scalars()
            .all()
        ):
            self.session.delete(intento)
            borrados += 1

        ahora = datetime.now(timezone.utc)
        for sesion in (
            self.session.execute(
                select(UserSession).where(UserSession.expires_at < ahora)
            )
            .scalars()
            .all()
        ):
            self.session.delete(sesion)
            borrados += 1

        self.session.commit()
        return borrados
