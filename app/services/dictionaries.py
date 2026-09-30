import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.recorder import log_action
from app.core.errors import ConflictError, NotFoundError
from app.models.entities import Department, DocumentType, Position, User
from app.repositories.dictionaries import (
    DepartmentRepository,
    DocumentTypeRepository,
    NamedRepository,
    PositionRepository,
)


class DictionaryService:
    """Справочники: подразделения, должности, типы документов."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.departments = DepartmentRepository(db)
        self.positions = PositionRepository(db)
        self.types = DocumentTypeRepository(db)

    async def _create(self, actor: User, repo: NamedRepository, model: type, label: str, values: dict[str, Any]):
        if await repo.get_by_name(values["name"]):
            raise ConflictError(f"{label} с таким названием уже существует", code="NAME_CONFLICT", field="name")
        item = model(**values)
        repo.add(item)
        await self.db.commit()
        log_action(actor.id, "dictionary_created", dictionary=model.__tablename__, item_id=item.id)
        return await repo.get(item.id)

    async def _update(self, actor: User, repo: NamedRepository, item_id: uuid.UUID, label: str,
                      changes: dict[str, Any]):
        item = await repo.get(item_id)
        if item is None:
            raise NotFoundError(f"{label}: запись не найдена")
        changes = {k: v for k, v in changes.items() if v is not None}
        if "name" in changes:
            other = await repo.get_by_name(changes["name"])
            if other is not None and other.id != item.id:
                raise ConflictError(f"{label} с таким названием уже существует", code="NAME_CONFLICT",
                                    field="name")
        for key, value in changes.items():
            setattr(item, key, value)
        await self.db.commit()
        log_action(actor.id, "dictionary_updated", item_id=item.id, fields=sorted(changes))
        return await repo.get(item.id)

    # подразделения
    async def list_departments(self):
        return await self.departments.list_all()

    async def create_department(self, actor: User, name: str):
        return await self._create(actor, self.departments, Department, "Подразделение", {"name": name})

    async def update_department(self, actor: User, item_id: uuid.UUID, changes: dict[str, Any]):
        return await self._update(actor, self.departments, item_id, "Подразделение", changes)

    # должности
    async def list_positions(self):
        return await self.positions.list_all()

    async def create_position(self, actor: User, name: str):
        return await self._create(actor, self.positions, Position, "Должность", {"name": name})

    async def update_position(self, actor: User, item_id: uuid.UUID, changes: dict[str, Any]):
        return await self._update(actor, self.positions, item_id, "Должность", changes)

    # типы документов
    async def list_types(self):
        return await self.types.list_all()

    async def create_type(self, actor: User, name: str, is_active: bool):
        return await self._create(actor, self.types, DocumentType, "Тип документа",
                                  {"name": name, "is_active": is_active})

    async def update_type(self, actor: User, item_id: uuid.UUID, changes: dict[str, Any]):
        return await self._update(actor, self.types, item_id, "Тип документа", changes)
