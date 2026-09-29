"""Tests de reuniones: carpetas, tablero y resumen."""

import uuid
from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.calendario import hoy
from app.core.config import Settings, get_settings
from app.core.exceptions import (
    MeetingFolderNameTakenError,
    MeetingFolderNotFoundError,
    MeetingNotFoundError,
    ReunionVaciaError,
)
from app.db.models import Meeting, MeetingItem
from app.db.session import declarar_dueno, get_session
from app.integrations.resumen import ResumenError, Resumidor
from app.main import create_app
from app.schemas.meeting import (
    FolderCreate,
    FolderUpdate,
    ItemCreate,
    ItemUpdate,
    MeetingCreate,
    MeetingUpdate,
)
from app.services import meeting as meeting_module
from app.services.auth import AuthService
from app.services.meeting import FolderService, MeetingService


@pytest.fixture
def carpetas(db_session: Session) -> FolderService:
    return FolderService(db_session)


@pytest.fixture
def reuniones(db_session: Session) -> MeetingService:
    return MeetingService(db_session)


@pytest.fixture
def leonardo(carpetas: FolderService):
    return carpetas.create(FolderCreate(name="Reuniones con Leonardo"))


@pytest.fixture
def reunion(reuniones: MeetingService, leonardo):
    return reuniones.create(
        MeetingCreate(folder_id=leonardo.id, fecha=date(2026, 9, 28))
    )


class ResumidorFalso:
    """Devuelve lo que recibió, para poder mirar qué se le mandó al modelo."""

    recibido: str | None = None

    def __init__(self, settings) -> None:
        pass

    def resumir(self, notas: str) -> str:
        ResumidorFalso.recibido = notas
        return "Se conversó lo anotado."


class ResumidorRoto:
    def __init__(self, settings) -> None:
        pass

    def resumir(self, notas: str) -> str:
        raise ResumenError("el proveedor se cayó")


@pytest.fixture
def modelo_falso(monkeypatch: pytest.MonkeyPatch) -> type[ResumidorFalso]:
    ResumidorFalso.recibido = None
    monkeypatch.setattr(meeting_module, "Resumidor", ResumidorFalso)
    return ResumidorFalso


class TestCarpetas:
    def test_crear(self, carpetas: FolderService) -> None:
        nueva = carpetas.create(FolderCreate(name="Reuniones con Benjamín"))
        assert [c.name for c in carpetas.list()] == ["Reuniones con Benjamín"]
        assert nueva.position == 0

    def test_nombre_repetido_falla_sin_distinguir_mayusculas(
        self, carpetas: FolderService, leonardo
    ) -> None:
        with pytest.raises(MeetingFolderNameTakenError):
            carpetas.create(FolderCreate(name="reuniones con LEONARDO"))

    def test_renombrar(self, carpetas: FolderService, leonardo) -> None:
        renombrada = carpetas.update(leonardo.id, FolderUpdate(name="Leo"))
        assert renombrada.name == "Leo"

    def test_renombrar_a_un_nombre_ocupado_falla(
        self, carpetas: FolderService, leonardo
    ) -> None:
        otra = carpetas.create(FolderCreate(name="Benjamín"))
        with pytest.raises(MeetingFolderNameTakenError):
            carpetas.update(otra.id, FolderUpdate(name="Reuniones con Leonardo"))

    def test_borrar_se_lleva_sus_reuniones(
        self, carpetas: FolderService, reuniones: MeetingService, leonardo, reunion
    ) -> None:
        """Una reunión sin su carpeta no tiene dónde verse."""
        # El id se guarda antes: leerlo de la instancia después del borrado
        # obliga a recargarla, y su fila ya no existe.
        id_reunion = reunion.id
        reuniones.add_item(id_reunion, ItemCreate(zona="temas", text="Presupuesto"))
        carpetas.delete(leonardo.id)

        with pytest.raises(MeetingNotFoundError):
            reuniones.get(id_reunion)

    def test_inexistente_falla(self, carpetas: FolderService) -> None:
        with pytest.raises(MeetingFolderNotFoundError):
            carpetas.get(uuid.uuid4())


