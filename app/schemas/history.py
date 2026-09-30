import uuid
from datetime import datetime
from typing import Any

from pydantic import AliasChoices, Field

from app.models.enums import DocumentStatus
from app.schemas.common import ORMModel
from app.schemas.user import UserBrief


class HistoryOut(ORMModel):
    id: uuid.UUID
    document_id: uuid.UUID
    user_id: uuid.UUID
    user: UserBrief
    action: str
    old_status: DocumentStatus | None = None
    new_status: DocumentStatus | None = None
    comment: str | None = None
    metadata: dict[str, Any] | None = Field(default=None, validation_alias=AliasChoices("meta", "metadata"),
                                          serialization_alias="metadata")
    created_at: datetime
