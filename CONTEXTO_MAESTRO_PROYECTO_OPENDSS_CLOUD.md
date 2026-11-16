# CONTEXTO MAESTRO DEL PROYECTO OPEN-DSS CLOUD
## Estado, objetivos, arquitectura objetivo, organización del repositorio y ruta de cierre

**Fecha de consolidación:** 6 de noviembre de 2026  
**Propósito:** documento autocontenido para retomar el proyecto en una conversación futura sin reconstruir el contexto.

---

# 1. Objetivo general

El proyecto busca construir una plataforma cloud-native para ejecutar simulaciones eléctricas OpenDSS/AltDSS desde una interfaz web multiusuario, con soporte para Snapshot, QSTS, múltiples modelos IEEE, aislamiento de simulaciones, REST, WebSocket, métricas, pruebas de rendimiento, JWT, cuotas, control de admisión, resiliencia y despliegue reproducible local/cloud.

Regla principal desde este punto:

> **El mismo código debe funcionar localmente y en AWS. Pasar de local a nube no debe requerir modificar lógica de aplicación. Solo deben cambiar configuración, secretos e infraestructura.**

---

# 2. Estado funcional alcanzado antes del refactor

Actualmente existe una aplicación FastAPI + AltDSS/OpenDSS funcional que ya implementa:

- IEEE13, IEEE34, IEEE123 e IEEE8500;
- sesiones independientes;
- `altdss.NewContext()` por sesión;
- Snapshot;
- QSTS;
- perfiles `constant`, `synthetic_daily`, `model` y `values`;
- REST;
- WebSocket;
- progreso QSTS;
- varios observadores por sesión;
- observador tardío;
- endpoint `/metrics`;
- frontend funcional;
- campañas de rendimiento;
- pruebas Locust;
- Docker;
- despliegue actual en EC2.

Arquitectura actual simplificada:

```text
Frontend
   |
FastAPI
   |
SimulationService
   |
asyncio.to_thread(...)
   |
OpenDSSContextEngine
```

FastAPI y OpenDSS todavía comparten la misma aplicación/máquina.

---

# 3. QSTS

QSTS significa **Quasi-Static Time Series**, en español **Simulación Cuasiestática de Series de Tiempo**.

Ejemplo:

```text
24 horas
paso = 5 minutos
= 288 soluciones consecutivas
```

En una misma simulación QSTS los pasos deben permanecer en un mismo contexto OpenDSS cuando existe dependencia temporal entre controles, reguladores, capacitores, almacenamiento u otros estados.

Regla:

```text
1 QSTS = 1 job = 1 contexto = 1 worker
```

La paralelización debe hacerse principalmente entre simulaciones o escenarios independientes.

---

# 4. Trabajo realizado por fases 1 a 7

## Fase 1 — Motor QSTS

- `QSTSConfig`;
- `QSTSStepResult`;
- `QSTSResult`;
- `solve_qsts()`;
- contexto único;
- resultados por step;
- métricas;
- RSS;
- smoke local.

## Fase 2 — Perfiles temporales

- `constant`;
- `synthetic_daily`;
- `model`;
- `qsts_profiles.py`;
- `synthetic_mixed_daily_v1`.

## Fase 3 — REST QSTS

- `POST /simulations`;
- `POST /simulations/{id}/solve`;
- `GET /simulations/{id}`;
- `GET /simulations/{id}/results`;
- Snapshot/QSTS;
- perfil `values`;
- `asyncio.to_thread`.

## Fase 4 — WebSocket QSTS

- `qsts_progress`;
- progreso ordenado;
- múltiples observadores;
- aislamiento entre sesiones;
- observador tardío;
- resultado final;
- smoke WebSocket.

## Fase 5 — Métricas y rendimiento

- `GET /metrics`;
- percentiles;
- RSS;
- CPU;
- sesiones activas;
- `performance_campaign.py`;
- Locust;
- evidencias JSON/CSV.

## Fase 6 — Frontend

- selección dinámica de modelos;
- Snapshot;
- QSTS;
- perfiles;
- values;
- progreso WebSocket;
- resultados REST;
- métricas;
- tabla QSTS;
- eventos.

Se corrigió además el contrato Snapshot envuelto en `result`.

