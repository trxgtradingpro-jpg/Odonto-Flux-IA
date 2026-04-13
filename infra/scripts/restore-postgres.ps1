param(
  [Parameter(Mandatory = $true)]
  [string]$InputPath
)

if (-not (Test-Path $InputPath)) {
  throw "Arquivo não encontrado: $InputPath"
}

$postgresUser = if ($env:POSTGRES_USER) { $env:POSTGRES_USER } else { "odontoflux" }
$postgresDb = if ($env:POSTGRES_DB) { $env:POSTGRES_DB } else { "odontoflux" }

$tempSql = [System.IO.Path]::GetTempFileName()
$inputFile = [System.IO.File]::OpenRead($InputPath)
$gzipStream = New-Object System.IO.Compression.GzipStream($inputFile, [System.IO.Compression.CompressionMode]::Decompress)
$outputFile = [System.IO.File]::Create($tempSql)
$gzipStream.CopyTo($outputFile)
$gzipStream.Close()
$outputFile.Close()
$inputFile.Close()

Write-Host "Restaurando backup $InputPath..."
Get-Content -Raw $tempSql | docker compose exec -T postgres psql -U $postgresUser -d $postgresDb
Remove-Item -LiteralPath $tempSql -Force
Write-Host "Restore concluído."
