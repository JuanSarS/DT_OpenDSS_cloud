param(
    [string]$Region = "us-east-2",
    [string]$Profile = "opendss-deployer",
    [string]$ProjectName = "opendss-thesis",
    [string]$Username = "admin"
)

$ErrorActionPreference = "Stop"

# ============================================================
# Rutas y configuracion general
# ============================================================

$Root = (
    Resolve-Path (
        Join-Path $PSScriptRoot ".."
    )
).Path

Set-Location $Root

$MainStack = "$ProjectName-main"

$Stamp = (
    Get-Date
).ToUniversalTime().ToString(
    "yyyyMMddTHHmmssZ"
)

$RunDir = Join-Path `
    $Root `
    "docs\evidence\deliverable_3\${Stamp}_resilience"

New-Item `
    -ItemType Directory `
    -Force `
    -Path $RunDir |
Out-Null

# ============================================================
# AWS CLI comun
# ============================================================

$AwsCommon = @(
    "--region"
    $Region
    "--no-cli-pager"
)

if ($Profile) {
    $AwsCommon += @(
        "--profile"
        $Profile
    )
}

function Invoke-AwsCli {
    param(
        [Parameter(
            ValueFromRemainingArguments = $true
        )]
        [string[]]$Arguments
    )

    $result = & aws.exe @AwsCommon @Arguments

    if ($LASTEXITCODE -ne 0) {
        throw (
            "AWS CLI fallo: aws " +
            ($Arguments -join " ")
        )
    }

    return $result
}

function Get-StackOutput {
    param(
        [string]$Key
    )

    $value = Invoke-AwsCli `
        cloudformation `
        describe-stacks `
        --stack-name $MainStack `
        --query "Stacks[0].Outputs[?OutputKey=='$Key'].OutputValue | [0]" `
        --output text

    return (
        $value |
        Out-String
    ).Trim()
}

# ============================================================
# Resolver infraestructura
# ============================================================

$BaseUrl = Get-StackOutput "ApplicationUrl"

if (
    -not $BaseUrl `
    -or `
    $BaseUrl -eq "None"
) {
    $CloudFrontDomain = Get-StackOutput "CloudFrontDomainName"

    if (
        -not $CloudFrontDomain `
        -or `
        $CloudFrontDomain -eq "None"
    ) {
        throw (
            "No se pudo resolver ApplicationUrl " +
            "ni CloudFrontDomainName."
        )
    }

    $BaseUrl = "https://$CloudFrontDomain"
}

$Cluster = Get-StackOutput "EcsClusterName"
$WorkerService = Get-StackOutput "WorkerServiceName"

if (
    -not $Cluster `
    -or `
    $Cluster -eq "None"
) {
    throw "No fue posible resolver EcsClusterName."
}

if (
    -not $WorkerService `
    -or `
    $WorkerService -eq "None"
) {
    throw "No fue posible resolver WorkerServiceName."
}

Write-Host ""
Write-Host "============================================"
Write-Host " OpenDSS Cloud - Entregable 3"
Write-Host " Seguridad + Resiliencia"
Write-Host "============================================"
Write-Host ""
Write-Host (
    "Esta prueba requiere despliegue con " +
    "-ResilienceMode para hacer visible el QSTS."
)
Write-Host "Base URL:       $BaseUrl"
Write-Host "Cluster:        $Cluster"
Write-Host "Worker service: $WorkerService"
Write-Host "Evidence:       $RunDir"
Write-Host ""

# ============================================================
# Passwords
# ============================================================

$OwnSmokePassword = $false
$OwnAdminPassword = $false
$OwnUser1Password = $false
$OwnUser2Password = $false

if (-not $env:OPENDSS_SMOKE_PASSWORD) {

    $secure = Read-Host `
        "Password de $Username" `
        -AsSecureString

    $credential = [pscredential]::new(
        $Username,
        $secure
    )

    $env:OPENDSS_SMOKE_PASSWORD = (
        $credential.GetNetworkCredential().Password
    )

    $OwnSmokePassword = $true
}

