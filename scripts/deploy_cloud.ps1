param(
    [string]$Region = "us-east-2",
    [string]$Profile = "opendss-deployer",
    [string]$ProjectName = "opendss-thesis",
    [int]$WorkerCount = 3,
    [int]$WorkerMinCount = 1,
    [int]$WorkerMaxCount = 6,
    [int]$WorkerCpuTarget = 60,
    [int]$MaxConcurrentPerUser = 2,
    [int]$MaxConcurrentJobs = 8,
    [switch]$PerformanceMode,
    [switch]$ResilienceMode,
    [switch]$ReuseImages,
    [switch]$SkipSmoke
)

$ErrorActionPreference = "Stop"

$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $Root

$BootstrapStack = "$ProjectName-bootstrap"
$MainStack = "$ProjectName-main"
$EvidenceStamp = (Get-Date).ToUniversalTime().ToString("yyyyMMddTHHmmssZ")
$EvidenceDir = Join-Path $Root "docs\evidence\deployments\$EvidenceStamp"

New-Item -ItemType Directory -Force -Path $EvidenceDir | Out-Null

$AwsCommon = @("--region", $Region, "--no-cli-pager")
if ($Profile) {
    $AwsCommon += @("--profile", $Profile)
}

function Invoke-Aws {
    param(
        [Parameter(ValueFromRemainingArguments = $true)]
        [string[]]$Arguments
    )

    & aws @AwsCommon @Arguments

    if ($LASTEXITCODE -ne 0) {
        throw "AWS CLI failed: aws $($Arguments -join ' ')"
    }
}

