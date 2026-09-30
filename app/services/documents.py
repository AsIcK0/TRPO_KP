"""Бизнес-логика входящих документов: регистрация, редактирование, статусы, удаление, поиск."""

import logging
import uuid
from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.recorder import AuditRecorder, jsonable, log_action
from app.core.config import Settings
from app.core.errors import ConflictError, DomainValidationError, ForbiddenError, NotFoundError
from app.models.entities import IncomingDocument, User, utcnow
from app.models.enums import DocumentStatus, ResolutionStatus, Role
from app.repositories.attachments import AttachmentRepository
from app.repositories.correspondents import CorrespondentRepository
from app.repositories.dictionaries import DocumentTypeRepository
from app.repositories.documents import DocumentRepository
from app.repositories.history import HistoryRepository
from app.repositories.resolutions import ResolutionRepository
from app.schemas.common import make_page
from app.schemas.document import (
    DocumentCreate,
    DocumentDetail,
    DocumentFilters,
    DocumentOut,
    DocumentUpdate,
    StatusChangeRequest,
)
from app.schemas.history import HistoryOut
from app.schemas.user import UserBrief
from app.security.permissions import Permission, has_permission
from app.services.access import assert_can_view_document
from app.services.deadlines import DeadlineState, business_today, days_left, deadline_state
from app.services.reg_number import counter_key, format_registration_number
from app.services.workflow import transition_roles
from app.storage.s3 import S3Storage

logger = logging.getLogger(__name__)

_REQUIRED_ON_UPDATE = ("received_date", "correspondent_id", "summary", "document_type_id", "page_count",
                       "execution_deadline")


