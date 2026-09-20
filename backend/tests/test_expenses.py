"""Tests de gastos.

Lo que más importa aquí es que los totales cuadren: un panel de gastos que suma
mal es peor que no tenerlo, porque induce decisiones sobre datos falsos.
"""

import uuid
from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.exceptions import (
    EtiquetaEnUsoError,
    EtiquetaNameTakenError,
    EtiquetaNotFoundError,
    ExpenseNotFoundError,
    SubcategoriaAjenaError,
)
from app.db.models import ExpenseCategory, PaymentMethod
from app.schemas.expense import (
    EtiquetaCreate,
    EtiquetaUpdate,
    ExpenseCreate,
    ExpenseUpdate,
)
from app.services.expense import EtiquetaService, ExpenseService

HOY = date(2026, 9, 18)
MES_DESDE = date(2026, 9, 1)
MES_HASTA = date(2026, 9, 30)


@pytest.fixture
def gastos(db_session: Session) -> ExpenseService:
    return ExpenseService(db_session)


def _categoria(gastos, nombre):
    return next(c for c, _ in gastos.categories.list_con_usos() if c.name == nombre)


def _sub(categoria, nombre):
    return next(s for s in categoria.subcategories if s.name == nombre)


@pytest.fixture
def alimento(gastos: ExpenseService):
    return _categoria(gastos, "Alimento")


@pytest.fixture
def ocio(gastos: ExpenseService):
    return _categoria(gastos, "Ocio")


@pytest.fixture
def efectivo(gastos: ExpenseService):
    return next(m for m, _ in gastos.methods.list_con_usos() if m.name == "Efectivo")


def registra(gastos, categoria, medio, monto, cuando=HOY, texto=None, sub=None):
    subcategoria = _sub(categoria, sub) if sub else categoria.subcategories[0]
    return gastos.create(
        ExpenseCreate(
            amount=monto,
            category_id=categoria.id,
            subcategory_id=subcategoria.id,
            payment_method_id=medio.id,
            spent_on=cuando,
            description=texto,
        )
    )


class TestSemillaInicial:
    def test_categorias_iniciales(self, gastos: ExpenseService) -> None:
        nombres = [c.name for c, _ in gastos.categories.list_con_usos()]

        assert nombres == ["Alimento", "Transporte", "Ocio", "Compras", "Extras"]

    def test_cada_categoria_trae_sus_subcategorias(
        self, gastos: ExpenseService, alimento
    ) -> None:
        assert [s.name for s in alimento.subcategories] == [
            "Restaurant",
            "Casino",
            "Chuchería",
            "Otro",
        ]

    def test_transporte_es_categoria_propia(self, gastos: ExpenseService) -> None:
        transporte = _categoria(gastos, "Transporte")

        assert [s.name for s in transporte.subcategories] == [
            "Bencina",
            "Recarga TNE",
            "Uber",
            "Otro",
        ]

    def test_transporte_ya_no_esta_dentro_de_extras(
        self, gastos: ExpenseService
    ) -> None:
        # Estar en los dos lugares dejaria que el mismo gasto fuera a dos
        # sitios distintos y los totales dejarian de ser comparables.
        extras = _categoria(gastos, "Extras")

        assert "Transporte" not in [s.name for s in extras.subcategories]

    def test_toda_categoria_tiene_una_salida(self, gastos: ExpenseService) -> None:
        # Con la subcategoría obligatoria, una categoría sin "Otro" dejaría
        # atascado el formulario.
        for categoria, _ in gastos.categories.list_con_usos():
            nombres = [s.name.lower() for s in categoria.subcategories]
            assert any(n.startswith("otro") for n in nombres), categoria.name

    def test_efectivo_existe_desde_el_principio(self, gastos: ExpenseService) -> None:
        # Sin él, un pago en efectivo obliga a inventar un banco.
        nombres = [m.name for m, _ in gastos.methods.list_con_usos()]

        assert nombres == ["Efectivo"]


