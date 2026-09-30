import uuid

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.entities import Correspondent
from app.repositories.common import LIKE_ESCAPE, like_pattern


class CorrespondentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, correspondent_id: uuid.UUID) -> Correspondent | None:
        stmt = select(Correspondent).where(Correspondent.id == correspondent_id).execution_options(
            populate_existing=True)
        return (await self.session.execute(stmt)).scalar_one_or_none()

    def add(self, correspondent: Correspondent) -> None:
        self.session.add(correspondent)

    async def list_page(self, *, search: str | None, inn: str | None, page: int, page_size: int
                   ) -> tuple[list[Correspondent], int]:
        clauses = []
        if search:
            pattern = like_pattern(search)
            clauses.append(or_(Correspondent.name.ilike(pattern, escape=LIKE_ESCAPE),
                               Correspondent.signer_full_name.ilike(pattern, escape=LIKE_ESCAPE)))
        if inn:
            clauses.append(Correspondent.inn == inn)
        total = (await self.session.execute(select(func.count(Correspondent.id)).where(*clauses))).scalar_one()
        stmt = (select(Correspondent).where(*clauses).order_by(Correspondent.name, Correspondent.id)
                .limit(page_size).offset((page - 1) * page_size))
        return list((await self.session.execute(stmt)).scalars().all()), total
