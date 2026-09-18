"""Acceso a datos del dashboard semanal."""

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.db.models import Thread, ThreadTask
from app.repositories.base import BaseRepository


class ThreadRepository(BaseRepository[Thread]):
    model = Thread

    def get(self, thread_id: UUID) -> Thread | None:
        return self.session.get(Thread, thread_id)

    def get_by_name(self, name: str) -> Thread | None:
        stmt = select(Thread).where(func.lower(Thread.name) == name.strip().lower())
        return self.session.execute(stmt).scalar_one_or_none()

    def list(self) -> Sequence[Thread]:
        # selectinload: sin esto, leer las tareas de cada thread dispara una
        # consulta por papel adhesivo.
        stmt = (
            select(Thread)
            .options(selectinload(Thread.tasks))
            .order_by(Thread.position, Thread.name)
        )
        return self.session.execute(stmt).scalars().unique().all()

    def add(self, thread: Thread) -> Thread:
        self.session.add(thread)
        self.session.flush()
        self.session.refresh(thread)
        return thread

    def delete(self, thread: Thread) -> None:
        self.session.delete(thread)
        self.session.flush()

    def next_position(self) -> int:
        stmt = select(func.coalesce(func.max(Thread.position), -1) + 1)
        return int(self.session.execute(stmt).scalar_one())


class TaskRepository(BaseRepository[ThreadTask]):
    model = ThreadTask

    def get(self, task_id: UUID) -> ThreadTask | None:
        return self.session.get(ThreadTask, task_id)

    def add(self, task: ThreadTask) -> ThreadTask:
        self.session.add(task)
        self.session.flush()
        self.session.refresh(task)
        return task

    def delete(self, task: ThreadTask) -> None:
        self.session.delete(task)
        self.session.flush()

    def next_position(self, thread_id: UUID) -> int:
        stmt = select(
            func.coalesce(func.max(ThreadTask.position), -1) + 1
        ).where(ThreadTask.thread_id == thread_id)
        return int(self.session.execute(stmt).scalar_one())

    def completed_on_board(self) -> Sequence[ThreadTask]:
        """Tareas marcadas que siguen en el pizarrón."""
        stmt = select(ThreadTask).where(
            ThreadTask.done_at.is_not(None), ThreadTask.cleared_at.is_(None)
        )
        return self.session.execute(stmt).scalars().all()