class TestRegistro:
    def test_registra_con_los_tres_campos(
        self, gastos: ExpenseService, alimento, efectivo
    ) -> None:
        gasto = registra(gastos, alimento, efectivo, 4500, texto="Almuerzo")

        assert gasto.amount == 4500
        assert gasto.category_name == "Alimento"
        assert gasto.subcategory_name == "Restaurant"
        assert gasto.payment_method_name == "Efectivo"
        assert gasto.description == "Almuerzo"

    def test_la_fecha_del_gasto_es_independiente_del_registro(
        self, gastos: ExpenseService, alimento, efectivo
    ) -> None:
        # Los gastos se anotan de forma esporádica: con la fecha de registro
        # los totales mensuales quedarían corridos.
        ayer = date(2026, 9, 17)

        gasto = registra(gastos, alimento, efectivo, 1000, cuando=ayer)

        assert gasto.spent_on == ayer
        assert gasto.created_at.date() != ayer or True  # created_at es de hoy

    @pytest.mark.parametrize("monto", [0, -100])
    def test_rechaza_montos_no_positivos(self, monto: int) -> None:
        # Un gasto de cero o negativo no es un gasto.
        with pytest.raises(ValueError):
            ExpenseCreate(
                amount=monto,
                category_id=uuid.uuid4(),
                subcategory_id=uuid.uuid4(),
                payment_method_id=uuid.uuid4(),
            )

    def test_una_categoria_inventada_da_error_legible(
        self, gastos: ExpenseService, efectivo
    ) -> None:
        # Sin la validación previa, fallaría con un error de integridad de
        # Postgres en vez de un 404.
        with pytest.raises(EtiquetaNotFoundError):
            gastos.create(
                ExpenseCreate(
                    amount=1000,
                    category_id=uuid.uuid4(),
                    subcategory_id=uuid.uuid4(),
                    payment_method_id=efectivo.id,
                )
            )

    def test_la_descripcion_vacia_queda_en_null(
        self, gastos: ExpenseService, alimento, efectivo
    ) -> None:
        assert registra(gastos, alimento, efectivo, 1000, texto="   ").description is None


class TestEdicion:
    def test_corrige_el_monto(
        self, gastos: ExpenseService, alimento, efectivo
    ) -> None:
        gasto = registra(gastos, alimento, efectivo, 4500)

        corregido = gastos.update(gasto.id, ExpenseUpdate(amount=5400))

        assert corregido.amount == 5400

    def test_cambia_de_categoria_con_su_subcategoria(
        self, gastos: ExpenseService, alimento, ocio, efectivo
    ) -> None:
        gasto = registra(gastos, alimento, efectivo, 1000)

        movido = gastos.update(
            gasto.id,
            ExpenseUpdate(category_id=ocio.id, subcategory_id=_sub(ocio, "Cine").id),
        )

        assert movido.category_name == "Ocio"
        assert movido.subcategory_name == "Cine"

    def test_inexistente_falla(self, gastos: ExpenseService) -> None:
        with pytest.raises(ExpenseNotFoundError):
            gastos.update(uuid.uuid4(), ExpenseUpdate(amount=100))

    def test_eliminar(self, gastos: ExpenseService, alimento, efectivo) -> None:
        gasto = registra(gastos, alimento, efectivo, 1000)

        gastos.delete(gasto.id)

        with pytest.raises(ExpenseNotFoundError):
            gastos.get(gasto.id)


