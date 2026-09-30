import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.recorder import AuditRecorder, jsonable, log_action
from app.core.errors import ConflictError, DomainValidationError, NotFoundError
from app.models.entities import Resolution, User
from app.models.enums import DocumentStatus, ResolutionStatus, Role
from app.repositories.documents import DocumentRepository
from app.repositories.resolutions import ResolutionRepository
from app.repositories.users import UserRepository
from app.schemas.resolution import ResolutionCreate, ResolutionUpdate
from app.services.access import assert_can_view_document
from app.services.workflow import RESOLUTION_OPEN_STATUSES


class ResolutionService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.docs = DocumentRepository(db)
        self.resolutions = ResolutionRepository(db)
        self.users = UserRepository(db)
        self.audit = AuditRecorder(db)

    async def _require_executor(self, executor_id: uuid.UUID) -> User:
        user = await self.users.get(executor_id)
        if user is None:
            raise DomainValidationError("Исполнитель не найден", field="assigned_executor_id")
        if user.role != Role.EXECUTOR or not user.is_active:
            raise DomainValidationError("Назначить можно только активного пользователя с ролью «исполнитель»",
                                        field="assigned_executor_id")
        return user

    async def create(self, actor: User, document_id: uuid.UUID, data: ResolutionCreate) -> Resolution:
        if not await self.docs.lock(document_id):
            raise NotFoundError("Документ не найден")
        doc = await self.docs.get(document_id)
        if doc is None:
            raise NotFoundError("Документ не найден")
        if doc.status not in RESOLUTION_OPEN_STATUSES:
            raise ConflictError("Резолюцию можно создать только для документа «на рассмотрении» "
                                "или «на исполнении»", code="INVALID_DOCUMENT_STATE")
        executor = await self._require_executor(data.assigned_executor_id)
        if data.deadline < doc.registration_date:
            raise DomainValidationError("Срок резолюции не может быть раньше даты регистрации документа",
                                        field="deadline")

        resolution = Resolution(document_id=doc.id, text=data.text.strip(), author_id=actor.id,
                                assigned_executor_id=executor.id, deadline=data.deadline,
                                status=ResolutionStatus.IN_PROGRESS)
        self.resolutions.add(resolution)
        await self.db.flush()
        self.audit.document_event(document_id=doc.id, user_id=actor.id, action="resolution_created",
                                  meta={"resolution_id": str(resolution.id), "executor_id": str(executor.id),
                                        "deadline": data.deadline.isoformat()})
        if doc.status == DocumentStatus.UNDER_REVIEW:
            doc.status = DocumentStatus.IN_EXECUTION
            self.audit.document_event(document_id=doc.id, user_id=actor.id, action="status_changed",
                                      old_status=DocumentStatus.UNDER_REVIEW,
                                      new_status=DocumentStatus.IN_EXECUTION, comment="Создана резолюция")
        await self.db.commit()
        log_action(actor.id, "resolution_created", document_id=doc.id, resolution_id=resolution.id)
        return await self._fresh(resolution.id)

    async def _fresh(self, resolution_id: uuid.UUID) -> Resolution:
        resolution = await self.resolutions.get(resolution_id)
        if resolution is None:
            raise NotFoundError("Резолюция не найдена")
        return resolution

    async def list_for_document(self, actor: User, document_id: uuid.UUID) -> list[Resolution]:
        doc = await self.docs.get(document_id)
        if doc is None:
            raise NotFoundError("Документ не найден")
        assert_can_view_document(actor, doc)
        executor_scope = actor.id if actor.role == Role.EXECUTOR else None
        return await self.resolutions.list_by_document(document_id, executor_id=executor_scope)

    async def update(self, actor: User, resolution_id: uuid.UUID, data: ResolutionUpdate) -> Resolution:
        resolution = await self._fresh(resolution_id)
        if not await self.docs.lock(resolution.document_id):
            raise NotFoundError("Документ не найден")
        resolution = await self._fresh(resolution_id)
        doc = await self.docs.get(resolution.document_id)
        if doc is None:
            raise NotFoundError("Документ не найден")
        if resolution.status != ResolutionStatus.IN_PROGRESS or doc.status not in RESOLUTION_OPEN_STATUSES:
            raise ConflictError("Резолюцию нельзя изменить: процесс исполнения завершен",
                                code="RESOLUTION_LOCKED")

        changes = data.model_dump(exclude_unset=True)
        for name in ("text", "assigned_executor_id", "deadline"):
            if name in changes and changes[name] is None:
                raise DomainValidationError("Поле не может быть пустым", field=name)
        if "assigned_executor_id" in changes and changes["assigned_executor_id"] != resolution.assigned_executor_id:
            await self._require_executor(changes["assigned_executor_id"])
        if "deadline" in changes and changes["deadline"] < doc.registration_date:
            raise DomainValidationError("Срок резолюции не может быть раньше даты регистрации документа",
                                        field="deadline")

        diff: dict[str, dict] = {}
        for name, new_value in changes.items():
            old_value = getattr(resolution, name)
            if old_value != new_value:
                diff[name] = {"old": jsonable(old_value), "new": jsonable(new_value)}
                setattr(resolution, name, new_value)
        if diff:
            self.audit.document_event(document_id=doc.id, user_id=actor.id, action="resolution_updated",
                                      meta={"resolution_id": str(resolution.id), "changes": diff})
            await self.db.commit()
            log_action(actor.id, "resolution_updated", resolution_id=resolution.id, fields=sorted(diff))
        return await self._fresh(resolution_id)
