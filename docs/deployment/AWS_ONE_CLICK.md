# AWS ONE CLICK — OpenDSS Cloud

## Objetivo

Esta guía deja el laboratorio AWS completamente reproducible. Después de la configuración inicial de credenciales en el PC, la operación normal es:

```powershell
.\scripts\deploy_cloud.ps1
```

para crear **toda** la plataforma, y:

```powershell
.\scripts\destroy_cloud.ps1
```

para eliminarla.

No se crean recursos manualmente en la consola durante un despliegue normal.

## 1. Arquitectura que se crea

```text
Internet
   |
HTTPS / WSS
   v
CloudFront (*.cloudfront.net)
   |
HTTP al origen, restringido por Security Group
   v
Application Load Balancer
   |
   v
ECS/Fargate api-manager (1 task)
   |
   | HTTP privado + WORKER_SHARED_TOKEN
   v
Cloud Map DNS -> ECS/Fargate simulation-worker (N tasks)
                    |
                    +-> OpenDSS / AltDSS

API + workers -> EFS /app/data/runtime/custom_models
Images        -> ECR
Secrets       -> Secrets Manager
Logs          -> CloudWatch Logs
```

La URL pública NO es una IP fija. El script imprime una URL semejante a:

```text
https://d123example.cloudfront.net
```

Esa es la URL que se abre en el navegador y la que usan REST y WSS.

## 2. Requisitos del PC

- Windows + PowerShell.
- Git.
- Docker Desktop funcionando.
- Python/entorno del proyecto.
- AWS CLI v2.
- Una identidad AWS con permisos suficientes para crear el stack.

Comprueba:

```powershell
git --version
docker version
aws --version
```

## 3. Instalar AWS CLI v2 en Windows

Opción PowerShell oficial:

```powershell
irm https://awscli.amazonaws.com/v2/install.ps1 | iex
```

Cierra y vuelve a abrir PowerShell y comprueba:

```powershell
aws --version
```

También puede instalarse mediante el MSI oficial de AWS CLI v2.

## 4. Autenticarse en AWS

### Opción recomendada: IAM Identity Center / SSO

Si la cuenta usa SSO:

```powershell
aws configure sso --profile opendss-deployer
aws sso login --profile opendss-deployer
aws sts get-caller-identity --profile opendss-deployer
```

Después despliega con:

```powershell
.\scripts\deploy_cloud.ps1 -Profile opendss-deployer
```

### Opción con access key — solo si tu cuenta no usa SSO

No uses access keys del usuario root.

En AWS Console:

1. IAM.
2. Users.
3. Selecciona un usuario dedicado de despliegue, por ejemplo `opendss-deployer`.
4. Security credentials.
5. Access keys.
6. Create access key.
7. Selecciona **Command Line Interface (CLI)**.
8. Crea la key y descarga el archivo `.csv`.

El CSV contiene `Access key ID` y `Secret access key`. Guárdalo fuera del repositorio.

Puedes importarlo:

```powershell
aws configure import --csv file://C:/RUTA/credentials.csv
```

O crear un perfil explícito:

```powershell
aws configure --profile opendss-deployer
```

Introduce Access Key ID, Secret Access Key, región `us-east-2` y output `json`.

Verifica:

```powershell
aws sts get-caller-identity --profile opendss-deployer
```

## 5. Permisos de la identidad de despliegue

Para el laboratorio de tesis se recomienda una identidad dedicada con capacidad para administrar los recursos creados por CloudFormation: CloudFormation, IAM runtime roles, ECR, ECS/Fargate, EC2/VPC/Security Groups, ELBv2, CloudFront, EFS, Cloud Map/Service Discovery, Secrets Manager, CloudWatch Logs y Application Auto Scaling.

La opción simple durante el montaje/desmontaje de tesis es asignar temporalmente `AdministratorAccess` a la identidad **de despliegue**. Esto NO se transfiere a los contenedores. Las tasks ECS utilizan un `TaskExecutionRole` limitado creado por la plantilla.

Cuando el stack quede estabilizado puede reemplazarse por una policy de despliegue de mínimo privilegio.

## 6. Configurar región

```powershell
aws configure set region us-east-2 --profile opendss-deployer
aws configure get region --profile opendss-deployer
```

Esperado:

```text
us-east-2
```

## 7. Preparar usuarios locales

El despliegue reutiliza los hashes Argon2 de:

```text
secrets/local/auth_users.json
```

Si no existe:

```powershell
python .\scripts\init_local_secrets.py
```

Ese archivo está ignorado por Git. El script `deploy_cloud.ps1` lo carga automáticamente en AWS Secrets Manager.

Verifica que nunca se versiona:

```powershell
git ls-files secrets/local
```

Debe devolver vacío.

## 8. Congelar el código antes de desplegar

El script exige Git limpio porque etiqueta las imágenes con el SHA del commit:

```powershell
git status
git rev-parse --short HEAD
```

Haz commit antes del deploy si existen cambios.

## 9. Desplegar TODO

Desde la raíz:

```powershell
.\scripts\deploy_cloud.ps1 -Profile opendss-deployer
```

Sin perfil:

```powershell
.\scripts\deploy_cloud.ps1
```

El script automáticamente:

