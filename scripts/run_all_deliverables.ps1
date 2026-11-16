param(
    [string]$Region = "us-east-2",
    [string]$Profile = "",
    [string]$ProjectName = "opendss-thesis",
    [int]$LoadSeconds = 180,
    [switch]$DestroyAfter
)

$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $Root

$Common = @{
    Region = $Region
    ProjectName = $ProjectName
}
if ($Profile) { $Common.Profile = $Profile }

Write-Host "=========================================="
Write-Host " OpenDSS - generación de 3 entregables"
Write-Host "=========================================="

$adminSecure = Read-Host "Password de admin" -AsSecureString
$user1Secure = Read-Host "Password de user1" -AsSecureString
$user2Secure = Read-Host "Password de user2" -AsSecureString
$env:OPENDSS_ADMIN_PASSWORD = ([pscredential]::new("admin", $adminSecure)).GetNetworkCredential().Password
$env:OPENDSS_USER1_PASSWORD = ([pscredential]::new("user1", $user1Secure)).GetNetworkCredential().Password
$env:OPENDSS_USER2_PASSWORD = ([pscredential]::new("user2", $user2Secure)).GetNetworkCredential().Password
$env:OPENDSS_LOAD_USERNAME = "admin"
$env:OPENDSS_LOAD_PASSWORD = $env:OPENDSS_ADMIN_PASSWORD
$env:OPENDSS_SMOKE_PASSWORD = $env:OPENDSS_ADMIN_PASSWORD

try {
    Write-Host "[1/7] Entregable 1: multi-contexto local"
    & .\scripts\run_deliverable1_evidence.ps1
    if ($LASTEXITCODE -ne 0) { throw "Entregable 1 fallo." }

    Write-Host "[2/7] AWS performance mode"
    & .\scripts\deploy_cloud.ps1 @Common `
        -PerformanceMode -WorkerCount 1 -WorkerMinCount 1 -WorkerMaxCount 6 `
        -ReuseImages -SkipSmoke
    if ($LASTEXITCODE -ne 0) { throw "Deploy performance fallo." }

    Write-Host "[3/7] Entregable 2"
    & .\scripts\run_deliverable2_cloud_evidence.ps1 @Common -LoadSeconds $LoadSeconds
    if ($LASTEXITCODE -ne 0) { throw "Entregable 2 fallo." }

    Write-Host "[4/7] AWS resilience mode"
    & .\scripts\deploy_cloud.ps1 @Common `
        -ResilienceMode -WorkerCount 3 -WorkerMinCount 1 -WorkerMaxCount 6 `
        -ReuseImages -SkipSmoke
    if ($LASTEXITCODE -ne 0) { throw "Deploy resilience fallo." }

    Write-Host "[5/7] Entregable 3"
    & .\scripts\run_deliverable3_cloud_evidence.ps1 @Common
    if ($LASTEXITCODE -ne 0) { throw "Entregable 3 fallo." }

    Write-Host "[6/7] Índice de evidencia"
    python .\scripts\build_evidence_index.py
    if ($LASTEXITCODE -ne 0) { throw "Evidence index fallo." }

    if ($DestroyAfter) {
        Write-Host "[7/7] Desmontando AWS"
        & .\scripts\destroy_cloud.ps1 @Common
        if ($LASTEXITCODE -ne 0) { throw "Destroy cloud fallo." }
    } else {
        Write-Host "[7/7] AWS se mantiene activo. Recuerda destruirlo al terminar."
    }

    Write-Host "=========================================="
    Write-Host " EVIDENCIA COMPLETA"
    Write-Host "=========================================="
    Write-Host "Revisa docs/evidence/EVIDENCE_INDEX.md"
}
finally {
    Remove-Item Env:OPENDSS_ADMIN_PASSWORD,Env:OPENDSS_USER1_PASSWORD,Env:OPENDSS_USER2_PASSWORD,Env:OPENDSS_LOAD_USERNAME,Env:OPENDSS_LOAD_PASSWORD,Env:OPENDSS_SMOKE_PASSWORD -ErrorAction SilentlyContinue
}
