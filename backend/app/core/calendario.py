"""Aritmetica de semanas.

La semana empieza el lunes, como `date_trunc('week', ...)` de Postgres: la
misma definicion en los dos lados evita que una tarea guardada por el servicio
choque con el CHECK de la base.
"""

from __future__ import annotations

from datetime import date, timedelta


def lunes_de(dia: date) -> date:
    """El lunes de la semana a la que pertenece `dia`."""
    return dia - timedelta(days=dia.weekday())


def semana_actual() -> date:
    return lunes_de(date.today())