class TestReuniones:
    def test_sin_titulo_se_llama_por_su_fecha(
        self, reuniones: MeetingService, leonardo
    ) -> None:
        creada = reuniones.create(
            MeetingCreate(folder_id=leonardo.id, fecha=date(2026, 9, 28))
        )
        assert creada.title == "Reunión del 28/09"

    def test_sin_fecha_es_hoy(self, reuniones: MeetingService, leonardo) -> None:
        creada = reuniones.create(MeetingCreate(folder_id=leonardo.id))
        assert creada.fecha == hoy()

    def test_un_titulo_en_blanco_cuenta_como_sin_titulo(
        self, reuniones: MeetingService, leonardo
    ) -> None:
        creada = reuniones.create(
            MeetingCreate(folder_id=leonardo.id, title="   ", fecha=date(2026, 9, 1))
        )
        assert creada.title == "Reunión del 01/09"

    def test_se_listan_de_la_mas_reciente_a_la_mas_antigua(
        self, reuniones: MeetingService, leonardo
    ) -> None:
        for dia in (1, 15, 8):
            reuniones.create(
                MeetingCreate(folder_id=leonardo.id, fecha=date(2026, 9, dia))
            )
        fechas = [m.fecha.day for m in reuniones.list(leonardo.id)]
        assert fechas == [15, 8, 1]

    def test_no_se_mezclan_entre_carpetas(
        self, carpetas: FolderService, reuniones: MeetingService, leonardo, reunion
    ) -> None:
        otra = carpetas.create(FolderCreate(name="Benjamín"))
        assert reuniones.list(otra.id) == []

    def test_crear_en_una_carpeta_inexistente_falla(
        self, reuniones: MeetingService
    ) -> None:
        with pytest.raises(MeetingFolderNotFoundError):
            reuniones.create(MeetingCreate(folder_id=uuid.uuid4()))

    def test_editar_titulo_y_fecha(self, reuniones: MeetingService, reunion) -> None:
        editada = reuniones.update(
            reunion.id, MeetingUpdate(title="Kickoff", fecha=date(2026, 10, 2))
        )
        assert (editada.title, editada.fecha) == ("Kickoff", date(2026, 10, 2))

    def test_borrar(self, reuniones: MeetingService, reunion) -> None:
        reuniones.delete(reunion.id)
        with pytest.raises(MeetingNotFoundError):
            reuniones.get(reunion.id)


class TestTablero:
    def test_lo_nuevo_va_al_final_de_su_cuadrante(
        self, reuniones: MeetingService, reunion
    ) -> None:
        a = reuniones.add_item(reunion.id, ItemCreate(zona="temas", text="A"))
        b = reuniones.add_item(reunion.id, ItemCreate(zona="temas", text="B"))
        apunte = reuniones.add_item(reunion.id, ItemCreate(zona="apuntes", text="X"))

        assert (a.position, b.position) == (0, 1)
        # Cada cuadrante lleva su propia cuenta.
        assert apunte.position == 0

    def test_mover_a_conversado_lo_deja_despues_de_lo_ya_conversado(
        self, reuniones: MeetingService, reunion
    ) -> None:
        """Es el orden en que se fue hablando."""
        primero = reuniones.add_item(reunion.id, ItemCreate(zona="temas", text="1"))
        segundo = reuniones.add_item(reunion.id, ItemCreate(zona="temas", text="2"))

        reuniones.update_item(segundo.id, ItemUpdate(zona="conversado"))
        movido = reuniones.update_item(primero.id, ItemUpdate(zona="conversado"))

        assert movido.zona == "conversado"
        assert movido.position > reuniones.get_item(segundo.id).position

    def test_mover_no_copia(self, reuniones: MeetingService, reunion) -> None:
        tema = reuniones.add_item(reunion.id, ItemCreate(zona="temas", text="Plazo"))
        reuniones.update_item(tema.id, ItemUpdate(zona="tareas"))

        zonas = [i.zona for i in reuniones.get(reunion.id).items]
        assert zonas == ["tareas"]

    def test_editar_el_texto_no_lo_mueve(
        self, reuniones: MeetingService, reunion
    ) -> None:
        tema = reuniones.add_item(reunion.id, ItemCreate(zona="temas", text="Plazo"))
        editado = reuniones.update_item(tema.id, ItemUpdate(text="Plazo del informe"))
        assert (editado.text_, editado.zona) == ("Plazo del informe", "temas")

    def test_el_texto_se_guarda_sin_espacios_alrededor(
        self, reuniones: MeetingService, reunion
    ) -> None:
        item = reuniones.add_item(
            reunion.id, ItemCreate(zona="apuntes", text="  Antonia entrega mañana  ")
        )
        assert item.text_ == "Antonia entrega mañana"

    def test_borrar(self, reuniones: MeetingService, reunion) -> None:
        item = reuniones.add_item(reunion.id, ItemCreate(zona="temas", text="X"))
        reuniones.delete_item(item.id)
        assert reuniones.get(reunion.id).items == []


