"""Tests del dashboard semanal."""

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.exceptions import (
    ThreadNameTakenError,
    ThreadNotFoundError,
)
from app.schemas.thread import (
    TaskCreate,
    TaskUpdate,
    ThreadCreate,
    ThreadUpdate,
)
from app.services.thread import ThreadService


@pytest.fixture
def threads(db_session: Session) -> ThreadService:
    return ThreadService(db_session)


@pytest.fixture
def guitarra(threads: ThreadService):
    return next(t for t in threads.list() if t.name == "Guitarra")


class TestSemillaInicial:
    def test_existen_los_cuatro_frentes(self, threads: ThreadService) -> None:
        assert [t.name for t in threads.list()] == [
            "Guitarra",
            "ICAI",
            "Chilean2Sign",
            "SILU",
        ]

    def test_cada_uno_trae_su_color(self, threads: ThreadService) -> None:
        colores = {t.name: t.color for t in threads.list()}

        assert colores["Chilean2Sign"] == "salvia"
        assert colores["SILU"] == "mostaza"


class TestThreads:
    def test_crear(self, threads: ThreadService) -> None:
        nuevo = threads.create(ThreadCreate(name="Gimnasio", color="oliva"))

        assert nuevo.color == "oliva"
        assert [t.name for t in threads.list()][-1] == "Gimnasio"

    def test_nombre_repetido_falla(self, threads: ThreadService) -> None:
        with pytest.raises(ThreadNameTakenError):
            threads.create(ThreadCreate(name="ICAI"))

    def test_cambiar_color(self, threads: ThreadService, guitarra) -> None:
        assert threads.update(guitarra.id, ThreadUpdate(color="ciruela")).color == (
            "ciruela"
        )

    def test_guardar_tamano(self, threads: ThreadService, guitarra) -> None:
        # Reacomodar el tablero cada vez que se abre sería trabajo perdido.
        actualizado = threads.update(guitarra.id, ThreadUpdate(width=420, height=300))

        assert (actualizado.width, actualizado.height) == (420, 300)

    def test_reordenar(self, threads: ThreadService) -> None:
        originales = list(threads.list())
        invertido = [t.id for t in reversed(originales)]

        resultado = threads.reorder(invertido)

        assert [t.id for t in resultado] == invertido

    def test_inexistente_falla(self, threads: ThreadService) -> None:
        with pytest.raises(ThreadNotFoundError):
            threads.update(uuid.uuid4(), ThreadUpdate(color="arena"))

    def test_borrar_se_lleva_sus_tareas(
        self, threads: ThreadService, guitarra, db_session: Session
    ) -> None:
        # Al revés de los tickets: una macro tarea sin su frente no significa nada.
        from app.db.models import ThreadTask

        threads.add_task(guitarra.id, TaskCreate(text="Estudiar escalas"))
        threads.delete(guitarra.id)

        assert db_session.query(ThreadTask).count() == 0


class TestTareas:
    def test_agregar_conserva_el_orden(
        self, threads: ThreadService, guitarra
    ) -> None:
        primera = threads.add_task(guitarra.id, TaskCreate(text="Escalas"))
        segunda = threads.add_task(guitarra.id, TaskCreate(text="Acordes"))

        assert primera.position == 0
        assert segunda.position == 1

    def test_marcar_guarda_el_instante(
        self, threads: ThreadService, guitarra
    ) -> None:
        # Un booleano no permitiría responder "qué cerré esta semana".
        tarea = threads.add_task(guitarra.id, TaskCreate(text="Escalas"))

        marcada = threads.update_task(tarea.id, TaskUpdate(done=True))

        assert marcada.done is True
        assert marcada.done_at is not None

    def test_desmarcar_limpia_el_instante(
        self, threads: ThreadService, guitarra
    ) -> None:
        tarea = threads.add_task(guitarra.id, TaskCreate(text="Escalas"))
        threads.update_task(tarea.id, TaskUpdate(done=True))

        desmarcada = threads.update_task(tarea.id, TaskUpdate(done=False))

        assert desmarcada.done is False
        assert desmarcada.done_at is None

    def test_editar_el_texto_no_desmarca(
        self, threads: ThreadService, guitarra
    ) -> None:
        tarea = threads.add_task(guitarra.id, TaskCreate(text="Escalas"))
        threads.update_task(tarea.id, TaskUpdate(done=True))

        editada = threads.update_task(tarea.id, TaskUpdate(text="Escalas mayores"))

        assert editada.text_ == "Escalas mayores"
        assert editada.done is True


