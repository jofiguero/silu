"""Tests del dashboard semanal."""

import uuid
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.calendario import lunes_de, semana_actual
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
from app.db.models import ThreadTask
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


class TestOrdenDeTareas:
    def test_reordenar_aplica_el_orden_completo(
        self, threads: ThreadService, guitarra
    ) -> None:
        a = threads.add_task(guitarra.id, TaskCreate(text="Escalas"))
        b = threads.add_task(guitarra.id, TaskCreate(text="Acordes"))
        c = threads.add_task(guitarra.id, TaskCreate(text="Ritmo"))

        resultado = threads.reorder_tasks(guitarra.id, [c.id, a.id, b.id])

        assert [t.text_ for t in resultado] == ["Ritmo", "Escalas", "Acordes"]

    def test_el_orden_persiste(self, threads: ThreadService, guitarra) -> None:
        a = threads.add_task(guitarra.id, TaskCreate(text="Escalas"))
        b = threads.add_task(guitarra.id, TaskCreate(text="Acordes"))
        threads.reorder_tasks(guitarra.id, [b.id, a.id])

        recargado = next(t for t in threads.list() if t.id == guitarra.id)

        assert [t.text_ for t in recargado.tasks] == ["Acordes", "Escalas"]

    def test_reordenar_no_toca_otros_papeles(
        self, threads: ThreadService, guitarra
    ) -> None:
        icai = next(t for t in threads.list() if t.name == "ICAI")
        ajena = threads.add_task(icai.id, TaskCreate(text="Informe"))
        propia = threads.add_task(guitarra.id, TaskCreate(text="Escalas"))

        threads.reorder_tasks(guitarra.id, [propia.id, ajena.id])

        # El id de otro papel se ignora en vez de robarle la tarea.
        assert threads.get_task(ajena.id).thread_id == icai.id

    def test_la_api_reordena(self, client: TestClient) -> None:
        guitarra = next(
            t for t in client.get("/api/v1/threads").json() if t["name"] == "Guitarra"
        )
        base = f"/api/v1/threads/{guitarra['id']}/tasks"
        a = client.post(base, json={"text": "Escalas"}).json()
        b = client.post(base, json={"text": "Acordes"}).json()

        respuesta = client.post(f"{base}/reorder", json={"ids": [b["id"], a["id"]]})

        assert respuesta.status_code == 200
        assert [t["text"] for t in respuesta.json()] == ["Acordes", "Escalas"]


class TestDescripcion:
    def test_se_puede_crear_con_descripcion(
        self, threads: ThreadService, guitarra
    ) -> None:
        tarea = threads.add_task(
            guitarra.id,
            TaskCreate(text="Escalas", description="Mayores y menores, 80 bpm."),
        )

        assert tarea.description == "Mayores y menores, 80 bpm."

    def test_sin_descripcion_queda_en_null(
        self, threads: ThreadService, guitarra
    ) -> None:
        assert threads.add_task(guitarra.id, TaskCreate(text="Escalas")).description is None

    def test_una_descripcion_en_blanco_queda_en_null(
        self, threads: ThreadService, guitarra
    ) -> None:
        tarea = threads.add_task(
            guitarra.id, TaskCreate(text="Escalas", description="   ")
        )

        assert tarea.description is None

    def test_se_puede_agregar_despues(
        self, threads: ThreadService, guitarra
    ) -> None:
        tarea = threads.add_task(guitarra.id, TaskCreate(text="Escalas"))

        actualizada = threads.update_task(
            tarea.id, TaskUpdate(description="Con metronomo.")
        )

        assert actualizada.description == "Con metronomo."

    def test_mandar_null_la_borra(self, threads: ThreadService, guitarra) -> None:
        # Se comprueba la presencia de la clave y no su valor: sin eso, borrar
        # una descripcion seria imposible.
        tarea = threads.add_task(
            guitarra.id, TaskCreate(text="Escalas", description="Algo")
        )

        limpia = threads.update_task(tarea.id, TaskUpdate(description=None))

        assert limpia.description is None

    def test_editar_el_texto_no_borra_la_descripcion(
        self, threads: ThreadService, guitarra
    ) -> None:
        tarea = threads.add_task(
            guitarra.id, TaskCreate(text="Escalas", description="Con metronomo.")
        )

        editada = threads.update_task(tarea.id, TaskUpdate(text="Escalas mayores"))

        assert editada.description == "Con metronomo."

    def test_la_api_la_expone(self, client: TestClient) -> None:
        guitarra = next(
            t for t in client.get("/api/v1/threads").json() if t["name"] == "Guitarra"
        )

        respuesta = client.post(
            f"/api/v1/threads/{guitarra['id']}/tasks",
            json={"text": "Escalas", "description": "Con metronomo."},
        )

        assert respuesta.status_code == 201
        assert respuesta.json()["description"] == "Con metronomo."


