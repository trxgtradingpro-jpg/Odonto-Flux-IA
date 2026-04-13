#!/usr/bin/env bash
set -euo pipefail

until pg_isready -h "${POSTGRES_HOST:-postgres}" -p "${POSTGRES_PORT:-5432}" -U "${POSTGRES_USER:-odontoflux}"; do
  echo "Aguardando banco de dados..."
  sleep 2
done

echo "Banco disponivel."
