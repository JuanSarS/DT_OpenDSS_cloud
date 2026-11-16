param(
  [string]$ComposeFile = ".\infra\local\compose.yaml"
)

$ErrorActionPreference = "Stop"
$target = Join-Path $PWD "secrets\local\root.crt"
New-Item -ItemType Directory -Force (Split-Path $target) | Out-Null

Write-Host "[1] Copiando la CA que usa el gateway actual..."
docker compose -f $ComposeFile cp gateway:/data/caddy/pki/authorities/local/root.crt $target
if ($LASTEXITCODE -ne 0) {
  throw "No se pudo copiar la CA. Primero levanta gateway con Docker Compose."
}

Write-Host "[2] Huella de la CA actual:"
certutil -hashfile $target SHA256

$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = [Security.Principal.WindowsPrincipal]::new($identity)
$isAdmin = $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)

if (-not $isAdmin) {
  Write-Warning "PowerShell no está elevado."
  Write-Host "Abre PowerShell como Administrador y ejecuta:"
  Write-Host "  certutil -addstore -f Root `"$target`""
  exit 2
}

Write-Host "[3] Instalando/actualizando la CA en Trusted Root..."
certutil -addstore -f Root $target
if ($LASTEXITCODE -ne 0) {
  throw "certutil devolvió código $LASTEXITCODE"
}

Write-Host ""
Write-Host "CA confiada. Cierra COMPLETAMENTE Chrome/Edge/Opera y vuelve a abrir:"
Write-Host "https://localhost:8443"
Write-Host ""
Write-Host "Si recreas caddy-data (por ejemplo docker compose down -v), ejecuta este script otra vez."
