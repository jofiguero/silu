"""Tests de la capa HTTP: códigos de estado, validación y forma de las respuestas.

Las reglas del dominio ya se prueban en test_services. Aquí interesa lo que la
capa de API aporta por sí misma: que un error del dominio llegue como el código
correcto, que la validación rechace lo que debe, y que el contrato de salida no
cambie sin querer.
"""

import uuid

from fastapi.testclient import TestClient


class TestHealth:
    def test_health_responde_sin_tocar_la_base(self, client: TestClient) -> None:
        response = client.get("/api/v1/health")

        assert response.status_code == 200
        assert response.json()["status"] == "ok"

    def test_health_db_verifica_la_conexion(self, client: TestClient) -> None:
        response = client.get("/api/v1/health/db")

        assert response.status_code == 200
        assert response.json()["database"] == "ok"


class TestCrear:
    def test_devuelve_201_y_el_ticket_completo(
        self, client: TestClient, ticket_payload: dict[str, str]
    ) -> None:
        response = client.post("/api/v1/tickets", json=ticket_payload)

        assert response.status_code == 201
        body = response.json()
        assert body["title"] == ticket_payload["title"]
        assert body["status"] == "pendiente"
        assert body["resolution"] is None
        assert uuid.UUID(body["id"])

    def test_rechaza_campos_desconocidos(self, client: TestClient) -> None:
        # Sin extra="forbid" esto respondería 201 ignorando el campo mal escrito,
        # que es la forma más silenciosa de perder datos.
        response = client.post(
            "/api/v1/tickets",
            json={
                "raw_text": "x",
                "titulo": "typo",
                "summary": "y",
            },
        )

        assert response.status_code == 422

    def test_rechaza_titulo_vacio(
        self, client: TestClient, ticket_payload: dict[str, str]
    ) -> None:
        response = client.post(
            "/api/v1/tickets", json={**ticket_payload, "title": ""}
        )

        assert response.status_code == 422

    def test_rechaza_campos_faltantes(self, client: TestClient) -> None:
        response = client.post("/api/v1/tickets", json={"title": "solo titulo"})

        assert response.status_code == 422


class TestObtener:
    def test_devuelve_el_ticket(self, client: TestClient, existing_ticket) -> None:
        response = client.get(f"/api/v1/tickets/{existing_ticket.id}")

        assert response.status_code == 200
        assert response.json()["id"] == str(existing_ticket.id)

    def test_inexistente_da_404(self, client: TestClient) -> None:
        response = client.get(f"/api/v1/tickets/{uuid.uuid4()}")

        assert response.status_code == 404
        assert "detail" in response.json()

    def test_id_mal_formado_da_422(self, client: TestClient) -> None:
        response = client.get("/api/v1/tickets/no-es-un-uuid")

        assert response.status_code == 422


class TestListar:
    def test_devuelve_la_forma_de_pagina(
        self, client: TestClient, existing_ticket
    ) -> None:
        response = client.get("/api/v1/tickets")

        assert response.status_code == 200
        body = response.json()
        assert set(body) == {"items", "total", "limit", "offset"}
        assert body["total"] == 1

    def test_filtra_por_estado(self, client: TestClient, existing_ticket) -> None:
        response = client.get("/api/v1/tickets", params={"status": "archivado"})

        assert response.status_code == 200
        assert response.json()["total"] == 0

    def test_rechaza_estado_invalido(self, client: TestClient) -> None:
        response = client.get("/api/v1/tickets", params={"status": "inventado"})

        assert response.status_code == 422

    def test_rechaza_limite_fuera_de_rango(self, client: TestClient) -> None:
        response = client.get("/api/v1/tickets", params={"limit": 5000})

        assert response.status_code == 422


class TestEditar:
    def test_edicion_parcial(self, client: TestClient, existing_ticket) -> None:
        response = client.patch(
            f"/api/v1/tickets/{existing_ticket.id}",
            json={"title": "Titulo corregido"},
        )

        assert response.status_code == 200
        body = response.json()
        assert body["title"] == "Titulo corregido"
        assert body["summary"] == existing_ticket.summary

    def test_archivar_sin_resolucion_da_409(
        self, client: TestClient, existing_ticket
    ) -> None:
        # El error del dominio se traduce a 409: la petición es válida, pero
        # choca con el estado del recurso.
        response = client.patch(
            f"/api/v1/tickets/{existing_ticket.id}", json={"status": "archivado"}
        )

        assert response.status_code == 409
        assert "resolución" in response.json()["detail"]

    def test_campo_desconocido_da_422(
        self, client: TestClient, existing_ticket
    ) -> None:
        response = client.patch(
            f"/api/v1/tickets/{existing_ticket.id}", json={"titulo": "typo"}
        )

        assert response.status_code == 422

    def test_inexistente_da_404(self, client: TestClient) -> None:
        response = client.patch(
            f"/api/v1/tickets/{uuid.uuid4()}", json={"title": "x"}
        )

        assert response.status_code == 404


class TestDespachar:
    def test_cierra_el_ticket(self, client: TestClient, existing_ticket) -> None:
        response = client.post(
            f"/api/v1/tickets/{existing_ticket.id}/dispatch",
            json={"resolution": "Registrado como gasto de comida"},
        )

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "archivado"
        assert body["resolution"] == "Registrado como gasto de comida"

    def test_exige_resolucion(self, client: TestClient, existing_ticket) -> None:
        response = client.post(
            f"/api/v1/tickets/{existing_ticket.id}/dispatch", json={}
        )

        assert response.status_code == 422

    def test_rechaza_resolucion_vacia(
        self, client: TestClient, existing_ticket
    ) -> None:
        response = client.post(
            f"/api/v1/tickets/{existing_ticket.id}/dispatch",
            json={"resolution": ""},
        )

        assert response.status_code == 422


class TestEliminar:
    def test_devuelve_204_y_desaparece(
        self, client: TestClient, existing_ticket
    ) -> None:
        assert client.delete(f"/api/v1/tickets/{existing_ticket.id}").status_code == 204
        assert client.get(f"/api/v1/tickets/{existing_ticket.id}").status_code == 404

    def test_inexistente_da_404(self, client: TestClient) -> None:
        response = client.delete(f"/api/v1/tickets/{uuid.uuid4()}")

        assert response.status_code == 404
