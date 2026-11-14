param(
    [string]$BaseUrl = "http://127.0.0.1:8000",
    [switch]$Full
)

$ErrorActionPreference = "Stop"

Write-Host ""
Write-Host "====================================="
Write-Host "OpenDSS Cloud Regression"
Write-Host "====================================="
Write-Host "Base URL: $BaseUrl"
Write-Host ""

Write-Host "[1] Python compile"
python -m compileall packages services scripts
if ($LASTEXITCODE -ne 0) {
    throw "compileall failed"
}

Write-Host "[2] Git diff check"
git diff --check
if ($LASTEXITCODE -ne 0) {
    throw "git diff --check failed"
}

Write-Host "[3] Health"
$health = Invoke-RestMethod "$BaseUrl/health"
Write-Host "Health OK"

Write-Host "[4] Frontend"
$root = Invoke-WebRequest "$BaseUrl/"
if ($root.StatusCode -ne 200) {
    throw "Frontend failed"
}

Write-Host "[5] CSS"
$css = Invoke-WebRequest "$BaseUrl/static/css/app.css"
if ($css.StatusCode -ne 200) {
    throw "CSS failed"
}

Write-Host "[6] JS"
$js = Invoke-WebRequest "$BaseUrl/static/js/app.js"
if ($js.StatusCode -ne 200) {
    throw "JS failed"
}

Write-Host "[7] Models"
$models = Invoke-RestMethod "$BaseUrl/models"
$modelIds = @($models | ForEach-Object { $_.id })

foreach ($required in @("ieee13", "ieee34", "ieee123", "ieee8500")) {
    if ($required -notin $modelIds) {
        throw "Missing model: $required"
    }
}

Write-Host "Models OK"

Write-Host "[8] Metrics"
$metrics = Invoke-RestMethod "$BaseUrl/metrics"
Write-Host "Metrics OK"

Write-Host "[9] OpenAPI baseline"
$api = Invoke-RestMethod "$BaseUrl/openapi.json"

$paths = @(
    $api.paths.PSObject.Properties.Name
)

foreach ($required in @(
    "/health",
    "/models",
    "/simulations",
    "/simulations/{session_id}",
    "/simulations/{session_id}/solve",
    "/simulations/{session_id}/results",
    "/metrics"
)) {
    if ($required -notin $paths) {
        throw "Missing OpenAPI path: $required"
    }
}

Write-Host "[10] QSTS REST smoke"
python .\scripts\qsts_api_smoke.py --base-url $BaseUrl

if ($LASTEXITCODE -ne 0) {
    throw "QSTS API smoke failed"
}

Write-Host "[11] QSTS WebSocket smoke"
python .\scripts\qsts_ws_smoke.py --base-url $BaseUrl

if ($LASTEXITCODE -ne 0) {
    throw "QSTS WS smoke failed"
}

if ($Full) {
    Write-Host "[12] IEEE8500 direct engine smoke"

    python .\scripts\ieee8500_smoke.py

    if ($LASTEXITCODE -ne 0) {
        throw "IEEE8500 engine smoke failed"
    }

    Write-Host "[13] IEEE8500 API smoke"

    python .\scripts\ieee8500_api_smoke.py

    if ($LASTEXITCODE -ne 0) {
        throw "IEEE8500 API smoke failed"
    }

    Write-Host "[14] Contract Jobs Smoke"
    python .\scripts\contracts_smoke.py
        if ($LASTEXITCODE -ne 0) {
        throw "Contract Jobs smoke failed"
    }
}

Write-Host ""
Write-Host "====================================="
Write-Host " REGRESSION OK"
Write-Host "====================================="