class TestInvariantesEnLaBase:
    """Lo que la base impide aunque el código se equivoque."""

    def test_una_zona_desconocida(
        self, db_session: Session, reunion
    ) -> None:
        db_session.add(MeetingItem(meeting_id=reunion.id, zona="otra", text_="X"))
        with pytest.raises(IntegrityError):
            db_session.flush()

    def test_un_texto_vacio(self, db_session: Session, reunion) -> None:
        db_session.add(MeetingItem(meeting_id=reunion.id, zona="temas", text_="  "))
        with pytest.raises(IntegrityError):
            db_session.flush()

    def test_un_resumen_sin_fecha(self, db_session: Session, reunion) -> None:
        with pytest.raises(IntegrityError):
            db_session.execute(
                text("UPDATE meetings SET summary = 'x' WHERE id = :id"),
                {"id": reunion.id},
            )

    def test_una_reunion_en_la_carpeta_de_otra_persona(
        self, db_session: Session, leonardo
    ) -> None:
        """La clave compuesta: el id de la carpeta existe, pero no es suya."""
        # Se guarda antes de cambiar de dueño: después, la política por fila
        # ya no deja recargar la carpeta para leerlo.
        ajena = leonardo.id
        beto = AuthService(db_session).crear_usuario("beto@example.com", "clave-larga-1")
        declarar_dueno(db_session, beto.id)

        db_session.add(Meeting(folder_id=ajena, title="Colada", fecha=hoy()))
        with pytest.raises(IntegrityError):
            db_session.flush()