# La suite de seguridad utiliza OPENDSS_ADMIN_PASSWORD.
# Reutilizamos el password de admin capturado arriba.

if (-not $env:OPENDSS_ADMIN_PASSWORD) {

    $env:OPENDSS_ADMIN_PASSWORD = (
        $env:OPENDSS_SMOKE_PASSWORD
    )

    $OwnAdminPassword = $true
}

# ============================================================
# Python
# ============================================================

$PythonExe = (
    Get-Command python
).Source

if (-not $PythonExe) {
    throw "No se encontro python en PATH."
}

$Stdout = Join-Path `
    $RunDir `
    "resilience_client.stdout.log"

$Stderr = Join-Path `
    $RunDir `
    "resilience_client.stderr.log"

$ClientArgs = @(
    "-u"
    "-m"
    "tools.evidence.resilience_client"
    "--base-url"
    $BaseUrl
    "--username"
    $Username
    "--output-dir"
    $RunDir
    "--topology"
    "ieee123"
    "--duration-hours"
    "24"
    "--step-minutes"
    "1"
)

$process = $null
$securityProcess = $null
$summaryProcess = $null

try {

    # ========================================================
    # 0. Validar AWS
    # ========================================================

    Write-Host "[0] Validando sesion AWS"

    $IdentityJson = Invoke-AwsCli `
        sts `
        get-caller-identity `
        --output json

    $IdentityJson |
    Set-Content `
        -Encoding utf8 `
        (
            Join-Path `
                $RunDir `
                "aws_identity.json"
        )

    Write-Host "[OK] Sesion AWS activa"

    # ========================================================
    # 0.1 Validar estado inicial de ECS
    # ========================================================

    Write-Host "[0.1] Validando servicio worker"

    $WorkerServiceBeforeJson = Invoke-AwsCli `
        ecs `
        describe-services `
        --cluster $Cluster `
        --services $WorkerService `
        --output json

    $WorkerServiceBeforeJson |
    Set-Content `
        -Encoding utf8 `
        (
            Join-Path `
                $RunDir `
                "worker_service_before_failover.json"
        )

    $WorkerServiceBefore = (
        $WorkerServiceBeforeJson |
        Out-String
    ) | ConvertFrom-Json

    if (
        -not $WorkerServiceBefore.services `
        -or `
        $WorkerServiceBefore.services.Count -eq 0
    ) {
        throw (
            "AWS no devolvio el servicio worker " +
            "'$WorkerService'."
        )
    }

    $WorkerState = $WorkerServiceBefore.services[0]

    $DesiredWorkers = [int]$WorkerState.desiredCount
    $RunningWorkers = [int]$WorkerState.runningCount
    $PendingWorkers = [int]$WorkerState.pendingCount

    Write-Host (
        "Workers ECS: " +
        "desired=$DesiredWorkers " +
        "running=$RunningWorkers " +
        "pending=$PendingWorkers"
    )

    if ($RunningWorkers -lt 3) {
        throw (
            "La prueba de resiliencia requiere al menos " +
            "3 workers RUNNING. Actualmente hay " +
            "$RunningWorkers."
        )
    }

    # ========================================================
    # 1. Iniciar cliente QSTS
    # ========================================================

    Write-Host "[1] Iniciando QSTS de resiliencia"

    $process = Start-Process `
        -FilePath $PythonExe `
        -ArgumentList $ClientArgs `
        -PassThru `
        -NoNewWindow `
        -RedirectStandardOutput $Stdout `
        -RedirectStandardError $Stderr

    $SessionFile = Join-Path `
        $RunDir `
        "resilience_session.json"

    $ReadyFile = Join-Path `
        $RunDir `
        "ready_to_kill.flag"

    # Esperamos hasta 180 segundos a que el cliente indique
    # que el QSTS esta ejecutandose y listo para inyectar falla.

    $Ready = $false

    for ($i = 0; $i -lt 180; $i++) {

        if ($process.HasExited) {

            Write-Host ""
            Write-Host "===== STDOUT resiliencia ====="

            Get-Content `
                $Stdout `
                -ErrorAction SilentlyContinue

            Write-Host ""
            Write-Host "===== STDERR resiliencia ====="

            Get-Content `
                $Stderr `
                -ErrorAction SilentlyContinue

            throw (
                "El cliente de resiliencia termino antes " +
                "de la inyeccion de falla."
            )
        }

        if (
            (Test-Path $SessionFile) `
            -and `
            (Test-Path $ReadyFile)
        ) {
            $Ready = $true
            break
        }

        Start-Sleep -Seconds 1
    }

    if (-not $Ready) {
        throw (
            "No se recibio progreso a tiempo para " +
            "inyectar la falla."
        )
    }

    # ========================================================
    # 2. Obtener worker propietario
    # ========================================================

    $session = Get-Content `
        $SessionFile `
        -Raw |
    ConvertFrom-Json

    if (-not $session.worker_identity) {
        throw (
            "resilience_session.json no contiene " +
            "worker_identity."
        )
    }

    $uri = [uri]$session.worker_identity
    $WorkerIp = $uri.Host

    if (-not $WorkerIp) {
        throw (
            "No fue posible obtener la IP desde " +
            "worker_identity: $($session.worker_identity)"
        )
    }

    Write-Host (
        "[2] Worker propietario detectado: " +
        $WorkerIp
    )

    # ========================================================
    # 2.1 Obtener ARNs worker
    #
    # IMPORTANTE:
    # No usamos ConvertFrom-Json para taskArns porque
    # Windows PowerShell 5 puede dejar el array JSON
    # anidado como un unico elemento.
    #
    # Pedimos texto plano y separamos explicitamente
    # por espacios, tabs y saltos de linea.
    # ========================================================

    $TaskArnsRaw = Invoke-AwsCli `
        ecs `
        list-tasks `
        --cluster $Cluster `
        --service-name $WorkerService `
        --desired-status RUNNING `
        --query "taskArns[]" `
        --output text

    $TaskArnsText = (
        $TaskArnsRaw |
        Out-String
    ).Trim()

    if (-not $TaskArnsText) {
        throw "No hay tasks worker RUNNING."
    }

    $taskArns = @(
        $TaskArnsText `
            -split "\s+" |
        Where-Object {
            $_ `
            -and `
            $_ -match "^arn:aws.*:ecs:"
        }
    )

    if ($taskArns.Count -eq 0) {
        throw (
            "No fue posible obtener ARN validas " +
            "de las tasks worker."
        )
    }

    Write-Host (
        "[2.1] Tasks worker RUNNING: " +
        $taskArns.Count
    )

    foreach ($TaskArn in $taskArns) {
        Write-Host "      $TaskArn"
    }

    # ========================================================
    # 2.2 Mapear IP privada a task ECS
    # ========================================================

    $TasksBefore = @()
    $TaskMappings = @()
    $TargetTask = $null

    foreach ($TaskArn in $taskArns) {

        # Garantia adicional: cada iteracion debe contener
        # exactamente una ARN, nunca una coleccion.

        $TaskArn = (
            $TaskArn |
            Out-String
        ).Trim()

        if (
            -not $TaskArn `
            -or `
            $TaskArn -notmatch "^arn:aws.*:ecs:"
        ) {
            throw (
                "ARN ECS invalida detectada: " +
                "'$TaskArn'"
            )
        }

        Write-Host ""
        Write-Host (
            "[2.2] Inspeccionando task: " +
            $TaskArn
        )

        $OneTaskJson = Invoke-AwsCli `
            ecs `
            describe-tasks `
            --cluster $Cluster `
            --tasks $TaskArn `
            --output json

        $OneTaskPayload = (
            $OneTaskJson |
            Out-String
        ) | ConvertFrom-Json

        if (
            -not $OneTaskPayload.tasks `
            -or `
            $OneTaskPayload.tasks.Count -eq 0
        ) {
            Write-Host (
                "      AWS no devolvio informacion " +
                "para esta task."
            )
            continue
        }

        foreach ($Task in @($OneTaskPayload.tasks)) {

            $TasksBefore += $Task

            $TaskIp = $null

            foreach (
                $Attachment in @($Task.attachments)
            ) {

                foreach (
                    $Detail in @($Attachment.details)
                ) {

                    if (
                        $Detail.name `
                        -eq `
                        "privateIPv4Address"
                    ) {
                        $TaskIp = $Detail.value
                        break
                    }
                }

                if ($TaskIp) {
                    break
                }
            }

            $TaskMappings += [pscustomobject]@{
                task_arn = $Task.taskArn
                private_ipv4 = $TaskIp
                last_status = $Task.lastStatus
                desired_status = $Task.desiredStatus
            }

            Write-Host (
                "      IP privada: " +
                $TaskIp
            )

            if (
                $TaskIp `
                -and `
                $TaskIp -eq $WorkerIp
            ) {
                $TargetTask = $Task.taskArn

                Write-Host (
                    "[OK] Task propietaria encontrada."
                )

                break
            }
        }

        if ($TargetTask) {
            break
        }
    }

    # Guardamos evidencia de todas las tasks revisadas.

    @{
        worker_ip = $WorkerIp
        mappings = $TaskMappings
        tasks = $TasksBefore
    } |
    ConvertTo-Json -Depth 30 |
    Set-Content `
        -Encoding utf8 `
        (
            Join-Path `
                $RunDir `
                "worker_tasks_before_kill.json"
        )

    $TaskMappings |
    ConvertTo-Json -Depth 10 |
    Set-Content `
        -Encoding utf8 `
        (
            Join-Path `
                $RunDir `
                "worker_task_mappings.json"
        )

    if (-not $TargetTask) {

        Write-Host ""
        Write-Host "Mapeo observado:"

        foreach ($Mapping in $TaskMappings) {
            Write-Host (
                "  " +
                $Mapping.private_ipv4 +
                " -> " +
                $Mapping.task_arn
            )
        }

        throw (
            "No fue posible mapear la IP " +
            "$WorkerIp a una task ECS."
        )
    }

    Write-Host ""
    Write-Host (
        "[OK] Task propietaria: " +
        $TargetTask
    )

    # ========================================================
    # 3. Inyectar falla
    # ========================================================

    Write-Host ""
    Write-Host (
        "[3] Deteniendo task para demostrar failover"
    )

    Invoke-AwsCli `
        ecs `
        stop-task `
        --cluster $Cluster `
        --task $TargetTask `
        --reason "OpenDSS thesis resilience evidence" `
        --output json |
    Set-Content `
        -Encoding utf8 `
        (
            Join-Path `
                $RunDir `
                "stopped_task.json"
        )

    # ========================================================
    # 4. Esperar final del QSTS
    # ========================================================

    Write-Host ""
    Write-Host (
        "[4] Esperando final del cliente QSTS"
    )

    # 5 minutos maximo.
    $Finished = $process.WaitForExit(
        300000
    )

    if (-not $Finished) {

        Write-Host (
            "[cleanup] Timeout del cliente QSTS."
        )

        Stop-Process `
            -Id $process.Id `
            -Force `
            -ErrorAction SilentlyContinue

        throw (
            "El cliente QSTS no termino dentro " +
            "de 300 segundos."
        )
    }

    # Segunda llamada para asegurar que Windows haya
    # terminado de vaciar stdout/stderr redirigidos.
    $process.WaitForExit()
