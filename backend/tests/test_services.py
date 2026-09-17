"""Tests de la capa de servicio: las reglas del dominio, sin HTTP."""

import uuid

import pytest

from app.core.exceptions import (
    InvalidTicketTransitionError,
    TicketNotFoundError,
)
from app.schemas.ticket import (
    TicketCreate,
    TicketDispatch,
    TicketStatus,
    TicketUpdate,
)
from app.services.ticket import TicketService


class TestCreate:
    def test_asigna_defaults_del_servidor(
        self, service: TicketService, ticket_payload: dict[str, str]
    ) -> None:
        ticket = service.create(TicketCreate(**ticket_payload))

        # id y created_at los pone Postgres, no la aplicación.
        assert ticket.id is not None
        assert ticket.created_at is not None
        assert ticket.status == TicketStatus.PENDIENTE
        assert ticket.resolution is None

    def test_id_es_uuidv7(
        self, service: TicketService, ticket_payload: dict[str, str]
    ) -> None:
        ticket = service.create(TicketCreate(**ticket_payload))
        assert ticket.id.version == 7

    def test_ids_quedan_ordenados_por_tiempo(
        self, service: TicketService, ticket_payload: dict[str, str]
    ) -> None:
        # La ventaja de uuidv7 sobre un uuid aleatorio: ordenar por id equivale
        # a ordenar por fecha de creación.
        primero = service.create(TicketCreate(**ticket_payload))
        segundo = service.create(TicketCreate(**ticket_payload))

        assert primero.id.hex < segundo.id.hex


class TestGet:
    def test_devuelve_el_ticket(self, service: TicketService, existing_ticket) -> None:
        assert service.get(existing_ticket.id).id == existing_ticket.id

    def test_falla_si_no_existe(self, service: TicketService) -> None:
        with pytest.raises(TicketNotFoundError):
            service.get(uuid.uuid4())


class TestUpdate:
    def test_edicion_parcial_no_borra_los_otros_campos(
        self, service: TicketService, existing_ticket
    ) -> None:
        # La razón de usar exclude_unset: sin eso, editar solo el título
        # pondría en null todo lo demás.
        summary_original = existing_ticket.summary

        actualizado = service.update(
            existing_ticket.id, TicketUpdate(title="Otro titulo")
        )

        assert actualizado.title == "Otro titulo"
        assert actualizado.summary == summary_original
        assert actualizado.raw_text == existing_ticket.raw_text

    def test_el_trigger_avanza_updated_at(
        self, service: TicketService, existing_ticket
    ) -> None:
        creado_en = existing_ticket.updated_at

        actualizado = service.update(
            existing_ticket.id, TicketUpdate(title="Titulo nuevo")
        )

        assert actualizado.updated_at > creado_en

    def test_falla_si_no_existe(self, service: TicketService) -> None:
        with pytest.raises(TicketNotFoundError):
            service.update(uuid.uuid4(), TicketUpdate(title="x"))


class TestReglaDeArchivado:
    # Archivar sin decir qué se hizo pierde justo la información que hace útil
    # releer la bandeja meses después.

    def test_archivar_sin_resolucion_falla(
        self, service: TicketService, existing_ticket
    ) -> None:
        with pytest.raises(InvalidTicketTransitionError):
            service.update(
                existing_ticket.id, TicketUpdate(status=TicketStatus.ARCHIVADO)
            )

    def test_archivar_con_resolucion_en_la_misma_llamada_funciona(
        self, service: TicketService, existing_ticket
    ) -> None:
        actualizado = service.update(
            existing_ticket.id,
            TicketUpdate(
                status=TicketStatus.ARCHIVADO,
                resolution="Registrado como gasto de comida",
            ),
        )

        assert actualizado.status == TicketStatus.ARCHIVADO

    def test_archivar_con_resolucion_previa_funciona(
        self, service: TicketService, existing_ticket
    ) -> None:
        service.update(existing_ticket.id, TicketUpdate(resolution="Ya anotado"))

        actualizado = service.update(
            existing_ticket.id, TicketUpdate(status=TicketStatus.ARCHIVADO)
        )

        assert actualizado.status == TicketStatus.ARCHIVADO

    def test_resolucion_en_blanco_no_cuenta(
        self, service: TicketService, existing_ticket
    ) -> None:
        with pytest.raises(InvalidTicketTransitionError):
            service.update(
                existing_ticket.id,
                TicketUpdate(status=TicketStatus.ARCHIVADO, resolution="   "),
            )

    def test_pasar_a_en_curso_no_exige_resolucion(
        self, service: TicketService, existing_ticket
    ) -> None:
        actualizado = service.update(
            existing_ticket.id, TicketUpdate(status=TicketStatus.EN_CURSO)
        )

        assert actualizado.status == TicketStatus.EN_CURSO


