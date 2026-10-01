# syntax=docker/dockerfile:1

# --- стадия сборки: wheel-пакеты (если для Python 3.14 нет готовой сборки — компилируются здесь) ---
FROM python:3.14-slim AS builder
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /build
COPY requirements.txt requirements-dev.txt ./
RUN pip wheel --wheel-dir /wheels -r requirements-dev.txt


# --- рабочий образ ---
FROM python:3.14-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# fonts-dejavu-core — шрифт с кириллицей для PDF-отчетов
RUN apt-get update \
    && apt-get install -y --no-install-recommends fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN --mount=type=bind,from=builder,source=/wheels,target=/wheels \
    pip install --no-index --find-links=/wheels -r requirements.txt

COPY . .
RUN useradd --create-home --uid 10001 appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000
# миграции -> uvicorn через exec: SIGTERM получает uvicorn (graceful shutdown)
ENTRYPOINT ["sh", "scripts/entrypoint.sh"]


# --- образ для тестов: docker compose --profile test run --rm tests ---
FROM runtime AS dev
USER root
RUN --mount=type=bind,from=builder,source=/wheels,target=/wheels \
    pip install --no-index --find-links=/wheels -r requirements-dev.txt
USER appuser
ENTRYPOINT []
CMD ["sh", "-c", "python -m pytest"]