## Fase 7 — IEEE8500

- modelo IEEE8500;
- `Master_cloud.dss`;
- bootstrap;
- catálogo;
- smoke engine;
- smoke API;
- soporte para performance campaign.

---

# 5. Evidencias de rendimiento ya disponibles

## IEEE123 Snapshot, 30 iteraciones

- errores: 0;
- media `solve_http_ms`: ~49.552 ms;
- p50: ~45.413 ms;
- p95: ~55.536 ms;
- p99: ~123.909 ms;
- máximo: ~151.524 ms.

## IEEE123 QSTS, 30 iteraciones

Configuración: 24 horas, paso 5 minutos, 288 steps, `synthetic_daily`.

- errores: 0;
- todos los steps convergentes;
- media `solve_http_ms`: ~391.319 ms;
- p50: ~363.058 ms;
- p95: ~550.675 ms;
- p99: ~572.757 ms;
- máximo: ~580.667 ms.

## Locust, 5 usuarios

- requests: 847;
- fallos: 0;
- RPS: ~29.12;
- p50: 16 ms;
- p95: 120 ms;
- p99: 240 ms;
- máximo: 569 ms.

## Locust, 10 usuarios

- requests: 1169;
- fallos: 0;
- RPS: ~39.34;
- p50: 25 ms;
- p95: 350 ms;
- p99: 1200 ms;
- máximo: 1695 ms.

## Recursos observados

Snapshot: RSS ~176.9 MB, CPU ~62.1 %.  
QSTS: RSS ~227.4 MB, CPU ~70.9 %.

El RSS actual corresponde al proceso completo, no a memoria exclusiva de una simulación.

---

# 6. Sprint 4 — Métricas y Entregable 2

## Estado

### Métricas p50/p95
**Prácticamente cumplido.** Existen `/metrics`, percentiles, performance campaign y evidencias.

### Memoria por contexto/worker
**Parcial.** Hoy se mide RSS del proceso completo. Con workers separados se podrá medir RSS por proceso de simulación.

### Locust 5-10 usuarios
**Cumplido localmente y preparado para cloud.**

### Ajuste antes/después
**Pendiente de formalizar.** Debe hacerse al cerrar pruebas finales, por ejemplo ajustando concurrencia, timeout, CPU/memoria de task o límite de jobs.

### Frontend usable
**Cumplido.**

### Entregable 2
Pendiente consolidación formal: aplicación desplegada, accesible, multiusuario, métricas reales, capturas, logs, checklist y documento final.

---

# 7. Sprint 5 — Seguridad y JWT

Se debe implementar antes del cierre:

- emisión y validación JWT REST;
- 401 para token ausente/incorrecto;
- JWT obligatorio en WebSocket;
- pruebas de token inválido/expirado;
- autorización por propietario de sesión/job;
- logs estructurados de 401/403;
- secretos fuera del repositorio;
- reglas de red mínimas;
- checklist Zero Trust.

## HTTPS/WSS

El sprint original lo exige. Decisión actual:

> **No se implementará por ahora si implica coste adicional.**

Debe quedar documentado como pendiente/fuera del alcance, nunca como criterio cumplido.

## Secrets

Local: `.env` no versionado.  
Cloud: gestor de secretos/SSM cuando corresponda.

---

# 8. Sprint 6 — Resiliencia y Entregable 3

Implementar:

- máximo de simulaciones concurrentes por usuario, inicialmente 2;
- tercera simultánea rechazada con error claro, preferiblemente HTTP 429;
- control de capacidad/backlog y respuesta 429 ordenada;
- simulación de caída de worker;
- recuperación/reintento;
- otras sesiones no afectadas;
- pruebas de acceso a sesiones ajenas;
- consolidación de carga/resiliencia;
- Entregable 3 con JWT, seguridad, cuotas, control de admisión y resultados.

---

# 9. Fuera de alcance deliberadamente

- HIL no se implementará en este ciclo.
- Kubernetes/EKS no se utilizará.
- TLS/WSS gestionado queda pendiente si exige gasto adicional.

---

# 10. Arquitectura objetivo de microservicios

