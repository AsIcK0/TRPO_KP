import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.schemas.common import ORMModel

_INN_PATTERN = r"^(\d{10}|\d{12})$"


class CorrespondentBase(BaseModel):
    name: str = Field(min_length=2, max_length=500)
    inn: str | None = Field(default=None, pattern=_INN_PATTERN, description="ИНН: 10 или 12 цифр")
    address: str | None = Field(default=None, max_length=2000)
    phone: str | None = Field(default=None, max_length=64)
    email: EmailStr | None = None
    signer_full_name: str | None = Field(default=None, max_length=255)

    @field_validator("email")
    @classmethod
    def _lower(cls, value: str | None) -> str | None:
        return value.lower() if value else value


class CorrespondentCreate(CorrespondentBase):
    model_config = ConfigDict(json_schema_extra={"example": {
        "name": "ООО «Северный ветер»", "inn": "7701234567", "address": "г. Москва, ул. Примерная, 1",
        "phone": "+7 495 000-00-00", "email": "info@example.org", "signer_full_name": "Кузнецов И. И."}})


class CorrespondentUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=500)
    inn: str | None = Field(default=None, pattern=_INN_PATTERN)
    address: str | None = Field(default=None, max_length=2000)
    phone: str | None = Field(default=None, max_length=64)
    email: EmailStr | None = None
    signer_full_name: str | None = Field(default=None, max_length=255)


class CorrespondentOut(ORMModel):
    id: uuid.UUID
    name: str
    inn: str | None
    address: str | None
    phone: str | None
    email: str | None
    signer_full_name: str | None
    created_at: datetime
    updated_at: datetime


class CorrespondentBrief(ORMModel):
    id: uuid.UUID
    name: str
    inn: str | None = None