1. valida AWS CLI, Docker y Git;
2. verifica identidad AWS;
3. crea el stack bootstrap;
4. crea ECR y Secrets Manager;
5. sincroniza `auth_users.json`;
6. construye las dos imágenes Docker;
7. autentica Docker en ECR;
8. sube las imágenes con tag Git SHA;
9. obtiene la managed prefix list de CloudFront;
10. valida `main.yaml`;
11. crea VPC, red, SG, EFS, ECS/Fargate, Cloud Map, ALB, CloudFront, logs y auto scaling;
12. espera estabilidad ECS;
13. obtiene la URL CloudFront;
14. ejecuta smoke cloud, salvo `-SkipSmoke`;
15. guarda evidencia del despliegue.

Parámetros útiles:

```powershell
.\scripts\deploy_cloud.ps1 `
  -Profile opendss-deployer `
  -WorkerCount 3 `
  -WorkerMinCount 1 `
  -WorkerMaxCount 6
```

Reutilizar imágenes ya subidas:

```powershell
.\scripts\deploy_cloud.ps1 -Profile opendss-deployer -ReuseImages
```

## 10. Dónde conectarse

Al finalizar, el script imprime:

```text
URL: https://dXXXXXXXXXXXX.cloudfront.net
```

Abre esa URL. No uses las IP privadas de Fargate ni el DNS del ALB.

El frontend, REST y WebSocket funcionan por el mismo dominio:

```text
https://dXXXXXXXXXXXX.cloudfront.net
wss://dXXXXXXXXXXXX.cloudfront.net/ws/...
```

## 11. Smoke cloud

Si el stack ya está desplegado:

```powershell
.\scripts\smoke_cloud.ps1 -Profile opendss-deployer
```

Guarda evidencia en:

```text
docs/evidence/deliverable_2/<timestamp>_cloud_smoke/
```

## 12. Evidencia Entregable 1

No requiere AWS. Ejecuta en Docker local para aislar el runtime:

```powershell
.\scripts\run_deliverable1_evidence.ps1
```

Genera pruebas secuenciales y concurrentes 2/4/8/16 para IEEE13, IEEE34, IEEE123 e IEEE8500.

Salida:

```text
docs/evidence/deliverable_1/<timestamp>_multicontext/
```

## 13. Evidencia Entregable 2 — rendimiento y autoscaling

Primero despliega en modo de rendimiento. Para hacer visible el scale-out se recomienda iniciar con un worker:

```powershell
.\scripts\deploy_cloud.ps1 `
  -Profile opendss-deployer `
  -ReuseImages `
  -PerformanceMode `
  -WorkerCount 1 `
  -WorkerMinCount 1 `
  -WorkerMaxCount 6 `
  -SkipSmoke
```

Después:

```powershell
.\scripts\run_deliverable2_cloud_evidence.ps1 `
  -Profile opendss-deployer `
  -LoadSeconds 180
```

La política de auto scaling es deliberadamente **scale-out-only** durante la tesis, porque cada worker posee contextos OpenDSS en memoria y un scale-in automático podría matar una sesión activa.

Salida:

```text
docs/evidence/deliverable_2/<timestamp>_cloud_performance/
```

## 14. Evidencia Entregable 3 — seguridad y resiliencia

Actualiza el mismo stack a modo resiliencia:

```powershell
.\scripts\deploy_cloud.ps1 `
  -Profile opendss-deployer `
  -ReuseImages `
  -ResilienceMode `
  -WorkerCount 3 `
  -SkipSmoke
```

Después:

```powershell
.\scripts\run_deliverable3_cloud_evidence.ps1 `
  -Profile opendss-deployer
```

El script identifica la task worker que posee la sesión, la detiene mediante ECS y comprueba la recuperación/reasignación del job.

## 15. Ejecutar todas las evidencias con un comando

```powershell
.\scripts\run_all_deliverables.ps1 `
  -Profile opendss-deployer `
  -DestroyAfter
```

Ese flujo:

1. genera Entregable 1 local;
2. despliega cloud performance;
3. genera Entregable 2;
4. actualiza a modo resiliencia;
5. genera Entregable 3;
6. construye índice de evidencia;
7. si se usa `-DestroyAfter`, elimina AWS al final.

## 16. Destruir TODO

```powershell
.\scripts\destroy_cloud.ps1 -Profile opendss-deployer
```

Elimina primero el stack principal y luego bootstrap. Esto elimina CloudFront, ALB, ECS/Fargate, Cloud Map, EFS, VPC, SG, logs, runtime roles, ECR e imágenes y los secretos creados por CloudFormation.

Verifica al final el archivo:

```text
docs/evidence/deployments/<timestamp>_destroy/tagged_leftovers.json
```

## 17. Costos y operación efímera

La intención es que AWS permanezca activo únicamente durante demostraciones/campañas. No hay NAT Gateway. Al terminar una sesión de trabajo ejecuta `destroy_cloud.ps1`.

La destrucción total también elimina el EFS y por tanto modelos custom cargados en AWS. Si necesitas conservarlos, expórtalos antes de destruir.

## 18. Nota de alineación del Entregable 2

El texto recibido del Entregable 2 dice literalmente **Google Cloud Platform**. Este repositorio genera evidencia en AWS. Antes de presentar el entregable debes contar con aprobación para cambiar el proveedor o modificar la frase a “nube pública/AWS”. No declares cumplimiento literal de GCP usando evidencia AWS.
