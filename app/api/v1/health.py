import asyncio
import logging

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.db.session import get_sessionmaker
from app.schemas.health import HealthResponse
from app.storage.s3 import get_storage

logger = logging.getLogger(__name__)
router = APIRouter(tags=["health"])


async def _check_db() -> str:
    try:
        async with get_sessionmaker()() as session:
            await asyncio.wait_for(session.execute(text("SELECT 1")), timeout=3)
        return "ok"
    except Exception as exc:  # noqa: BLE001
        logger.warning("Health: БД недоступна: %s", type(exc).__name__)
        return "unavailable"


async def _check_storage() -> str:
    try:
        await asyncio.wait_for(get_storage().check(), timeout=3)
        return "ok"
    except Exception as exc:  # noqa: BLE001
        logger.warning("Health: S3 недоступно: %s", type(exc).__name__)
        return "unavailable"


@router.get("/health", response_model=HealthResponse, summary="Проверка БД, S3 и доступности сервиса",
            responses={503: {"model": HealthResponse, "description": "Одна из зависимостей недоступна"}})
async def health():
    database, storage = await asyncio.gather(_check_db(), _check_storage())
    ok = database == "ok" and storage == "ok"
    body = HealthResponse(status="ok" if ok else "degraded", database=database, storage=storage)
    return JSONResponse(body.model_dump(), status_code=200 if ok else 503)
