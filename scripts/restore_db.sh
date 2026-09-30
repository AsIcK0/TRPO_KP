#!/usr/bin/env bash
# Восстановление PostgreSQL из копии. Использование: scripts/restore_db.sh backups/db/db_YYYYMMDD_HHMMSS.dump
# БД пересоздается с нуля, backend на время восстановления останавливается.
source "$(dirname "${BASH_SOURCE[0]}")/_common.sh"

FILE="${1:?Укажите файл копии: scripts/restore_db.sh backups/db/<файл>.dump}"
[ -f "$FILE" ] || { echo "Файл не найден: $FILE" >&2; exit 1; }
DB_USER="$(env_get POSTGRES_USER)"
DB_NAME="$(env_get POSTGRES_DB)"

echo "Останавливаю backend..."
docker compose stop backend
docker compose up -d --wait postgres

docker compose exec -T postgres psql -U "$DB_USER" -d postgres -v ON_ERROR_STOP=1 \
  -c "DROP DATABASE IF EXISTS \"$DB_NAME\" WITH (FORCE)" -c "CREATE DATABASE \"$DB_NAME\""
docker compose exec -T postgres pg_restore -U "$DB_USER" -d "$DB_NAME" --no-owner --exit-on-error < "$FILE"

echo "Запускаю backend..."
docker compose up -d backend
echo "БД восстановлена из $FILE"