class TestLimpieza:
    def test_solo_saca_las_marcadas(self, threads: ThreadService, guitarra) -> None:
        hecha = threads.add_task(guitarra.id, TaskCreate(text="Escalas"))
        pendiente = threads.add_task(guitarra.id, TaskCreate(text="Acordes"))
        threads.update_task(hecha.id, TaskUpdate(done=True))

        limpiadas = threads.cleanup()

        assert limpiadas == 1
        assert threads.get_task(pendiente.id).cleared_at is None

    def test_no_borra_la_tarea(self, threads: ThreadService, guitarra) -> None:
        # Se archiva, no se elimina: queda el registro de lo que se cerró.
        tarea = threads.add_task(guitarra.id, TaskCreate(text="Escalas"))
        threads.update_task(tarea.id, TaskUpdate(done=True))

        threads.cleanup()

        conservada = threads.get_task(tarea.id)
        assert conservada.cleared_at is not None
        assert conservada.done_at is not None

    def test_limpiar_dos_veces_no_cuenta_lo_mismo(
        self, threads: ThreadService, guitarra
    ) -> None:
        tarea = threads.add_task(guitarra.id, TaskCreate(text="Escalas"))
        threads.update_task(tarea.id, TaskUpdate(done=True))
        threads.cleanup()

        assert threads.cleanup() == 0


class TestApi:
    def test_listar_no_incluye_lo_limpiado(self, client: TestClient) -> None:
        threads = client.get("/api/v1/threads").json()
        guitarra = next(t for t in threads if t["name"] == "Guitarra")

        tarea = client.post(
            f"/api/v1/threads/{guitarra['id']}/tasks", json={"text": "Escalas"}
        ).json()
        client.patch(f"/api/v1/threads/tasks/{tarea['id']}", json={"done": True})
        client.post("/api/v1/threads/cleanup")

        actualizado = next(
            t for t in client.get("/api/v1/threads").json() if t["name"] == "Guitarra"
        )
        assert actualizado["tasks"] == []

    def test_se_pueden_pedir_las_limpiadas(self, client: TestClient) -> None:
        guitarra = next(
            t for t in client.get("/api/v1/threads").json() if t["name"] == "Guitarra"
        )
        tarea = client.post(
            f"/api/v1/threads/{guitarra['id']}/tasks", json={"text": "Escalas"}
        ).json()
        client.patch(f"/api/v1/threads/tasks/{tarea['id']}", json={"done": True})
        client.post("/api/v1/threads/cleanup")

        respuesta = client.get(
            "/api/v1/threads", params={"include_cleared": "true"}
        ).json()
        actualizado = next(t for t in respuesta if t["name"] == "Guitarra")

        assert len(actualizado["tasks"]) == 1

    def test_la_paleta_esta_disponible(self, client: TestClient) -> None:
        colores = client.get("/api/v1/threads/colors").json()

        assert "terracota" in colores
        assert len(colores) >= 8

    def test_un_color_fuera_de_la_paleta_da_422(self, client: TestClient) -> None:
        # Sin esto el pizarrón terminaría con un fucsia fosforescente.
        respuesta = client.post(
            "/api/v1/threads", json={"name": "Nuevo", "color": "fucsia-neon"}
        )

        assert respuesta.status_code == 422

    def test_campos_desconocidos_dan_422(self, client: TestClient) -> None:
        respuesta = client.post("/api/v1/threads", json={"nombre": "typo"})

        assert respuesta.status_code == 422

    def test_sin_sesion_responde_401(self, db_session: Session) -> None:
        from app.core.config import Settings, get_settings
        from app.db.session import get_session
        from app.main import create_app

        settings = Settings(
            postgres_user="u",
            postgres_password="p",
            postgres_db="d",
            app_password="x",
            session_secret="y",
        )
        app = create_app()
        app.dependency_overrides[get_session] = lambda: db_session
        app.dependency_overrides[get_settings] = lambda: settings
        sin_sesion = TestClient(app, base_url="https://testserver")

        assert sin_sesion.get("/api/v1/threads").status_code == 401
        app.dependency_overrides.clear()


