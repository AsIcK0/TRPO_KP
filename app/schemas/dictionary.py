import uuid
from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from app.schemas.common import ORMModel


class NamedBrief(ORMModel):
    id: uuid.UUID
    name: str


class _NameMixin(BaseModel):
    @field_validator("name", check_fields=False)
    @classmethod
    def _strip(cls, value: str | None) -> str | None:
        return value.strip() if isinstance(value, str) else value


class DepartmentCreate(_NameMixin):
    name: str = Field(min_length=2, max_length=255, examples=["Юридический отдел"])


class DepartmentUpdate(_NameMixin):
    name: str | None = Field(default=None, min_length=2, max_length=255)


class DepartmentOut(ORMModel):
    id: uuid.UUID
    name: str
    created_at: datetime
    updated_at: datetime


class PositionCreate(_NameMixin):
    name: str = Field(min_length=2, max_length=255, examples=["Начальник отдела"])


class PositionUpdate(_NameMixin):
    name: str | None = Field(default=None, min_length=2, max_length=255)


class PositionOut(NamedBrief):
    pass


class DocumentTypeCreate(_NameMixin):
    name: str = Field(min_length=2, max_length=255, examples=["Претензия"])
    is_active: bool = True


class DocumentTypeUpdate(_NameMixin):
    name: str | None = Field(default=None, min_length=2, max_length=255)
    is_active: bool | None = None


class DocumentTypeOut(NamedBrief):
    is_active: bool
