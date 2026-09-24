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
from app.db.models import Thread, ThreadTask, ThreadTaskEvent
from app.repositories.thread import (
    TaskEventRepository,
    TaskRepository,
    ThreadRepository,
)
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
        self.events = TaskEventRepository(session)

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

    # --- Historia ---

    def _registrar(
        self,
        task: ThreadTask,
        kind: str,
        *,
        from_day=None,
        to_day=None,
    ) -> None:
        """Deja constancia de algo que le pasó a una tarea.

        Se copian el nombre del thread y el texto: el registro tiene que
        seguir siendo legible aunque después se borre la tarea o se renombre
        el thread. El evento se agrega a la sesión y viaja en el mismo commit
        que el cambio, así que no puede quedar uno sin el otro.
        """
        nombre = task.thread.name if task.thread else "(thread borrado)"
        self.session.add(
            ThreadTaskEvent(
                task_id=task.id,
                thread_name=nombre,
                task_text=task.text_,
                kind=kind,
                from_day=from_day,
                to_day=to_day,
            )
        )

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
        self._registrar(task, "creada", from_day=day)
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

        # El dia antes de tocarlo: lo que se pierde al reprogramar es
        # justamente de donde venia, que es lo que dice cuanto se pospone.
        dia_previo = task.day

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

        if ("day" in changes or "week" in changes) and task.day != dia_previo:
            self._registrar(task, "movida", from_day=dia_previo, to_day=task.day)

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

            # El registro guarda los dos sentidos. En la tabla, desmarcar
            # borra done_at y con eso el cierre anterior; aquí no se pierde.
            # from_day es el día al que estaba comprometida: es contra eso que
            # se mide el atraso.
            self._registrar(
                task,
                "hecha" if changes["done"] else "reabierta",
                from_day=task.day,
            )

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
        """Borra la tarea, pero no su historia.

        El evento se escribe antes: la fila del registro lleva el texto y el
        thread copiados, asi que sobrevive al borrado con `task_id` en NULL.
        Sin esto el historico solo mostraria lo que salio bien.
        """
        task = self.get_task(task_id)
        self._registrar(task, "eliminada", from_day=task.day)
        self.session.flush()

        self.tasks.delete(task)
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

    # --- Histórico ---

    def history(self, desde: date, hasta: date) -> dict:
        """Qué pasó entre dos fechas, con el resumen ya calculado.

        El atraso se mide contra el día al que la tarea estaba comprometida
        cuando se cerró. Lo cerrado sin día asignado no entra en el promedio:
        no se pospuso nada, simplemente no tenía fecha, y contarlo como cero
        de atraso haría ver más puntual de lo que se fue.
        """
        eventos = self.events.between(desde, hasta)

        atrasos = []
        salida = []
        for evento in eventos:
            atraso = None
            if evento.kind == "hecha" and evento.from_day is not None:
                # .date() sobre un timestamptz da el día en UTC; en Chile eso
                # puede correr un cierre nocturno al día siguiente. Se pasa a
                # hora local antes de restar.
                cerrado = evento.at.astimezone().date()
                atraso = (cerrado - evento.from_day).days
                atrasos.append(atraso)
            salida.append((evento, atraso))

        def cuantos(kind: str) -> int:
            return sum(1 for e in eventos if e.kind == kind)

        return {
            "desde": desde,
            "hasta": hasta,
            "hechas": cuantos("hecha"),
            "creadas": cuantos("creada"),
            "movidas": cuantos("movida"),
            "eliminadas": cuantos("eliminada"),
            "atraso_promedio": (
                round(sum(atrasos) / len(atrasos), 1) if atrasos else None
            ),
            "a_tiempo": sum(1 for a in atrasos if a <= 0),
            "atrasadas": sum(1 for a in atrasos if a > 0),
            "eventos": salida,
        }
