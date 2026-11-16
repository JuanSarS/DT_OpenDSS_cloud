# Entregable 2 — Evidencia MVP cloud

## ADVERTENCIA DE PROVEEDOR

El requisito recibido dice literalmente **Google Cloud Platform**. El despliegue actual es AWS. Esta evidencia solo puede presentarse como cumplimiento del Entregable 2 si se aprueba cambiar el proveedor o reformularlo como “nube pública/AWS”. Véase `PROVIDER_ALIGNMENT_REQUIRED.md`.

## Evidencia funcional

```powershell
.\scripts\smoke_cloud.ps1 -Profile opendss-deployer
```

## Evidencia de rendimiento + auto scaling

Despliega en modo performance con 1 worker inicial y hasta 6:

```powershell
.\scripts\deploy_cloud.ps1 -Profile opendss-deployer -ReuseImages -PerformanceMode -WorkerCount 1 -WorkerMinCount 1 -WorkerMaxCount 6 -SkipSmoke
```

Luego:

```powershell
.\scripts\run_deliverable2_cloud_evidence.ps1 -Profile opendss-deployer -LoadSeconds 180
```

Genera:
- flujo multiusuario real REST/WSS;
- resultados IEEE123/IEEE8500;
- Locust 5 usuarios;
- Locust 10 usuarios;
- latencias p50/p95/p99 en CSV Locust;
- CPU/Memory CloudWatch;
- timeline desired/running/pending workers para evidenciar scale-out;
- resumen automático `PERFORMANCE_SUMMARY.json` y `REPORT.md`.
