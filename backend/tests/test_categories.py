"""Tests de categorías (líneas de vida)."""

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.exceptions import (
    CategoryNameTakenError,
    CategoryNotFoundError,
    ProtectedCategoryError,
)
from app.schemas.category import CategoryCreate, CategoryUpdate
from app.schemas.ticket import TicketCreate
from app.services.category import CategoryService
from app.services.ticket import TicketService


@pytest.fixture
def categories(db_session: Session) -> CategoryService:
    return CategoryService(db_session)


class TestSemillaInicial:
    def test_existen_las_cuatro_definidas(self, categories: CategoryService) -> None:
        nombres = [c.name for c in categories.list()]

        assert nombres == ["Bandeja", "Gastos", "Conversar con Luna", "Metro"]

    def test_la_bandeja_es_la_default(self, categories: CategoryService) -> None:
        assert categories.get_default().name == "Bandeja"


class TestResolucionPorNombre:
    def test_encuentra_sin_distinguir_mayusculas(
        self, categories: CategoryService
    ) -> None:
        # El modelo puede devolver "gastos" donde la categoría es "Gastos".
        assert categories.resolve("gastos").name == "Gastos"
        assert categories.resolve("  METRO ").name == "Metro"

    def test_un_nombre_inventado_cae_en_la_bandeja(
        self, categories: CategoryService
    ) -> None:
        # Perder la captura por un nombre inventado sería el peor resultado.
        assert categories.resolve("Categoria Inexistente").name == "Bandeja"

    def test_sin_nombre_cae_en_la_bandeja(self, categories: CategoryService) -> None:
        assert categories.resolve(None).name == "Bandeja"


class TestCrear:
    def test_crea_y_queda_al_final(self, categories: CategoryService) -> None:
        nueva = categories.create(CategoryCreate(name="Guitarra"))

        assert nueva.name == "Guitarra"
        assert nueva.is_default is False
        assert [c.name for c in categories.list()][-1] == "Guitarra"

    def test_rechaza_nombres_repetidos(self, categories: CategoryService) -> None:
        with pytest.raises(CategoryNameTakenError):
            categories.create(CategoryCreate(name="Gastos"))

    def test_el_nombre_se_limpia(self, categories: CategoryService) -> None:
        assert categories.create(CategoryCreate(name="  Trabajo  ")).name == "Trabajo"


class TestEditar:
    def test_renombra(self, categories: CategoryService) -> None:
        metro = next(c for c in categories.list() if c.name == "Metro")

        renombrada = categories.update(metro.id, CategoryUpdate(name="Transporte"))

        assert renombrada.name == "Transporte"

    def test_renombrar_a_uno_existente_falla(
        self, categories: CategoryService
    ) -> None:
        metro = next(c for c in categories.list() if c.name == "Metro")

        with pytest.raises(CategoryNameTakenError):
            categories.update(metro.id, CategoryUpdate(name="Gastos"))

    def test_renombrarse_a_si_misma_funciona(
        self, categories: CategoryService
    ) -> None:
        metro = next(c for c in categories.list() if c.name == "Metro")

        assert categories.update(metro.id, CategoryUpdate(name="Metro")).name == "Metro"

    def test_inexistente_falla(self, categories: CategoryService) -> None:
        with pytest.raises(CategoryNotFoundError):
            categories.update(uuid.uuid4(), CategoryUpdate(name="x"))


class TestEliminar:
    def test_la_bandeja_esta_protegida(self, categories: CategoryService) -> None:
        # Es el destino de los tickets sin clasificar: sin ella el sistema no
        # tendría dónde poner una captura.
        with pytest.raises(ProtectedCategoryError):
            categories.delete(categories.get_default().id)

    def test_los_tickets_se_mueven_a_la_bandeja(
        self,
        categories: CategoryService,
        db_session: Session,
        ticket_payload: dict[str, str],
    ) -> None:
        # Reorganizar las líneas de vida no debe costar capturas.
        gastos = next(c for c in categories.list() if c.name == "Gastos")
        tickets = TicketService(db_session)
        ticket = tickets.create(
            TicketCreate(**ticket_payload, category_id=gastos.id)
        )

        movidos = categories.delete(gastos.id)

        assert movidos == 1
        assert tickets.get(ticket.id).category_name == "Bandeja"

    def test_desaparece_de_la_lista(self, categories: CategoryService) -> None:
        metro = next(c for c in categories.list() if c.name == "Metro")

        categories.delete(metro.id)

        assert "Metro" not in [c.name for c in categories.list()]


class TestConteos:
    def test_cuenta_solo_los_vivos(
        self,
        categories: CategoryService,
        db_session: Session,
        ticket_payload: dict[str, str],
    ) -> None:
        from app.schemas.ticket import TicketDispatch

        tickets = TicketService(db_session)
        tickets.create(TicketCreate(**ticket_payload))
        archivado = tickets.create(TicketCreate(**ticket_payload))
        tickets.dispatch(archivado.id, TicketDispatch(resolution="hecho"))

        conteos = {c.name: n for c, n in categories.list_with_counts()}

        assert conteos["Bandeja"] == 1


class TestApi:
    def test_lista_con_conteos(self, client: TestClient) -> None:
        response = client.get("/api/v1/categories")

        assert response.status_code == 200
        cuerpo = response.json()
        assert [c["name"] for c in cuerpo] == [
            "Bandeja",
            "Gastos",
            "Conversar con Luna",
            "Metro",
        ]
        assert cuerpo[0]["is_default"] is True

    def test_crear_devuelve_201(self, client: TestClient) -> None:
        response = client.post("/api/v1/categories", json={"name": "Guitarra"})

        assert response.status_code == 201
        assert response.json()["name"] == "Guitarra"

    def test_nombre_repetido_da_409(self, client: TestClient) -> None:
        response = client.post("/api/v1/categories", json={"name": "Gastos"})

        assert response.status_code == 409

    def test_borrar_la_bandeja_da_409(self, client: TestClient) -> None:
        bandeja = next(
            c for c in client.get("/api/v1/categories").json() if c["is_default"]
        )

        response = client.delete(f"/api/v1/categories/{bandeja['id']}")

        assert response.status_code == 409

    def test_campos_desconocidos_dan_422(self, client: TestClient) -> None:
        response = client.post(
            "/api/v1/categories", json={"nombre": "typo"}
        )

        assert response.status_code == 422

    def test_filtrar_tickets_por_categoria(
        self, client: TestClient, ticket_payload: dict[str, str]
    ) -> None:
        gastos = next(
            c for c in client.get("/api/v1/categories").json() if c["name"] == "Gastos"
        )
        client.post(
            "/api/v1/tickets", json={**ticket_payload, "category_id": gastos["id"]}
        )
        client.post("/api/v1/tickets", json=ticket_payload)

        response = client.get(
            "/api/v1/tickets", params={"category_id": gastos["id"]}
        )

        assert response.json()["total"] == 1
        assert response.json()["items"][0]["category_name"] == "Gastos"