```text
USUARIO
   |
   v
FRONTEND
   |
 REST + WebSocket
   |
   v
SIMULATION API / MANAGER
   |
 SimulationJob
   |
   v
ORQUESTADOR / EXECUTOR
   |
   v
SIMULATION WORKER(S)
   |
   v
AltDSS / OpenDSS
```

## Frontend

Responsabilidades:
- interfaz;
- selección de modelo;
- Snapshot/QSTS;
- progreso;
- resultados;
- autenticación.

## Simulation API / Manager

Responsabilidades:
- REST;
- WebSocket;
- JWT;
- autorización;
- propiedad de sesiones;
- creación de jobs;
- cuotas;
- admisión;
- estado lógico;
- progreso;
- resultados;
- logs.

No debe ejecutar directamente OpenDSS en la arquitectura final.

## Simulation Worker

Responsabilidades:
- cargar modelo;
- crear `OpenDSSContextEngine`;
- ejecutar Snapshot/QSTS;
- reportar progreso;
- guardar/devolver resultado;
- terminar.

No conoce HTML, usuarios ni autenticación web.

---

# 11. Contratos centrales

Se crearán contratos explícitos:

- `SimulationJob`;
- `SimulationProgress`;
- `SimulationResult`;
- `SimulationError`.

Ejemplo conceptual de `SimulationJob`:

```json
{
  "job_id": "uuid",
  "session_id": "uuid",
  "user_id": "user-1",
  "topology": "ieee8500",
  "simulation_type": "qsts",
  "qsts": {
    "duration_hours": 24,
    "step_minutes": 5,
    "profile_source": "synthetic_daily"
  }
}
```

---

# 12. Paralelización

QSTS individual dependiente:

```text
QSTS A → Worker A → 288 steps secuenciales
```

Escenarios independientes:

```text
Escenario A → Worker 1
Escenario B → Worker 2
Escenario C → Worker 3
```

Esto habilita Monte Carlo, contingencias, perfiles distintos, feeders distintos y usuarios concurrentes.

---

# 13. Arquitectura cloud recomendada

Servicios previstos:

- Amazon ECR para imágenes Docker;
- ECS/Fargate para workers;
- Step Functions o executor equivalente para orquestación;
- S3 para resultados/inputs grandes;
- CloudWatch para logs y métricas;
- Secrets Manager/SSM para secretos;
- almacenamiento de estado/usuarios cuando se cierre autenticación.

No se requiere RDS obligatoriamente en la primera versión.

---

# 14. Regla local/cloud

> **No debe existir una versión del código para local y otra para nube.**

Mismas imágenes, contratos, endpoints, worker, engine y pruebas.

Solo cambian:

- variables de entorno;
- infraestructura;
- URLs;
- secretos;
- número de réplicas;
- recursos asignados.

Puede existir configuración como:

```text
EXECUTION_BACKEND=local
```

o:

```text
EXECUTION_BACKEND=aws
```

sin modificar código.

---

# 15. Infraestructura como código

Recomendación: **Terraform** para AWS.

Objetivo cloud:

```powershell
./scripts/deploy_cloud.ps1
```

Debe validar configuración, construir imágenes, publicar en ECR, aplicar Terraform, desplegar, esperar health y ejecutar smoke tests.

Objetivo local:

```powershell
./scripts/deploy_local.ps1
```

Debe ejecutar Docker Compose y smoke tests.

También:

```powershell
./scripts/destroy_cloud.ps1
```

para evitar costos accidentales.

---

# 16. Estructura propuesta del repositorio