class TestSemanaYDia:
    """Las dos coordenadas de una tarea.

    Lo que se prueba una y otra vez aquí es que es UNA fila: no hay copias que
    sincronizar entre el día, la semana y otras tareas.
    """

    def test_nace_en_la_semana_en_curso(
        self, threads: ThreadService, guitarra
    ) -> None:
        tarea = threads.add_task(guitarra.id, TaskCreate(text="Escalas"))
        assert tarea.week == semana_actual()
        assert tarea.day is None

    def test_backlog_nace_sin_fecha(self, threads: ThreadService, guitarra) -> None:
        tarea = threads.add_task(
            guitarra.id, TaskCreate(text="Aprender jazz", backlog=True)
        )
        assert tarea.week is None
        assert tarea.day is None

    def test_crear_con_dia_deduce_la_semana(
        self, threads: ThreadService, guitarra
    ) -> None:
        jueves = date(2026, 9, 24)
        tarea = threads.add_task(guitarra.id, TaskCreate(text="Clase", day=jueves))
        assert tarea.day == jueves
        assert tarea.week == date(2026, 9, 21)

    def test_crear_el_domingo_para_el_lunes_no_parte_la_semana(
        self, threads: ThreadService, guitarra
    ) -> None:
        """La semana sale del día que se pidió, no del día de hoy."""
        lunes_siguiente = date(2026, 9, 28)
        tarea = threads.add_task(
            guitarra.id, TaskCreate(text="Ensayo", day=lunes_siguiente)
        )
        assert tarea.week == lunes_siguiente

    def test_bajar_a_un_dia_la_mete_en_su_semana(
        self, threads: ThreadService, guitarra
    ) -> None:
        tarea = threads.add_task(guitarra.id, TaskCreate(text="Escalas", backlog=True))
        movida = threads.update_task(tarea.id, TaskUpdate(day=date(2026, 9, 23)))
        assert movida.day == date(2026, 9, 23)
        assert movida.week == date(2026, 9, 21)

    def test_soltar_el_dia_la_deja_en_la_semana(
        self, threads: ThreadService, guitarra
    ) -> None:
        tarea = threads.add_task(guitarra.id, TaskCreate(text="Escalas"))
        threads.update_task(tarea.id, TaskUpdate(day=date(2026, 9, 23)))
        vuelta = threads.update_task(tarea.id, TaskUpdate(day=None))
        assert vuelta.day is None
        assert vuelta.week == date(2026, 9, 21)

    def test_sin_semana_se_va_a_otras_tareas_y_suelta_el_dia(
        self, threads: ThreadService, guitarra
    ) -> None:
        tarea = threads.add_task(guitarra.id, TaskCreate(text="Escalas"))
        threads.update_task(tarea.id, TaskUpdate(day=date(2026, 9, 23)))
        guardada = threads.update_task(tarea.id, TaskUpdate(week=None))
        assert guardada.week is None
        assert guardada.day is None

    def test_cambiar_de_semana_suelta_el_dia(
        self, threads: ThreadService, guitarra
    ) -> None:
        """Un miércoles de otra semana no significa nada."""
        tarea = threads.add_task(guitarra.id, TaskCreate(text="Escalas"))
        threads.update_task(tarea.id, TaskUpdate(day=date(2026, 9, 23)))
        movida = threads.update_task(tarea.id, TaskUpdate(week=date(2026, 9, 28)))
        assert movida.week == date(2026, 9, 28)
        assert movida.day is None

    def test_la_semana_se_normaliza_al_lunes(
        self, threads: ThreadService, guitarra
    ) -> None:
        """Mandar un jueves como semana guarda su lunes, no el jueves."""
        tarea = threads.add_task(guitarra.id, TaskCreate(text="Escalas"))
        movida = threads.update_task(tarea.id, TaskUpdate(week=date(2026, 9, 24)))
        assert movida.week == date(2026, 9, 21)

    def test_cerrarla_en_el_dia_la_cierra_en_la_semana(
        self, threads: ThreadService, guitarra
    ) -> None:
        """No por una regla de sincronización: es la misma fila."""
        tarea = threads.add_task(guitarra.id, TaskCreate(text="Escalas"))
        threads.update_task(tarea.id, TaskUpdate(day=date.today()))
        threads.update_task(tarea.id, TaskUpdate(done=True))

        misma = threads.get_task(tarea.id)
        assert misma.done is True
        assert misma.week == semana_actual()


