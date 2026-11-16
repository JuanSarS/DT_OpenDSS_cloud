# Manifest de archivos — cierre AWS + evidencias

Este documento explica qué archivo agregar/modificar y para qué existe.

### `START_HERE_AWS.md`
Entrada corta: despliegue, destrucción y generación integral de evidencias.

## Infraestructura AWS

### `infra/aws/cloudformation/bootstrap.yaml`
Stack de bootstrap efímero. Crea los dos repositorios ECR y tres secretos base: JWT, token API→worker y directorio de usuarios. Los repositorios usan `EmptyOnDelete` para que el stack pueda destruirlos junto con las imágenes.

### `infra/aws/cloudformation/main.yaml`
Infraestructura principal completa: VPC, dos subnets, SG, EFS, ECS/Fargate, Cloud Map, ALB, CloudFront, CloudWatch Logs, task execution role y auto scaling scale-out-only de workers.

### `infra/aws/cloudformation/parameters.example.json`
Referencia humana de parámetros y valores por defecto.

### `infra/evidence/Dockerfile`
Imagen temporal para ejecutar las pruebas multi-contexto del Entregable 1 con el mismo runtime Linux/AltDSS del worker.

## Discovery cloud

### `services/api_manager/execution/worker_discovery.py`
Abstracción de discovery. `StaticWorkerDiscovery` conserva Docker Compose; `DnsWorkerDiscovery` resuelve las IP privadas registradas por Cloud Map.

### `services/api_manager/execution/factory.py`
Selecciona discovery `static` o `dns` mediante variables de entorno.

### `services/api_manager/execution/worker_pool.py`
Pool dinámico: sincroniza endpoints descubiertos, conserva afinidad de sesión, marca fallos, retry/failover y reincorpora workers saludables.

### `services/api_manager/platform/settings.py`
Nuevas variables `WORKER_DISCOVERY_*`.

## Proxy/CloudFront

### `services/api_manager/security/proxy.py`
Obtiene la IP real del viewer mediante `CloudFront-Viewer-Address` y detecta HTTPS externo mediante `CloudFront-Forwarded-Proto`; conserva fallback para Caddy local.

### `services/api_manager/main.py`
Rate limiting usa la IP externa resuelta correctamente detrás de proxy.

### `services/api_manager/auth/routes.py`
La cookie `Secure` reconoce HTTPS de CloudFront/Caddy aunque el hop interno sea HTTP.

### `services/api_manager/api/routes/simulations.py`
Rate limiting WebSocket usa la IP real del viewer.

### `tests/security/test_proxy_headers.py`
Pruebas de headers CloudFront/local.

## Operación AWS

### `scripts/deploy_cloud.ps1`
Comando one-click. Despliega bootstrap, sincroniza usuarios, build/push ECR, resuelve CloudFront prefix list, despliega stack principal, espera ECS y opcionalmente ejecuta smoke.

### `scripts/destroy_cloud.ps1`
Elimina stack principal y bootstrap y guarda inventario pre/post destrucción.

### `scripts/smoke_cloud.ps1`
Smoke cloud contra la URL CloudFront.

### `scripts/run_all_deliverables.ps1`
Orquestador opcional que genera Entregable 1, despliega performance, genera Entregable 2, actualiza a resiliencia, genera Entregable 3 e incluso destruye AWS con `-DestroyAfter`.

## Evidencia Entregable 1

### `tools/evidence/deliverable1_multicontext.py`
Referencia secuencial + concurrencia 2/4/8/16 para IEEE13/34/123/8500. Compara hash canónico y delta absoluto.

### `scripts/run_deliverable1_evidence.ps1`
Build y ejecución reproducible de la imagen de evidencia.

## Evidencia Entregable 2

### `tools/evidence/cloud_mvp_evidence.py`
Dos usuarios reales concurrentes, REST/WSS, IEEE123 + IEEE8500, métricas antes/después.

### `load/locustfile.py`
Locust autenticado por JWT para Snapshot/QSTS.

### `scripts/run_deliverable2_cloud_evidence.ps1`
Locust 5/10 usuarios, monitor ECS desired/running/pending, CloudWatch CPU/memoria.

### `tools/evidence/summarize_deliverable2.py`
Extrae p50/p95/p99, failures, CPU/memoria y detecta scale-out; escribe `PERFORMANCE_SUMMARY.json` y `REPORT.md`.

## Evidencia Entregable 3

### `tools/evidence/security_cloud_evidence.py`
401, token inválido, aislamiento 403, viewer read-only, cuota/admission, rate limiting y health bajo abuso.

### `tools/evidence/resilience_client.py`
QSTS largo por WSS; deja archivo de readiness para que el orquestador mate exactamente el worker propietario.

### `scripts/run_deliverable3_cloud_evidence.ps1`
Mapea IP del worker a task ECS, ejecuta `stop-task`, espera failover y reúne evidencia.

### `tools/evidence/summarize_deliverable3.py`
Resumen de failover y suite de seguridad.

## Índice y regresión

### `scripts/run_all_smokes.ps1`
Ahora conserva logs y manifest de cada paso local.

### `scripts/build_evidence_index.py`
Genera `docs/evidence/EVIDENCE_INDEX.md` con las corridas encontradas.

### `docs/evidence/README.md`
Convención de almacenamiento de evidencia.

## Documentación

- `README.md`: entrada actualizada del proyecto.
- `docs/architecture/AWS_ARCHITECTURE.md`: arquitectura y decisiones cloud.
- `docs/deployment/AWS_ONE_CLICK.md`: guía desde credenciales hasta destroy.
- `docs/deployment/AWS_DEPLOYMENT.md`: índice operativo corto.
- `docs/security/AWS_IAM.md`: roles/credenciales/permisos.
- `docs/deliverable_1/README.md`: mapa de evidencia Entregable 1.
- `docs/deliverable_2/README.md`: mapa de evidencia Entregable 2.
- `docs/deliverable_2/PROVIDER_ALIGNMENT_REQUIRED.md`: advertencia AWS vs requisito literal GCP.
- `docs/deliverable_3/README.md`: mapa de evidencia Entregable 3.
- `CONTEXTO_MAESTRO_PROYECTO_OPENDSS_CLOUD.md`: actualizado con decisiones AWS finales.
