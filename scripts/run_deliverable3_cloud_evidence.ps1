param(
    [string]$Region = "us-east-2",
    [string]$Profile = "opendss-deployer",
    [string]$ProjectName = "opendss-thesis",
    [string]$Username = "admin"
)


$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $Root
$MainStack = "$ProjectName-main"
$Stamp = (Get-Date).ToUniversalTime().ToString("yyyyMMddTHHmmssZ")
$RunDir = Join-Path $Root "docs\evidence\deliverable_3\${Stamp}_resilience"
New-Item -ItemType Directory -Force -Path $RunDir | Out-Null

$AwsCommon = @("--region", $Region, "--no-cli-pager")
if ($Profile) { $AwsCommon += @("--profile", $Profile) }
function Invoke-AwsCli { param([Parameter(ValueFromRemainingArguments=$true)][string[]]$Arguments); & aws @AwsCommon @Arguments }
function Output([string]$Key) {
    return (Invoke-AwsCli cloudformation describe-stacks --stack-name $MainStack `
      --query "Stacks[0].Outputs[?OutputKey=='$Key'].OutputValue | [0]" --output text | Out-String).Trim()
}

$BaseUrl = Output "ApplicationUrl"
$Cluster = Output "EcsClusterName"
$WorkerService = Output "WorkerServiceName"
if (-not $BaseUrl) { throw "No se encontro ApplicationUrl." }

Write-Host "Esta prueba requiere despliegue con -ResilienceMode para hacer visible el QSTS."
$OwnSmokePassword = $false
if (-not $env:OPENDSS_SMOKE_PASSWORD) {
    $secure = Read-Host "Password de $Username" -AsSecureString
    $credential = [pscredential]::new($Username, $secure)
    $env:OPENDSS_SMOKE_PASSWORD = $credential.GetNetworkCredential().Password
    $OwnSmokePassword = $true
}

$Stdout = Join-Path $RunDir "resilience_client.stdout.log"
$Stderr = Join-Path $RunDir "resilience_client.stderr.log"
$args = @(
    "-m", "tools.evidence.resilience_client",
    "--base-url", $BaseUrl,
    "--username", $Username,
    "--output-dir", $RunDir,
    "--topology", "ieee123",
    "--duration-hours", "24",
    "--step-minutes", "1"
)

try {
    Write-Host "[1] Iniciando QSTS de resiliencia"
    $process = Start-Process -FilePath "python" -ArgumentList $args -PassThru `
        -RedirectStandardOutput $Stdout -RedirectStandardError $Stderr

    $SessionFile = Join-Path $RunDir "resilience_session.json"
    $ReadyFile = Join-Path $RunDir "ready_to_kill.flag"
    for ($i = 0; $i -lt 180; $i++) {
        if ($process.HasExited) {
            throw "El cliente de resiliencia termino antes de la inyeccion de falla. Revisa $Stderr"
        }
        if ((Test-Path $SessionFile) -and (Test-Path $ReadyFile)) { break }
        Start-Sleep -Seconds 1
        if ($i -eq 179) { throw "No se recibio progreso a tiempo para inyectar la falla." }
    }

    $session = Get-Content $SessionFile -Raw | ConvertFrom-Json
    $uri = [uri]$session.worker_identity
    $WorkerIp = $uri.Host
    Write-Host "[2] Worker propietario detectado: $WorkerIp"

    $taskText = (Invoke-AwsCli ecs list-tasks --cluster $Cluster --service-name $WorkerService `
        --desired-status RUNNING --query "taskArns" --output text | Out-String).Trim()
    $taskArns = @($taskText -split "\s+" | Where-Object { $_ })
    if ($taskArns.Count -eq 0) { throw "No hay tasks worker RUNNING." }

    $tasksJson = Invoke-AwsCli ecs describe-tasks --cluster $Cluster --tasks $taskArns --output json
    $tasksJson | Set-Content -Encoding utf8 (Join-Path $RunDir "worker_tasks_before_kill.json")
    $tasks = ($tasksJson | ConvertFrom-Json).tasks
    $TargetTask = $null
    foreach ($task in $tasks) {
        foreach ($attachment in $task.attachments) {
            $ipDetail = $attachment.details | Where-Object { $_.name -eq "privateIPv4Address" }
            if ($ipDetail.value -eq $WorkerIp) {
                $TargetTask = $task.taskArn
                break
            }
        }
        if ($TargetTask) { break }
    }
    if (-not $TargetTask) { throw "No fue posible mapear $WorkerIp a una task ECS." }

    Write-Host "[3] Deteniendo task para demostrar failover"
    Invoke-AwsCli ecs stop-task --cluster $Cluster --task $TargetTask `
      --reason "OpenDSS thesis resilience evidence" --output json |
      Set-Content -Encoding utf8 (Join-Path $RunDir "stopped_task.json")

    Write-Host "[4] Esperando final del cliente QSTS"

    if (-not $process) {
        throw "No existe proceso cliente de resiliencia."
    }

    $process.WaitForExit()
    $process.Refresh()

    $ExitCode = $process.ExitCode

    Write-Host "Exit code cliente resiliencia: $ExitCode"

    if ($ExitCode -ne 0) {

        Write-Host ""
        Write-Host "===== STDOUT resiliencia ====="

        if (Test-Path $ClientStdout) {
            Get-Content $ClientStdout
        }

        Write-Host ""
        Write-Host "===== STDERR resiliencia ====="

        if (Test-Path $ClientStderr) {
            Get-Content $ClientStderr
        }

        throw "La prueba de resiliencia fallo con codigo $ExitCode."
    }

    Write-Host "[OK] Cliente QSTS de resiliencia finalizado"

    Invoke-AwsCli ecs describe-services --cluster $Cluster --services $WorkerService --output json |
        Set-Content -Encoding utf8 (Join-Path $RunDir "worker_service_after_failover.json")

    Write-Host "[5] Ejecutando pruebas de seguridad y admision"
    python -m tools.evidence.security_cloud_evidence --base-url $BaseUrl --test-admission --output-root $RunDir
    if ($LASTEXITCODE -ne 0) { throw "Security evidence fallo." }
    $SecurityDir = Get-ChildItem -Path $RunDir -Directory | Where-Object { $_.Name -like "*_security" } | Sort-Object Name -Descending | Select-Object -First 1

    @{
        timestamp_utc = $Stamp
        base_url = $BaseUrl
        cluster = $Cluster
        worker_service = $WorkerService
        stopped_task = $TargetTask
        initial_worker_ip = $WorkerIp
    } | ConvertTo-Json -Depth 5 | Set-Content -Encoding utf8 (Join-Path $RunDir "manifest.json")

    $summaryArgs = @("-m", "tools.evidence.summarize_deliverable3", "--run-dir", $RunDir)
    if ($SecurityDir) { $summaryArgs += @("--security-dir", $SecurityDir.FullName) }
    python @summaryArgs
    if ($LASTEXITCODE -ne 0) { throw "Resumen Entregable 3 fallo." }

    Write-Host "[OK] Evidencia Entregable 3: $RunDir"
}
finally {
    if ($OwnSmokePassword) { Remove-Item Env:OPENDSS_SMOKE_PASSWORD -ErrorAction SilentlyContinue }
}
