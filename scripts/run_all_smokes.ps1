param(
    [string]$BaseUrl = "https://localhost:8443",
    [string]$Username = "admin",
    [string]$CaCert = ".\secrets\local\root.crt",
    [switch]$Insecure,
    [switch]$Native
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path $CaCert) -and -not $Insecure) {
    throw "No existe $CaCert. Ejecuta .\scripts\trust_local_ca.ps1 primero."
}

$secure = Read-Host "Password de $Username" -AsSecureString
$credential = [pscredential]::new($Username, $secure)
$env:OPENDSS_SMOKE_PASSWORD = $credential.GetNetworkCredential().Password
$common = @("--base-url", $BaseUrl, "--username", $Username, "--ca-cert", $CaCert)
if ($Insecure) { $common += "--insecure" }

function Run-Step([string]$Name, [scriptblock]$Command) {
    Write-Host ""
    Write-Host "=== $Name ==="
    & $Command
    if ($LASTEXITCODE -ne 0) { throw "$Name failed with code $LASTEXITCODE" }
}

try {
    Run-Step "Compile" { python -m compileall -q packages services scripts tests tools }
    Run-Step "Compose config" { docker compose -f .\infra\local\compose.yaml config --quiet }
    Run-Step "Contracts" { python .\scripts\contracts_smoke.py }
    Run-Step "Snapshot + WSS" { python .\scripts\smoke_test.py @common }
    Run-Step "QSTS REST" { python .\scripts\qsts_api_smoke.py @common }
    Run-Step "QSTS WSS" { python .\scripts\qsts_ws_smoke.py @common }
    Run-Step "IEEE8500 API" { python .\scripts\ieee8500_api_smoke.py @common }
    Run-Step "Security tests" { python -m pytest tests\security -q }
    Run-Step "Unit tests" { python -m pytest tests\unit -q }
    Run-Step "Unit tests" { python -m pytest tests -q }
    if ($Native) {
        Run-Step "QSTS native" { python .\scripts\qsts_smoke.py }
        Run-Step "IEEE8500 native" { python .\scripts\ieee8500_smoke.py }
        Run-Step "Executor" { python .\scripts\executor_smoke.py }
        Run-Step "Executor isolation" { python .\scripts\executor_isolation_smoke.py }
        Run-Step "Executor recycle" { python .\scripts\executor_recycle_smoke.py }
    }

    Write-Host ""
    Write-Host "====================================="
    Write-Host " ALL SMOKES OK"
    Write-Host "====================================="
}
finally {
    Remove-Item Env:OPENDSS_SMOKE_PASSWORD -ErrorAction SilentlyContinue
}
