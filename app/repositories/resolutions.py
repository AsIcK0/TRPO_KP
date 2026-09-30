import uuid
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.entities import IncomingDocument, Resolution
from app.models.enums import DocumentStatus, ResolutionStatus


class ResolutionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, resolution_id: uuid.UUID) -> Resolution | None:
        stmt = select(Resolution).where(Resolution.id == resolution_id).execution_options(populate_existing=True)
        return (await self.session.execute(stmt)).scalar_one_or_none()

    def add(self, resolution: Resolution) -> None:
        self.session.add(resolution)

    async def list_by_document(self, document_id: uuid.UUID, *, executor_id: uuid.UUID | None = None
                               ) -> list[Resolution]:
        stmt = (select(Resolution).where(Resolution.document_id == document_id)
                .order_by(Resolution.created_at, Resolution.id).execution_options(populate_existing=True))
        if executor_id is not None:
            stmt = stmt.where(Resolution.assigned_executor_id == executor_id)
        return list((await self.session.execute(stmt)).scalars().all())

    async def count_active(self, document_id: uuid.UUID) -> int:
        stmt = select(func.count(Resolution.id)).where(Resolution.document_id == document_id,
                                                       Resolution.status == ResolutionStatus.IN_PROGRESS)
        return (await self.session.execute(stmt)).scalar_one()

    async def for_report(self, *, date_from: date, date_to: date, executor_id: uuid.UUID | None,
                         correspondent_id: uuid.UUID | None, status: DocumentStatus | None,
                         document_type_id: uuid.UUID | None) -> list[Resolution]:
        """Резолюции документов, зарегистрированных в периоде (для отчета по исполнителям)."""
        stmt = (select(Resolution).join(IncomingDocument, IncomingDocument.id == Resolution.document_id)
                .where(IncomingDocument.registration_date >= date_from,
                       IncomingDocument.registration_date <= date_to)
                .order_by(Resolution.created_at, Resolution.id))
        if executor_id:
            stmt = stmt.where(Resolution.assigned_executor_id == executor_id)
        if correspondent_id:
            stmt = stmt.where(IncomingDocument.correspondent_id == correspondent_id)
        if status:
            stmt = stmt.where(IncomingDocument.status == status)
        if document_type_id:
            stmt = stmt.where(IncomingDocument.document_type_id == document_type_id)
        return list((await self.session.execute(stmt)).scalars().all())
