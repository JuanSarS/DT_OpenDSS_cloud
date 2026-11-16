$ErrorActionPreference = "Stop"
$ComposeFile = ".\infra\local\compose.yaml"
$BaseUrl = "https://localhost:8443"

foreach ($secret in @(
  ".\secrets\local\jwt_secret.txt",
  ".\secrets\local\worker_shared_token.txt",
  ".\secrets\local\auth_users.json"
)) {
  if (-not (Test-Path $secret)) {
    throw "Falta $secret. Ejecuta: python .\scripts\init_local_secrets.py"
  }
}

Write-Host "[1] Build + start"
docker compose -f $ComposeFile up -d --build
if ($LASTEXITCODE -ne 0) { throw "docker compose up failed" }

Write-Host "[2] Esperando contenedores healthy"
Write-Host ""
Write-Host "[2] Esperando contenedores y gateway HTTPS..."

$ready = $false

for ($i = 0; $i -lt 60; $i++) {

    # Primero comprobamos que ningún servicio con healthcheck
    # haya entrado explícitamente en estado unhealthy.
    $status = docker compose `
        -f $ComposeFile `
        ps `
        --format json `
        2>$null

    $hasUnhealthy = (
        $status -and
        (
            $status |
            Select-String "unhealthy" -Quiet
        )
    )

    if (-not $hasUnhealthy) {

        # Gateway se valida de extremo a extremo:
        # navegador -> Caddy -> API Manager.
        try {
            $probe = curl.exe `
                -ksS `
                "$BaseUrl/health" `
                2>$null

            if (
                $LASTEXITCODE -eq 0 -and
                $probe -match '"status"\s*:\s*"ok"'
            ) {
                $ready = $true
                break
            }
        }
        catch {
        }
    }

    Start-Sleep -Seconds 2
}

if (-not $ready) {

    Write-Host ""
    Write-Host "Estado de los servicios:"
    docker compose `
        -f $ComposeFile `
        ps

    Write-Host ""
    Write-Host "Últimos logs:"
    docker compose `
        -f $ComposeFile `
        logs `
        --tail=200

    throw "El laboratorio no alcanzó estado operativo"
}

Write-Host "[OK] Gateway HTTPS y API responden correctamente"
Write-Host "[3] Verificando pool interno"
$workers = @(
  "simulation-worker-1",
  "simulation-worker-2",
  "simulation-worker-3"
)
foreach ($worker in $workers) {
  docker compose -f $ComposeFile exec -T api-manager python -c "import urllib.request; print(urllib.request.urlopen('http://$worker`:8100/internal/health').read().decode())"
  if ($LASTEXITCODE -ne 0) { throw "$worker no responde" }
}

Write-Host ""
Write-Host "LOCAL LAB READY: $BaseUrl"
Write-Host "Si el navegador muestra NET::ERR_CERT_AUTHORITY_INVALID, ejecuta como Administrador:"
Write-Host "  .\scripts\trust_local_ca.ps1"
