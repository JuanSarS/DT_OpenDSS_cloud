param(
    [string]$Region = "us-east-2",
    [string]$Profile = "opendss-deployer",
    [string]$ProjectName = "opendss-thesis"
)
$AwsCliNew = "$env:LOCALAPPDATA\Programs\Amazon\AWSCLIV2"                        
$env:Path = "$AwsCliNew;$env:Path"            

$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $Root

$BootstrapStack = "$ProjectName-bootstrap"
$MainStack = "$ProjectName-main"
$EvidenceStamp = (Get-Date).ToUniversalTime().ToString("yyyyMMddTHHmmssZ")
$EvidenceDir = Join-Path $Root "docs\evidence\deployments\${EvidenceStamp}_destroy"
New-Item -ItemType Directory -Force -Path $EvidenceDir | Out-Null

$AwsCommon = @("--region", $Region, "--no-cli-pager")
if ($Profile) { $AwsCommon += @("--profile", $Profile) }

function Invoke-AwsCli {
    param([Parameter(ValueFromRemainingArguments=$true)][string[]]$Arguments)
    & aws @AwsCommon @Arguments
}

function Test-StackExists {
    param([string]$Name)
    & aws @AwsCommon cloudformation describe-stacks --stack-name $Name *> $null
    return $LASTEXITCODE -eq 0
}

Write-Host ""
Write-Host "============================================"
Write-Host " OpenDSS Cloud - destruccion TOTAL AWS"
Write-Host "============================================"
Write-Host "Project: $ProjectName"
Write-Host "Region:  $Region"
Write-Host ""

$identity = Invoke-AwsCli sts get-caller-identity --output json
if ($LASTEXITCODE -ne 0) { 
    Write-Host "No hay autenticacion AWS valida." 
    aws login --profile opendss-deployer
    }
    
$identity | Set-Content -Encoding utf8 (Join-Path $EvidenceDir "aws_identity.json")

if (Test-StackExists $MainStack) {
    Write-Host "[1] Guardando inventario final del stack principal"
    Invoke-AwsCli cloudformation describe-stack-resources --stack-name $MainStack --output json |
        Set-Content -Encoding utf8 (Join-Path $EvidenceDir "main_resources_before_delete.json")

    Write-Host "[2] Eliminando stack principal: $MainStack"
    Invoke-AwsCli cloudformation delete-stack --stack-name $MainStack
    if ($LASTEXITCODE -ne 0) { throw "No fue posible iniciar delete-stack principal." }
    & aws @AwsCommon cloudformation wait stack-delete-complete --stack-name $MainStack
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Eventos de CloudFormation:"
        Invoke-AwsCli cloudformation describe-stack-events --stack-name $MainStack --output table
        throw "El stack principal no pudo eliminarse completamente."
    }
} else {
    Write-Host "[1-2] Stack principal no existe."
}

if (Test-StackExists $BootstrapStack) {
    Write-Host "[3] Guardando inventario bootstrap"
    Invoke-AwsCli cloudformation describe-stack-resources --stack-name $BootstrapStack --output json |
        Set-Content -Encoding utf8 (Join-Path $EvidenceDir "bootstrap_resources_before_delete.json")

    Write-Host "[4] Eliminando bootstrap: ECR + secretos"
    Invoke-AwsCli cloudformation delete-stack --stack-name $BootstrapStack
    if ($LASTEXITCODE -ne 0) { throw "No fue posible iniciar delete-stack bootstrap." }
    & aws @AwsCommon cloudformation wait stack-delete-complete --stack-name $BootstrapStack
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Eventos de CloudFormation:"
        Invoke-AwsCli cloudformation describe-stack-events --stack-name $BootstrapStack --output table
        throw "El bootstrap no pudo eliminarse completamente."
    }
} else {
    Write-Host "[3-4] Bootstrap no existe."
}

Write-Host "[5] Verificando recursos etiquetados que hayan quedado"
$leftovers = Invoke-AwsCli resourcegroupstaggingapi get-resources `
    --tag-filters "Key=Project,Values=$ProjectName" `
    --output json
$leftovers | Set-Content -Encoding utf8 (Join-Path $EvidenceDir "tagged_leftovers.json")

$parsed = $leftovers | ConvertFrom-Json
if ($parsed.ResourceTagMappingList.Count -gt 0) {
    Write-Warning "AWS aun reporta recursos etiquetados. Revisa tagged_leftovers.json. Algunos recursos globales pueden tardar en desaparecer de los indices."
} else {
    Write-Host "[OK] No se reportan recursos etiquetados restantes."
}

Write-Host ""
Write-Host "============================================"
Write-Host " AWS desmontado"
Write-Host "============================================"
Write-Host "Evidence: $EvidenceDir"