class TestResumen:
    def _llenar(self, reuniones: MeetingService, reunion) -> None:
        for zona, texto in (
            ("conversado", "Presupuesto del Q4"),
            ("tareas", "Antonia entrega el reporte mañana"),
            ("apuntes", "El cliente aprobó el diseño"),
            ("temas", "Contrataciones"),
        ):
            reuniones.add_item(reunion.id, ItemCreate(zona=zona, text=texto))

    def test_se_guarda_con_su_fecha(
        self, reuniones: MeetingService, reunion, modelo_falso
    ) -> None:
        self._llenar(reuniones, reunion)
        resumida = reuniones.summarize(reunion.id)

        assert resumida.summary == "Se conversó lo anotado."
        assert resumida.summary_at is not None

    def test_al_modelo_le_llega_todo_lo_anotado(
        self, reuniones: MeetingService, reunion, modelo_falso
    ) -> None:
        self._llenar(reuniones, reunion)
        reuniones.summarize(reunion.id)

        notas = modelo_falso.recibido
        assert "Reuniones con Leonardo" in notas
        assert "Presupuesto del Q4" in notas
        assert "Antonia entrega el reporte mañana" in notas
        assert "El cliente aprobó el diseño" in notas

    def test_lo_que_quedo_arriba_a_la_izquierda_va_como_no_alcanzado(
        self, reuniones: MeetingService, reunion, modelo_falso
    ) -> None:
        self._llenar(reuniones, reunion)
        reuniones.summarize(reunion.id)
        assert "no se alcanzaron a conversar:\n- Contrataciones" in (
            modelo_falso.recibido
        )

    def test_los_cuadrantes_vacios_no_van(
        self, reuniones: MeetingService, reunion, modelo_falso
    ) -> None:
        """Un encabezado vacío invita al modelo a comentar lo que no hubo."""
        reuniones.add_item(reunion.id, ItemCreate(zona="conversado", text="Algo"))
        reuniones.summarize(reunion.id)

        assert "Tareas pendientes" not in modelo_falso.recibido
        assert "Apuntes" not in modelo_falso.recibido

    def test_una_reunion_sin_nada_conversado_ni_anotado_no_se_resume(
        self, reuniones: MeetingService, reunion, modelo_falso
    ) -> None:
        reuniones.add_item(reunion.id, ItemCreate(zona="temas", text="Pendiente"))
        with pytest.raises(ReunionVaciaError):
            reuniones.summarize(reunion.id)
        assert modelo_falso.recibido is None

    def test_si_el_modelo_falla_queda_el_resumen_anterior(
        self,
        reuniones: MeetingService,
        reunion,
        modelo_falso,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        self._llenar(reuniones, reunion)
        reuniones.summarize(reunion.id)

        monkeypatch.setattr(meeting_module, "Resumidor", ResumidorRoto)
        with pytest.raises(ResumenError):
            reuniones.summarize(reunion.id)
        assert reuniones.get(reunion.id).summary == "Se conversó lo anotado."


class TestLimpiezaDelResumen:
    def test_quita_el_bloque_de_codigo(self) -> None:
        assert Resumidor._limpiar("```\nPárrafo uno.\n\nDos.\n```") == (
            "Párrafo uno.\n\nDos."
        )

    def test_quita_los_espacios_alrededor(self) -> None:
        assert Resumidor._limpiar("\n  Párrafo.  \n") == "Párrafo."

    def test_vacio_es_un_error(self) -> None:
        with pytest.raises(ResumenError):
            Resumidor._limpiar("   ")


class TestApi:
    def _carpeta(self, client: TestClient, nombre: str = "Leonardo") -> dict:
        respuesta = client.post("/api/v1/meetings/folders", json={"name": nombre})
        assert respuesta.status_code == 201
        return respuesta.json()

    def _reunion(self, client: TestClient, carpeta: dict) -> dict:
        respuesta = client.post(
            "/api/v1/meetings", json={"folder_id": carpeta["id"], "fecha": "2026-09-28"}
        )
        assert respuesta.status_code == 201
        return respuesta.json()

    def test_flujo_completo(self, client: TestClient, modelo_falso) -> None:
        carpeta = self._carpeta(client)
        reunion = self._reunion(client, carpeta)
        assert reunion["title"] == "Reunión del 28/09"
        assert reunion["folder_name"] == "Leonardo"

        tema = client.post(
            f"/api/v1/meetings/{reunion['id']}/items",
            json={"zona": "temas", "text": "Presupuesto"},
        ).json()
        movido = client.patch(
            f"/api/v1/meetings/items/{tema['id']}", json={"zona": "conversado"}
        )
        assert movido.json()["zona"] == "conversado"

        resumida = client.post(f"/api/v1/meetings/{reunion['id']}/summary")
        assert resumida.status_code == 200
        assert resumida.json()["summary"] == "Se conversó lo anotado."

        lista = client.get(
            "/api/v1/meetings", params={"folder_id": carpeta["id"]}
        ).json()
        assert lista[0]["tiene_resumen"] is True

    def test_la_carpeta_cuenta_sus_reuniones(self, client: TestClient) -> None:
        carpeta = self._carpeta(client)
        self._reunion(client, carpeta)
        carpetas = client.get("/api/v1/meetings/folders").json()
        assert carpetas[0]["meetings_count"] == 1

    def test_listar_una_carpeta_inexistente_da_404(self, client: TestClient) -> None:
        respuesta = client.get(
            "/api/v1/meetings", params={"folder_id": str(uuid.uuid4())}
        )
        assert respuesta.status_code == 404

    def test_una_zona_desconocida_da_422(self, client: TestClient) -> None:
        reunion = self._reunion(client, self._carpeta(client))
        respuesta = client.post(
            f"/api/v1/meetings/{reunion['id']}/items",
            json={"zona": "otra", "text": "X"},
        )
        assert respuesta.status_code == 422

    def test_un_texto_de_puros_espacios_da_422(self, client: TestClient) -> None:
        reunion = self._reunion(client, self._carpeta(client))
        respuesta = client.post(
            f"/api/v1/meetings/{reunion['id']}/items",
            json={"zona": "temas", "text": "   "},
        )
        assert respuesta.status_code == 422

    def test_nombre_de_carpeta_repetido_da_409(self, client: TestClient) -> None:
        self._carpeta(client)
        respuesta = client.post("/api/v1/meetings/folders", json={"name": "leonardo"})
        assert respuesta.status_code == 409

    def test_resumir_una_reunion_vacia_da_409(
        self, client: TestClient, modelo_falso
    ) -> None:
        reunion = self._reunion(client, self._carpeta(client))
        respuesta = client.post(f"/api/v1/meetings/{reunion['id']}/summary")
        assert respuesta.status_code == 409

    def test_si_el_modelo_falla_da_502(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(meeting_module, "Resumidor", ResumidorRoto)
        reunion = self._reunion(client, self._carpeta(client))
        client.post(
            f"/api/v1/meetings/{reunion['id']}/items",
            json={"zona": "apuntes", "text": "Algo"},
        )
        respuesta = client.post(f"/api/v1/meetings/{reunion['id']}/summary")
        assert respuesta.status_code == 502

    def test_borrar_la_carpeta(self, client: TestClient) -> None:
        carpeta = self._carpeta(client)
        reunion = self._reunion(client, carpeta)

        borrado = client.delete(f"/api/v1/meetings/folders/{carpeta['id']}")
        assert borrado.status_code == 204
        assert client.get(f"/api/v1/meetings/{reunion['id']}").status_code == 404

    def test_sin_sesion_responde_401(
        self, db_session: Session, app_settings: Settings
    ) -> None:
        app = create_app()
        app.dependency_overrides[get_session] = lambda: db_session
        app.dependency_overrides[get_settings] = lambda: app_settings
        anonimo = TestClient(app, base_url="https://testserver")

        assert anonimo.get("/api/v1/meetings/folders").status_code == 401
        app.dependency_overrides.clear()

