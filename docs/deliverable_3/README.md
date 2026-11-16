# Entregable 3 — Seguridad y resiliencia

Primero despliega el stack seguro/resiliente:

```powershell
.\scripts\deploy_cloud.ps1 -Profile opendss-deployer -ReuseImages -ResilienceMode -WorkerCount 3 -SkipSmoke
```

Luego:

```powershell
.\scripts\run_deliverable3_cloud_evidence.ps1 -Profile opendss-deployer
```

La evidencia incluye:
- REST sin token 401;
- token inválido 401;
- aislamiento horizontal 403;
- viewer read-only;
- métricas admin;
- cuota/admission 429;
- rate limiting 429 y `/health` operativo;
- selección del worker propietario;
- terminación deliberada de una task ECS;
- retry/reasignación del job;
- eventos WebSocket y restart de pasos QSTS;
- estado del ECS worker service después del fallo.

Salida:

```text
docs/evidence/deliverable_3/
```
