"""Acceso a datos de proyectos y prompts."""

from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.db.models import Prompt, PromptProject
from app.repositories.base import BaseRepository


class ProjectRepository(BaseRepository[PromptProject]):
    model = PromptProject

    def get(self, project_id: UUID) -> PromptProject | None:
        return self.session.get(PromptProject, project_id)

    def get_by_name(self, name: str) -> PromptProject | None:
        # Sin distinguir mayúsculas: el modelo puede devolver "chilean2sign"
        # donde el proyecto se llama "Chilean2Sign".
        stmt = select(PromptProject).where(
            func.lower(PromptProject.name) == name.strip().lower()
        )
        return self.session.execute(stmt).scalar_one_or_none()

    def list(self) -> Sequence[PromptProject]:
        stmt = (
            select(PromptProject)
            .options(selectinload(PromptProject.prompts))
            .order_by(PromptProject.position, PromptProject.name)
        )
        return self.session.execute(stmt).scalars().unique().all()

    def add(self, proyecto: PromptProject) -> PromptProject:
        self.session.add(proyecto)
        self.session.flush()
        self.session.refresh(proyecto)
        return proyecto

    def delete(self, proyecto: PromptProject) -> None:
        self.session.delete(proyecto)
        self.session.flush()

    def next_position(self) -> int:
        stmt = select(func.coalesce(func.max(PromptProject.position), -1) + 1)
        return int(self.session.execute(stmt).scalar_one())


class PromptRepository(BaseRepository[Prompt]):
    model = Prompt

    def get(self, prompt_id: UUID) -> Prompt | None:
        return self.session.get(Prompt, prompt_id)

    def list(
        self, *, project_id: UUID | None = None, sin_proyecto: bool = False
    ) -> Sequence[Prompt]:
        stmt = select(Prompt).options(selectinload(Prompt.project))

        if sin_proyecto:
            stmt = stmt.where(Prompt.project_id.is_(None))
        elif project_id is not None:
            stmt = stmt.where(Prompt.project_id == project_id)

        # Del más nuevo al más viejo: al buscar un prompt, el último que
        # dictaste es casi siempre el que andas buscando. Es lo opuesto a la
        # bandeja de tickets, donde lo viejo sin resolver es lo urgente.
        stmt = stmt.order_by(Prompt.created_at.desc(), Prompt.id.desc())
        return self.session.execute(stmt).scalars().all()

    def add(self, prompt: Prompt) -> Prompt:
        self.session.add(prompt)
        self.session.flush()
        self.session.refresh(prompt)
        return prompt

    def delete(self, prompt: Prompt) -> None:
        self.session.delete(prompt)
        self.session.flush()