```text
DT_OpenDSS_cloud/
│
├── services/
│   ├── api-manager/
│   │   ├── app/
│   │   │   ├── api/
│   │   │   ├── auth/
│   │   │   ├── orchestration/
│   │   │   ├── security/
│   │   │   ├── repositories/
│   │   │   ├── platform/
│   │   │   └── main.py
│   │   ├── Dockerfile
│   │   └── requirements.txt
│   │
│   ├── simulation-worker/
│   │   ├── app/
│   │   │   ├── worker.py
│   │   │   ├── executor.py
│   │   │   ├── callbacks.py
│   │   │   └── platform/
│   │   ├── Dockerfile
│   │   └── requirements.txt
│   │
│   └── frontend/
│       ├── templates/
│       ├── static/
│       ├── Dockerfile
│       └── nginx.conf
│
├── packages/
│   ├── simulation-core/
│   │   ├── engine.py
│   │   ├── qsts_profiles.py
│   │   ├── model_catalog.py
│   │   ├── topology_catalog.py
│   │   └── models/
│   │
│   └── contracts/
│       ├── jobs.py
│       ├── progress.py
│       ├── results.py
│       ├── errors.py
│       └── auth.py
│
├── data/
│   └── networks/
│       ├── ieee13/
│       ├── ieee34/
│       ├── ieee123/
│       └── ieee8500/
│
├── infra/
│   ├── local/
│   │   ├── docker-compose.yml
│   │   ├── .env.example
│   │   └── README.md
│   │
│   └── aws/
│       ├── terraform/
│       │   ├── main.tf
│       │   ├── variables.tf
│       │   ├── outputs.tf
│       │   ├── networking.tf
│       │   ├── ecr.tf
│       │   ├── ecs.tf
│       │   ├── iam.tf
│       │   ├── s3.tf
│       │   ├── cloudwatch.tf
│       │   ├── secrets.tf
│       │   └── stepfunctions.tf
│       └── stepfunctions/
│           └── simulation.asl.json
│
├── scripts/
│   ├── bootstrap_ieee_models.py
│   ├── qsts_smoke.py
│   ├── qsts_api_smoke.py
│   ├── qsts_ws_smoke.py
│   ├── ieee8500_smoke.py
│   ├── ieee8500_api_smoke.py
│   ├── performance_campaign.py
│   ├── deploy_local.ps1
│   ├── deploy_cloud.ps1
│   └── destroy_cloud.ps1
│
├── load/
│   └── locustfile.py
│
├── tests/
│   ├── unit/
│   ├── integration/
│   ├── security/
│   ├── resilience/
│   └── load/
│
├── docs/
│   ├── architecture/
│   ├── deployment/
│   ├── security/
│   ├── evidence/
│   ├── deliverable_2/
│   ├── deliverable_3/
│   ├── retrospectives/
│   └── CONTEXTO_MAESTRO_PROYECTO.md
│
├── .env.example
├── .gitignore
├── README.md
└── pyproject.toml / requirements correspondientes
```

---

# 17. Imágenes Docker previstas

## `opendss-api-manager`

Contiene FastAPI, REST, WebSocket, JWT, cuotas, admisión, logs y manejo de jobs.

## `opendss-simulation-worker`

Contiene Python, AltDSS, OpenDSSContextEngine, QSTS, perfiles y modelos IEEE13/34/123/8500.

## `opendss-frontend`

Opcional. Localmente puede usar Nginx. En producción podría sustituirse por hosting estático.

---

# 18. Qué código se sube a AWS

No se copia manualmente todo el repositorio a cada instancia/worker.

Flujo final:

```text
Git repository
    |
Docker build
    |
ECR
    |
AWS ejecuta imágenes
```

Los workers reciben el código dentro de la imagen `opendss-simulation-worker:<version>`.

La API recibe `opendss-api-manager:<version>`.

La infraestructura se crea desde `infra/aws/terraform/`.

---

# 19. Versionado de imágenes

Usar tags reproducibles:

```text
opendss-api-manager:<git-sha>
opendss-simulation-worker:<git-sha>
```

`:latest` solo para desarrollo.

---

# 20. Configuración

Toda configuración variable debe salir del código.

Ejemplos:

```text
APP_ENV
JWT_SECRET
JWT_EXPIRATION
MAX_CONCURRENT_SIMULATIONS_PER_USER
MAX_QUEUE_DEPTH
EXECUTION_BACKEND
RESULT_BUCKET
AWS_REGION
WORKER_CPU
WORKER_MEMORY
LOG_LEVEL
```

Local: `.env`.  
Cloud: variables de entorno + Secrets Manager/SSM.

---

# 21. Seguridad

La autenticación puede comenzar con usuarios de laboratorio configurados de forma segura, sin requerir todavía una base de datos compleja.

Cada job debe incluir `user_id` y cada endpoint debe validar propiedad.

---

# 22. Control de admisión

Flujo:

```text
authenticate
    ↓
authorize
    ↓
quota check
    ↓
capacity check
    ↓
accept / reject
```

Códigos esperados:

