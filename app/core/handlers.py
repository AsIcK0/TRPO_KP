"""Единый формат ошибок API: {"detail": ..., "code": ..., "field": ... (опционально)}."""

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.errors import AppError

logger = logging.getLogger(__name__)

_HTTP_CODES = {
    400: "BAD_REQUEST",
    401: "UNAUTHORIZED",
    403: "FORBIDDEN",
    404: "NOT_FOUND",
    405: "METHOD_NOT_ALLOWED",
    409: "CONFLICT",
    413: "FILE_TOO_LARGE",
    422: "VALIDATION_ERROR",
}
_SKIP_LOC = {"body", "query", "path", "form", "header", "cookie"}


def error_body(detail: str, code: str, field: str | None = None) -> dict[str, str]:
    body = {"detail": detail, "code": code}
    if field:
        body["field"] = field
    return body


async def _app_error(_: Request, exc: AppError) -> JSONResponse:
    return JSONResponse(error_body(exc.detail, exc.code, exc.field), status_code=exc.status_code,
                        headers=exc.headers)


async def _validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
    messages: list[str] = []
    field: str | None = None
    for err in exc.errors():
        loc = [str(part) for part in err.get("loc", ()) if part not in _SKIP_LOC]
        name = ".".join(loc)
        messages.append(f"{name}: {err.get('msg')}" if name else str(err.get("msg")))
        if field is None and loc:
            field = loc[-1]
    return JSONResponse(error_body("; ".join(messages) or "Ошибка валидации", "VALIDATION_ERROR", field),
                        status_code=422)


async def _http_error(_: Request, exc: StarletteHTTPException) -> JSONResponse:
    code = _HTTP_CODES.get(exc.status_code, "HTTP_ERROR")
    return JSONResponse(error_body(str(exc.detail), code), status_code=exc.status_code,
                        headers=getattr(exc, "headers", None))


async def _integrity_error(_: Request, exc: IntegrityError) -> JSONResponse:
    logger.warning("Нарушение ограничения целостности БД: %s", exc.orig)
    return JSONResponse(error_body("Операция нарушает ограничения целостности данных", "CONFLICT"),
                        status_code=409)


async def _unhandled(_: Request, exc: Exception) -> JSONResponse:
    logger.exception("Необработанная ошибка: %s", exc)
    return JSONResponse(error_body("Внутренняя ошибка сервера", "INTERNAL_ERROR"), status_code=500)


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AppError, _app_error)
    app.add_exception_handler(RequestValidationError, _validation_error)
    app.add_exception_handler(StarletteHTTPException, _http_error)
    app.add_exception_handler(IntegrityError, _integrity_error)
    app.add_exception_handler(Exception, _unhandled)
