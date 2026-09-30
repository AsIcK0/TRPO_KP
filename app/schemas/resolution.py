import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import ResolutionStatus
from app.schemas.common import ORMModel
from app.schemas.user import UserBrief


class ResolutionCreate(BaseModel):
    text: str = Field(min_length=3, max_length=5000)
    assigned_executor_id: uuid.UUID
    deadline: date

    model_config = ConfigDict(json_schema_extra={"example": {
        "text": "Подготовить ответ и согласовать с юристом",
        "assigned_executor_id": "00000000-0000-0000-0000-000000000002", "deadline": "2026-10-15"}})


class ResolutionUpdate(BaseModel):
    text: str | None = Field(default=None, min_length=3, max_length=5000)
    assigned_executor_id: uuid.UUID | None = None
    deadline: date | None = None


class ResolutionOut(ORMModel):
    id: uuid.UUID
    document_id: uuid.UUID
    text: str
    author_id: uuid.UUID
    author: UserBrief
    assigned_executor_id: uuid.UUID
    assigned_executor: UserBrief
    deadline: date
    status: ResolutionStatus
    executed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
