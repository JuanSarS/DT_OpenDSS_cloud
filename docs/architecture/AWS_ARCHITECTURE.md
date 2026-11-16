# Arquitectura AWS — OpenDSS Cloud

## Principio

AWS no cambia la lógica científica. Se preservan las imágenes, contratos, `SimulationService`, `WorkerPoolSimulationExecutor`, JWT, ownership/viewers, Snapshot/QSTS, WSS y autenticación interna. Solo cambian infraestructura, almacenamiento compartido y discovery de workers. Esta es la misma regla establecida en el contexto maestro del proyecto.

## Componentes

### CloudFront
Punto de entrada público HTTPS/WSS. Usa el certificado predeterminado `*.cloudfront.net`, por lo que no requiere dominio ni ACM para el laboratorio efímero.

### Application Load Balancer
Origen HTTP de CloudFront. Su Security Group acepta puerto 80 únicamente desde la managed prefix list `com.amazonaws.global.cloudfront.origin-facing`. Reenvía a API port 8000.

### API Manager ECS/Fargate
Una task inicial. La única réplica es deliberada porque sesiones, viewers, suscriptores WebSocket y bindings worker viven en memoria.

### Simulation Worker ECS/Fargate
Un solo ECS Service con N tasks idénticas. Cada task ejecuta AltDSS/OpenDSS y mantiene contextos aislados.

### AWS Cloud Map
Registra las direcciones privadas de workers como registros A de `simulation-worker.opendss.local`. `DnsWorkerDiscovery` resuelve periódicamente esos registros y el pool mantiene afinidad `session_id -> endpoint`.

### Amazon EFS
Sustituye el volumen Docker compartido de custom models. API y workers montan el mismo Access Point en `/app/data/runtime/custom_models`, con transit encryption habilitado.

### Amazon ECR
Dos repositorios: API y worker. Las imágenes se etiquetan con Git SHA.

### AWS Secrets Manager
Guarda JWT secret, worker service token y JSON de usuarios con hashes Argon2. Las task definitions los inyectan en runtime.

### CloudWatch Logs y métricas ECS
Logs JSON vía `awslogs`; CPU y memoria del servicio worker se consultan desde `AWS/ECS`.

## Red

VPC 10.42.0.0/16, dos subnets públicas en dos AZ. No se usa NAT Gateway para reducir costo. Las tasks reciben IP pública únicamente para egress hacia servicios AWS/ECR, pero sus Security Groups no permiten inbound público.

Trust path:

```text
Internet
 -> CloudFront
 -> ALB:80 (solo CloudFront managed prefix list)
 -> API:8000 (solo ALB SG)
 -> Worker:8100 (solo API SG)
 -> EFS:2049 (solo API/Worker SG)
```

## Auto scaling

`simulation-worker` usa Application Auto Scaling por CPU. La policy tiene `DisableScaleIn: true`: puede demostrar scale-out, pero no elimina automáticamente workers que podrían poseer contextos activos. El scale-in queda para una arquitectura futura con drenaje explícito de sesiones.

## Estado y limitaciones deliberadas

- API: 1 replica.
- Workers: N replicas.
- No RDS, Redis, Kafka, Kubernetes ni Step Functions obligatorios.
- API→worker usa HTTP privado + service token. El cifrado externo cliente→CloudFront es TLS y EFS usa cifrado en tránsito.
- CloudFront URL cambia al destruir y recrear el stack.
