# CONTEXTO PARA DESPLIEGUE AWS — OpenDSS Cloud

## 1. Estado local actual

La plataforma está organizada como monorepo y funciona con dos tipos de servicio de aplicación:

1. `api-manager`
   - FastAPI
   - frontend estático
   - JWT y ownership
   - viewers/espectadores
   - WebSocket
   - rate limiting
   - control de admisión
   - métricas y security events
   - WorkerPoolSimulationExecutor

2. `simulation-worker`
   - AltDSS/OpenDSS
   - Snapshot
   - QSTS
   - contextos aislados
   - validación y ejecución de modelos custom
   - autenticación interna mediante `WORKER_SHARED_TOKEN`

En local existe Caddy delante del API para HTTPS/WSS. El API y los workers no publican sus puertos directamente al host.

El laboratorio local usa tres instancias idénticas de `simulation-worker` y el API mantiene afinidad `session_id -> worker endpoint`.

## 2. Estado que debe mantenerse en AWS

La lógica funcional NO debe cambiar al migrar.

Se mantienen:

- las mismas imágenes Docker;
- los mismos contratos;
- el mismo `SimulationService`;
- el mismo `WorkerPoolSimulationExecutor`;
- JWT y roles;
- ownership y viewers;
- Snapshot/QSTS;
- WebSocket;
- worker service token;
- logs JSON.

Solo cambia infraestructura y descubrimiento de workers.

## 3. Arquitectura objetivo AWS

```text
Internet
   |
   v
Application Load Balancer
HTTPS 443 / WSS
ACM certificate
   |
   v
ECS/Fargate service: api-manager
DesiredCount inicial: 1
   |
   | private VPC traffic
   v
Worker discovery
AWS Cloud Map
   |
   +--> ECS/Fargate simulation-worker task 1
   +--> ECS/Fargate simulation-worker task 2
   +--> ECS/Fargate simulation-worker task N

Shared custom-model storage:
Amazon EFS mounted into API and workers

Images:
Amazon ECR

Secrets:
AWS Secrets Manager

Logs:
CloudWatch Logs
```

## 4. Decisión importante: API inicialmente con una sola réplica

El estado lógico de sesiones, viewers, WebSocket subscribers y bindings de worker vive actualmente en memoria del proceso API.

Por tanto, el primer despliegue AWS debe usar:

`api-manager desiredCount = 1`

Los workers sí pueden ser N.

Escalar el API a múltiples réplicas requeriría externalizar estado y fanout WebSocket, lo cual no es necesario para el cierre actual de la tesis.

## 5. Descubrimiento de workers

Localmente el pool recibe URLs estáticas:

`SIMULATION_WORKER_URLS=http://simulation-worker-1:8100,...`

En ECS/Fargate las tasks pueden cambiar de IP. Antes del despliegue AWS se debe introducir una interfaz pequeña:

```text
WorkerDiscovery
├── StaticWorkerDiscovery
└── CloudMapWorkerDiscovery
```

Local:

`WORKER_DISCOVERY_BACKEND=static`

AWS:

`WORKER_DISCOVERY_BACKEND=cloudmap`

CloudMapWorkerDiscovery obtiene los endpoints de las tasks healthy del servicio worker y actualiza el pool.

La afinidad `session_id -> worker` se conserva dentro de WorkerPoolSimulationExecutor.

## 6. Modelos personalizados

En local API y workers comparten un Docker volume.

En Fargate no existe ese volumen Docker compartido entre tasks.

Para mantener el código actual con el menor cambio posible se recomienda Amazon EFS:

- crear un EFS filesystem;
- crear access point;
- montar `/app/data/runtime/custom_models` en api-manager;
- montar el mismo path en todos los workers;
- habilitar encryption in transit.

Los modelos IEEE builtin continúan empaquetados dentro de la imagen worker.

## 7. TLS

Caddy solo es necesario en local.

En AWS:

- Application Load Balancer público;
- listener HTTPS 443;
- certificado de AWS Certificate Manager;
- target group hacia api-manager:8000;
- WebSockets atraviesan el mismo ALB;
- API task sin IP/puerto público directo.

## 8. Red

VPC con al menos dos Availability Zones.

Security Groups sugeridos:

### ALB SG
Inbound:
- TCP 443 desde Internet.
- TCP 80 opcional únicamente para redirect a 443.

Outbound:
- TCP 8000 hacia API SG.

### API SG
Inbound:
- TCP 8000 SOLO desde ALB SG.

Outbound:
- TCP 8100 hacia Worker SG.
- HTTPS 443 hacia servicios AWS requeridos.
- NFS 2049 hacia EFS SG si el API monta EFS.

### Worker SG
Inbound:
- TCP 8100 SOLO desde API SG.