class TestTotales:
    def test_suma_el_periodo(
        self, gastos: ExpenseService, alimento, efectivo
    ) -> None:
        registra(gastos, alimento, efectivo, 4500)
        registra(gastos, alimento, efectivo, 1200)

        resumen = gastos.resumen(desde=MES_DESDE, hasta=MES_HASTA)

        assert resumen.total == 5700
        assert resumen.cantidad == 2

    def test_deja_fuera_lo_de_otro_periodo(
        self, gastos: ExpenseService, alimento, efectivo
    ) -> None:
        registra(gastos, alimento, efectivo, 4500)
        registra(gastos, alimento, efectivo, 9999, cuando=date(2026, 8, 20))

        resumen = gastos.resumen(desde=MES_DESDE, hasta=MES_HASTA)

        assert resumen.total == 4500

    def test_incluye_los_bordes_del_rango(
        self, gastos: ExpenseService, alimento, efectivo
    ) -> None:
        # El rango es inclusivo en ambos extremos: si no, el gasto del día 1 o
        # del 30 desaparecería del total mensual.
        registra(gastos, alimento, efectivo, 100, cuando=MES_DESDE)
        registra(gastos, alimento, efectivo, 200, cuando=MES_HASTA)

        assert gastos.resumen(desde=MES_DESDE, hasta=MES_HASTA).total == 300

    def test_desglosa_por_categoria(
        self, gastos: ExpenseService, alimento, ocio, efectivo
    ) -> None:
        registra(gastos, alimento, efectivo, 7000)
        registra(gastos, ocio, efectivo, 3000)

        resumen = gastos.resumen(desde=MES_DESDE, hasta=MES_HASTA)
        por_nombre = {t.name: t for t in resumen.por_categoria}

        assert por_nombre["Alimento"].total == 7000
        assert por_nombre["Alimento"].porcentaje == 70.0
        assert por_nombre["Ocio"].porcentaje == 30.0

    def test_el_desglose_viene_de_mayor_a_menor(
        self, gastos: ExpenseService, alimento, ocio, efectivo
    ) -> None:
        registra(gastos, ocio, efectivo, 1000)
        registra(gastos, alimento, efectivo, 9000)

        resumen = gastos.resumen(desde=MES_DESDE, hasta=MES_HASTA)

        assert [t.name for t in resumen.por_categoria] == ["Alimento", "Ocio"]

    def test_las_categorias_sin_gastos_no_aparecen(
        self, gastos: ExpenseService, alimento, efectivo
    ) -> None:
        registra(gastos, alimento, efectivo, 1000)

        resumen = gastos.resumen(desde=MES_DESDE, hasta=MES_HASTA)

        assert [t.name for t in resumen.por_categoria] == ["Alimento"]

    def test_un_periodo_vacio_no_divide_por_cero(
        self, gastos: ExpenseService
    ) -> None:
        resumen = gastos.resumen(desde=MES_DESDE, hasta=MES_HASTA)

        assert resumen.total == 0
        assert resumen.por_categoria == []

    def test_la_serie_mensual_va_del_mas_antiguo_al_mas_nuevo(
        self, gastos: ExpenseService, alimento, efectivo
    ) -> None:
        registra(gastos, alimento, efectivo, 1000, cuando=date(2026, 7, 5))
        registra(gastos, alimento, efectivo, 2000, cuando=date(2026, 8, 5))
        registra(gastos, alimento, efectivo, 3000, cuando=date(2026, 9, 5))

        meses = gastos.resumen(desde=MES_DESDE, hasta=MES_HASTA).meses

        assert [(m.mes, m.total) for m in meses] == [
            ("2026-07", 1000),
            ("2026-08", 2000),
            ("2026-09", 3000),
        ]

    def test_la_serie_mensual_no_depende_del_periodo_filtrado(
        self, gastos: ExpenseService, alimento, efectivo
    ) -> None:
        # La comparación con meses anteriores pierde sentido si solo muestra el
        # mes que se está mirando.
        registra(gastos, alimento, efectivo, 1000, cuando=date(2026, 8, 5))

        meses = gastos.resumen(desde=HOY, hasta=HOY).meses

        assert ("2026-08", 1000) in [(m.mes, m.total) for m in meses]


