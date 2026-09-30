"""Окружение тестов. Настраивается ДО импорта приложения.

Интеграционные тесты работают с отдельными БД (<имя>_test) и бакетом S3, боевые данные не затрагиваются.
Запуск: docker compose --profile test run --rm tests
"""

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _configure_environment() -> None:
    os.environ.setdefault("JWT_SECRET", "test-secret-test-secret-test-secret-123")
    os.environ.setdefault("S3_ENDPOINT", "http://minio:9000")
    os.environ.setdefault("S3_ACCESS_KEY", "minioadmin")
    os.environ.setdefault("S3_SECRET_KEY", "minioadmin")
    os.environ["S3_BUCKET"] = os.environ.get("TEST_S3_BUCKET", "correspondence-test")
    os.environ["MAX_UPLOAD_SIZE_MB"] = "1"
    os.environ["REG_NUMBER_TEMPLATE"] = "ВХ-{YYYY}-{NNNNNN}"
    os.environ["DEADLINE_WARNING_DAYS"] = "3"

    base = os.environ.get("DATABASE_URL",
                          "postgresql+asyncpg://correspondence:correspondence@localhost:5432/correspondence")
    head, _, name = base.rpartition("/")
    name = name.split("?")[0]
    if not name.endswith("_test"):
        os.environ["DATABASE_URL"] = f"{head}/{name}_test"


_configure_environment()


def pytest_collection_modifyitems(items):
    """Все асинхронные тесты — в одном event loop сессии (общий пул соединений приложения)."""
    import pytest
    import pytest_asyncio

    marker = pytest.mark.asyncio(loop_scope="session")
    for item in items:
        if pytest_asyncio.is_async_test(item):
            item.add_marker(marker, append=False)
