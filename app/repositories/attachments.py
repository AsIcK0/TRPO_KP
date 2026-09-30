import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.entities import Attachment


class AttachmentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, attachment_id: uuid.UUID) -> Attachment | None:
        stmt = select(Attachment).where(Attachment.id == attachment_id).execution_options(populate_existing=True)
        return (await self.session.execute(stmt)).scalar_one_or_none()

    def add(self, attachment: Attachment) -> None:
        self.session.add(attachment)

    async def storage_keys(self, document_id: uuid.UUID) -> list[str]:
        stmt = select(Attachment.storage_key).where(Attachment.document_id == document_id)
        return list((await self.session.execute(stmt)).scalars().all())
