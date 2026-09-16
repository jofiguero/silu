"""Tests de autenticación.

Lo que importa aquí no es que el login funcione, sino que **nada quede abierto**:
la API guarda capturas personales y vive en internet.
"""

import time

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.security import (
    SESSION_COOKIE,
    create_session_token,
    verify_session_token,
)
from app.db.session import get_session
from app.main import create_app

PASSWORD = "una-contrasena-de-pruebas"
SECRET = "un-secreto-para-firmar"


@pytest.fixture
def auth_settings() -> Settings:
    return Settings(
        postgres_user="u",
        postgres_password="p",
        postgres_db="d",
        app_password=PASSWORD,
        session_secret=SECRET,
    )


@pytest.fixture
def client(db_session: Session, auth_settings: Settings):
    app = create_app()
    app.dependency_overrides[get_session] = lambda: db_session
    app.dependency_overrides[get_settings] = lambda: auth_settings
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def logged_in(client: TestClient) -> TestClient:
    response = client.post("/api/v1/auth/login", json={"password": PASSWORD})
    assert response.status_code == 200
    return client


class TestTokenDeSesion:
    def test_un_token_recien_creado_es_valido(self) -> None:
        token = create_session_token(SECRET, ttl_seconds=60)

        assert verify_session_token(token, SECRET) is True

    def test_un_token_firmado_con_otro_secreto_no_sirve(self) -> None:
        token = create_session_token(SECRET, ttl_seconds=60)

        assert verify_session_token(token, "otro-secreto") is False

    def test_un_token_alterado_no_sirve(self) -> None:
        # El objetivo del HMAC: cambiar el contenido invalida la firma.
        token = create_session_token(SECRET, ttl_seconds=60)
        body, signature = token.split(".", 1)
        alterado = f"{body}x.{signature}"

        assert verify_session_token(alterado, SECRET) is False

    def test_un_token_vencido_no_sirve(self) -> None:
        token = create_session_token(SECRET, ttl_seconds=-1)
        time.sleep(0.01)

        assert verify_session_token(token, SECRET) is False

    @pytest.mark.parametrize("basura", ["", "sin-punto", "a.b.c", "....", "x."])
    def test_basura_no_revienta(self, basura: str) -> None:
        assert verify_session_token(basura, SECRET) is False


class TestLogin:
    def test_con_la_contrasena_correcta_entrega_cookie(
        self, client: TestClient
    ) -> None:
        response = client.post("/api/v1/auth/login", json={"password": PASSWORD})

        assert response.status_code == 200
        assert response.json() == {"authenticated": True}
        assert SESSION_COOKIE in response.cookies

    def test_la_cookie_no_es_legible_desde_javascript(
        self, client: TestClient
    ) -> None:
        # httponly es lo que impide que un XSS se lleve la sesión.
        response = client.post("/api/v1/auth/login", json={"password": PASSWORD})

        cookie_header = response.headers["set-cookie"].lower()
        assert "httponly" in cookie_header
        assert "secure" in cookie_header

    def test_con_la_contrasena_incorrecta_da_401(self, client: TestClient) -> None:
        response = client.post("/api/v1/auth/login", json={"password": "equivocada"})

        assert response.status_code == 401

    def test_logout_borra_la_cookie(self, logged_in: TestClient) -> None:
        logged_in.post("/api/v1/auth/logout")

        assert logged_in.get("/api/v1/auth/me").status_code == 401


class TestProteccionDeLaApi:
    """Ningún endpoint de datos debe responder sin sesión."""

    @pytest.mark.parametrize(
        ("method", "path"),
        [
            ("get", "/api/v1/tickets"),
            ("post", "/api/v1/tickets"),
            ("get", "/api/v1/tickets/00000000-0000-0000-0000-000000000000"),
            ("patch", "/api/v1/tickets/00000000-0000-0000-0000-000000000000"),
            ("delete", "/api/v1/tickets/00000000-0000-0000-0000-000000000000"),
            ("post", "/api/v1/tickets/00000000-0000-0000-0000-000000000000/dispatch"),
            ("post", "/api/v1/agent/chat"),
            ("get", "/api/v1/auth/me"),
        ],
    )
    def test_sin_sesion_responde_401(
        self, client: TestClient, method: str, path: str
    ) -> None:
        response = getattr(client, method)(path, json={})

        assert response.status_code == 401

    def test_con_sesion_la_bandeja_responde(self, logged_in: TestClient) -> None:
        response = logged_in.get("/api/v1/tickets")

        assert response.status_code == 200

    def test_una_cookie_inventada_no_sirve(self, client: TestClient) -> None:
        client.cookies.set(SESSION_COOKIE, "token.inventado")

        assert client.get("/api/v1/tickets").status_code == 401

    def test_la_salud_sigue_siendo_publica(self, client: TestClient) -> None:
        # Se deja abierta a propósito, para monitoreo externo.
        assert client.get("/api/v1/health").status_code == 200


class TestSinConfigurar:
    """Si falta la credencial, la API se cierra en vez de quedar abierta."""

    @pytest.fixture
    def client_sin_auth(self, db_session: Session):
        sin_auth = Settings(
            postgres_user="u",
            postgres_password="p",
            postgres_db="d",
            app_password=None,
            session_secret=None,
        )
        app = create_app()
        app.dependency_overrides[get_session] = lambda: db_session
        app.dependency_overrides[get_settings] = lambda: sin_auth
        yield TestClient(app)
        app.dependency_overrides.clear()

    def test_los_tickets_no_quedan_expuestos(self, client_sin_auth: TestClient) -> None:
        response = client_sin_auth.get("/api/v1/tickets")

        assert response.status_code == 503
        assert response.status_code != 200

    def test_el_login_avisa_que_no_hay_nada_configurado(
        self, client_sin_auth: TestClient
    ) -> None:
        response = client_sin_auth.post("/api/v1/auth/login", json={"password": "x"})

        assert response.status_code == 503
