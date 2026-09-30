import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.models.enums import Role
from app.schemas.common import ORMModel
from app.schemas.dictionary import NamedBrief


class UserBrief(ORMModel):
    id: uuid.UUID
    full_name: str


class UserCreate(BaseModel):
    full_name: str = Field(min_length=2, max_length=255)
    login: str = Field(min_length=3, max_length=64, pattern=r"^[A-Za-z0-9_.-]+$")
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    role: Role
    department_id: uuid.UUID
    position_id: uuid.UUID | None = None

    model_config = ConfigDict(json_schema_extra={"example": {
        "full_name": "Сидорова Мария Петровна", "login": "sidorova", "email": "sidorova@example.org",
        "password": "S3cretPass!", "role": "executor",
        "department_id": "00000000-0000-0000-0000-000000000001", "position_id": None}})

    @field_validator("email")
    @classmethod
    def _lower(cls, value: str) -> str:
        return value.lower()


class UserUpdate(BaseModel):
    full_name: str | None = Field(default=None, min_length=2, max_length=255)
    email: EmailStr | None = None
    role: Role | None = None
    department_id: uuid.UUID | None = None
    position_id: uuid.UUID | None = None

    @field_validator("email")
    @classmethod
    def _lower(cls, value: str | None) -> str | None:
        return value.lower() if value else value


class UserOut(ORMModel):
    """password_hash в схему намеренно не входит и никогда не возвращается."""

    id: uuid.UUID
    full_name: str
    login: str
    email: str
    role: Role
    department: NamedBrief
    position: NamedBrief | None = None
    is_active: bool
    created_at: datetime
    updated_at: datetime


class ExecutorBrief(ORMModel):
    id: uuid.UUID
    full_name: str
    department: NamedBrief