class TestAreasEnLaApi:
    def _tareas(self, client: TestClient, **params) -> list[str]:
        respuesta = client.get("/api/v1/threads", params=params)
        assert respuesta.status_code == 200
        return [t["text"] for hilo in respuesta.json() for t in hilo["tasks"]]

    def test_la_semana_no_trae_otras_tareas(
        self, client: TestClient, threads: ThreadService, guitarra
    ) -> None:
        threads.add_task(guitarra.id, TaskCreate(text="De esta semana"))
        threads.add_task(guitarra.id, TaskCreate(text="Algún día", backlog=True))

        assert "De esta semana" in self._tareas(client)
        assert "Algún día" not in self._tareas(client)

    def test_otras_tareas_solo_trae_lo_sin_fecha(
        self, client: TestClient, threads: ThreadService, guitarra
    ) -> None:
        threads.add_task(guitarra.id, TaskCreate(text="De esta semana"))
        threads.add_task(guitarra.id, TaskCreate(text="Algún día", backlog=True))

        textos = self._tareas(client, scope="backlog")
        assert textos == ["Algún día"]

    def test_otra_semana_no_aparece_en_la_actual(
        self, client: TestClient, threads: ThreadService, guitarra
    ) -> None:
        tarea = threads.add_task(guitarra.id, TaskCreate(text="La otra semana"))
        threads.update_task(tarea.id, TaskUpdate(week=semana_actual() + timedelta(days=7)))

        assert "La otra semana" not in self._tareas(client)
        futura = self._tareas(client, week=str(semana_actual() + timedelta(days=7)))
        assert "La otra semana" in futura

    def test_se_puede_pedir_la_semana_con_cualquier_dia(
        self, client: TestClient, threads: ThreadService, guitarra
    ) -> None:
        """El backend normaliza al lunes para que el frontend no repita la cuenta."""
        threads.add_task(guitarra.id, TaskCreate(text="De esta semana"))
        jueves = semana_actual() + timedelta(days=3)
        assert "De esta semana" in self._tareas(client, week=str(jueves))

    def test_la_base_rechaza_un_dia_fuera_de_su_semana(
        self, db_session: Session, guitarra
    ) -> None:
        """La invariante no depende de que el servicio la respete."""
        db_session.add(
            ThreadTask(
                thread_id=guitarra.id,
                text_="Incoherente",
                week=date(2026, 9, 21),
                day=date(2026, 10, 1),
            )
        )
        with pytest.raises(IntegrityError):
            db_session.flush()