class TestDispatch:
    def test_cierra_el_ticket_con_constancia(
        self, service: TicketService, existing_ticket
    ) -> None:
        despachado = service.dispatch(
            existing_ticket.id,
            TicketDispatch(resolution="Registrado como gasto de comida"),
        )

        assert despachado.status == TicketStatus.ARCHIVADO
        assert despachado.resolution == "Registrado como gasto de comida"

    def test_permite_dejarlo_en_curso(
        self, service: TicketService, existing_ticket
    ) -> None:
        despachado = service.dispatch(
            existing_ticket.id,
            TicketDispatch(
                resolution="Enviado a Notion, falta completar",
                status=TicketStatus.EN_CURSO,
            ),
        )

        assert despachado.status == TicketStatus.EN_CURSO


class TestList:
    def test_filtra_por_estado(
        self, service: TicketService, ticket_payload: dict[str, str]
    ) -> None:
        pendiente = service.create(TicketCreate(**ticket_payload))
        otro = service.create(TicketCreate(**ticket_payload))
        service.dispatch(otro.id, TicketDispatch(resolution="hecho"))

        items, total = service.list(status=TicketStatus.PENDIENTE)

        assert total == 1
        assert [t.id for t in items] == [pendiente.id]

    def test_busca_en_titulo_y_descripcion(
        self, service: TicketService, ticket_payload: dict[str, str]
    ) -> None:
        service.create(TicketCreate(**ticket_payload))
        service.create(
            TicketCreate(
                raw_text="Trabajar en PowerQuery",
                title="PowerQuery de tia Loro",
                summary="Retomar el trabajo pendiente de PowerQuery.",
            )
        )

        _, total = service.list(search="powerquery")

        assert total == 1

    def test_devuelve_lo_mas_antiguo_primero(
        self, service: TicketService, ticket_payload: dict[str, str]
    ) -> None:
        # Al revés de un feed: lo viejo sin resolver es lo que hay que mirar.
        primero = service.create(TicketCreate(**ticket_payload))
        segundo = service.create(TicketCreate(**ticket_payload))

        items, _ = service.list()

        assert [t.id for t in items] == [primero.id, segundo.id]

    def test_los_urgentes_van_arriba_sin_importar_la_fecha(
        self, service: TicketService, ticket_payload: dict[str, str]
    ) -> None:
        antiguo = service.create(TicketCreate(**ticket_payload))
        urgente = service.create(TicketCreate(**ticket_payload, urgent=True))

        items, _ = service.list()

        assert [t.id for t in items] == [urgente.id, antiguo.id]

    def test_los_archivados_no_aparecen_por_defecto(
        self, service: TicketService, ticket_payload: dict[str, str]
    ) -> None:
        vivo = service.create(TicketCreate(**ticket_payload))
        archivado = service.create(TicketCreate(**ticket_payload))
        service.dispatch(archivado.id, TicketDispatch(resolution="hecho"))

        items, total = service.list()

        assert total == 1
        assert [t.id for t in items] == [vivo.id]

    def test_se_pueden_pedir_los_archivados(
        self, service: TicketService, ticket_payload: dict[str, str]
    ) -> None:
        service.create(TicketCreate(**ticket_payload))
        archivado = service.create(TicketCreate(**ticket_payload))
        service.dispatch(archivado.id, TicketDispatch(resolution="hecho"))

        _, total = service.list(include_archived=True)

        assert total == 2

    def test_pagina_sin_alterar_el_total(
        self, service: TicketService, ticket_payload: dict[str, str]
    ) -> None:
        for _ in range(3):
            service.create(TicketCreate(**ticket_payload))

        items, total = service.list(limit=2, offset=0)

        assert len(items) == 2
        assert total == 3


class TestDelete:
    def test_elimina(self, service: TicketService, existing_ticket) -> None:
        service.delete(existing_ticket.id)

        with pytest.raises(TicketNotFoundError):
            service.get(existing_ticket.id)

    def test_falla_si_no_existe(self, service: TicketService) -> None:
        with pytest.raises(TicketNotFoundError):
            service.delete(uuid.uuid4())
