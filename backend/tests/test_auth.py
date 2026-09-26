"""Tests de cuentas, sesiones y freno a la fuerza bruta."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.security import (
    SESSION_COOKIE,
    create_session_token,
    hash_password,
    hash_session_token,
    verify_password,
)
from app.db.session import get_session
from app.main import create_app
from app.services.auth import (
    FALLOS_POR_IP,
    AuthService,
    CredencialesInvalidas,
    DemasiadosIntentos,
    SinUsuarios,
)

EMAIL = "joaquin@example.com"
PASSWORD = "una-contrasena-larga"


@pytest.fixture
def auth(db_session: Session) -> AuthService:
    return AuthService(db_session)


@pytest.fixture
def usuario(auth: AuthService):
    return auth.crear_usuario(EMAIL, PASSWORD, rol="admin")


@pytest.fixture
def sin_sesion(db_session: Session) -> TestClient:
    """Cliente sin autenticar, para probar el login mismo."""
    app = create_app()
    app.dependency_overrides[get_session] = lambda: db_session
    return TestClient(app, base_url="https://testserver")


class TestContrasenas:
    def test_el_hash_no_contiene_la_contrasena(self) -> None:
        hashed = hash_password(PASSWORD)
        assert PASSWORD not in hashed
        assert hashed.startswith("$argon2id$")

    def test_dos_hashes_de_lo_mismo_son_distintos(self) -> None:
        """Cada uno lleva su propia sal; si no, se verían las repetidas."""
        assert hash_password(PASSWORD) != hash_password(PASSWORD)

    def test_verifica_la_correcta_y_rechaza_el_resto(self) -> None:
        hashed = hash_password(PASSWORD)
        assert verify_password(PASSWORD, hashed) is True
        assert verify_password("otra cosa", hashed) is False

    def test_un_hash_corrupto_no_revienta(self) -> None:
        assert verify_password(PASSWORD, "esto no es un hash") is False


class TestCuentas:
    def test_el_correo_se_guarda_normalizado(self, auth: AuthService) -> None:
        creado = auth.crear_usuario("  Joaquin@EXAMPLE.com ", PASSWORD)
        assert creado.email == "joaquin@example.com"

    def test_no_se_repite_el_correo_ni_cambiando_mayusculas(
        self, auth: AuthService, usuario
    ) -> None:
        # Que Joaquin@x.cl y joaquin@x.cl fueran cuentas distintas invita a
        # suplantar a alguien.
        with pytest.raises(ValueError):
            auth.crear_usuario(EMAIL.upper(), PASSWORD)

    def test_el_rol_por_defecto_es_usuario(self, auth: AuthService) -> None:
        assert auth.crear_usuario("otro@example.com", PASSWORD).role == "usuario"

    def test_un_rol_inventado_se_rechaza(self, auth: AuthService) -> None:
        with pytest.raises(ValueError):
            auth.crear_usuario("otro@example.com", PASSWORD, rol="superjefe")


class TestLogin:
    def test_entra_con_las_credenciales_correctas(
        self, auth: AuthService, usuario
    ) -> None:
        entrado, token = auth.login(EMAIL, PASSWORD, ip="1.2.3.4")
        assert entrado.id == usuario.id
        assert token

    def test_la_contrasena_mala_no_entra(self, auth: AuthService, usuario) -> None:
        with pytest.raises(CredencialesInvalidas):
            auth.login(EMAIL, "otra cosa", ip="1.2.3.4")

    def test_un_correo_inexistente_da_el_mismo_error(
        self, auth: AuthService, usuario
    ) -> None:
        """Distinguirlo le diría a quien prueba qué cuentas existen."""
        with pytest.raises(CredencialesInvalidas):
            auth.login("nadie@example.com", PASSWORD, ip="1.2.3.4")

    def test_una_cuenta_desactivada_no_entra(
        self, auth: AuthService, usuario, db_session: Session
    ) -> None:
        usuario.is_active = False
        db_session.commit()

        with pytest.raises(CredencialesInvalidas):
            auth.login(EMAIL, PASSWORD, ip="1.2.3.4")

    def test_sin_ninguna_cuenta_lo_dice(
        self, auth: AuthService, db_session: Session
    ) -> None:
        # db_session nace con una cuenta; aquí se prueba el arranque en frío.
        for u in auth.listar():
            db_session.delete(u)
        db_session.commit()

        with pytest.raises(SinUsuarios):
            auth.login(EMAIL, PASSWORD, ip="1.2.3.4")


class TestSesiones:
    def test_la_tabla_guarda_el_hash_y_no_el_token(
        self, auth: AuthService, usuario
    ) -> None:
        """Leer la tabla no puede entregar sesiones utilizables."""
        _, token = auth.login(EMAIL, PASSWORD, ip="1.2.3.4")

        guardada = usuario.sessions[0]
        assert guardada.token_hash != token
        assert guardada.token_hash == hash_session_token(token)

    def test_el_token_identifica_a_su_duenio(self, auth: AuthService, usuario) -> None:
        _, token = auth.login(EMAIL, PASSWORD, ip="1.2.3.4")
        assert auth.usuario_de_sesion(token).id == usuario.id

    def test_un_token_inventado_no_sirve(self, auth: AuthService, usuario) -> None:
        assert auth.usuario_de_sesion(create_session_token()) is None

    def test_cerrar_sesion_la_invalida(self, auth: AuthService, usuario) -> None:
        _, token = auth.login(EMAIL, PASSWORD, ip="1.2.3.4")
        auth.cerrar_sesion(token)
        assert auth.usuario_de_sesion(token) is None

    def test_cambiar_la_contrasena_cierra_las_sesiones(
        self, auth: AuthService, usuario
    ) -> None:
        """Si alguien más la tenía, cambiarla lo tiene que dejar afuera."""
        _, token = auth.login(EMAIL, PASSWORD, ip="1.2.3.4")
        assert auth.usuario_de_sesion(token) is not None

        auth.cambiar_password(usuario, "otra-contrasena-larga")
        assert auth.usuario_de_sesion(token) is None

    def test_desactivar_la_cuenta_invalida_su_sesion(
        self, auth: AuthService, usuario, db_session: Session
    ) -> None:
        _, token = auth.login(EMAIL, PASSWORD, ip="1.2.3.4")
        usuario.is_active = False
        db_session.commit()

        assert auth.usuario_de_sesion(token) is None


class TestFuerzaBruta:
    def test_se_corta_despues_de_varios_fallos_de_la_misma_ip(
        self, auth: AuthService, usuario
    ) -> None:
        for _ in range(FALLOS_POR_IP):
            with pytest.raises(CredencialesInvalidas):
                auth.login(EMAIL, "mala", ip="9.9.9.9")

        # Y ahora ni siquiera con la buena: el límite va antes de mirar nada.
        with pytest.raises(DemasiadosIntentos):
            auth.login(EMAIL, PASSWORD, ip="9.9.9.9")

    def test_el_limite_es_por_ip_y_no_global(
        self, auth: AuthService, usuario
    ) -> None:
        """Si fuera global, un bot dejaría afuera a todo el mundo."""
        for _ in range(FALLOS_POR_IP):
            with pytest.raises(CredencialesInvalidas):
                auth.login(EMAIL, "mala", ip="9.9.9.9")

        entrado, _ = auth.login(EMAIL, PASSWORD, ip="1.2.3.4")
        assert entrado.id == usuario.id

    def test_los_intentos_no_guardan_la_contrasena(
        self, auth: AuthService, usuario, db_session: Session
    ) -> None:
        from app.db.models import LoginAttempt

        with pytest.raises(CredencialesInvalidas):
            auth.login(EMAIL, "la-contrasena-secreta", ip="1.2.3.4")

        anotados = db_session.query(LoginAttempt).all()
        assert anotados
        for intento in anotados:
            assert "la-contrasena-secreta" not in str(intento.__dict__)


class TestApi:
    def test_login_y_me(self, sin_sesion: TestClient, usuario) -> None:
        respuesta = sin_sesion.post(
            "/api/v1/auth/login", json={"email": EMAIL, "password": PASSWORD}
        )
        assert respuesta.status_code == 200
        assert respuesta.json()["email"] == EMAIL
        assert respuesta.json()["role"] == "admin"

        yo = sin_sesion.get("/api/v1/auth/me")
        assert yo.status_code == 200
        assert yo.json()["authenticated"] is True

    def test_la_cookie_es_httponly_y_secure(
        self, sin_sesion: TestClient, usuario
    ) -> None:
        respuesta = sin_sesion.post(
            "/api/v1/auth/login", json={"email": EMAIL, "password": PASSWORD}
        )
        cookie = respuesta.headers["set-cookie"]
        assert "HttpOnly" in cookie
        assert "Secure" in cookie
        assert "SameSite=lax" in cookie

    def test_la_contrasena_mala_responde_401_generico(
        self, sin_sesion: TestClient, usuario
    ) -> None:
        respuesta = sin_sesion.post(
            "/api/v1/auth/login", json={"email": EMAIL, "password": "mala"}
        )
        assert respuesta.status_code == 401
        assert respuesta.json()["detail"] == "Credenciales incorrectas"

    def test_un_correo_inexistente_responde_igual(
        self, sin_sesion: TestClient, usuario
    ) -> None:
        respuesta = sin_sesion.post(
            "/api/v1/auth/login",
            json={"email": "nadie@example.com", "password": PASSWORD},
        )
        assert respuesta.status_code == 401
        assert respuesta.json()["detail"] == "Credenciales incorrectas"

    def test_demasiados_intentos_responden_429(
        self, sin_sesion: TestClient, usuario
    ) -> None:
        for _ in range(FALLOS_POR_IP):
            sin_sesion.post(
                "/api/v1/auth/login", json={"email": EMAIL, "password": "mala"}
            )

        respuesta = sin_sesion.post(
            "/api/v1/auth/login", json={"email": EMAIL, "password": PASSWORD}
        )
        assert respuesta.status_code == 429
        assert "Retry-After" in respuesta.headers

    def test_sin_sesion_la_api_responde_401(self, sin_sesion: TestClient) -> None:
        assert sin_sesion.get("/api/v1/tickets").status_code == 401

    def test_logout_invalida_la_sesion_en_el_servidor(
        self, sin_sesion: TestClient, usuario
    ) -> None:
        """Borrar la cookie no basta: quien la tuviera podría seguir usándola."""
        sin_sesion.post(
            "/api/v1/auth/login", json={"email": EMAIL, "password": PASSWORD}
        )
        token = sin_sesion.cookies[SESSION_COOKIE]

        sin_sesion.post("/api/v1/auth/logout")

        sin_sesion.cookies.set(SESSION_COOKIE, token)
        assert sin_sesion.get("/api/v1/auth/me").status_code == 401

    def test_sin_cuentas_creadas_lo_dice(self, db_session: Session) -> None:
        for u in AuthService(db_session).listar():
            db_session.delete(u)
        db_session.commit()

        app = create_app()
        app.dependency_overrides[get_session] = lambda: db_session
        cliente = TestClient(app, base_url="https://testserver")

        respuesta = cliente.post(
            "/api/v1/auth/login", json={"email": EMAIL, "password": PASSWORD}
        )
        assert respuesta.status_code == 503
        assert "crear_usuario" in respuesta.json()["detail"]
