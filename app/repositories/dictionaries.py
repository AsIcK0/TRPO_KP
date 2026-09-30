import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.entities import Department, DocumentType, Position

class NamedRepository[M: (Department, Position, DocumentType)]:
    model: type[M]

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, item_id: uuid.UUID) -> M | None:
        stmt = select(self.model).where(self.model.id == item_id).execution_options(populate_existing=True)
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def get_by_name(self, name: str) -> M | None:
        stmt = select(self.model).where(self.model.name == name)
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def list_all(self) -> list[M]:
        return list((await self.session.execute(select(self.model).order_by(self.model.name))).scalars().all())

    def add(self, item: M) -> None:
        self.session.add(item)


class DepartmentRepository(NamedRepository[Department]):
    model = Department


class PositionRepository(NamedRepository[Position]):
    model = Position


class DocumentTypeRepository(NamedRepository[DocumentType]):
    model = DocumentType
