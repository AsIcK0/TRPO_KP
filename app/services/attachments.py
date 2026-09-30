import logging
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.recorder import AuditRecorder, log_action
from app.core.config import Settings
from app.core.errors import ConflictError, ForbiddenError, NotFoundError
from app.models.entities import Attachment, User
from app.models.enums import AttachmentType, DocumentStatus, Role
from app.repositories.attachments import AttachmentRepository
from app.repositories.documents import DocumentRepository
from app.services.access import assert_can_view_document
from app.storage.s3 import S3Storage
from app.storage.validation import validate_upload

logger = logging.getLogger(__name__)

_EXECUTOR_UPLOAD_STATUSES = frozenset({DocumentStatus.IN_EXECUTION, DocumentStatus.EXECUTED})


class AttachmentService:
    def __init__(self, db: AsyncSession, settings: Settings, storage: S3Storage) -> None:
        self.db = db
        self.settings = settings
        self.storage = storage
        self.docs = DocumentRepository(db)
        self.attachments = AttachmentRepository(db)
        self.audit = AuditRecorder(db)

    async def upload(self, actor: User, document_id: uuid.UUID, *, filename: str | None,
                     content_type: str | None, data: bytes, attachment_type: AttachmentType | None) -> Attachment:
        doc = await self.docs.get(document_id)
        if doc is None:
            raise NotFoundError("Документ не найден")
        assert_can_view_document(actor, doc)
        if doc.status == DocumentStatus.ARCHIVED:
            raise ConflictError("К архивному документу нельзя прикреплять файлы", code="DOCUMENT_ARCHIVED")

        if actor.role == Role.EXECUTOR:
            if doc.status not in _EXECUTOR_UPLOAD_STATUSES:
                raise ConflictError("Отчетные материалы можно прикреплять к документам «на исполнении» "
                                    "и «исполнен»", code="INVALID_DOCUMENT_STATE")
            if attachment_type == AttachmentType.SOURCE_SCAN:
                raise ForbiddenError("Исполнитель не может загружать исходный скан документа", code="FORBIDDEN")
            attachment_type = attachment_type or AttachmentType.EXECUTION_REPORT
        else:
            attachment_type = attachment_type or AttachmentType.SOURCE_SCAN

        checked = validate_upload(filename, content_type, data, self.settings.max_upload_bytes)
        key = f"documents/{doc.id}/{uuid.uuid4()}{checked.extension}"  # имя пользователя в путь не попадает
        await self.storage.upload(key, data, checked.content_type)
        try:
            attachment = Attachment(document_id=doc.id, original_filename=checked.filename, storage_key=key,
                                    content_type=checked.content_type, size_bytes=checked.size,
                                    attachment_type=attachment_type, uploaded_by=actor.id)
            self.attachments.add(attachment)
            await self.db.flush()
            self.audit.document_event(document_id=doc.id, user_id=actor.id, action="file_attached",
                                      meta={"attachment_id": str(attachment.id), "filename": checked.filename,
                                            "type": attachment_type.value, "size_bytes": checked.size})
            await self.db.commit()
        except Exception:
            await self.db.rollback()
            try:
                await self.storage.delete(key)  # не оставляем «осиротевший» объект в хранилище
            except Exception:  # noqa: BLE001
                logger.warning("Не удалось удалить объект %s после ошибки записи в БД", key)
            raise
        log_action(actor.id, "file_attached", document_id=doc.id, attachment_id=attachment.id)
        return await self._fresh(attachment.id)

    async def _fresh(self, attachment_id: uuid.UUID) -> Attachment:
        attachment = await self.attachments.get(attachment_id)
        if attachment is None:
            raise NotFoundError("Файл не найден")
        return attachment

    async def get_for_download(self, actor: User, attachment_id: uuid.UUID) -> Attachment:
        """Метаданные файла после проверки прав: роль (DOCUMENT_VIEW) + контекст (исполнитель — только свои)."""
        attachment = await self._fresh(attachment_id)
        doc = await self.docs.get(attachment.document_id)
        if doc is None:
            raise NotFoundError("Документ не найден")
        assert_can_view_document(actor, doc)
        if not await self.storage.exists(attachment.storage_key):
            raise NotFoundError("Файл отсутствует в хранилище", code="FILE_MISSING")
        log_action(actor.id, "file_downloaded", document_id=doc.id, attachment_id=attachment.id)
        return attachment