Outbound:
- NFS 2049 hacia EFS SG.
- HTTPS 443 si se requieren APIs AWS.

### EFS SG
Inbound:
- TCP 2049 desde API SG y Worker SG.

## 9. Secretos

Localmente existen Docker secrets.

En AWS usar Secrets Manager para:

- `JWT_SECRET`
- `WORKER_SHARED_TOKEN`
- `AUTH_USERS_JSON`

La task definition los inyecta en runtime.

No se versionan ni se incluyen en imágenes ECR.

## 10. IAM

Roles mínimos:

### CloudFormation service role
Permite que CloudFormation cree y actualice los recursos declarados del stack.

### ECS task execution role
Usado por ECS/Fargate para:
- pull ECR;
- CloudWatch logs;
- lectura de Secrets Manager referenciados por task definition.

### API task role
Solo permisos que usa el código de api-manager.
Inicialmente:
- descubrir workers en Cloud Map, si la aplicación llama la API Cloud Map directamente.

Si EFS usa IAM authorization, añadir permisos EFS necesarios.

### Worker task role
Puede quedar sin permisos de aplicación si solo usa red/EFS y no llama APIs AWS.

## 11. Infrastructure as Code

Usar AWS CloudFormation con plantillas YAML.

Estructura sugerida:

```text
infra/aws/cloudformation/
├── bootstrap.yaml
├── main.yaml
└── parameters.example.json

scripts/
├── deploy_cloud.ps1
└── destroy_cloud.ps1
```

### bootstrap.yaml
Recursos iniciales de despliegue que se crean una vez:
- ECR repositories;
- CloudFormation service role, si se decide administrarlo aquí;
- opcional bucket de artefactos.

### main.yaml
- VPC/subnets/routes;
- security groups;
- ECS cluster;
- EFS;
- Cloud Map namespace/service;
- log groups;
- Secrets Manager references or secret resources;
- task definitions;
- ECS services;
- ALB;
- target group;
- HTTPS listener;
- ACM certificate ARN parameter;
- Application Auto Scaling worker target/policy.

## 12. Imágenes

Crear dos repositorios ECR:

- `opendss-api-manager`
- `opendss-simulation-worker`

Etiquetar imágenes con Git SHA.

Ejemplo conceptual:

`opendss-api-manager:a1b2c3d`
`opendss-simulation-worker:a1b2c3d`

Evitar usar `latest` como única referencia de producción.

## 13. Autoscaling de workers

Inicio recomendado:

`WorkerDesiredCount = 3`

Configurar mínimos/máximos, por ejemplo:

- min: 1
- desired inicial: 3
- max: configurable

El escalado puede utilizar CPU inicialmente. Una evolución posterior puede usar una métrica de backlog/job count.

El código del pool debe actualizar discovery para poder incorporar o retirar workers.

## 14. Logs y métricas

Configurar task definitions con `awslogs`.

Crear log groups separados:

- `/opendss/api-manager`
- `/opendss/simulation-worker`

Los logs estructurados JSON actuales pasan a CloudWatch sin cambiar código.

## 15. Recursos deliberadamente no incluidos al inicio

- Kubernetes/EKS.
- RDS.
- Redis.
- Kafka.
- Step Functions obligatorio.
- múltiples réplicas de API.

## 16. Flujo de despliegue final esperado

```text
Git
 |
 v
Docker build
 |
 v
ECR push
 |
 v
CloudFormation deploy
 |
 +--> red
 +--> IAM
 +--> EFS
 +--> ECS
 +--> Cloud Map
 +--> ALB/ACM
 +--> Secrets
 +--> CloudWatch
 |
 v
health check
 |
 v
secure smoke tests
```

Comando objetivo:

`./scripts/deploy_cloud.ps1`

El script debe:

1. comprobar AWS CLI;
2. comprobar identidad/region;
3. obtener Git SHA;
4. construir imágenes;
5. autenticar Docker en ECR;
6. push de imágenes;
7. validar template CloudFormation;
8. ejecutar `aws cloudformation deploy`;
9. esperar servicios ECS stable;
10. obtener endpoint ALB;
11. ejecutar smokes HTTPS/WSS;
12. imprimir recursos y URLs.

## 17. Criterios antes de iniciar AWS

Local debe quedar verde en:

- certificado confiado;
- login/logout;
- autenticación compartida entre pestañas;
- Snapshot;
- QSTS REST;
- QSTS WSS;
- IEEE8500;
- ownership/viewers;
- custom models;
- 3-worker pool;
- failover básico;
- security tests;
- secrets fuera de Git;
- run_all_smokes.ps1.

Después de esto el único cambio funcional previo al stack AWS debe ser `WorkerDiscovery` estático/Cloud Map y, si se adopta, el montaje EFS para custom models.