function Get-StackOutput {
    param(
        [string]$StackName,
        [string]$Key
    )

    $value = Invoke-Aws cloudformation describe-stacks `
        --stack-name $StackName `
        --query "Stacks[0].Outputs[?OutputKey=='$Key'].OutputValue | [0]" `
        --output text

    return ($value | Out-String).Trim()
}

function Test-EcrImageExists {
    param(
        [string]$RepositoryName,
        [string]$Tag
    )

    # No usamos describe-images con imageTag porque AWS devuelve
    # ImageNotFoundException cuando la imagen todavía no existe.
    # Con $ErrorActionPreference = "Stop", PowerShell convierte ese
    # caso esperado en una excepción y aborta el despliegue.
    #
    # list-images devuelve una lista vacía si el tag aún no existe.

    $tagsOutput = & aws @AwsCommon ecr list-images `
        --repository-name $RepositoryName `
        --filter "tagStatus=TAGGED" `
        --query "imageIds[].imageTag" `
        --output text

    if ($LASTEXITCODE -ne 0) {
        throw "No fue posible consultar las imagenes del repositorio ECR '$RepositoryName'."
    }

    $tagsText = (
        $tagsOutput |
        Out-String
    ).Trim()

    if (-not $tagsText) {
        return $false
    }

    $tags = $tagsText -split "\s+"

    return $tags -contains $Tag
}

Write-Host ""
Write-Host "============================================"
Write-Host " OpenDSS Cloud - despliegue AWS completo"
Write-Host "============================================"
Write-Host "Region:  $Region"
Write-Host "Project: $ProjectName"
Write-Host "Workers: $WorkerCount"
Write-Host ""

foreach ($command in @("aws", "docker", "git")) {
    if (-not (Get-Command $command -ErrorAction SilentlyContinue)) {
        throw "No se encuentra '$command' en PATH."
    }
}

Write-Host "[1] Validando identidad AWS"

$identity = Invoke-Aws sts get-caller-identity --output json
$identity | Set-Content -Encoding utf8 (Join-Path $EvidenceDir "aws_identity.json")
Write-Host $identity

Write-Host "[2] Validando Docker"

docker info *> $null
if ($LASTEXITCODE -ne 0) {
    throw "Docker Desktop no esta disponible."
}

Write-Host "[3] Validando repositorio Git"

$GitSha = (git rev-parse --short HEAD).Trim()
if ($LASTEXITCODE -ne 0) {
    throw "No fue posible obtener Git SHA."
}

# Los archivos de evidencia se generan después de pruebas/despliegues
# y no deben impedir actualizar la misma versión comprometida del código.
$dirty = git status --porcelain -- . ":(exclude)docs/evidence/**"

if ($dirty) {
    Write-Host $dirty
    throw "El codigo/configuracion tiene cambios sin commit. Haz commit antes de desplegar AWS."
}

Write-Host "Git SHA: $GitSha"

$AuthUsersPath = Join-Path $Root "secrets\local\auth_users.json"

if (-not (Test-Path $AuthUsersPath)) {
    Write-Host "No existe secrets/local/auth_users.json; ejecutando inicializador local."

    python .\scripts\init_local_secrets.py

    if ($LASTEXITCODE -ne 0 -or -not (Test-Path $AuthUsersPath)) {
        throw "No fue posible crear auth_users.json."
    }
}

Write-Host "[4] Desplegando bootstrap: ECR + secretos"

Invoke-Aws cloudformation deploy `
    --template-file .\infra\aws\cloudformation\bootstrap.yaml `
    --stack-name $BootstrapStack `
    --parameter-overrides "ProjectName=$ProjectName" `
    --tags "Project=$ProjectName" "Purpose=thesis"

$ApiRepo = Get-StackOutput $BootstrapStack "ApiRepositoryUri"
$WorkerRepo = Get-StackOutput $BootstrapStack "WorkerRepositoryUri"
$JwtSecretArn = Get-StackOutput $BootstrapStack "JwtSecretArn"
$WorkerTokenArn = Get-StackOutput $BootstrapStack "WorkerSharedTokenSecretArn"
$AuthUsersArn = Get-StackOutput $BootstrapStack "AuthUsersSecretArn"

Write-Host "[5] Sincronizando directorio de usuarios con Secrets Manager"

$AuthUsersCliPath = ($AuthUsersPath -replace "\\", "/")

Invoke-Aws secretsmanager put-secret-value `
    --secret-id $AuthUsersArn `
    --secret-string "file://$AuthUsersCliPath" `
    *> (Join-Path $EvidenceDir "auth_users_secret_update.json")

$AccountId = (
    Invoke-Aws sts get-caller-identity `
        --query Account `
        --output text |
    Out-String
).Trim()

$Registry = "$AccountId.dkr.ecr.$Region.amazonaws.com"

$ApiImage = "$ApiRepo`:$GitSha"
$WorkerImage = "$WorkerRepo`:$GitSha"

$ApiRepoName = ($ApiRepo -split "/")[-1]
$WorkerRepoName = ($WorkerRepo -split "/")[-1]

Write-Host "[6] Preparando autenticacion temporal Docker -> ECR"

$DockerEcrConfig = Join-Path `
    $env:TEMP `
    "opendss-ecr-docker-$PID"

$EcrAuthToken = $null
$DockerConfig = $null

try {
    Remove-Item `
        $DockerEcrConfig `
        -Recurse `
        -Force `
        -ErrorAction SilentlyContinue

    New-Item `
        -ItemType Directory `
        -Force `
        -Path $DockerEcrConfig |
    Out-Null

    $EcrAuthToken = (
        & aws `
            @AwsCommon `
            ecr `
            get-authorization-token `
            --query "authorizationData[0].authorizationToken" `
            --output text
    ).Trim()

    if (
        $LASTEXITCODE -ne 0 `
        -or `
        -not $EcrAuthToken
    ) {
        throw "No fue posible obtener el token de autorizacion ECR."
    }

    $DockerConfig = @{
        auths = @{
            $Registry = @{
                auth = $EcrAuthToken
            }
        }
    }

    $DockerConfig |
    ConvertTo-Json -Depth 5 |
    Set-Content `
        -Path (Join-Path $DockerEcrConfig "config.json") `
        -Encoding ascii

    Write-Host "[OK] Configuracion ECR temporal creada"

    $ApiExists = Test-EcrImageExists $ApiRepoName $GitSha

    if (-not $ApiExists) {
        Write-Host "[7] Build + push API image"

        docker build `
            -f .\services\api_manager\Dockerfile `
            -t $ApiImage `
            .

        if ($LASTEXITCODE -ne 0) {
            throw "Build API fallo."
        }

        docker `
            --config $DockerEcrConfig `
            push `
            $ApiImage

        if ($LASTEXITCODE -ne 0) {
            throw "Push API fallo."
        }
    }
    else {
        Write-Host "[7] API image ya existe en ECR: $ApiImage"
    }

    $WorkerExists = Test-EcrImageExists $WorkerRepoName $GitSha

    if (-not $WorkerExists) {
        Write-Host "[8] Build + push worker image"

        docker build `
            -f .\services\simulation_worker\Dockerfile `
            -t $WorkerImage `
            .

        if ($LASTEXITCODE -ne 0) {
            throw "Build worker fallo."
        }

        docker `
            --config $DockerEcrConfig `
            push `
            $WorkerImage

        if ($LASTEXITCODE -ne 0) {
            throw "Push worker fallo."
        }
    }
    else {
        Write-Host "[8] Worker image ya existe en ECR: $WorkerImage"
    }
}
finally {
    Write-Host "[8.1] Limpiando credenciales temporales ECR"

    if ($DockerEcrConfig) {
        Remove-Item `
            $DockerEcrConfig `
            -Recurse `
            -Force `
            -ErrorAction SilentlyContinue
    }

    $EcrAuthToken = $null
    $DockerConfig = $null
}

