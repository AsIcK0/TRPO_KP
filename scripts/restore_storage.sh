#!/usr/bin/env bash
# Восстановление файлов в MinIO. Использование: scripts/restore_storage.sh backups/storage/storage_YYYYMMDD_HHMMSS
source "$(dirname "${BASH_SOURCE[0]}")/_common.sh"

DIR="${1:?Укажите каталог копии: scripts/restore_storage.sh backups/storage/<каталог>}"
[ -d "$DIR" ] || { echo "Каталог не найден: $DIR" >&2; exit 1; }
NAME="$(basename "$DIR")"
BUCKET="$(env_get S3_BUCKET)"
MC_HOST_src="http://$(env_get S3_ACCESS_KEY):$(env_get S3_SECRET_KEY)@minio:9000"
export MC_HOST_src

docker compose up -d --wait minio
docker compose --profile tools run --rm -e MC_HOST_src mc mb --ignore-existing "src/$BUCKET"
docker compose --profile tools run --rm -e MC_HOST_src mc mirror --overwrite "/backups/storage/$NAME" "src/$BUCKET"
echo "Файлы восстановлены из $DIR"
