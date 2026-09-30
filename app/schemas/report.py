import uuid
from datetime import date
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, model_validator

from app.models.enums import DocumentStatus


class ReportType(StrEnum):
    DOCUMENTS = "documents"    # по документам
    EXECUTORS = "executors"    # по исполнителям
    DEADLINES = "deadlines"    # по срокам исполнения


class ReportRequest(BaseModel):
    report_type: ReportType
    period_from: date
    period_to: date
    correspondent_id: uuid.UUID | None = None
    executor_id: uuid.UUID | None = None
    status: DocumentStatus | None = None
    document_type_id: uuid.UUID | None = None

    model_config = ConfigDict(json_schema_extra={"example": {
        "report_type": "executors", "period_from": "2026-09-01", "period_to": "2026-09-30"}})

    @model_validator(mode="after")
    def _check_period(self) -> "ReportRequest":
        if self.period_from > self.period_to:
            raise ValueError("period_from не может быть позже period_to")
        return self


class RegistrationLogQuery(BaseModel):
    date_from: date | None = None
    date_to: date | None = None
    correspondent_id: uuid.UUID | None = None
    status: DocumentStatus | None = None
    document_type_id: uuid.UUID | None = None

    @model_validator(mode="after")
    def _check_period(self) -> "RegistrationLogQuery":
        if self.date_from and self.date_to and self.date_from > self.date_to:
            raise ValueError("date_from не может быть позже date_to")
        return self