$imageManifest = [ordered]@{
    timestamp_utc = $EvidenceStamp
    git_sha = $GitSha
    registry = $Registry
    api_image = $ApiImage
    worker_image = $WorkerImage
}

$imageManifest |
ConvertTo-Json -Depth 5 |
Set-Content `
    -Encoding utf8 `
    (Join-Path $EvidenceDir "image_manifest.json")

Write-Host "[9] Resolviendo AWS managed prefix list de CloudFront"

$PrefixListId = (
    Invoke-Aws ec2 describe-managed-prefix-lists `
        --filters "Name=prefix-list-name,Values=com.amazonaws.global.cloudfront.origin-facing" `
        --query "PrefixLists[0].PrefixListId" `
        --output text |
    Out-String
).Trim()

if (-not $PrefixListId -or $PrefixListId -eq "None") {
    throw "No fue posible resolver la prefix list de CloudFront origin-facing."
}

$Admission = "true"
$RateLimit = "true"
$RateRequests = 120
$WorkerDelay = 0

if ($PerformanceMode) {
    $Admission = "false"
    $RateLimit = "false"
    $WorkerCpuTarget = 20
    $MaxConcurrentPerUser = 32
    $MaxConcurrentJobs = 64
}

if ($ResilienceMode) {
    $WorkerDelay = 75
}

Write-Host "[10] Validando plantilla principal"

Invoke-Aws cloudformation validate-template `
    --template-body file://infra/aws/cloudformation/main.yaml `
    --output json |
Set-Content `
    -Encoding utf8 `
    (Join-Path $EvidenceDir "template_validation.json")

Write-Host "[11] Desplegando infraestructura principal"

Invoke-Aws cloudformation deploy `
    --template-file .\infra\aws\cloudformation\main.yaml `
    --stack-name $MainStack `
    --capabilities CAPABILITY_IAM `
    --parameter-overrides `
        "ProjectName=$ProjectName" `
        "ApiImageUri=$ApiImage" `
        "WorkerImageUri=$WorkerImage" `
        "JwtSecretArn=$JwtSecretArn" `
        "WorkerSharedTokenSecretArn=$WorkerTokenArn" `
        "AuthUsersSecretArn=$AuthUsersArn" `
        "CloudFrontPrefixListId=$PrefixListId" `
        "WorkerDesiredCount=$WorkerCount" `
        "WorkerMinCount=$WorkerMinCount" `
        "WorkerMaxCount=$WorkerMaxCount" `
        "WorkerCpuTarget=$WorkerCpuTarget" `
        "MaxConcurrentSimulationsPerUser=$MaxConcurrentPerUser" `
        "MaxConcurrentJobs=$MaxConcurrentJobs" `
        "AdmissionControlEnabled=$Admission" `
        "RateLimitEnabled=$RateLimit" `
        "RateLimitRequests=$RateRequests" `
        "WorkerTestProgressDelayMs=$WorkerDelay" `
    --tags `
        "Project=$ProjectName" `
        "GitSha=$GitSha" `
        "Purpose=thesis"

$Cluster = Get-StackOutput $MainStack "EcsClusterName"
$ApiService = Get-StackOutput $MainStack "ApiServiceName"
$WorkerService = Get-StackOutput $MainStack "WorkerServiceName"
$CloudFrontDomain = Get-StackOutput $MainStack "CloudFrontDomainName"
$DistributionId = Get-StackOutput $MainStack "CloudFrontDistributionId"

$BaseUrl = "https://$CloudFrontDomain"

Write-Host "[12] Esperando estabilidad de servicios ECS"

Invoke-Aws ecs wait services-stable `
    --cluster $Cluster `
    --services $ApiService $WorkerService

Invoke-Aws cloudformation describe-stacks `
    --stack-name $BootstrapStack `
    --output json |
Set-Content `
    -Encoding utf8 `
    (Join-Path $EvidenceDir "bootstrap_stack.json")

Invoke-Aws cloudformation describe-stacks `
    --stack-name $MainStack `
    --output json |
Set-Content `
    -Encoding utf8 `
    (Join-Path $EvidenceDir "main_stack.json")

Invoke-Aws ecs describe-services `
    --cluster $Cluster `
    --services $ApiService $WorkerService `
    --output json |
Set-Content `
    -Encoding utf8 `
    (Join-Path $EvidenceDir "ecs_services.json")

Invoke-Aws cloudfront get-distribution `
    --id $DistributionId `
    --output json |
Set-Content `
    -Encoding utf8 `
    (Join-Path $EvidenceDir "cloudfront_distribution.json")

$manifest = [ordered]@{
    timestamp_utc = $EvidenceStamp
    project = $ProjectName
    region = $Region
    git_sha = $GitSha
    bootstrap_stack = $BootstrapStack
    main_stack = $MainStack
    base_url = $BaseUrl
    worker_desired_count = $WorkerCount
    worker_min_count = $WorkerMinCount
    worker_max_count = $WorkerMaxCount
    worker_cpu_target = $WorkerCpuTarget
    performance_mode = [bool]$PerformanceMode
    resilience_mode = [bool]$ResilienceMode
}

$manifest |
ConvertTo-Json -Depth 5 |
Set-Content `
    -Encoding utf8 `
    (Join-Path $EvidenceDir "deploy_manifest.json")

if (-not $SkipSmoke) {
    Write-Host "[13] Smoke cloud"

    & .\scripts\smoke_cloud.ps1 `
        -BaseUrl $BaseUrl `
        -Region $Region `
        -Profile $Profile `
        -ProjectName $ProjectName

    if ($LASTEXITCODE -ne 0) {
        throw "Smoke cloud fallo."
    }
}

Write-Host ""
Write-Host "============================================"
Write-Host " OpenDSS Cloud desplegado"
Write-Host "============================================"
Write-Host "URL:      $BaseUrl"
Write-Host "Region:   $Region"
Write-Host "Git SHA:  $GitSha"
Write-Host "Workers:  $WorkerCount (autoscaling $WorkerMinCount..$WorkerMaxCount)"
Write-Host "Evidence: $EvidenceDir"
Write-Host ""
Write-Host "Para eliminar TODO:"

$DestroyCommand = ".\scripts\destroy_cloud.ps1 -Region $Region -ProjectName $ProjectName"

if ($Profile) {
    $DestroyCommand += " -Profile $Profile"
}

Write-Host $DestroyCommand
