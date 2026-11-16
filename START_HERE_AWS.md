# START HERE — AWS OpenDSS Cloud

Este repositorio queda preparado para un laboratorio AWS efímero y reproducible.

## Operación normal

Después de configurar una sola vez la identidad AWS en este PC:

```powershell
.\scripts\deploy_cloud.ps1 -Profile opendss-deployer
```

El comando crea bootstrap, ECR, secretos, imágenes, red, EFS, ECS/Fargate, N workers, Cloud Map, ALB, CloudFront, logs y auto scaling, y devuelve la URL HTTPS pública.

Para eliminar TODO:

```powershell
.\scripts\destroy_cloud.ps1 -Profile opendss-deployer
```

## Generar la evidencia completa de los tres entregables

```powershell
.\scripts\run_all_deliverables.ps1 `
  -Profile opendss-deployer `
  -LoadSeconds 180 `
  -DestroyAfter
```

Ese orquestador:

1. genera Entregable 1 local (secuencial vs 2/4/8/16 contextos, 4 feeders);
2. despliega AWS en modo performance;
3. genera Entregable 2 con multiusuario, REST/WSS, Locust, p50/p95, CPU/memoria y auto scaling;
4. actualiza AWS a modo resiliencia;
5. genera Entregable 3 con 401/403, viewers, 429, rate limit y caída/failover de worker;
6. construye `docs/evidence/EVIDENCE_INDEX.md`;
7. elimina AWS si se usa `-DestroyAfter`.

## Guía completa

Lee en este orden:

1. `PATCH_MANIFEST.md`
2. `docs/deployment/AWS_ONE_CLICK.md`
3. `docs/architecture/AWS_ARCHITECTURE.md`
4. `docs/evidence/DELIVERABLE_MAPPING.md`
5. `docs/security/AWS_IAM.md`

## URL cloud

No se usa una IP fija. El despliegue devuelve una URL CloudFront semejante a:

```text
https://d123example.cloudfront.net
```

Esa URL sirve para frontend, REST y WSS.

## Advertencia Entregable 2

El enunciado entregado por el usuario menciona literalmente **Google Cloud Platform**. Esta implementación y su evidencia son **AWS**. Antes de presentar el Entregable 2 debe existir aprobación del cambio de proveedor o corregirse el enunciado a nube pública/AWS.