class DocumentService:
    def __init__(self, db: AsyncSession, settings: Settings, storage: S3Storage) -> None:
        self.db = db
        self.settings = settings
        self.storage = storage
        self.docs = DocumentRepository(db)
        self.correspondents = CorrespondentRepository(db)
        self.types = DocumentTypeRepository(db)
        self.resolutions = ResolutionRepository(db)
        self.attachments = AttachmentRepository(db)
        self.history_repo = HistoryRepository(db)
        self.audit = AuditRecorder(db)

    # --- преобразование ORM -> схемы ----------------------------------------------------------
    def _decorate(self, out: DocumentOut, doc: IncomingDocument, actor: User | None, today: date) -> None:
        state = deadline_state(doc.execution_deadline, doc.status, today, self.settings.deadline_warning_days)
        out.deadline_state = state
        out.is_overdue = state == DeadlineState.OVERDUE
        out.days_left = None if state == DeadlineState.CLOSED else days_left(doc.execution_deadline, today)
        executors = {}
        for resolution in doc.resolutions:
            executors.setdefault(resolution.assigned_executor_id, resolution.assigned_executor)
        if actor is not None and actor.role == Role.EXECUTOR:
            executors = {k: v for k, v in executors.items() if k == actor.id}
        out.executors = [UserBrief.model_validate(u) for u in executors.values()]

    def to_out(self, doc: IncomingDocument, actor: User | None, today: date) -> DocumentOut:
        out = DocumentOut.model_validate(doc)
        self._decorate(out, doc, actor, today)
        return out

    def to_detail(self, doc: IncomingDocument, actor: User | None, today: date) -> DocumentDetail:
        detail = DocumentDetail.model_validate(doc)
        self._decorate(detail, doc, actor, today)
        if actor is not None and actor.role == Role.EXECUTOR:
            detail.resolutions = [r for r in detail.resolutions if r.assigned_executor_id == actor.id]
        return detail

    async def _detail(self, actor: User, document_id: uuid.UUID) -> DocumentDetail:
        doc = await self.docs.get(document_id, detail=True)
        if doc is None:
            raise NotFoundError("Документ не найден")
        return self.to_detail(doc, actor, business_today())

    # --- чтение ---------------------------------------------------------------------------------
    async def get_detail(self, actor: User, document_id: uuid.UUID) -> DocumentDetail:
        doc = await self.docs.get(document_id, detail=True)
        if doc is None:
            raise NotFoundError("Документ не найден")
        assert_can_view_document(actor, doc)
        return self.to_detail(doc, actor, business_today())

    async def get_by_number(self, actor: User, registration_number: str) -> DocumentDetail:
        doc = await self.docs.get_by_number(registration_number, detail=True)
        if doc is None:
            raise NotFoundError("Документ с таким регистрационным номером не найден")
        assert_can_view_document(actor, doc)
        return self.to_detail(doc, actor, business_today())

    async def search(self, actor: User, filters: DocumentFilters) -> dict:
        # матрица прав: без DOCUMENT_SEARCH доступен только список (пагинация, сортировка) без фильтров
        if filters.has_search_filters and not has_permission(actor.role, Permission.DOCUMENT_SEARCH):
            raise ForbiddenError("Поиск и фильтрация недоступны для вашей роли", code="FORBIDDEN")
        scope = actor.id if actor.role == Role.EXECUTOR else None  # исполнитель — только свои поручения
        today = business_today()
        docs, total = await self.docs.search(filters, executor_scope=scope, today=today,
                                             warning_days=self.settings.deadline_warning_days)
        items = [self.to_out(d, actor, today) for d in docs]
        return make_page(items, total, filters.page, filters.page_size)

    async def history(self, actor: User, document_id: uuid.UUID) -> list[HistoryOut]:
        doc = await self.docs.get(document_id)
        if doc is None:
            raise NotFoundError("Документ не найден")
        assert_can_view_document(actor, doc)
        entries = await self.history_repo.list_by_document(document_id)
        return [HistoryOut.model_validate(e) for e in entries]

    # --- проверки -------------------------------------------------------------------------------
    async def _require_correspondent(self, correspondent_id: uuid.UUID) -> None:
        if await self.correspondents.get(correspondent_id) is None:
            raise DomainValidationError("Корреспондент не найден", field="correspondent_id")

    async def _require_document_type(self, type_id: uuid.UUID) -> None:
        dtype = await self.types.get(type_id)
        if dtype is None:
            raise DomainValidationError("Тип документа не найден", field="document_type_id")
        if not dtype.is_active:
            raise DomainValidationError("Тип документа выведен из использования", field="document_type_id")

    @staticmethod
    def _check_dates(received: date, deadline: date, registration_date: date) -> None:
        if received > registration_date:
            raise DomainValidationError("Дата поступления не может быть позже даты регистрации",
                                        field="received_date")
        if deadline < registration_date:
            raise DomainValidationError("Срок исполнения не может быть раньше даты регистрации",
                                        field="execution_deadline")

    # --- регистрация ----------------------------------------------------------------------------
    async def register(self, actor: User, data: DocumentCreate) -> DocumentDetail:
        await self._require_correspondent(data.correspondent_id)
        await self._require_document_type(data.document_type_id)
        today = business_today()
        self._check_dates(data.received_date, data.execution_deadline, today)

        template = self.settings.reg_number_template
        sequence = await self.docs.next_sequence(counter_key(template, today.year))
        number = format_registration_number(template, today.year, sequence)

        doc = IncomingDocument(
            registration_number=number, received_date=data.received_date, registration_date=today,
            correspondent_id=data.correspondent_id, addressee=data.addressee, summary=data.summary.strip(),
            document_type_id=data.document_type_id, page_count=data.page_count,
            execution_deadline=data.execution_deadline, status=DocumentStatus.REGISTERED, created_by=actor.id,
        )
        self.docs.add(doc)
        await self.db.flush()
        self.audit.document_event(document_id=doc.id, user_id=actor.id, action="document_registered",
                                  new_status=DocumentStatus.REGISTERED,
                                  meta={"registration_number": number})
        await self.db.commit()
        log_action(actor.id, "document_registered", document_id=doc.id, registration_number=number)
        return await self._detail(actor, doc.id)

    # --- редактирование -------------------------------------------------------------------------
    async def update(self, actor: User, document_id: uuid.UUID, data: DocumentUpdate) -> DocumentDetail:
        if not await self.docs.lock(document_id):
            raise NotFoundError("Документ не найден")
        doc = await self.docs.get(document_id)
        if doc is None:
            raise NotFoundError("Документ не найден")
        if doc.status == DocumentStatus.ARCHIVED:
            raise ConflictError("Архивный документ не может быть изменен", code="DOCUMENT_ARCHIVED")

        changes = data.model_dump(exclude_unset=True)
        for name in _REQUIRED_ON_UPDATE:
            if name in changes and changes[name] is None:
                raise DomainValidationError("Поле не может быть пустым", field=name)
        if "correspondent_id" in changes and changes["correspondent_id"] != doc.correspondent_id:
            await self._require_correspondent(changes["correspondent_id"])
        if "document_type_id" in changes and changes["document_type_id"] != doc.document_type_id:
            await self._require_document_type(changes["document_type_id"])
        self._check_dates(changes.get("received_date", doc.received_date),
                          changes.get("execution_deadline", doc.execution_deadline), doc.registration_date)

        diff: dict[str, dict] = {}
        for name, new_value in changes.items():
            old_value = getattr(doc, name)
            if old_value != new_value:
                diff[name] = {"old": jsonable(old_value), "new": jsonable(new_value)}
                setattr(doc, name, new_value)
        if diff:
            self.audit.document_event(document_id=doc.id, user_id=actor.id, action="document_updated",
                                      meta={"changes": diff})
            await self.db.commit()
            log_action(actor.id, "document_updated", document_id=doc.id, fields=sorted(diff))
        return await self._detail(actor, doc.id)

    # --- смена статуса --------------------------------------------------------------------------
    async def change_status(self, actor: User, document_id: uuid.UUID, data: StatusChangeRequest
                            ) -> DocumentDetail:
        if not await self.docs.lock(document_id):
            raise NotFoundError("Документ не найден")
        doc = await self.docs.get(document_id)
        if doc is None:
            raise NotFoundError("Документ не найден")
        assert_can_view_document(actor, doc)

        old, new = doc.status, data.status
        allowed_roles = transition_roles(old, new)
        if allowed_roles is None:
            raise ConflictError(f"Переход «{old.value}» → «{new.value}» недопустим",
                                code="INVALID_STATUS_TRANSITION", field="status")
        if actor.role not in allowed_roles:
            raise ForbiddenError("Ваша роль не может выполнить этот переход статуса", code="FORBIDDEN")

        if actor.role == Role.EXECUTOR:
            await self._complete_as_executor(actor, doc, data.comment)
        else:
            doc.status = new
            doc.archived_at = utcnow() if new == DocumentStatus.ARCHIVED else None
            self.audit.document_event(
                document_id=doc.id, user_id=actor.id, old_status=old, new_status=new, comment=data.comment,
                action="document_annulled" if new == DocumentStatus.REGISTERED else "status_changed")
        await self.db.commit()
        log_action(actor.id, "status_change", document_id=doc.id, old=old, requested=new)
        return await self._detail(actor, doc.id)

    async def _complete_as_executor(self, actor: User, doc: IncomingDocument, comment: str | None) -> None:
        """Исполнитель закрывает свои резолюции; документ становится «исполнен», когда закрыты все."""
        mine = await self.resolutions.list_by_document(doc.id, executor_id=actor.id)
        if not mine:
            raise ForbiddenError("Документ не назначен вам на исполнение", code="FORBIDDEN")
        active = [r for r in mine if r.status == ResolutionStatus.IN_PROGRESS]
        if not active:
            raise ConflictError("Ваши резолюции по этому документу уже исполнены",
                                code="RESOLUTION_ALREADY_EXECUTED")
        now = utcnow()
        for resolution in active:
            resolution.status = ResolutionStatus.EXECUTED
            resolution.executed_at = now
        await self.db.flush()
        self.audit.document_event(document_id=doc.id, user_id=actor.id, action="resolution_executed",
                                  comment=comment, meta={"resolution_ids": [str(r.id) for r in active]})
        if await self.resolutions.count_active(doc.id) == 0:
            doc.status = DocumentStatus.EXECUTED
            self.audit.document_event(document_id=doc.id, user_id=actor.id, action="status_changed",
                                      old_status=DocumentStatus.IN_EXECUTION, new_status=DocumentStatus.EXECUTED,
                                      comment=comment)

    # --- удаление -------------------------------------------------------------------------------
    async def delete(self, actor: User, document_id: uuid.UUID) -> None:
        doc = await self.docs.get(document_id)
        if doc is None:
            raise NotFoundError("Документ не найден")
        number, keys = doc.registration_number, await self.attachments.storage_keys(document_id)
        await self.docs.delete(document_id)
        await self.db.commit()
        for key in keys:  # после успешного commit; сбой удаления файла не откатывает удаление карточки
            try:
                await self.storage.delete(key)
            except Exception:  # noqa: BLE001
                logger.warning("Не удалось удалить объект хранилища %s", key)
        log_action(actor.id, "document_deleted", document_id=document_id, registration_number=number,
                   files=len(keys))
