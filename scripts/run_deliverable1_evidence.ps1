param(
    [string]$Models = "ieee13,ieee34,ieee123,ieee8500",
    [string]$Levels = "2,4,8,16"
)

$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $Root
$EvidenceRoot = Join-Path $Root "docs\evidence\deliverable_1"
New-Item -ItemType Directory -Force -Path $EvidenceRoot | Out-Null

Write-Host "[1] Building evidence image"
docker build -f .\infra\evidence\Dockerfile -t opendss-evidence:local .
if ($LASTEXITCODE -ne 0) { throw "Evidence image build fallo." }

Write-Host "[2] Running multi-context matrix 2/4/8/16"
docker run --rm `
  -v "${EvidenceRoot}:/evidence" `
  opendss-evidence:local `
  --models $Models `
  --levels $Levels
if ($LASTEXITCODE -ne 0) { throw "Entregable 1 evidence fallo." }

Write-Host "[OK] Evidencia Entregable 1 guardada en $EvidenceRoot"
