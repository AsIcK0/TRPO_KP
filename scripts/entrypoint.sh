#!/bin/sh
set -e
echo "Применение миграций Alembic..."
alembic upgrade head
echo "Запуск uvicorn"
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --timeout-graceful-shutdown 20 --no-server-header
