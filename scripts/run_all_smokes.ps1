param(
    [string]$BaseUrl = "https://localhost:8443",
    [string]$Username = "admin",
    [string]$CaCert = ".\secrets\local\root.crt",
    [switch]$Insecure,
    [switch]$Native
)

$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $Root
$Stamp = (Get-Date).ToUniversalTime().ToString("yyyyMMddTHHmmssZ")
$RunDir = Join-Path $Root "docs\evidence\regression\$Stamp"
New-Item -ItemType Directory -Force -Path $RunDir | Out-Null

if (-not (Test-Path $CaCert) -and -not $Insecure -and $BaseUrl -match "localhost") {
    throw "No existe $CaCert. Ejecuta .\scripts\trust_local_ca.ps1 primero."
}

$secure = Read-Host "Password de $Username" -AsSecureString
$credential = [pscredential]::new($Username, $secure)
$env:OPENDSS_SMOKE_PASSWORD = $credential.GetNetworkCredential().Password
$common = @("--base-url", $BaseUrl, "--username", $Username)
if ($CaCert) { $common += @("--ca-cert", $CaCert) }
if ($Insecure) { $common += "--insecure" }

$script:results = @()
function Run-Step([string]$Name, [scriptblock]$Command, [string]$FileName) {
    Write-Host ""
    Write-Host "=== $Name ==="
    $started = Get-Date
    & $Command 2>&1 | Tee-Object -FilePath (Join-Path $RunDir $FileName)
    $code = $LASTEXITCODE
    $script:results += [pscustomobject]@{
        name = $Name
        exit_code = $code
        started_utc = $started.ToUniversalTime().ToString("o")
        ended_utc = (Get-Date).ToUniversalTime().ToString("o")
    }
    if ($code -ne 0) { throw "$Name failed with code $code" }
}



try {
    Run-Step "Compile" { python -m compileall -q packages services scripts tests tools } "01_compile.log"
    Run-Step "Compose config" { docker compose -f .\infra\local\compose.yaml config --quiet } "02_compose_config.log"
    Run-Step "Contracts" { python .\scripts\contracts_smoke.py } "03_contracts.log"
    Run-Step "Snapshot + WSS" { python .\scripts\smoke_test.py @common } "04_snapshot_wss.log"
    Run-Step "QSTS REST" { python .\scripts\qsts_api_smoke.py @common } "05_qsts_rest.log"
    Run-Step "QSTS WSS" { python .\scripts\qsts_ws_smoke.py @common } "06_qsts_wss.log"
    Run-Step "IEEE8500 API" { python .\scripts\ieee8500_api_smoke.py @common } "07_ieee8500.log"
    Run-Step "Security tests" { python -m pytest tests\security -q -p no:faulthandler } "08_security_pytest.log"
    Run-Step "Execution/contract unit tests" { python -m pytest tests\unit -q -p no:faulthandler } "09_unit_pytest.log"
    Run-Step "Full pytest" { python -m pytest tests -q -p no:faulthandler } "10_full_pytest.log"
    if ($Native) {
        Run-Step "QSTS native" { python .\scripts\qsts_smoke.py } "11_qsts_native.log"
        Run-Step "IEEE8500 native" { python .\scripts\ieee8500_smoke.py } "12_ieee8500_native.log"
        Run-Step "Executor" { python .\scripts\executor_smoke.py } "13_executor.log"
        Run-Step "Executor isolation" { python .\scripts\executor_isolation_smoke.py } "14_executor_isolation.log"
        Run-Step "Executor recycle" { python .\scripts\executor_recycle_smoke.py } "15_executor_recycle.log"
    }

    $script:results | ConvertTo-Json -Depth 5 | Set-Content -Encoding utf8 (Join-Path $RunDir "manifest.json")
    Write-Host ""
    Write-Host "====================================="
    Write-Host " ALL SMOKES OK"
    Write-Host "====================================="
    Write-Host "Evidence: $RunDir"
}
finally {
    Remove-Item Env:OPENDSS_SMOKE_PASSWORD -ErrorAction SilentlyContinue
}
