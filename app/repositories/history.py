import uuid
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.entities import DocumentHistory
from app.models.enums import DocumentStatus


class HistoryRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_by_document(self, document_id: uuid.UUID) -> list[DocumentHistory]:
        stmt = (select(DocumentHistory).where(DocumentHistory.document_id == document_id)
                .order_by(DocumentHistory.created_at, DocumentHistory.seq)
                .execution_options(populate_existing=True))
        return list((await self.session.execute(stmt)).scalars().all())

    async def executed_moments(self, document_ids: list[uuid.UUID]) -> dict[uuid.UUID, datetime]:
        """Момент последнего перехода документа в статус «исполнен» (по истории)."""
        if not document_ids:
            return {}
        stmt = (select(DocumentHistory.document_id, func.max(DocumentHistory.created_at))
                .where(DocumentHistory.document_id.in_(document_ids),
                       DocumentHistory.new_status == DocumentStatus.EXECUTED)
                .group_by(DocumentHistory.document_id))
        rows = (await self.session.execute(stmt)).all()
        return dict(rows)
