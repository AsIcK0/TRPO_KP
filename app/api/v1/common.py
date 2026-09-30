from app.schemas.common import ErrorResponse

ERROR_RESPONSES = {
    401: {"model": ErrorResponse, "description": "Не аутентифицирован: токен отсутствует, неверен или просрочен"},
    403: {"model": ErrorResponse, "description": "Недостаточно прав (роль или контекст доступа)"},
    404: {"model": ErrorResponse, "description": "Объект не найден"},
    409: {"model": ErrorResponse, "description": "Конфликт: недопустимый переход статуса, дубликат, блокировка"},
    422: {"model": ErrorResponse, "description": "Ошибка валидации входных данных"},
}
