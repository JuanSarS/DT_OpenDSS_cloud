# Mapeo requisito → evidencia

## Entregable 1

| Requisito | Archivo generado |
|---|---|
| Redes IEEE13/34/123/8500 | `deliverable_1/*/config.json` |
| Referencia estrictamente secuencial | `deliverable_1/*/raw_results.csv`, filas `mode=sequential` |
| Concurrencia 2/4/8/16 | `deliverable_1/*/raw_results.csv`, campo `level` |
| Equivalencia exacta | `deliverable_1/*/summary.json` (`all_exact`, `reference_hash`) |
| Delta numérico | `deliverable_1/*/raw_results.csv` (`max_abs_delta`) |
| Resumen para informe | `deliverable_1/*/REPORT.md` |

## Entregable 2

| Requisito | Archivo generado |
|---|---|
| URL cloud / stack | `deployments/*/deploy_manifest.json` |
| Servicios ECS | `deployments/*/ecs_services.json` |
| REST + WSS multiusuario | `deliverable_2/*/*_cloud_mvp/multiuser_flows.json` |
| Modelos disponibles | `deliverable_2/*/*_cloud_mvp/models.json` |
| Métricas API | `deliverable_2/*/*_cloud_mvp/metrics_before.json`, `metrics_after.json` |
| Locust 5 usuarios | `deliverable_2/*/locust_5_stats.csv`, `locust_5_stats_history.csv` |
| Locust 10 usuarios | `deliverable_2/*/locust_10_stats.csv`, `locust_10_stats_history.csv` |
| p50/p95/p99 | `deliverable_2/*/PERFORMANCE_SUMMARY.json` |
| CPU workers | `deliverable_2/*/cloudwatch_CPUUtilization.json` |
| Memoria workers | `deliverable_2/*/cloudwatch_MemoryUtilization.json` |
| Auto scaling | `deliverable_2/*/autoscaling_timeline.jsonl` y `PERFORMANCE_SUMMARY.json` |
| Reporte listo para citar | `deliverable_2/*/REPORT.md` |

> El requerimiento original menciona GCP. La evidencia anterior es AWS y necesita aprobación de cambio de proveedor.

## Entregable 3

| Requisito | Archivo generado |
|---|---|
| Sin token / token inválido | `deliverable_3/*/*_security/security_results.json` |
| Acceso horizontal bloqueado | mismo `security_results.json` |
| Viewer read-only | mismo `security_results.json` |
| Admission / overload 429 | mismo `security_results.json` |
| Rate limit + health | mismo `security_results.json` |
| Worker propietario antes de fallo | `deliverable_3/*/resilience_session.json` |
| Task detenida | `deliverable_3/*/stopped_task.json` |
| Eventos WSS durante recuperación | `deliverable_3/*/ws_events.jsonl` |
| Retry/restart QSTS | `deliverable_3/*/resilience_result.json` |
| Estado ECS posterior | `deliverable_3/*/worker_service_after_failover.json` |
| Resumen | `deliverable_3/*/SUMMARY.json`, `REPORT.md` |
