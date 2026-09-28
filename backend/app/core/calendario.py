"""Aritmetica de semanas.

La semana empieza el lunes, como `date_trunc('week', ...)` de Postgres: la
misma definicion en los dos lados evita que una tarea guardada por el servicio
choque con el CHECK de la base.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

# El contenedor corre en UTC y quien usa Silu vive en Chile. Con date.today()
# el backend daba por empezado el dia siguiente a las 21:00, y desde esa hora
# la vista de hoy dejaba de mostrar lo atrasado. Va fija en el codigo y no en
# el TZ del contenedor para que no dependa de como se levante la imagen.
ZONA = ZoneInfo("America/Santiago")


def hoy() -> date:
    return datetime.now(ZONA).date()


def lunes_de(dia: date) -> date:
    """El lunes de la semana a la que pertenece `dia`."""
    return dia - timedelta(days=dia.weekday())


def semana_actual() -> date:
    return lunes_de(hoy())
