> AWS one-click: comienza en [`START_HERE_AWS.md`](START_HERE_AWS.md).

# OpenDSS Cloud

Plataforma cloud-native de simulación eléctrica basada en FastAPI, AltDSS/OpenDSS, REST, WebSocket, Docker y un pool de workers aislados.

## Arquitectura local actual

```text
Browser
  |
HTTPS / WSS :8443
  v
Caddy
  |
  v
api-manager
  |
  v
WorkerPoolSimulationExecutor
  |        |        |
worker-1 worker-2 worker-3
  |        |        |
OpenDSS contexts aislados
```

- JWT + cookie HttpOnly para navegador.
- Ownership y viewers/espectadores.
- Rate limiting y admission control.
- Worker service token interno.
- Custom models compartidos mediante volumen Docker.
- 3 workers idénticos con afinidad `session_id -> worker`.

## Laboratorio local

Inicializa secretos si es la primera vez:

```powershell
python .\scripts\init_local_secrets.py
```

Levanta todo:

```powershell
.\scripts\deploy_local.ps1
```

Instala la CA local de Caddy en Windows si es necesario, desde PowerShell Administrador:

```powershell
.\scripts\trust_local_ca.ps1
```

Abre:

```text
https://localhost:8443
```

Detén el laboratorio:

```powershell
.\scripts\stop_local.ps1
```

## Regresión local con evidencia

```powershell
.\scripts\run_all_smokes.ps1
```

Los resultados se conservan en:

```text
docs/evidence/regression/<timestamp>/
```

## Entregable 1 — multi-contexto

```powershell
.\scripts\run_deliverable1_evidence.ps1
```

Valida IEEE13, IEEE34, IEEE123 e IEEE8500 con referencia secuencial y concurrencia 2/4/8/16. Resultados:

```text
docs/evidence/deliverable_1/
```

## AWS — despliegue efímero one-click

Guía completa:

[`docs/deployment/AWS_ONE_CLICK.md`](docs/deployment/AWS_ONE_CLICK.md)

Operación normal:

```powershell
.\scripts\deploy_cloud.ps1 -Profile opendss-deployer
```

El script crea ECR, Secrets Manager, VPC, SG, EFS, ECS/Fargate, Cloud Map, ALB, CloudFront, logs y auto scaling, construye/sube las dos imágenes y devuelve la URL pública HTTPS.

Destruir todo:

```powershell
.\scripts\destroy_cloud.ps1 -Profile opendss-deployer
```

La URL pública AWS es un dominio CloudFront, no una IP fija:

```text
https://dXXXXXXXXXXXX.cloudfront.net
```

## Evidencia cloud

Entregable 2:

```powershell
.\scripts\run_deliverable2_cloud_evidence.ps1 -Profile opendss-deployer -LoadSeconds 180
```

Entregable 3:

```powershell
.\scripts\run_deliverable3_cloud_evidence.ps1 -Profile opendss-deployer
```

Automatizar los tres entregables y desmontar AWS al final:

```powershell
.\scripts\run_all_deliverables.ps1 -Profile opendss-deployer -DestroyAfter
```

Índice de evidencia:

```powershell
python .\scripts\build_evidence_index.py
```

## Documentación principal

- `CONTEXTO_MAESTRO_PROYECTO_OPENDSS_CLOUD.md`
- `docs/architecture/AWS_ARCHITECTURE.md`
- `docs/deployment/AWS_ONE_CLICK.md`
- `docs/security/AWS_IAM.md`
- `docs/evidence/README.md`

## Nota importante del Entregable 2

El texto recibido del Entregable 2 menciona explícitamente **Google Cloud Platform**. La infraestructura generada por este repositorio es AWS. Antes de presentar esa evidencia debe existir aprobación del cambio de proveedor o ajuste de redacción a nube pública/AWS. Véase `docs/deliverable_2/PROVIDER_ALIGNMENT_REQUIRED.md`.
