import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.recorder import log_action
from app.core.errors import DomainValidationError, NotFoundError
from app.models.entities import Correspondent, User
from app.repositories.correspondents import CorrespondentRepository
from app.schemas.common import make_page
from app.schemas.correspondent import CorrespondentCreate, CorrespondentUpdate


class CorrespondentService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.repo = CorrespondentRepository(db)

    async def create(self, actor: User, data: CorrespondentCreate) -> Correspondent:
        item = Correspondent(**data.model_dump())
        item.name = item.name.strip()
        self.repo.add(item)
        await self.db.commit()
        log_action(actor.id, "correspondent_created", correspondent_id=item.id, name=item.name)
        return await self.get(item.id)

    async def get(self, correspondent_id: uuid.UUID) -> Correspondent:
        item = await self.repo.get(correspondent_id)
        if item is None:
            raise NotFoundError("Корреспондент не найден")
        return item

    async def list_page(self, *, search: str | None, inn: str | None, page: int, page_size: int) -> dict:
        items, total = await self.repo.list_page(search=search, inn=inn, page=page, page_size=page_size)
        return make_page(items, total, page, page_size)

    async def update(self, actor: User, correspondent_id: uuid.UUID, data: CorrespondentUpdate) -> Correspondent:
        item = await self.get(correspondent_id)
        changes = data.model_dump(exclude_unset=True)
        if "name" in changes and not changes["name"]:
            raise DomainValidationError("Наименование не может быть пустым", field="name")
        for key, value in changes.items():
            setattr(item, key, value)
        await self.db.commit()
        log_action(actor.id, "correspondent_updated", correspondent_id=item.id, fields=sorted(changes))
        return await self.get(item.id)
