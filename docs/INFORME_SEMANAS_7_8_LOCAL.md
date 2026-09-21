# Informe Semanas 7–8 (entorno local)

## 1. Resumen y arquitectura

Se incorporó un catálogo dinámico IEEE13/34/123, UI de crear/unirse,
workspaces aislados para modelos personalizados, edición DSS segura,
configuración por entorno y empaquetado Docker/Compose.

```text
clientes (REST + WS)
          |
    FastAPI container
          |
  SimulationService ---- model catalog
          |                    |
 sessions/contextos       custom workspaces
          |
        AltDSS
```

## 2. Archivos

### Creados

| Ruta | Cambio y criterio |
|---|---|
| `app/platform/settings.py` | Defaults y variables de entorno centralizadas (F). |
| `app/adapters/opendss/model_catalog.py` | Catálogo incorporado (C). |
| `app/orchestration/custom_models.py` | Upload, extracción segura, validación y edición (D/E/O). |
| `app/api/routes/models.py` | Endpoints de modelos (C/D/E). |
| `app/static/css/app.css`, `app/static/js/app.js` | UI técnica separada (A/B). |
| `scripts/bootstrap_ieee_models.py` | Bootstrap idempotente conservando testcase (C). |
| `Dockerfile`, `.dockerignore`, `compose.yaml` | Contenedor, healthcheck y volumen (G/H). |
| `.env.example`, `scripts/smoke_test.py` | Operación configurable y smoke REST/WS (F/J). |
| `docs/CLOUD_READINESS.md` | Preparación local y pendientes AWS (L). |

### Modificados

`app/main.py` monta estáticos y rutas; `topology_catalog.py` resuelve los tres
masters y custom; `simulation_service.py` usa límites de configuración y
conserva el reciclaje; `simulations.py` expone errores de creación; `README.md`
y `.gitignore` documentan operación y runtime; `requirements.txt` declara
multipart para uploads; `scripts/bootstrap_ieee13.py` delega al bootstrap nuevo.

## 3. Funciones y clases principales

`Settings` centraliza defaults; `CustomModelManager` mantiene cada carga bajo
su workspace, valida ZIP Slip y extensiones, y compila en un `OpenDSSContextEngine`
descartable. Las rutas `/models` listan, cargan, validan, leen y guardan.
`SimulationService` continúa siendo la autoridad de cada sesión: un join solo
lee detalle y subscribe, y el broadcast se entrega a todos los subscribers del
mismo ID.

## 4. Docker y Compose

`Dockerfile` usa `python:3.13-slim`, instala `requirements.txt`, prepara los
tres snapshots, crea usuario `appuser`, expone 8000 y comprueba `/health`.
Compose publica `${APP_PORT:-8000}`, carga `.env`, monta `custom-models` y no
añade servicios externos. No usar múltiples workers/replicas mientras el
estado sea memoria.

## 5. Variables

| Variable | Default | Propósito |
|---|---:|---|
| APP_HOST | 0.0.0.0 | Bind |
| APP_PORT | 8000 | Puerto documentado |
| LOG_LEVEL | INFO | Logging |
| RECYCLE_THRESHOLD | 162 | Reciclaje lógico |
| MAX_ACTIVE_SIMULATIONS | 32 | Límite memoria |
| MAX_UPLOAD_MB | 25 | Tamaño de upload |
| MAX_UPLOAD_FILES | 500 | Archivos ZIP |
| ALLOW_CUSTOM_MODELS | true | Habilitar custom |
| CUSTOM_MODELS_DIR | data/runtime/custom_models | Workspace |
| CORS_ORIGINS | vacío | CORS opcional |

## 6. Modelos y flujo custom

IEEE13 usa `IEEE13Nodeckt.dss`, IEEE34 `Run_IEEE34Mod1.dss` e IEEE123
`IEEE123Master.dss`, copiados con sus auxiliares y redirects. Flujo custom:
`upload -> extract -> select master -> validate -> error -> edit -> save ->
validate -> simulation`. No se registra una `SimulationSession` durante upload
ni validación.

## 7. Pruebas y aceptación

La suite existente se ejecutó antes de los cambios: 12 passed en 5.84 s.
La suite final ejecutó 15 passed en 3.79 s. En ambas ejecuciones apareció el
diagnóstico Windows `0xe0465043` conocido durante importación DSS, sin impedir
la ejecución. La prueba adicional de modelos ejecutó 3 passed en 3.17 s.
`scripts/smoke_test.py` cubre health, docs, modelos, sesión, solve,
WebSocket, resultado y cierre; acepta `BASE_URL`/`WS_BASE_URL`.

| Área | Estado |
|---|---|
| Catálogo y API local | CUMPLE |
| UI multi-viewer same-origin | CUMPLE |
| Upload/seguridad/edición | CUMPLE |
| Docker/Compose | NO VERIFICADO (daemon Docker no disponible en el host) |
| Smoke contra contenedor | NO VERIFICADO (daemon Docker no disponible en el host) |
| Registry, URL, latencia e aislamiento cloud | PENDIENTE |
| Despliegue AWS | PENDIENTE |

## 8. Limitaciones y próximos pasos AWS

Estado en memoria, una instancia, sin JWT, TLS externo, autoscaling ni
persistencia distribuida. En Semana 8/AWS se debe elegir registry y runtime,
configurar secretos/IAM, almacenamiento de modelos, observabilidad, TLS,
afinidad o broker WebSocket y pruebas de carga; esos criterios permanecen
**PENDIENTE DE AWS** y no se declaran cumplidos aquí.
