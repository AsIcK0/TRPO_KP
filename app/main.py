import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.v1 import health
from app.api.v1.router import api_router
from app.core.config import get_settings
from app.core.handlers import register_exception_handlers
from app.core.logging import configure_logging
from app.db.session import get_engine
from app.storage.s3 import get_storage

logger = logging.getLogger(__name__)

TAGS = [
    {"name": "auth", "description": "Вход и текущий пользователь"},
    {"name": "users", "description": "Управление пользователями (admin)"},
    {"name": "departments", "description": "Подразделения (admin)"},
    {"name": "positions", "description": "Должности (admin)"},
    {"name": "document-types", "description": "Типы документов"},
    {"name": "correspondents", "description": "Корреспонденты (делопроизводитель)"},
    {"name": "incoming", "description": "Входящие документы, статусы, история, резолюции, файлы"},
    {"name": "resolutions", "description": "Редактирование резолюций (руководитель)"},
    {"name": "files", "description": "Скачивание вложений"},
    {"name": "reports", "description": "PDF-отчеты"},
    {"name": "exports", "description": "CSV-выгрузка журнала регистрации"},
    {"name": "health", "description": "Состояние сервиса"},
]


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings = get_settings()
    configure_logging(settings.log_level)
    try:
        await get_storage().ensure_bucket()
    except Exception as exc:  # noqa: BLE001 — сервис стартует; недоступность S3 видна в /health
        logger.error("Не удалось подготовить S3-бакет: %s", exc)
    logger.info("Сервис запущен")
    yield
    await get_engine().dispose()
    logger.info("Сервис остановлен")


def create_app() -> FastAPI:
    app = FastAPI(
        title="Информационная система учета входящей корреспонденции",
        description="REST API: регистрация, поиск, резолюции, исполнение, контроль сроков, файлы, "
                    "история, отчеты (PDF) и выгрузки (CSV). Авторизация: JWT (кнопка Authorize → токен "
                    "из `POST /api/v1/auth/login`).",
        version="1.0.0", openapi_tags=TAGS, docs_url="/docs", redoc_url=None, lifespan=lifespan,
    )
    register_exception_handlers(app)
    app.include_router(api_router, prefix="/api/v1")
    app.include_router(health.router, include_in_schema=False)  # /health — для Docker и балансировщиков
    return app


app = create_app()
