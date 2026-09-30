import math

from pydantic import BaseModel, ConfigDict

class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class ErrorResponse(BaseModel):
    detail: str
    code: str
    field: str | None = None

    model_config = ConfigDict(json_schema_extra={"example": {
        "detail": "Регистрационный номер уже существует",
        "code": "REGISTRATION_NUMBER_CONFLICT", "field": "registration_number"}})


class Page[T](BaseModel):
    items: list[T]
    total: int
    page: int
    page_size: int
    pages: int


def make_page(items: list, total: int, page: int, page_size: int) -> dict:
    return {"items": items, "total": total, "page": page, "page_size": page_size,
            "pages": math.ceil(total / page_size) if page_size else 0}