- 401: no autenticado;
- 403: no autorizado;
- 429: cuota/capacidad excedida.

---

# 23. Resiliencia de workers

Estados mínimos:

```text
QUEUED
RUNNING
FAILED
RETRYING
COMPLETED
```

Prueba obligatoria:

1. lanzar múltiples jobs;
2. matar un worker;
3. otros jobs continúan;
4. el job fallido se reintenta/reasigna;
5. medir tiempo de recuperación.

---

# 24. Logs estructurados

Formato recomendado JSON.

Eventos mínimos:

- LOGIN_SUCCESS;
- LOGIN_FAILED;
- AUTH_REJECTED;
- ACCESS_DENIED;
- QUOTA_EXCEEDED;
- OVERLOAD_REJECTED;
- JOB_CREATED;
- JOB_STARTED;
- JOB_COMPLETED;
- JOB_FAILED;
- WORKER_LOST;
- JOB_RETRY.

Cada evento debe registrar timestamp, origen/IP cuando aplique y tipo de evento.

---

# 25. Métricas finales

Mantener:

- p50;
- p95;
- p99;
- mean;
- max;
- RPS;
- errors;
- RSS;
- CPU.

Agregar con workers:

- jobs queued;
- jobs running;
- jobs completed;
- jobs failed;
- worker count;
- worker RSS;
- worker CPU;
- retry count;
- queue wait time;
- execution time;
- end-to-end time.

---

# 26. Documentación requerida

```text
docs/
├── architecture/
│   ├── ARCHITECTURE_LOGICAL.md
│   ├── ARCHITECTURE_DEPLOYMENT_AWS.md
│   └── ADR/
├── deployment/
│   ├── LOCAL_DEPLOYMENT.md
│   ├── AWS_DEPLOYMENT.md
│   └── DISASTER_RECOVERY.md
├── security/
│   ├── JWT_SECURITY.md
│   ├── ZERO_TRUST_CHECKLIST.md
│   └── SECURITY_TEST_RESULTS.md
├── deliverable_2/
│   ├── CHECKLIST_ENTREGABLE_2.md
│   └── ENTREGABLE_2.md
├── deliverable_3/
│   ├── CHECKLIST_ENTREGABLE_3.md
│   └── ENTREGABLE_3.md
├── retrospectives/
│   ├── SPRINT_4.md
│   ├── SPRINT_5.md
│   └── SPRINT_6.md
└── CONTEXTO_MAESTRO_PROYECTO.md
```

---

# 27. Un botón de despliegue

## Local

```powershell
./scripts/deploy_local.ps1
```

Debe construir, levantar Docker Compose y ejecutar smoke tests.

## AWS

```powershell
./scripts/deploy_cloud.ps1
```

Debe validar AWS CLI, construir imágenes, publicar en ECR, aplicar Terraform, actualizar servicios, esperar health, ejecutar smoke tests e imprimir endpoints.

## Destrucción

```powershell
./scripts/destroy_cloud.ps1
```

para evitar costos accidentales.

---

# 28. Orden recomendado de trabajo

## R0 — Congelar baseline

- tag Git;
- guardar resultados actuales;
- documentar baseline;
- preservar versión monolítica funcional.

## R1 — Reorganizar sin cambiar comportamiento

Mover hacia `services/`, `packages/`, `infra/` manteniendo tests y funcionalidad.

## R2 — Contratos

Crear `SimulationJob`, `SimulationProgress`, `SimulationResult`, `SimulationError`.

## R3 — Executor abstracto

Crear interfaz `submit/cancel/status` y primera implementación local.

## R4 — Separar worker

Crear imagen `simulation-worker`, primero ejecutada localmente.

## R5 — Docker Compose laboratorio

Levantar frontend, api-manager y simulation-worker con las mismas imágenes destinadas a AWS.

## R6 — JWT y seguridad

Implementar JWT REST/WS, ownership, logs, secretos y pruebas 401/403.

## R7 — Cuotas/admisión

Máximo 2 jobs por usuario, backlog máximo y 429.

## R8 — Resiliencia

Worker failure, retry/reassignment y métricas.

## R9 — Infraestructura AWS

