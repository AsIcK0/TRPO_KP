#!/usr/bin/env bash
# Копия файлового хранилища MinIO через mc mirror. Использование: scripts/backup_storage.sh
source "$(dirname "${BASH_SOURCE[0]}")/_common.sh"

BUCKET="$(env_get S3_BUCKET)"
# адрес с учетными данными передается в контейнер через окружение (не через аргументы командной строки)
MC_HOST_src="http://$(env_get S3_ACCESS_KEY):$(env_get S3_SECRET_KEY)@minio:9000"
export MC_HOST_src

NAME="storage_$(date +%Y%m%d_%H%M%S)"
mkdir -p "backups/storage/$NAME"
docker compose up -d --wait minio
docker compose --profile tools run --rm -e MC_HOST_src mc mirror --overwrite "src/$BUCKET" "/backups/storage/$NAME"
echo "Копия хранилища создана: backups/storage/$NAME ($(find "backups/storage/$NAME" -type f | wc -l) файлов)"
