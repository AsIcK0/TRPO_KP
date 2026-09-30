#!/usr/bin/env bash
# Резервная копия PostgreSQL (pg_dump, custom-формат). Использование: scripts/backup_db.sh
source "$(dirname "${BASH_SOURCE[0]}")/_common.sh"

DB_USER="$(env_get POSTGRES_USER)"
DB_NAME="$(env_get POSTGRES_DB)"
mkdir -p backups/db
OUT="backups/db/db_$(date +%Y%m%d_%H%M%S).dump"

docker compose exec -T postgres pg_dump -U "$DB_USER" -d "$DB_NAME" -Fc > "$OUT"
[ -s "$OUT" ] || { echo "Ошибка: файл резервной копии пуст" >&2; rm -f "$OUT"; exit 1; }
echo "Резервная копия БД создана: $OUT"