$process.Refresh()

Write-Host ""
Write-Host "===== STDOUT resiliencia ====="

Get-Content `
    $Stdout `
    -ErrorAction SilentlyContinue

if (Test-Path $Stderr) {

    $StderrText = Get-Content `
        $Stderr `
        -Raw `
        -ErrorAction SilentlyContinue

    if ($StderrText) {

        Write-Host ""
        Write-Host "===== STDERR resiliencia ====="
        Write-Host $StderrText
    }
}

    $ResilienceResultFile = Join-Path `
        $RunDir `
        "resilience_result.json"

    if (-not (Test-Path $ResilienceResultFile)) {
        throw (
            "El cliente de resiliencia termino sin generar " +
            "resilience_result.json. Revisa stdout/stderr."
        )
    }

    $ResilienceResult = Get-Content `
        $ResilienceResultFile `
        -Raw |
    ConvertFrom-Json

    if (-not $ResilienceResult.passed) {
        throw (
            "La prueba de resiliencia genero resultado FAIL."
        )
    }

    if (-not $ResilienceResult.observed_restart) {
        throw (
            "La simulacion termino, pero no se observo " +
            "reinicio QSTS despues de la perdida del worker."
        )
    }

    Write-Host (
        "[OK] Cliente QSTS de resiliencia finalizado"
    )

    # ========================================================
    # 4.1 Esperar recuperacion ECS
    # ========================================================

    Write-Host ""
    Write-Host (
        "[4.1] Esperando recuperacion del servicio ECS"
    )

    Invoke-AwsCli `
        ecs `
        wait `
        services-stable `
        --cluster $Cluster `
        --services $WorkerService

    Write-Host (
        "[OK] Servicio worker nuevamente estable"
    )

    Invoke-AwsCli `
        ecs `
        describe-services `
        --cluster $Cluster `
        --services $WorkerService `
        --output json |
    Set-Content `
        -Encoding utf8 `
        (
            Join-Path `
                $RunDir `
                "worker_service_after_failover.json"
        )

    # ========================================================
    # 5. Evidencia de seguridad
    # ========================================================

    Write-Host ""
    Write-Host (
        "[5] Ejecutando pruebas de seguridad y admision"
    )

    if (-not $env:OPENDSS_USER1_PASSWORD) {

        $secureUser1 = Read-Host `
            "Password de user1" `
            -AsSecureString

        $credentialUser1 = [pscredential]::new(
            "user1",
            $secureUser1
        )

        $env:OPENDSS_USER1_PASSWORD = (
            $credentialUser1.GetNetworkCredential().Password
        )

        $OwnUser1Password = $true
    }

    if (-not $env:OPENDSS_USER2_PASSWORD) {

        $secureUser2 = Read-Host `
            "Password de user2" `
            -AsSecureString

        $credentialUser2 = [pscredential]::new(
            "user2",
            $secureUser2
        )

        $env:OPENDSS_USER2_PASSWORD = (
            $credentialUser2.GetNetworkCredential().Password
        )

        $OwnUser2Password = $true
    }

    $SecurityStdout = Join-Path `
        $RunDir `
        "security.stdout.log"

    $SecurityStderr = Join-Path `
        $RunDir `
        "security.stderr.log"

    $SecurityArgs = @(
        "-m"
        "tools.evidence.security_cloud_evidence"
        "--base-url"
        $BaseUrl
        "--test-admission"
        "--output-root"
        $RunDir
    )

    $securityProcess = Start-Process `
        -FilePath $PythonExe `
        -ArgumentList $SecurityArgs `
        -PassThru `
        -Wait `
        -NoNewWindow `
        -RedirectStandardOutput $SecurityStdout `
        -RedirectStandardError $SecurityStderr

    Write-Host ""
    Write-Host "===== STDOUT seguridad ====="

    Get-Content `
        $SecurityStdout `
        -ErrorAction SilentlyContinue

    if (Test-Path $SecurityStderr) {

        $SecurityStderrText = Get-Content `
            $SecurityStderr `
            -Raw `
            -ErrorAction SilentlyContinue

        if ($SecurityStderrText) {

            Write-Host ""
            Write-Host "===== STDERR seguridad ====="
            Write-Host $SecurityStderrText
        }
    }

    if ($securityProcess.ExitCode -ne 0) {
        throw (
            "Security evidence fallo con codigo " +
            "$($securityProcess.ExitCode)."
        )
    }

    Write-Host (
        "[OK] Pruebas de seguridad finalizadas"
    )

    # ========================================================
    # Localizar carpeta generada por security evidence
    # ========================================================

    $SecurityDir = Get-ChildItem `
        -Path $RunDir `
        -Directory |
    Where-Object {
        $_.Name -like "*_security"
    } |
    Sort-Object `
        Name `
        -Descending |
    Select-Object `
        -First 1

    # ========================================================
    # Manifest general
    # ========================================================

    @{
        timestamp_utc = $Stamp
        base_url = $BaseUrl
        cluster = $Cluster
        worker_service = $WorkerService
        stopped_task = $TargetTask
        initial_worker_ip = $WorkerIp
        initial_desired_workers = $DesiredWorkers
        initial_running_workers = $RunningWorkers
        result = "PASS"
    } |
    ConvertTo-Json -Depth 10 |
    Set-Content `
        -Encoding utf8 `
        (
            Join-Path `
                $RunDir `
                "manifest.json"
        )

    # ========================================================
    # 6. Resumen Entregable 3
    # ========================================================

    Write-Host ""
    Write-Host (
        "[6] Generando resumen Entregable 3"
    )

    $SummaryArgs = @(
        "-m"
        "tools.evidence.summarize_deliverable3"
        "--run-dir"
        $RunDir
    )

    if ($SecurityDir) {

        $SummaryArgs += @(
            "--security-dir"
            $SecurityDir.FullName
        )
    }

    $summaryProcess = Start-Process `
        -FilePath $PythonExe `
        -ArgumentList $SummaryArgs `
        -PassThru `
        -Wait `
        -NoNewWindow

    if ($summaryProcess.ExitCode -ne 0) {
        throw (
            "Resumen Entregable 3 fallo con codigo " +
            "$($summaryProcess.ExitCode)."
        )
    }

    Write-Host ""
    Write-Host "============================================"
    Write-Host " ENTREGABLE 3 FINALIZADO"
    Write-Host "============================================"
    Write-Host ""
    Write-Host (
        "[OK] Evidencia Entregable 3: " +
        $RunDir
    )
    Write-Host ""

}
finally {

    # ========================================================
    # Cleanup
    # ========================================================

    if (
        $process `
        -and `
        -not $process.HasExited
    ) {

        Write-Host (
            "[cleanup] Deteniendo cliente Python " +
            "de resiliencia que quedo activo."
        )

        Stop-Process `
            -Id $process.Id `
            -Force `
            -ErrorAction SilentlyContinue
    }

    if (
        $securityProcess `
        -and `
        -not $securityProcess.HasExited
    ) {
        Stop-Process `
            -Id $securityProcess.Id `
            -Force `
            -ErrorAction SilentlyContinue
    }

    if (
        $summaryProcess `
        -and `
        -not $summaryProcess.HasExited
    ) {
        Stop-Process `
            -Id $summaryProcess.Id `
            -Force `
            -ErrorAction SilentlyContinue
    }

    if ($OwnSmokePassword) {
        Remove-Item `
            Env:OPENDSS_SMOKE_PASSWORD `
            -ErrorAction SilentlyContinue
    }

    if ($OwnAdminPassword) {
        Remove-Item `
            Env:OPENDSS_ADMIN_PASSWORD `
            -ErrorAction SilentlyContinue
    }

    if ($OwnUser1Password) {
        Remove-Item `
            Env:OPENDSS_USER1_PASSWORD `
            -ErrorAction SilentlyContinue
    }

    if ($OwnUser2Password) {
        Remove-Item `
            Env:OPENDSS_USER2_PASSWORD `
            -ErrorAction SilentlyContinue
    }
}