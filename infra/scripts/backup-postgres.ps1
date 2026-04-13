param(
  [string]$OutputPath
)

$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
if (-not $OutputPath) {
  $OutputPath = ".\\storage\\backups\\postgres-$timestamp.sql.gz"
}

$directory = Split-Path -Parent $OutputPath
if (-not (Test-Path $directory)) {
  New-Item -ItemType Directory -Path $directory | Out-Null
}

$postgresUser = if ($env:POSTGRES_USER) { $env:POSTGRES_USER } else { "odontoflux" }
$postgresDb = if ($env:POSTGRES_DB) { $env:POSTGRES_DB } else { "odontoflux" }

Write-Host "Gerando backup em $OutputPath..."
$tempSql = [System.IO.Path]::GetTempFileName()

docker compose exec -T postgres pg_dump -U $postgresUser $postgresDb | Out-File -FilePath $tempSql -Encoding utf8

$inputBytes = [System.IO.File]::ReadAllBytes($tempSql)
$outputFile = [System.IO.File]::Create($OutputPath)
$gzipStream = New-Object System.IO.Compression.GzipStream($outputFile, [System.IO.Compression.CompressionMode]::Compress)
$gzipStream.Write($inputBytes, 0, $inputBytes.Length)
$gzipStream.Close()
$outputFile.Close()

Remove-Item -LiteralPath $tempSql -Force

Write-Host "Backup concluído: $OutputPath"