CloudFormation para ECR, IAM, VPC/SG, ECS/Fargate, Cloud Map, EFS, CloudFront/ALB, CloudWatch, Secrets Manager y auto scaling.

## R10 — Despliegue cloud

Mismas imágenes Docker.

## R11 — Pruebas cloud

Smoke, performance campaign, Locust, seguridad y resiliencia.

## R12 — Documentación final

Entregables 2 y 3, checklists, retrospectivas y backlog HIL.

---

# 29. Criterio de terminado

El proyecto se considera listo cuando:

- código local organizado;
- Docker Compose reproduce laboratorio;
- frontend/API/worker separados;
- Snapshot y QSTS funcionan;
- IEEE13/34/123/8500 funcionan;
- JWT funciona;
- WebSocket protegido;
- ownership funciona;
- cuota funciona;
- overload devuelve 429;
- worker failure se recupera;
- métricas disponibles;
- Locust 5-10 usuarios documentado;
- cloud desplegable mediante IaC;
- evidencias guardadas;
- Entregable 2 completo;
- Entregable 3 completo;
- TLS/WSS marcado pendiente si no se implementa;
- HIL fuera de alcance;
- no existen secretos versionados;
- despliegue reproducible documentado.

---

# 30. Decisiones arquitectónicas vigentes

1. No Kubernetes/EKS.
2. Docker como unidad de empaquetado.
3. Monorepo por servicios.
4. Mismo código local/cloud.
5. Configuración por entorno.
6. Worker OpenDSS separado de API.
7. Un QSTS dependiente completo permanece en un worker.
8. Paralelización entre jobs/escenarios.
9. Infraestructura AWS declarativa.
10. AWS CloudFormation es el IaC definitivo del laboratorio AWS.
11. ECS/Fargate para API (1 task inicial) y un worker service con N tasks.
12. ECR para imágenes.
13. EFS para modelos custom compartidos; S3 queda opcional para resultados grandes futuros.
14. CloudWatch para logs/métricas.
15. JWT y ownership antes del cierre.
16. TLS/WSS implementado localmente con Caddy y en AWS mediante CloudFront HTTPS/WSS con certificado predeterminado.
17. HIL fuera de alcance.

---

# 31. Prioridad inmediata

La prioridad ya no es agregar funcionalidad eléctrica.

```text
ORGANIZAR
→ DESACOPLAR
→ ASEGURAR
→ HACER RESILIENTE
→ EMPAQUETAR
→ AUTOMATIZAR DESPLIEGUE
→ PROBAR
→ DOCUMENTAR
```

El motor eléctrico ya funciona. El trabajo restante es principalmente arquitectura, operación, seguridad, resiliencia, despliegue y evidencia.


---

# 32. Actualización final para AWS one-click

Estado de cierre previo a cloud:

- API Manager seguro, ownership/viewers y JWT: implementado.
- Pool de N workers y afinidad de sesión: implementado.
- Retry/failover: implementado.
- HTTPS/WSS local: Caddy.
- AWS entrypoint: CloudFront `*.cloudfront.net`, evitando dominio/ACM manual para el laboratorio efímero.
- Origen: ALB restringido a la managed prefix list de CloudFront.
- API AWS: ECS/Fargate desiredCount=1 porque el estado lógico/WebSocket continúa en memoria.
- Workers AWS: un ECS service con N tasks.
- Discovery AWS: Cloud Map DNS `simulation-worker.opendss.local` + `DnsWorkerDiscovery`.
- Custom models: EFS compartido en `/app/data/runtime/custom_models`.
- Images: ECR, tag Git SHA.
- Secrets: Secrets Manager.
- Logs: CloudWatch.
- Auto scaling workers: CPU scale-out-only; scale-in automático deshabilitado para no matar contextos stateful activos.
- IaC: CloudFormation en dos stacks, `bootstrap` y `main`.
- Operación objetivo: `scripts/deploy_cloud.ps1` crea todo y `scripts/destroy_cloud.ps1` elimina todo.
- Evidencia reproducible: `docs/evidence/` organizada por entregable y timestamp.

Advertencia académica: el texto recibido del Entregable 2 menciona literalmente Google Cloud Platform, mientras la implementación final es AWS. Se requiere aprobación de cambio de proveedor o ajuste de redacción antes de declarar cumplimiento literal.