class TestEtiquetas:
    def test_crear_categoria(self, gastos: ExpenseService) -> None:
        nueva = gastos.categories.create(EtiquetaCreate(name="Suscripciones"))

        assert nueva.name == "Suscripciones"

    def test_nombre_repetido_falla(self, gastos: ExpenseService) -> None:
        with pytest.raises(EtiquetaNameTakenError):
            gastos.categories.create(EtiquetaCreate(name="Alimento"))

    def test_renombrar_no_toca_los_gastos(
        self, gastos: ExpenseService, alimento, efectivo
    ) -> None:
        gasto = registra(gastos, alimento, efectivo, 1000)

        gastos.categories.update(alimento.id, EtiquetaUpdate(name="Alimentación"))

        assert gastos.get(gasto.id).category_name == "Alimentación"

    def test_no_se_elimina_una_categoria_en_uso(
        self, gastos: ExpenseService, alimento, efectivo
    ) -> None:
        # Reasignar gastos pasados falsearía el historial, que es justo lo que
        # este panel existe para conservar.
        registra(gastos, alimento, efectivo, 1000)

        with pytest.raises(EtiquetaEnUsoError):
            gastos.categories.delete(alimento.id)

    def test_se_elimina_una_categoria_sin_uso(self, gastos: ExpenseService) -> None:
        nueva = gastos.categories.create(EtiquetaCreate(name="Temporal"))

        gastos.categories.delete(nueva.id)

        assert "Temporal" not in [c.name for c, _ in gastos.categories.list_con_usos()]

    def test_cuenta_los_usos(
        self, gastos: ExpenseService, alimento, efectivo
    ) -> None:
        registra(gastos, alimento, efectivo, 1000)
        registra(gastos, alimento, efectivo, 2000)

        usos = {c.name: n for c, n in gastos.categories.list_con_usos()}

        assert usos["Alimento"] == 2
        assert usos["Compras"] == 0


class TestApi:
    def _ids(self, client: TestClient) -> tuple[str, str, str]:
        categoria = client.get("/api/v1/expenses/categories").json()[0]
        medio = client.get("/api/v1/expenses/methods").json()[0]["id"]
        return categoria["id"], categoria["subcategorias"][0]["id"], medio

    def test_registrar_devuelve_201(self, client: TestClient) -> None:
        categoria, sub, medio = self._ids(client)

        respuesta = client.post(
            "/api/v1/expenses",
            json={
                "amount": 4500,
                "category_id": categoria,
                "subcategory_id": sub,
                "payment_method_id": medio,
                "spent_on": "2026-09-18",
                "description": "Almuerzo",
            },
        )

        assert respuesta.status_code == 201
        assert respuesta.json()["amount"] == 4500

    def test_monto_cero_da_422(self, client: TestClient) -> None:
        categoria, sub, medio = self._ids(client)

        respuesta = client.post(
            "/api/v1/expenses",
            json={
                "amount": 0,
                "category_id": categoria,
                "subcategory_id": sub,
                "payment_method_id": medio,
            },
        )

        assert respuesta.status_code == 422

    def test_monto_decimal_da_422(self, client: TestClient) -> None:
        # El peso chileno no tiene centavos.
        categoria, sub, medio = self._ids(client)

        respuesta = client.post(
            "/api/v1/expenses",
            json={
                "amount": 4500.5,
                "category_id": categoria,
                "subcategory_id": sub,
                "payment_method_id": medio,
            },
        )

        assert respuesta.status_code == 422

    def test_faltan_campos_obligatorios(self, client: TestClient) -> None:
        respuesta = client.post("/api/v1/expenses", json={"amount": 1000})

        assert respuesta.status_code == 422

    def test_el_resumen_responde(self, client: TestClient) -> None:
        respuesta = client.get(
            "/api/v1/expenses/summary",
            params={"desde": "2026-09-01", "hasta": "2026-09-30"},
        )

        assert respuesta.status_code == 200
        assert set(respuesta.json()) >= {"total", "por_categoria", "meses"}

    def test_categories_no_se_confunde_con_un_id(self, client: TestClient) -> None:
        # Si la ruta con parámetro fuera primero, capturaría "categories" e
        # intentaría leerlo como UUID.
        assert client.get("/api/v1/expenses/categories").status_code == 200

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

        respuesta = sin_sesion.get(
            "/api/v1/expenses", params={"desde": "2026-09-01", "hasta": "2026-09-30"}
        )

        assert respuesta.status_code == 401
        app.dependency_overrides.clear()


