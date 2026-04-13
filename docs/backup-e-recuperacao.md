# Backup e Recuperação

## Backup PostgreSQL

### Linux/macOS
```bash
./infra/scripts/backup-postgres.sh
./infra/scripts/backup-postgres.sh ./storage/backups/producao-2026-04-08.sql.gz
```

### Windows (PowerShell)
```powershell
.\infra\scripts\backup-postgres.ps1
.\infra\scripts\backup-postgres.ps1 -OutputPath .\storage\backups\producao-2026-04-08.sql.gz
```

## Restore PostgreSQL

### Linux/macOS
```bash
./infra/scripts/restore-postgres.sh ./storage/backups/producao-2026-04-08.sql.gz
```

### Windows (PowerShell)
```powershell
.\infra\scripts\restore-postgres.ps1 -InputPath .\storage\backups\producao-2026-04-08.sql.gz
```

## Política recomendada
- Backup completo diário.
- Retenção mínima de 30 dias.
- 1 restore de teste por semana.
- Armazenamento externo (bucket ou volume separado).
