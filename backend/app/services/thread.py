"""Lógica del dashboard semanal."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date, datetime, timezone
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.calendario import lunes_de, semana_actual
from app.core.exceptions import (
    ThreadNameTakenError,
    ThreadNotFoundError,
    ThreadTaskNotFoundError,
)
from app.db.models import Thread, ThreadTask
from app.repositories.thread import TaskRepository, ThreadRepository
from app.schemas.thread import (
    TaskCreate,
    TaskUpdate,
    ThreadCreate,
    ThreadUpdate,
)


class ThreadService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.threads = ThreadRepository(session)
        self.tasks = TaskRepository(session)

    # --- Threads ---

    def get(self, thread_id: UUID) -> Thread:
        thread = self.threads.get(thread_id)
        if thread is None:
            raise ThreadNotFoundError(thread_id)
        return thread

    def list(self) -> Sequence[Thread]:
        return self.threads.list()

    def create(self, data: ThreadCreate) -> Thread:
        name = data.name.strip()
        if self.threads.get_by_name(name) is not None:
            raise ThreadNameTakenError(name)

        thread = Thread(
            name=name,
            color=data.color,
            position=self.threads.next_position(),
        )
        self.threads.add(thread)
        self.session.commit()
        self.session.refresh(thread)
        return thread

    def update(self, thread_id: UUID, data: ThreadUpdate) -> Thread:
        thread = self.get(thread_id)
        changes = data.model_dump(exclude_unset=True)

        if changes.get("name"):
            nuevo = changes["name"].strip()
            existente = self.threads.get_by_name(nuevo)
            if existente is not None and existente.id != thread.id:
                raise ThreadNameTakenError(nuevo)
            thread.name = nuevo

        for campo in ("color", "position", "width", "height"):
            if campo in changes:
                setattr(thread, campo, changes[campo])

        self.session.commit()
        self.session.refresh(thread)
        return thread

    def delete(self, thread_id: UUID) -> None:
        """Elimina el thread y sus tareas.

        Se borra todo: una macro tarea de la semana sin su frente de trabajo
        no significa nada.
        """
        thread = self.get(thread_id)
        self.threads.delete(thread)
        self.session.commit()

    def reorder(self, ids: list[UUID]) -> Sequence[Thread]:
        """Aplica el orden que dejó la persona al arrastrar los papeles."""
        posiciones = {tid: indice for indice, tid in enumerate(ids)}
        for thread in self.threads.list():
            if thread.id in posiciones:
                thread.position = posiciones[thread.id]
        self.session.commit()
        return self.threads.list()

    # --- Tareas ---

    def get_task(self, task_id: UUID) -> ThreadTask:
        task = self.tasks.get(task_id)
        if task is None:
            raise ThreadTaskNotFoundError(task_id)
        return task

    def add_task(self, thread_id: UUID, data: TaskCreate) -> ThreadTask:
        thread = self.get(thread_id)

        # Escribir una tarea en el pizarron es comprometerla para esta semana:
        # ese es el caso por defecto. Bajarla de una a un dia la mete en la
        # semana de ese dia, no en la actual, para que crear una tarea el
        # domingo para el lunes no la parta en dos semanas.
        if data.backlog:
            week, day = None, None
        elif data.day is not None:
            week, day = lunes_de(data.day), data.day
        elif data.week is not None:
            week, day = lunes_de(data.week), None
        else:
            week, day = semana_actual(), None

        task = ThreadTask(
            thread_id=thread.id,
            text_=data.text.strip(),
            description=(data.description or "").strip() or None,
            position=self.tasks.next_position(thread.id),
            week=week,
            day=day,
        )
        self.tasks.add(task)
        self.session.commit()
        self.session.refresh(task)
        return task

    def update_task(self, task_id: UUID, data: TaskUpdate) -> ThreadTask:
        task = self.get_task(task_id)
        changes = data.model_dump(exclude_unset=True)

        if changes.get("text"):
            task.text_ = changes["text"].strip()

        # Se comprueba la presencia de la clave y no su valor: mandar null es
        # como se borra una descripcion.
        if "description" in changes:
            task.description = (changes["description"] or "").strip() or None

        if "position" in changes and changes["position"] is not None:
            task.position = changes["position"]

        # El orden importa: la semana se procesa primero porque cambiarla
        # suelta el dia, y despues el dia puede volver a fijar ambas.
        if "week" in changes:
            nueva: date | None = changes["week"]
            task.week = lunes_de(nueva) if nueva is not None else None
            # Sin semana no puede haber dia, y un dia de otra semana tampoco
            # significa nada. En los dos casos se suelta.
            task.day = None

        if "day" in changes:
            task.day = changes["day"]
            if task.day is not None:
                task.week = lunes_de(task.day)

        if "active" in changes and changes["active"] is not None:
            task.active = changes["active"]

        if "done" in changes and changes["done"] is not None:
            # Se guarda el instante y no un booleano: permite responder después
            # "qué cerré esta semana", que un true/false no puede.
            task.done_at = (
                datetime.now(timezone.utc) if changes["done"] else None
            )
            # Terminar algo implica dejar de estar en ello. Sin esto, el panel
            # quedaría marcando como "en curso" tareas ya tachadas, que es
            # justo el ruido que la marca busca evitar.
            if changes["done"]:
                task.active = False

        self.session.commit()
        self.session.refresh(task)
        return task

    def reorder_tasks(self, thread_id: UUID, ids: list[UUID]) -> Sequence[ThreadTask]:
        """Aplica el orden dentro de un papel.

        Recibe la lista completa de lo que se estaba viendo y no un
        movimiento: mandar el orden entero evita que dos reacomodos seguidos
        dejen posiciones inconsistentes.

        Lo que llega puede ser solo una parte de las tareas del thread, porque
        la vista diaria muestra las de un dia. Por eso las tareas movidas se
        reparten las posiciones que ya ocupaban entre si, en vez de numerarse
        desde cero: numerar desde cero chocaria con las posiciones de las
        tareas que no estaban a la vista y dejaria el orden al azar.
        """
        thread = self.get(thread_id)
        por_id = {t.id: t for t in thread.tasks}
        movidas = [tid for tid in ids if tid in por_id]
        huecos = sorted(por_id[tid].position for tid in movidas)

        for hueco, tid in zip(huecos, movidas):
            por_id[tid].position = hueco

        self.session.commit()
        self.session.refresh(thread)
        return thread.tasks

    def delete_task(self, task_id: UUID) -> None:
        self.tasks.delete(self.get_task(task_id))
        self.session.commit()

    def cleanup(self) -> int:
        """Saca del pizarrón lo tachado. Devuelve cuántas se limpiaron.

        No borra: marca `cleared_at`. El tablero queda limpio y queda el
        registro de lo que efectivamente se cerró.
        """
        ahora = datetime.now(timezone.utc)
        limpiadas = 0
        for task in self.tasks.completed_on_board():
            task.cleared_at = ahora
            limpiadas += 1

        self.session.commit()
        return limpiadas
