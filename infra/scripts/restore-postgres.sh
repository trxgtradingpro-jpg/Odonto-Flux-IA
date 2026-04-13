#!/usr/bin/env sh
set -eu

if [ $# -lt 1 ]; then
  echo "Uso: ./infra/scripts/restore-postgres.sh <arquivo.sql.gz>"
  exit 1
fi

INPUT_PATH="$1"
if [ ! -f "${INPUT_PATH}" ]; then
  echo "Arquivo nao encontrado: ${INPUT_PATH}"
  exit 1
fi

POSTGRES_USER="${POSTGRES_USER:-odontoflux}"
POSTGRES_DB="${POSTGRES_DB:-odontoflux}"

echo "Restaurando backup ${INPUT_PATH}..."
gzip -dc "${INPUT_PATH}" | docker compose exec -T postgres psql -U "${POSTGRES_USER}" -d "${POSTGRES_DB}"
echo "Restore concluido."
