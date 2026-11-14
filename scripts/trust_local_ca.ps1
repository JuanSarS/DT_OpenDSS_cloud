param(
  [string]$ComposeFile = ".\infra\local\compose.yaml"
)

$ErrorActionPreference = "Stop"
$target = Join-Path $PWD "secrets\local\root.crt"
New-Item -ItemType Directory -Force (Split-Path $target) | Out-Null

docker compose -f $ComposeFile cp gateway:/data/caddy/pki/authorities/local/root.crt $target
if ($LASTEXITCODE -ne 0) {
  Write-Error "No se pudo copiar la CA local. Asegúrate de que gateway esté iniciado."
}

try {
  certutil -addstore -f Root $target
  if ($LASTEXITCODE -ne 0) {
    throw "certutil devolvió código $LASTEXITCODE"
  }
  Write-Host "CA instalada. Usa https://localhost:8443."
}
catch {
  Write-Warning "Se requiere PowerShell elevado para instalar la CA: $target"
  Write-Host "Ejecuta como administrador: certutil -addstore -f Root `"$target`""
}
