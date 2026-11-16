param(
    [string]$BaseUrl = "",
    [string]$Region = "us-east-2",
    [string]$Profile = "",
    [string]$ProjectName = "opendss-thesis",
    [string]$Username = "admin"
)

$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $Root
$MainStack = "$ProjectName-main"

$AwsCommon = @("--region", $Region, "--no-cli-pager")
if ($Profile) { $AwsCommon += @("--profile", $Profile) }

function Aws {
    param([Parameter(ValueFromRemainingArguments=$true)][string[]]$Arguments)
    & aws @AwsCommon @Arguments
    if ($LASTEXITCODE -ne 0) { throw "AWS CLI fallo: $($Arguments -join ' ')" }
}

if (-not $BaseUrl) {
    $BaseUrl = (Aws cloudformation describe-stacks `
        --stack-name $MainStack `
        --query "Stacks[0].Outputs[?OutputKey=='ApplicationUrl'].OutputValue | [0]" `
        --output text | Out-String).Trim()
}
if (-not $BaseUrl -or $BaseUrl -eq "None") { throw "No fue posible resolver ApplicationUrl." }

$Stamp = (Get-Date).ToUniversalTime().ToString("yyyyMMddTHHmmssZ")
$RunDir = Join-Path $Root "docs\evidence\deliverable_2\${Stamp}_cloud_smoke"
New-Item -ItemType Directory -Force -Path $RunDir | Out-Null

$OwnSmokePassword = $false
if (-not $env:OPENDSS_SMOKE_PASSWORD) {
    $secure = Read-Host "Password de $Username" -AsSecureString
    $credential = [pscredential]::new($Username, $secure)
    $env:OPENDSS_SMOKE_PASSWORD = $credential.GetNetworkCredential().Password
    $OwnSmokePassword = $true
}

function Run-Step {
    param([string]$Name, [scriptblock]$Command, [string]$FileName)
    Write-Host ""
    Write-Host "=== $Name ==="
    & $Command 2>&1 | Tee-Object -FilePath (Join-Path $RunDir $FileName)
    if ($LASTEXITCODE -ne 0) { throw "$Name fallo con codigo $LASTEXITCODE" }
}

try {
    Run-Step "Snapshot + WSS" {
        python .\scripts\smoke_test.py --base-url $BaseUrl --username $Username --ca-cert ""
    } "01_snapshot_wss.log"

    Run-Step "QSTS REST" {
        python .\scripts\qsts_api_smoke.py --base-url $BaseUrl --username $Username --ca-cert ""
    } "02_qsts_rest.log"

    Run-Step "QSTS WSS" {
        python .\scripts\qsts_ws_smoke.py --base-url $BaseUrl --username $Username --ca-cert ""
    } "03_qsts_wss.log"

    Run-Step "IEEE8500" {
        python .\scripts\ieee8500_api_smoke.py --base-url $BaseUrl --username $Username --ca-cert ""
    } "04_ieee8500.log"

    $Cluster = (Aws cloudformation describe-stacks --stack-name $MainStack `
        --query "Stacks[0].Outputs[?OutputKey=='EcsClusterName'].OutputValue | [0]" --output text | Out-String).Trim()
    $ApiService = (Aws cloudformation describe-stacks --stack-name $MainStack `
        --query "Stacks[0].Outputs[?OutputKey=='ApiServiceName'].OutputValue | [0]" --output text | Out-String).Trim()
    $WorkerService = (Aws cloudformation describe-stacks --stack-name $MainStack `
        --query "Stacks[0].Outputs[?OutputKey=='WorkerServiceName'].OutputValue | [0]" --output text | Out-String).Trim()

    Aws ecs describe-services --cluster $Cluster --services $ApiService $WorkerService --output json |
        Set-Content -Encoding utf8 (Join-Path $RunDir "ecs_services.json")

    $manifest = [ordered]@{
        timestamp_utc = $Stamp
        base_url = $BaseUrl
        username = $Username
        cluster = $Cluster
        api_service = $ApiService
        worker_service = $WorkerService
        result = "PASS"
    }
    $manifest | ConvertTo-Json -Depth 4 | Set-Content -Encoding utf8 (Join-Path $RunDir "manifest.json")

    Write-Host ""
    Write-Host "CLOUD SMOKE OK"
    Write-Host "Evidence: $RunDir"
}
finally {
    if ($OwnSmokePassword) { Remove-Item Env:OPENDSS_SMOKE_PASSWORD -ErrorAction SilentlyContinue }
}