class TestEnCurso:
    """La marca de "estoy en esto ahora": ni importancia ni término, atención."""

    def test_se_activa_y_desactiva(self, threads: ThreadService, guitarra) -> None:
        tarea = threads.add_task(guitarra.id, TaskCreate(text="Escalas"))

        assert tarea.active is False
        assert threads.update_task(tarea.id, TaskUpdate(active=True)).active is True
        assert threads.update_task(tarea.id, TaskUpdate(active=False)).active is False

    def test_marcar_hecha_la_saca_de_en_curso(
        self, threads: ThreadService, guitarra
    ) -> None:
        # Sin esto el panel marcaría como "en curso" tareas ya tachadas, que es
        # justo el ruido que la marca busca evitar.
        tarea = threads.add_task(guitarra.id, TaskCreate(text="Escalas"))
        threads.update_task(tarea.id, TaskUpdate(active=True))

        terminada = threads.update_task(tarea.id, TaskUpdate(done=True))

        assert terminada.active is False

    def test_desmarcar_no_la_reactiva(
        self, threads: ThreadService, guitarra
    ) -> None:
        # Reabrir una tarea no implica estar trabajando en ella en ese momento.
        tarea = threads.add_task(guitarra.id, TaskCreate(text="Escalas"))
        threads.update_task(tarea.id, TaskUpdate(active=True))
        threads.update_task(tarea.id, TaskUpdate(done=True))

        reabierta = threads.update_task(tarea.id, TaskUpdate(done=False))

        assert reabierta.active is False

    def test_editar_el_texto_no_la_desactiva(
        self, threads: ThreadService, guitarra
    ) -> None:
        tarea = threads.add_task(guitarra.id, TaskCreate(text="Escalas"))
        threads.update_task(tarea.id, TaskUpdate(active=True))

        editada = threads.update_task(tarea.id, TaskUpdate(text="Escalas mayores"))

        assert editada.active is True

    def test_varias_pueden_estar_en_curso_a_la_vez(
        self, threads: ThreadService, guitarra
    ) -> None:
        # El caso de uso es justamente trabajar en varias cosas en paralelo.
        una = threads.add_task(guitarra.id, TaskCreate(text="Escalas"))
        otra = threads.add_task(guitarra.id, TaskCreate(text="Acordes"))

        threads.update_task(una.id, TaskUpdate(active=True))
        threads.update_task(otra.id, TaskUpdate(active=True))

        assert threads.get_task(una.id).active is True
        assert threads.get_task(otra.id).active is True

    def test_la_api_expone_la_marca(self, client: TestClient) -> None:
        guitarra = next(
            t for t in client.get("/api/v1/threads").json() if t["name"] == "Guitarra"
        )
        tarea = client.post(
            f"/api/v1/threads/{guitarra['id']}/tasks", json={"text": "Escalas"}
        ).json()

        respuesta = client.patch(
            f"/api/v1/threads/tasks/{tarea['id']}", json={"active": True}
        )

        assert respuesta.status_code == 200
        assert respuesta.json()["active"] is True