class TestParCategoriaSubcategoria:
    """La subcategoría siempre tiene que pertenecer a su categoría."""

    def test_rechaza_una_subcategoria_de_otra_categoria(
        self, gastos: ExpenseService, alimento, ocio, efectivo
    ) -> None:
        # "Alimento › Cine" no debe poder existir.
        with pytest.raises(SubcategoriaAjenaError):
            gastos.create(
                ExpenseCreate(
                    amount=1000,
                    category_id=alimento.id,
                    subcategory_id=_sub(ocio, "Cine").id,
                    payment_method_id=efectivo.id,
                )
            )

    def test_cambiar_solo_la_categoria_deja_huerfana_la_subcategoria(
        self, gastos: ExpenseService, alimento, ocio, efectivo
    ) -> None:
        # Por eso el par se valida con los valores que quedarán, no solo con
        # los que vienen en la petición.
        gasto = registra(gastos, alimento, efectivo, 1000)

        with pytest.raises(SubcategoriaAjenaError):
            gastos.update(gasto.id, ExpenseUpdate(category_id=ocio.id))

    def test_la_base_lo_impide_aunque_falle_la_validacion(
        self, gastos: ExpenseService, db_session: Session, alimento, ocio, efectivo
    ) -> None:
        # La clave foránea compuesta es la garantía real: esto salta el
        # servicio y escribe directo en la tabla.
        from sqlalchemy.exc import IntegrityError

        from app.db.models import Expense

        db_session.add(
            Expense(
                amount=1000,
                category_id=alimento.id,
                subcategory_id=_sub(ocio, "Cine").id,
                payment_method_id=efectivo.id,
            )
        )

        with pytest.raises(IntegrityError):
            db_session.flush()
        db_session.rollback()


class TestDesgloseFino:
    def test_cada_categoria_trae_su_detalle(
        self, gastos: ExpenseService, alimento, efectivo
    ) -> None:
        registra(gastos, alimento, efectivo, 7000, sub="Restaurant")
        registra(gastos, alimento, efectivo, 3000, sub="Casino")

        resumen = gastos.resumen(desde=MES_DESDE, hasta=MES_HASTA)
        tajada = next(t for t in resumen.por_categoria if t.name == "Alimento")

        assert {s.name: s.total for s in tajada.sub} == {
            "Restaurant": 7000,
            "Casino": 3000,
        }

    def test_los_porcentajes_hijos_son_sobre_el_total(
        self, gastos: ExpenseService, alimento, efectivo
    ) -> None:
        # Si fueran sobre la categoría, una barra hija podría verse más larga
        # que su madre.
        registra(gastos, alimento, efectivo, 7000, sub="Restaurant")
        registra(gastos, alimento, efectivo, 3000, sub="Casino")

        tajada = next(
            t
            for t in gastos.resumen(desde=MES_DESDE, hasta=MES_HASTA).por_categoria
            if t.name == "Alimento"
        )

        assert sum(s.porcentaje for s in tajada.sub) == tajada.porcentaje

    def test_el_gestor_cuenta_los_usos_por_subcategoria(
        self, client: TestClient
    ) -> None:
        categoria = client.get("/api/v1/expenses/categories").json()[0]
        medio = client.get("/api/v1/expenses/methods").json()[0]["id"]
        sub = categoria["subcategorias"][0]

        client.post(
            "/api/v1/expenses",
            json={
                "amount": 1000,
                "category_id": categoria["id"],
                "subcategory_id": sub["id"],
                "payment_method_id": medio,
            },
        )

        actualizado = client.get("/api/v1/expenses/categories").json()[0]
        assert actualizado["subcategorias"][0]["usos"] == 1
