import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models.enums import DocumentStatus
from app.schemas.attachment import AttachmentOut
from app.schemas.common import ORMModel
from app.schemas.correspondent import CorrespondentBrief
from app.schemas.dictionary import NamedBrief
from app.schemas.history import HistoryOut
from app.schemas.resolution import ResolutionOut
from app.schemas.user import UserBrief
from app.services.deadlines import DeadlineState

DOCUMENT_SORT_FIELDS = frozenset({
    "registration_number", "received_date", "registration_date", "execution_deadline", "status", "created_at",
})


class DocumentCreate(BaseModel):
    received_date: date
    correspondent_id: uuid.UUID
    addressee: str | None = Field(default=None, max_length=255)
    summary: str = Field(min_length=3, max_length=5000)
    document_type_id: uuid.UUID
    page_count: int = Field(ge=1, le=100000)
    execution_deadline: date

    model_config = ConfigDict(json_schema_extra={"example": {
        "received_date": "2026-09-28", "correspondent_id": "00000000-0000-0000-0000-000000000003",
        "addressee": "Директору", "summary": "Запрос сведений о ходе исполнения договора",
        "document_type_id": "00000000-0000-0000-0000-000000000004", "page_count": 3,
        "execution_deadline": "2026-10-20"}})


class DocumentUpdate(BaseModel):
    received_date: date | None = None
    correspondent_id: uuid.UUID | None = None
    addressee: str | None = Field(default=None, max_length=255)
    summary: str | None = Field(default=None, min_length=3, max_length=5000)
    document_type_id: uuid.UUID | None = None
    page_count: int | None = Field(default=None, ge=1, le=100000)
    execution_deadline: date | None = None


class StatusChangeRequest(BaseModel):
    status: DocumentStatus
    comment: str | None = Field(default=None, max_length=2000)

    model_config = ConfigDict(json_schema_extra={"example": {
        "status": "на рассмотрении", "comment": "Передано руководителю"}})


class DocumentOut(ORMModel):
    id: uuid.UUID
    registration_number: str
    received_date: date
    registration_date: date
    correspondent: CorrespondentBrief
    addressee: str | None
    summary: str
    document_type: NamedBrief
    page_count: int
    execution_deadline: date
    status: DocumentStatus
    created_by: uuid.UUID
    created_at: datetime
    updated_at: datetime
    archived_at: datetime | None
    # вычисляемые сервисом поля контроля сроков
    deadline_state: DeadlineState = DeadlineState.OK
    is_overdue: bool = False
    days_left: int | None = None
    executors: list[UserBrief] = Field(default_factory=list)


class DocumentDetail(DocumentOut):
    resolutions: list[ResolutionOut] = Field(default_factory=list)
    attachments: list[AttachmentOut] = Field(default_factory=list)
    history: list[HistoryOut] = Field(default_factory=list)


class DocumentFilters(BaseModel):
    """Параметры поиска и фильтрации (GET /incoming). Даты — по дате регистрации."""

    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)
    sort: str = Field(default="-registration_date",
                      description="Поля через запятую, «-» перед именем — по убыванию. "
                                  f"Допустимые: {', '.join(sorted(DOCUMENT_SORT_FIELDS))}")
    registration_number: str | None = Field(default=None, max_length=64)
    date_from: date | None = None
    date_to: date | None = None
    correspondent_id: uuid.UUID | None = None
    executor_id: uuid.UUID | None = None
    status: DocumentStatus | None = None
    document_type_id: uuid.UUID | None = None
    search: str | None = Field(default=None, max_length=200,
                               description="Ключевые слова: содержание, адресат, номер, корреспондент")
    deadline_state: DeadlineState | None = Field(
        default=None, description="Только overdue (просрочены) или warning (срок близок)")

    @field_validator("sort")
    @classmethod
    def _check_sort(cls, value: str) -> str:
        for token in value.split(","):
            if token.strip().lstrip("-") not in DOCUMENT_SORT_FIELDS:
                raise ValueError(f"недопустимое поле сортировки: {token}")
        return value

    @field_validator("deadline_state")
    @classmethod
    def _check_state(cls, value: DeadlineState | None) -> DeadlineState | None:
        if value in (DeadlineState.OK, DeadlineState.CLOSED):
            raise ValueError("допустимы только overdue и warning")
        return value

    @model_validator(mode="after")
    def _check_dates(self) -> "DocumentFilters":
        if self.date_from and self.date_to and self.date_from > self.date_to:
            raise ValueError("date_from не может быть позже date_to")
        return self

    @property
    def has_search_filters(self) -> bool:
        return any(v is not None for v in (
            self.registration_number, self.date_from, self.date_to, self.correspondent_id,
            self.executor_id, self.status, self.document_type_id, self.search, self.deadline_state))
