# Infra

- `nginx/default.conf`: proxy reverso para `web` e `api`.
- `scripts/wait-for-db.sh`: aguarda PostgreSQL.
- `scripts/migrate.sh`: roda migracoes Alembic.
- `scripts/seed.sh`: executa seed demo.
- `scripts/backup-postgres.sh` e `scripts/backup-postgres.ps1`: backup do banco.
- `scripts/restore-postgres.sh` e `scripts/restore-postgres.ps1`: restore do banco.
