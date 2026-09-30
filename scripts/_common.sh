#!/usr/bin/env bash
# Общие функции для скриптов резервного копирования. Значения читаются из .env без его выполнения.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

env_get() {
  local value
  value="$(grep -E "^$1=" .env | head -n1 | cut -d= -f2-)" || true
  if [ -z "$value" ]; then
    echo "Переменная $1 не найдена в .env" >&2
    exit 1
  fi
  printf '%s' "$value"
}
