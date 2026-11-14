$ErrorActionPreference = "Stop"

$ComposeFile = (
    ".\infra\local\compose.yaml"
)

Write-Host ""
Write-Host "===================================="
Write-Host " OpenDSS Cloud - Local Deployment"
Write-Host "===================================="
Write-Host ""

Write-Host "[1] Building and starting services"

docker compose `
  -f $ComposeFile `
  up `
  -d `
  --build 

if ($LASTEXITCODE -ne 0) {
    throw "docker compose up failed"
}

Write-Host ""
Write-Host "[2] Waiting for API health"

$healthy = $false

for ($i = 0; $i -lt 60; $i++) {

    try {
        $response = Invoke-RestMethod `
          "http://127.0.0.1:8000/health"

        if ($response.status -eq "ok") {
            $healthy = $true
            break
        }
    }
    catch {
    }

    Start-Sleep -Seconds 2
}

if (-not $healthy) {
    docker compose `
      -f $ComposeFile `
      logs `
      --tail=200

    throw "API did not become healthy"
}

Write-Host "[OK] API healthy"

Write-Host ""
Write-Host "[3] Checking internal worker"

docker compose `
  -f $ComposeFile `
  exec `
  -T `
  api-manager `
  python `
  -c `
  "import urllib.request; print(urllib.request.urlopen('http://simulation-worker:8100/internal/health').read().decode())"

if ($LASTEXITCODE -ne 0) {
    throw "worker health failed"
}

Write-Host ""
Write-Host "[4] Running smoke"

python .\scripts\smoke_test.py

if ($LASTEXITCODE -ne 0) {
    throw "smoke_test failed"
}

Write-Host ""
Write-Host "[5] QSTS REST"

python .\scripts\qsts_api_smoke.py `
  --base-url http://127.0.0.1:8000

if ($LASTEXITCODE -ne 0) {
    throw "QSTS API smoke failed"
}

Write-Host ""
Write-Host "[6] QSTS WebSocket"

python .\scripts\qsts_ws_smoke.py `
  --base-url http://127.0.0.1:8000

if ($LASTEXITCODE -ne 0) {
    throw "QSTS WS smoke failed"
}

Write-Host ""
Write-Host "===================================="
Write-Host " LOCAL DEPLOYMENT OK"
Write-Host " http://127.0.0.1:8000"
Write-Host "===================================="