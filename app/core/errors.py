"""Прикладные исключения. Преобразуются в единый формат {detail, code, field} в app/core/handlers.py."""


class AppError(Exception):
    status_code = 500
    code = "INTERNAL_ERROR"

    def __init__(self, detail: str, *, code: str | None = None, field: str | None = None,
                 headers: dict[str, str] | None = None) -> None:
        super().__init__(detail)
        self.detail = detail
        if code:
            self.code = code
        self.field = field
        self.headers = headers


class UnauthorizedError(AppError):
    status_code = 401
    code = "UNAUTHORIZED"

    def __init__(self, detail: str = "Требуется аутентификация", **kwargs) -> None:
        kwargs.setdefault("headers", {"WWW-Authenticate": "Bearer"})
        super().__init__(detail, **kwargs)


class ForbiddenError(AppError):
    status_code = 403
    code = "FORBIDDEN"


class NotFoundError(AppError):
    status_code = 404
    code = "NOT_FOUND"


class ConflictError(AppError):
    status_code = 409
    code = "CONFLICT"


class DomainValidationError(AppError):
    status_code = 422
    code = "VALIDATION_ERROR"


class PayloadTooLargeError(AppError):
    status_code = 413
    code = "FILE_TOO_LARGE"
