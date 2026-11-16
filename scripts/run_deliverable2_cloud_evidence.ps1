param(
    [string]$Region = "us-east-2",
    [string]$Profile = "",
    [string]$ProjectName = "opendss-thesis",
    [int]$LoadSeconds = 90
)

$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $Root
$MainStack = "$ProjectName-main"
$Stamp = (Get-Date).ToUniversalTime().ToString("yyyyMMddTHHmmssZ")
$RunDir = Join-Path $Root "docs\evidence\deliverable_2\${Stamp}_cloud_performance"
New-Item -ItemType Directory -Force -Path $RunDir | Out-Null

$AwsCommon = @("--region", $Region, "--no-cli-pager")
if ($Profile) { $AwsCommon += @("--profile", $Profile) }
function Aws { param([Parameter(ValueFromRemainingArguments=$true)][string[]]$Arguments); & aws @AwsCommon @Arguments }
function Output([string]$Key) {
    return (Aws cloudformation describe-stacks --stack-name $MainStack `
      --query "Stacks[0].Outputs[?OutputKey=='$Key'].OutputValue | [0]" --output text | Out-String).Trim()
}

$BaseUrl = Output "ApplicationUrl"
$Cluster = Output "EcsClusterName"
$WorkerService = Output "WorkerServiceName"
if (-not $BaseUrl) { throw "No se encontro ApplicationUrl." }

Write-Host "IMPORTANTE: para esta campaña despliega previamente con:"
Write-Host ".\scripts\deploy_cloud.ps1 -PerformanceMode -ReuseImages ..."
Write-Host ""

python -m tools.evidence.cloud_mvp_evidence --base-url $BaseUrl --output-root $RunDir
if ($LASTEXITCODE -ne 0) { throw "Cloud MVP evidence fallo." }

$env:OPENDSS_LOAD_USERNAME = "admin"
$OwnLoadPassword = $false
if (-not $env:OPENDSS_LOAD_PASSWORD) {
    $secure = Read-Host "Password del usuario admin para Locust" -AsSecureString
    $credential = [pscredential]::new("admin", $secure)
    $env:OPENDSS_LOAD_PASSWORD = $credential.GetNetworkCredential().Password
    $OwnLoadPassword = $true
}
$env:OPENDSS_LOAD_MODEL = "ieee123"
$env:OPENDSS_LOAD_DURATION_HOURS = "24"
$env:OPENDSS_LOAD_STEP_MINUTES = "5"

$Sentinel = Join-Path $RunDir "monitor.running"
New-Item -ItemType File -Force $Sentinel | Out-Null
$Timeline = Join-Path $RunDir "autoscaling_timeline.jsonl"
$ProfileArg = $Profile
$monitor = Start-Job -ArgumentList $Sentinel,$Timeline,$Region,$ProfileArg,$Cluster,$WorkerService -ScriptBlock {
    param($Sentinel,$Timeline,$Region,$Profile,$Cluster,$WorkerService)
    while (Test-Path $Sentinel) {
        $args = @("--region",$Region,"--no-cli-pager")
        if ($Profile) { $args += @("--profile",$Profile) }
        $raw = & aws @args ecs describe-services --cluster $Cluster --services $WorkerService --output json
        if ($LASTEXITCODE -eq 0) {
            $service = ($raw | ConvertFrom-Json).services[0]
            $sample = [ordered]@{
                timestamp_utc = (Get-Date).ToUniversalTime().ToString("o")
                desired_count = $service.desiredCount
                running_count = $service.runningCount
                pending_count = $service.pendingCount
                deployments = $service.deployments
            }
            Add-Content -Encoding utf8 -Path $Timeline -Value ($sample | ConvertTo-Json -Compress -Depth 8)
        }
        Start-Sleep -Seconds 10
    }
}

$Start = (Get-Date).ToUniversalTime()
try {
    Write-Host "[Locust] 5 usuarios QSTS"
    python -m locust -f .\load\locustfile.py --headless -u 5 -r 1 -t "${LoadSeconds}s" `
      --host $BaseUrl --csv (Join-Path $RunDir "locust_5") --csv-full-history QSTSUser `
      2>&1 | Tee-Object -FilePath (Join-Path $RunDir "locust_5.log")
    if ($LASTEXITCODE -ne 0) { throw "Locust 5 usuarios fallo." }

    Write-Host "[Locust] 10 usuarios QSTS"
    python -m locust -f .\load\locustfile.py --headless -u 10 -r 2 -t "${LoadSeconds}s" `
      --host $BaseUrl --csv (Join-Path $RunDir "locust_10") --csv-full-history QSTSUser `
      2>&1 | Tee-Object -FilePath (Join-Path $RunDir "locust_10.log")
    if ($LASTEXITCODE -ne 0) { throw "Locust 10 usuarios fallo." }
}
finally {
    Remove-Item $Sentinel -ErrorAction SilentlyContinue
    Wait-Job $monitor -Timeout 20 | Out-Null
    Receive-Job $monitor | Out-Null
    Remove-Job $monitor -Force -ErrorAction SilentlyContinue
    if ($OwnLoadPassword) { Remove-Item Env:OPENDSS_LOAD_PASSWORD -ErrorAction SilentlyContinue }
    Remove-Item Env:OPENDSS_LOAD_USERNAME,Env:OPENDSS_LOAD_MODEL,Env:OPENDSS_LOAD_DURATION_HOURS,Env:OPENDSS_LOAD_STEP_MINUTES -ErrorAction SilentlyContinue
}
$End = (Get-Date).ToUniversalTime()

$StartIso = $Start.ToString("o")
$EndIso = $End.AddMinutes(2).ToString("o")
foreach ($metric in @("CPUUtilization","MemoryUtilization")) {
    Aws cloudwatch get-metric-statistics `
      --namespace AWS/ECS `
      --metric-name $metric `
      --dimensions "Name=ClusterName,Value=$Cluster" "Name=ServiceName,Value=$WorkerService" `
      --start-time $StartIso `
      --end-time $EndIso `
      --period 60 `
      --statistics Average Maximum `
      --output json | Set-Content -Encoding utf8 (Join-Path $RunDir "cloudwatch_$metric.json")
}
Aws ecs describe-services --cluster $Cluster --services $WorkerService --output json |
    Set-Content -Encoding utf8 (Join-Path $RunDir "worker_service_final.json")

@{
    timestamp_utc = $Stamp
    base_url = $BaseUrl
    cluster = $Cluster
    worker_service = $WorkerService
    load_seconds = $LoadSeconds
    note = "Run intended for PerformanceMode: rate limit/admission disabled to measure platform capacity."
} | ConvertTo-Json -Depth 5 | Set-Content -Encoding utf8 (Join-Path $RunDir "manifest.json")

python -m tools.evidence.summarize_deliverable2 --run-dir $RunDir
if ($LASTEXITCODE -ne 0) { throw "Resumen Entregable 2 fallo." }

Write-Host "[OK] Evidence Entregable 2: $RunDir"
