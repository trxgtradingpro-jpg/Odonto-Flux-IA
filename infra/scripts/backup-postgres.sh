#!/usr/bin/env sh
set -eu

TIMESTAMP="$(date +%Y%m%d-%H%M%S)"
OUTPUT_PATH="${1:-./storage/backups/postgres-${TIMESTAMP}.sql.gz}"

mkdir -p "$(dirname "${OUTPUT_PATH}")"

POSTGRES_USER="${POSTGRES_USER:-odontoflux}"
POSTGRES_DB="${POSTGRES_DB:-odontoflux}"

echo "Gerando backup em ${OUTPUT_PATH}..."
docker compose exec -T postgres pg_dump -U "${POSTGRES_USER}" "${POSTGRES_DB}" | gzip > "${OUTPUT_PATH}"
echo "Backup concluido: ${OUTPUT_PATH}"