class TestVistaDiaria:
    def _tareas(self, client: TestClient, **params) -> list[str]:
        respuesta = client.get("/api/v1/threads", params=params)
        assert respuesta.status_code == 200
        return [t["text"] for hilo in respuesta.json() for t in hilo["tasks"]]

    def test_el_dia_solo_trae_lo_bajado_a_ese_dia(
        self, client: TestClient, threads: ThreadService, guitarra
    ) -> None:
        threads.add_task(guitarra.id, TaskCreate(text="De hoy", day=date.today()))
        threads.add_task(guitarra.id, TaskCreate(text="Sin bajar"))

        textos = self._tareas(client, scope="day")
        assert "De hoy" in textos
        assert "Sin bajar" not in textos

    def test_lo_pendiente_de_ayer_aparece_hoy(
        self, client: TestClient, threads: ThreadService, guitarra
    ) -> None:
        ayer = date.today() - timedelta(days=1)
        threads.add_task(guitarra.id, TaskCreate(text="Quedó pendiente", day=ayer))
        assert "Quedó pendiente" in self._tareas(client, scope="day")

    def test_lo_atrasado_conserva_su_dia(
        self, threads: ThreadService, guitarra
    ) -> None:
        """No se mueve sola a hoy: el panel no miente sobre lo comprometido."""
        ayer = date.today() - timedelta(days=1)
        tarea = threads.add_task(guitarra.id, TaskCreate(text="Pendiente", day=ayer))
        assert threads.get_task(tarea.id).day == ayer

    def test_lo_terminado_ayer_no_reaparece_hoy(
        self, client: TestClient, threads: ThreadService, guitarra
    ) -> None:
        ayer = date.today() - timedelta(days=1)
        tarea = threads.add_task(guitarra.id, TaskCreate(text="Cerrada ayer", day=ayer))
        threads.update_task(tarea.id, TaskUpdate(done=True))
        assert "Cerrada ayer" not in self._tareas(client, scope="day")

    def test_un_dia_pasado_muestra_lo_suyo_y_no_lo_atrasado(
        self, client: TestClient, threads: ThreadService, guitarra
    ) -> None:
        """Mirar un martes anterior muestra ese martes, no un arrastre."""
        anteayer = date.today() - timedelta(days=2)
        ayer = date.today() - timedelta(days=1)
        threads.add_task(guitarra.id, TaskCreate(text="De anteayer", day=anteayer))
        threads.add_task(guitarra.id, TaskCreate(text="De ayer", day=ayer))

        textos = self._tareas(client, scope="day", day=str(ayer))
        assert textos == ["De ayer"]

    def test_crear_en_la_vista_diaria_la_mete_en_la_semana(
        self, client: TestClient, threads: ThreadService, guitarra
    ) -> None:
        hoy = date.today()
        tarea = threads.add_task(guitarra.id, TaskCreate(text="Del día", day=hoy))
        assert tarea.week == lunes_de(hoy)
        assert "Del día" in self._tareas(client, week=str(hoy))

    def test_crear_apuntando_a_otra_semana(
        self, threads: ThreadService, guitarra
    ) -> None:
        tarea = threads.add_task(
            guitarra.id, TaskCreate(text="La otra semana", week=date(2026, 9, 30))
        )
        assert tarea.week == date(2026, 9, 28)
        assert tarea.day is None


class TestReordenParcial:
    """Reordenar viendo un día no puede desordenar lo que no estaba a la vista."""

    def test_reordenar_una_parte_no_toca_al_resto(
        self, threads: ThreadService, guitarra
    ) -> None:
        a = threads.add_task(guitarra.id, TaskCreate(text="A"))
        b = threads.add_task(guitarra.id, TaskCreate(text="B"))
        c = threads.add_task(guitarra.id, TaskCreate(text="C"))
        posicion_b = b.position

        threads.reorder_tasks(guitarra.id, [c.id, a.id])

        # A y C se reparten los huecos que ya ocupaban; B se queda donde estaba.
        assert threads.get_task(c.id).position < threads.get_task(a.id).position
        assert threads.get_task(b.id).position == posicion_b

    def test_no_se_pisan_las_posiciones(
        self, threads: ThreadService, guitarra
    ) -> None:
        a = threads.add_task(guitarra.id, TaskCreate(text="A"))
        b = threads.add_task(guitarra.id, TaskCreate(text="B"))
        c = threads.add_task(guitarra.id, TaskCreate(text="C"))

        threads.reorder_tasks(guitarra.id, [c.id, a.id])

        posiciones = [threads.get_task(t.id).position for t in (a, b, c)]
        assert len(set(posiciones)) == 3
