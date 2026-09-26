"""Fixtures compartidas.

Los tests corren contra un Postgres real, en una base efímera `silu_test`. Usar
SQLite sería más rápido pero inútil aquí: el esquema depende de `uuidv7()`, de
valores por defecto del servidor y de un trigger, nada de lo cual existe en
SQLite. Un test que pasa contra un motor distinto al de producción no prueba
lo que uno cree.
"""

from collections.abc import Iterator

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.session import get_session
from app.main import create_app
from app.schemas.ticket import TicketCreate
from app.services.auth import AuthService
from app.services.ticket import TicketService

TEST_DB_NAME = "silu_test"


def _url_for(database: str) -> str:
    s = get_settings()
    return (
        f"postgresql+psycopg://{s.postgres_user}:{s.postgres_password}"
        f"@{s.postgres_host}:{s.postgres_port}/{database}"
    )


@pytest.fixture(scope="session")
def test_engine() -> Iterator[Engine]:
    """Crea la base de tests desde cero y le aplica las migraciones.

    Migrar en vez de usar `Base.metadata.create_all` es deliberado: así los
    tests ejercitan el mismo esquema que produce Alembic en producción,
    incluidos el trigger y los CHECK, que no viven en los modelos.
    """
    admin = create_engine(_url_for("postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as connection:
        connection.execute(text(f"DROP DATABASE IF EXISTS {TEST_DB_NAME} WITH (FORCE)"))
        connection.execute(text(f"CREATE DATABASE {TEST_DB_NAME}"))
    admin.dispose()

    url = _url_for(TEST_DB_NAME)
    config = Config("alembic.ini")
    config.set_main_option("script_location", "alembic")
    config.set_main_option("sqlalchemy.url", url)
    command.upgrade(config, "head")

    engine = create_engine(url)
    yield engine
    engine.dispose()


@pytest.fixture
def db_session(test_engine: Engine) -> Iterator[Session]:
    """Sesión aislada por test.

    Cada test corre dentro de una transacción externa que se revierte al final.
    `join_transaction_mode="create_savepoint"` permite que el código bajo prueba
    llame a `commit()` de verdad —los servicios lo hacen— sin que eso escape del
    aislamiento. Así los tests no se contaminan entre sí ni hay que limpiar
    tablas a mano.
    """
    connection = test_engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection, join_transaction_mode="create_savepoint")

    yield session

    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture
def service(db_session: Session) -> TicketService:
    return TicketService(db_session)


TEST_EMAIL = "pruebas@example.com"
TEST_PASSWORD = "contrasena-de-pruebas"
TEST_SECRET = "secreto-de-pruebas"


@pytest.fixture
def app_settings() -> Settings:
    """Configuración hermética: no hereda el .env del contenedor."""
    return Settings(
        postgres_user=get_settings().postgres_user,
        postgres_password=get_settings().postgres_password,
        postgres_db=get_settings().postgres_db,
        postgres_host=get_settings().postgres_host,
        app_password=TEST_PASSWORD,
        session_secret=TEST_SECRET,
    )


@pytest.fixture
def client(db_session: Session, app_settings: Settings) -> Iterator[TestClient]:
    """Cliente HTTP autenticado, con la sesión del test inyectada.

    Se construye sin `with`, para que no se dispare el lifespan: verificar la
    conexión al arrancar tiene sentido en producción, no aquí.
    """
    app = create_app()
    app.dependency_overrides[get_session] = lambda: db_session
    app.dependency_overrides[get_settings] = lambda: app_settings

    # base_url https: la cookie de sesión es `secure` y sobre http el cliente
    # no la enviaría, haciendo fallar todo por una razón que no es del código.
    test_client = TestClient(app, base_url="https://testserver")
    # La mayoría de los tests prueban comportamiento de negocio, no el login:
    # se crea la cuenta y se autentica una vez aquí. Los tests de
    # autenticación usan su propio cliente sin sesión.
    AuthService(db_session).crear_usuario(TEST_EMAIL, TEST_PASSWORD, rol="admin")
    test_client.post(
        "/api/v1/auth/login",
        json={"email": TEST_EMAIL, "password": TEST_PASSWORD},
    )

    yield test_client

    app.dependency_overrides.clear()


@pytest.fixture
def ticket_payload() -> dict[str, str]:
    return {
        "raw_text": "Gaste 1.000 pesos en un helado",
        "title": "Gasto: helado",
        "summary": "Compra de un helado por $1.000 en la calle.",
    }


@pytest.fixture
def existing_ticket(service: TicketService, ticket_payload: dict[str, str]):
    return service.create(TicketCreate(**ticket_payload))
