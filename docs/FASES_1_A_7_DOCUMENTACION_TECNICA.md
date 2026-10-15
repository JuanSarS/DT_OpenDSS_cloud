# OpenDSS Cloud — Documentación técnica consolidada Fases 1 a 7

## 1. Objetivo general

OpenDSS Cloud proporciona una consola local para cargar modelos OpenDSS,
crear sesiones aisladas, ejecutar flujos Snapshot y QSTS, observar progreso
por WebSocket y consultar resultados completos por REST. La implementación
actual prioriza reproducibilidad local, separación de contextos OpenDSS y
preparación para comparar posteriormente el mismo flujo contra cloud.

Al cierre de la Fase 7, el flujo local funciona con IEEE13, IEEE34, IEEE123 e
IEEE8500 para Snapshot. QSTS está validado con IEEE123 y con IEEE8500 para
una prueba corta de tres pasos y una hora (12 pasos). No se ejecutó QSTS de
24 horas sobre IEEE8500.

## 2. Arquitectura general

El flujo principal es:

```text
Frontend HTML/CSS/JavaScript
        |
        +--> REST FastAPI
        |       |
        |       +--> SimulationService
        |                    |
        |                    +--> OpenDSSContextEngine
        |                              |
        |                              +--> AltDSS NewContext()
        |
        +--> WebSocket /ws/simulations/{session_id}
        |
        +--> GET /metrics
```

### Frontend

La interfaz existente mantiene su diseño blanco y fluido. Carga modelos con
`GET /models`, crea o une sesiones, configura Snapshot/QSTS, conecta el
WebSocket, muestra progreso y consulta `/results` al finalizar. Las pestañas
incluyen Voltajes, Potencias, QSTS, Métricas, Eventos, Resumen y el Diagrama
reservado para una fase futura.

### FastAPI y SimulationService

FastAPI expone las rutas de health, modelos, simulaciones y métricas.
`SimulationService` mantiene las sesiones en memoria, un lock por sesión,
un contexto OpenDSS por sesión, el último resultado y los observadores
WebSocket.

### OpenDSSContextEngine

Cada `OpenDSSContextEngine` crea un `altdss.NewContext()` independiente.
Snapshot y QSTS usan el mismo contexto de la sesión; QSTS no recompila el
modelo por paso.

### REST

- `POST /simulations`: crea una sesión y carga el modelo.
- `GET /simulations`: lista sesiones activas.
- `GET /simulations/{id}`: devuelve estado y resumen del modelo.
- `POST /simulations/{id}/solve`: ejecuta Snapshot o QSTS.
- `GET /simulations/{id}/results`: fuente final del resultado completo.
- `DELETE /simulations/{id}`: libera la sesión.
- `GET /metrics`: devuelve métricas internas del proceso.

### WebSocket

`/ws/simulations/{session_id}` acepta varios observadores de una misma
sesión, envía un snapshot inicial y reutiliza el broadcast existente para
eventos Snapshot y QSTS.

### QSTS

`solve_qsts()` ejecuta un `Solve()` por paso y puede invocar un callback
opcional. El callback se ejecuta en el worker thread y se conecta al event
loop mediante `asyncio.run_coroutine_threadsafe()`.

### Métricas, performance y Locust

`app/platform/metrics.py` mantiene acumuladores y buffers limitados. La
campaña `scripts/performance_campaign.py` mide REST y WebSocket y guarda
evidencias comparables local/cloud. `load/locustfile.py` contiene usuarios
Snapshot y QSTS para pruebas de carga controladas.

## 3. Fase 1 — Engine QSTS

Se incorporaron los contratos:

- `QSTSConfig`: duración, tamaño de paso, fuente de perfil y multiplicadores.
- `QSTSStepResult`: step, tiempo simulado, convergencia, LoadMult, potencias,
  voltajes mínimos/máximos, solve time e información de RSS.
- `QSTSResult`: configuración, total de pasos, convergencia, tiempos
  estadísticos, RSS y lista completa de steps.

`OpenDSSContextEngine.solve_qsts()`:

1. configura modo diario y tamaño de paso;
2. obtiene o valida el perfil temporal;
3. actualiza `Solution.LoadMult`;
4. ejecuta un solve;
5. calcula datos compactos del step;
6. invoca el callback opcional;
7. construye el resultado completo para REST.

El modelo se carga una sola vez y se mantiene un contexto por sesión.

### Resultado real

El smoke QSTS local para IEEE123 validó 288 pasos de 24 horas a cinco minutos,
con todos los pasos convergentes. También se creó `tests/test_qsts_engine.py`
para el motor.

## 4. Fase 2 — Perfiles temporales

Se creó `app/domain/qsts_profiles.py` con los perfiles:

- `constant`: LoadMult constante.
- `synthetic_daily`: perfil determinista `synthetic_mixed_daily_v1`.
- `model`: utiliza el comportamiento temporal definido en el DSS.
- `values`: lista explícita de un valor por paso.

El perfil sintético es determinista y se interpola linealmente entre puntos de
la curva diaria. En el smoke IEEE123 de 288 pasos, el LoadMult observado
estuvo entre `0.46` y `1.0`. El resultado incluyó potencias, voltajes
mínimos/máximos, tiempos de solve y RSS por step.

`values` valida que:

```text
duration_hours * 60 / step_minutes
```

sea entero y que la lista tenga exactamente esa cantidad de valores positivos.

## 5. Fase 3 — REST QSTS

`POST /simulations/{id}/solve` acepta:

```json
{
  "simulation_type": "qsts",
  "qsts": {
    "duration_hours": 0.25,
    "step_minutes": 5,
    "profile_source": "values",
    "load_multipliers": [0.8, 1.0, 1.2]
  }
}
```

También conserva Snapshot cuando no se envía body o se usa
`simulation_type="snapshot"`.

Las validaciones incluyen:

- `qsts` obligatorio para QSTS;
- `qsts` prohibido para Snapshot;
- duración divisible entre paso;
- lista `values` obligatoria y de longitud exacta;
- valores numéricos, no booleanos y positivos;
- perfiles compatibles con sus campos.

La ejecución nativa se mantiene fuera del event loop mediante
`asyncio.to_thread()`.

### Resultado real REST

El smoke REST validó:

- Snapshot convergente;
- QSTS IEEE123 de 288 pasos convergentes;
- QSTS `values=[0.8, 1.0, 1.2]` con 3 pasos;
- recuperación completa mediante `GET /results`.

## 6. Fase 4 — WebSocket QSTS

Se reutilizó la ruta:

```text
/ws/simulations/{session_id}
```

El servicio mantiene un conjunto de subscribers por sesión. Al conectar,
cada observador recibe un evento `snapshot` con estado actual. El broadcast
elimina conexiones cerradas y no mezcla sesiones.

Se preservaron los eventos generales:

- `simulation_started`
- `model_loaded`
- `solving`
- `result`
- `completed`
- `error`

Se agregó únicamente el evento específico:

```text
qsts_progress
```

Su payload compacto contiene step, total_steps, progress_pct,
simulated_minutes, simulated_hour, converged, solve_ms y load_multiplier,
con potencias y voltajes resumidos cuando están disponibles.

El estado tardío mantiene:

- `current_step`;
- `total_steps`;
- `progress_pct`;
- `simulated_hour`;
- `last_qsts_step`.

Se probaron:

- progreso ordenado 1, 2, 3;
- dos observadores de la misma sesión;
- aislamiento entre sesiones;
- observador tardío;
- health durante QSTS;
- recuperación REST posterior.

El smoke `scripts/qsts_ws_smoke.py` confirmó tres pasos,
`result`, `completed` y tres steps disponibles por REST.

## 7. Fase 5 — Métricas y rendimiento

### Métricas internas

`GET /metrics` expone:

- proceso: RSS MB, CPU %, threads;
- sesiones: active, running, completed, error;
- REST: latencias de creación, Snapshot, QSTS y resultados;
- Snapshot: count y distribución de solve;
- QSTS: runs, total steps, elapsed y distribución por step.

Las estadísticas incluyen count, mean, min, p50, p95, p99 y max. Los buffers
se limitan con `deque(maxlen=2000)`.

### Evidencias

Cada campaña crea:

```text
docs/evidence/performance/<run_id>/
├── config.json
├── raw_results.csv
├── summary.json
├── metrics_before.json
└── metrics_after.json
```

### Snapshot IEEE123 — 30 iteraciones

Evidencia:
`docs/evidence/performance/20261014T230630Z_local_ieee123_snapshot/summary.json`

| Métrica `solve_http_ms` | Valor |
|---|---:|
| Media | 49.552 ms |
| p50 | 45.413 ms |
| p95 | 55.536 ms |
| p99 | 123.909 ms |
| Máximo | 151.524 ms |
| Errores | 0 |

### QSTS IEEE123 — 30 iteraciones

Evidencia:
`docs/evidence/performance/20261014T230642Z_local_ieee123_qsts/summary.json`

Configuración: 24 horas, cinco minutos, `synthetic_daily`, 288 steps.

| Métrica `solve_http_ms` | Valor |
|---|---:|
| Media | 391.319 ms |
| p50 | 363.058 ms |
| p95 | 550.675 ms |
| p99 | 572.757 ms |
| Máximo | 580.667 ms |
| Errores | 0 |

### Locust

| Campaña | Requests | Failures | RPS | p50 | p95 | p99 | Máximo |
|---|---:|---:|---:|---:|---:|---:|---:|
| 5 usuarios | 847 | 0 | 29.12 | 16 ms | 120 ms | 240 ms | 569 ms |
| 10 usuarios | 1169 | 0 | 39.34 | 25 ms | 350 ms | 1200 ms | 1695 ms |

Las ejecuciones distribuyeron usuarios entre Snapshot y QSTS. Los CSV están
en `docs/evidence/performance/locust_local_5users_*` y
`docs/evidence/performance/locust_local_10users_*`.

RSS observado al final de campañas anteriores:

- Snapshot IEEE123: aproximadamente 176.9 MB, CPU 62.1%.
- QSTS IEEE123: aproximadamente 227.4 MB, CPU 70.9%.

## 8. Fase 6 y 6.1 — Frontend

El frontend carga el catálogo con `GET /models`; no contiene una lista fija
de IEEE13, IEEE34, IEEE123 o IEEE8500.

La configuración permite Snapshot y QSTS. Para QSTS se muestran duración,
paso y perfiles `constant`, `synthetic_daily`, `model` y `values`. La UI
cuenta los valores esperados y bloquea una petición incompleta.

El WebSocket actualiza el indicador API/WS, la barra, el step, hora, LoadMult,
potencias, Vmin, Vmax y solve time. Los eventos se conservan en una lista de
los últimos 100.

Al recibir `completed`, la interfaz consulta siempre:

```text
GET /simulations/{id}/results
```

Se corrigió el problema Snapshot porque `/results` no devuelve el Snapshot
directamente en la raíz, sino:

```json
{
  "session_id": "...",
  "simulation_type": "snapshot",
  "result": {
    "converged": true,
    "voltages": {},
    "total_power_kw": 0,
    "total_power_kvar": 0
  }
}
```

QSTS, en cambio, devuelve `config`, `summary` y `steps` en la raíz. Se
implementaron `normalizeSnapshotResult()` y `normalizeQSTSResult()` para no
mezclar contratos.

La validación visual confirmó Snapshot IEEE123 con:

- convergencia: Sí;
- 132 buses;
- 278 nodos;
- 278 filas de voltaje;
- potencias activa y reactiva visibles;
- resumen visible.

## 9. Fase 7 — IEEE8500

### Fuente y bootstrap

IEEE8500 proviene del conjunto público OpenDSS `electricdss-tst`, dentro de:

```text
Version8/Distrib/IEEETestCases/8500-Node
```

El bootstrap existente `scripts/bootstrap_ieee_models.py` fue extendido. No
se creó una arquitectura de descarga nueva. El modelo instalado queda en:

```text
data/networks/ieee8500/
```

El master original es:

```text
data/networks/ieee8500/Master.dss
```

### Dependencias

El master utiliza Redirect relativos para:

- `LineCodes2.DSS`;
- `Triplex_Linecodes.dss`;
- `Lines.dss`;
- `Transformers.dss`;
- `LoadXfmrCodes.dss`;
- `Triplex_Lines.DSS`;
- `Loads.dss`;
- `Capacitors.dss`;
- `CapControls.DSS`;
- `Regulators.dss`;
- `Buscoords.dss`.

Las dependencias fueron copiadas por el bootstrap y se verificó que las
rutas relativas fueran resolubles.

### Adaptación headless

`Run_8500Node.dss` contiene comandos interactivos como `Show`, `Export` y
`Plot`; no se usa para el backend.

El master original no fue modificado. Debido a que Snapshot no convergía con
el límite predeterminado de iteraciones, se generó:

```text
data/networks/ieee8500/Master_cloud.dss
```

La única diferencia funcional es:

```text
Set Maxiterations=20
```

El catálogo apunta a `Master_cloud.dss`. Esta copia conserva todos los
Redirect relativos del original y no agrega comandos gráficos.

### Registro

`app/adapters/opendss/model_catalog.py` registra:

```text
ieee8500 -> data/networks/ieee8500/Master_cloud.dss
```

`GET /models` devuelve automáticamente IEEE13, IEEE34, IEEE123 e IEEE8500.

### Snapshot directo del engine

Script:
`scripts/ieee8500_smoke.py`

| Campo | Resultado |
|---|---:|
| Convergencia | True |
| Buses | 4876 |
| Nodos | 8531 |
| Total kW | -11983.670215 |
| Total kvar | -1385.200499 |
| Solve | 159.213 ms |
| Carga del modelo | 362.472 ms |
| RSS antes | 109.348 MB |
| RSS después de carga | 143.867 MB |
| RSS después de solve | 168.215 MB |

### Snapshot REST, QSTS corto y QSTS de una hora

Script:
`scripts/ieee8500_api_smoke.py`

Snapshot REST:

- convergente: `true`;
- buses: 4876;
- nodos: 8531;
- solve: 177.046 ms;
- total kW: -11983.670215;
- total kvar: -1385.200499.

QSTS corto:

- duración: 15 minutos;
- paso: 5 minutos;
- steps: 3;
- convergentes: 3;
- LoadMult: `[0.8, 1.0, 1.2]`.

QSTS de una hora:

- duración: 1 hora;
- paso: 5 minutos;
- steps: 12;
- convergentes: 12;
- fallidos: 0;
- elapsed: 332.639 ms;
- Vmin observado: 0.962568;
- Vmax observado: 1.072498.

Métricas del proceso durante el smoke REST:

- RSS antes: 117.457 MB;
- RSS después: 215.234 MB;
- CPU después: 60.2%;
- threads después: 9.

### Interfaz y campaña Snapshot

La interfaz mostró IEEE8500 automáticamente, creó la sesión, conectó el
WebSocket y mostró:

- convergente: Sí;
- 4876 buses;
- 8531 nodos;
- 8531 filas de voltaje;
- potencias;
- resultado completo.

La campaña Snapshot IEEE8500 se ejecutó con 10 iteraciones, sin Locust y sin
QSTS de 24 horas.

Evidencia:
`docs/evidence/performance/20261015T003106Z_local_ieee8500_snapshot/summary.json`

| Operación | Media | p50 | p95 | p99 | Máximo |
|---|---:|---:|---:|---:|---:|
| create_ms | 239.773 | 235.173 | 261.984 | 268.761 | 270.455 |
| solve_http_ms | 1119.684 | 1090.628 | 1281.244 | 1292.691 | 1295.552 |
| ws_result_ms | 1044.336 | 1008.807 | 1216.080 | 1219.497 | 1220.351 |
| ws_completed_ms | 1090.780 | 1055.290 | 1246.999 | 1247.725 | 1247.906 |
| get_results_ms | 261.586 | 240.806 | 367.502 | 443.795 | 462.868 |

Errores: 0.

La primera ejecución de la campaña falló por el límite de tamaño de mensaje
del cliente WebSocket (`1009`) debido al payload Snapshot grande de IEEE8500.
Se ajustó únicamente `performance_campaign.py` para aceptar frames de hasta
16 MiB; el contrato del backend no fue modificado.

No se ejecutó QSTS de 24 horas ni Locust para IEEE8500.

## 10. Inventario de archivos

| Archivo | Fase | Tipo | Cambio realizado | Motivo | Impacto |
|---|---|---|---|---|---|
| `app/adapters/opendss/engine.py` | 1, 2, 4 | Modificado | QSTS, perfiles, callback y resultados por step | Ejecutar QSTS y publicar progreso sin acoplar FastAPI | Motor temporal reutilizable |
| `app/adapters/opendss/model_catalog.py` | 7 | Modificado | Registro de IEEE8500 y `Master_cloud.dss` | Exponer el modelo en `/models` | Catálogo dinámico |
| `app/adapters/opendss/topology_catalog.py` | 1-7 | Modificado | Resolución del catálogo existente | Resolver masters registrados | Carga de sesiones |
| `app/api/routes/metrics.py` | 5 | Creado | Endpoint `GET /metrics` | Exponer métricas internas | Observabilidad local |
| `app/api/routes/simulations.py` | 3-5 | Modificado | REST Snapshot/QSTS y latencias | Integrar solve, resultados y métricas | API completa |
| `app/domain/models.py` | 1-4 | Modificado | Contratos QSTS y validaciones | Tipar configuración y resultados | Contratos REST/engine |
| `app/domain/ports.py` | 1-4 | Modificado | Interfaces relacionadas con solve | Mantener separación de capas | Adaptadores compatibles |
| `app/domain/qsts_profiles.py` | 2 | Creado | Perfiles temporales | Soportar perfiles QSTS | Perfiles deterministas |
| `app/main.py` | 3-6 | Modificado | Routers, frontend y assets | Publicar API e interfaz | Aplicación local |
| `app/orchestration/simulation_service.py` | 3-5 | Modificado | Lifecycle, broadcast, estado y métricas | Orquestar REST/WS/QSTS | Sesiones aisladas |
| `app/platform/metrics.py` | 5 | Creado | Registry acotado y percentiles | Medición interna | Métricas en memoria |
| `app/static/app/templates/index.html` | 6 | Creado/modificado | UI Snapshot/QSTS/resultados/métricas | Integración frontend | Consola funcional |
| `app/static/app/static/js/app.js` | 6, 6.1 | Creado/modificado | REST, WS, normalización y tablas | Ejecutar y visualizar flujos | UI conectada |
| `app/static/app/static/css/app.css` | 6 | Creado/modificado | Controles y tarjetas de métricas | Mantener diseño existente | UI legible |
| `app/static/app/static/css/sessions.css` | 6 | Creado | Estilos de sesiones | Lista y unión | Navegación de sesiones |
| `app/static/OLD/` | Pre-Fase 1 | Restaurado | Assets legacy preservados | Compatibilidad histórica | Sin impacto backend |
| `scripts/bootstrap_ieee_models.py` | 7 | Modificado | Copia IEEE8500 y master headless | Reutilizar bootstrap existente | Instalación reproducible |
| `scripts/ieee8500_smoke.py` | 7 | Creado | Smoke directo engine | Validar carga/Snapshot | Evidencia IEEE8500 |
| `scripts/ieee8500_api_smoke.py` | 7 | Creado | Smoke REST Snapshot/QSTS | Validar integración API | Evidencia REST |
| `scripts/qsts_smoke.py` | 1-2 | Creado | Smoke engine QSTS | Validar motor | Regresión local |
| `scripts/qsts_api_smoke.py` | 3 | Creado | Smoke REST | Validar API | Regresión REST |
| `scripts/qsts_ws_smoke.py` | 4 | Creado | Smoke WebSocket | Validar progreso y resultados | Regresión WS |
| `scripts/performance_campaign.py` | 5, 7 | Creado/modificado | Campañas y max frame WS 16 MiB | Medir local/cloud y IEEE8500 | Evidencias de rendimiento |
| `load/locustfile.py` | 5 | Creado | Usuarios Snapshot/QSTS | Carga local controlada | Pruebas Locust |
| `requirements-dev.txt` | 5 | Creado | Dependencia Locust | Separar carga del runtime | Entorno de desarrollo |
| `tests/test_qsts_engine.py` | 1 | Creado | Pruebas de engine QSTS | Regresión del motor | Cobertura QSTS |
| `tests/test_ws_basic.py` | 4 | Modificado | Tests de progreso, observers y aislamiento | Regresión WebSocket | Cobertura WS |
| `README.md` | 5-6 | Modificado | Comandos métricas/performance | Operación reproducible | Documentación de uso |
| `data/networks/ieee8500/` | 7 | Creado por bootstrap | Modelo original y `Master_cloud.dss` | Ejecutar IEEE8500 local | Nuevo feeder |

## 11. Pruebas ejecutadas

| Prueba | Modelo | Configuración | Resultado | Métrica principal |
|---|---|---|---|---|
| Snapshot directo | IEEE13 | Snapshot | Convergente | 41 voltajes |
| Snapshot directo | IEEE34 | Snapshot | Convergente | 95 voltajes |
| Snapshot directo | IEEE123 | Snapshot | Convergente | 278 voltajes |
| QSTS engine | IEEE123 | 24 h / 5 min / synthetic_daily | 288/288 | LoadMult 0.46–1.0 |
| QSTS values | IEEE123 | 15 min / 5 min / `[0.8,1.0,1.2]` | 3/3 | Valores preservados |
| REST smoke | IEEE123 | Snapshot, QSTS y values | OK | `/results` completo |
| WS smoke | IEEE123 | QSTS 3 pasos | OK | `qsts_progress` 1,2,3 |
| Dos observers | IEEE123 | Misma sesión | OK | Ambos reciben 3 steps |
| Aislamiento | IEEE123 | Sesiones A/B | OK | Sin eventos cruzados |
| Health durante solve | IEEE123 | QSTS activo | OK | Event loop disponible |
| Performance Snapshot | IEEE123 | 30 iteraciones | 0 errores | p50 45.413 ms |
| Performance QSTS | IEEE123 | 30 × 288 steps | 0 errores | p50 363.058 ms |
| Locust | Local | 5 usuarios / mixto | 0 fallos | 29.12 RPS |
| Locust | Local | 10 usuarios / mixto | 0 fallos | 39.34 RPS |
| Snapshot engine | IEEE8500 | `Master_cloud.dss` | Convergente | 4876 buses, 8531 nodos |
| Snapshot REST | IEEE8500 | Snapshot | Convergente | 177.046 ms |
| QSTS corto | IEEE8500 | 15 min / 5 min / values | 3/3 | `[0.8,1.0,1.2]` |
| QSTS 1 hora | IEEE8500 | 1 h / 5 min / synthetic_daily | 12/12 | Vmin 0.962568 |
| Interfaz | IEEE8500 | Selector + Snapshot | OK | Resultado y tablas visibles |
| Performance Snapshot | IEEE8500 | 10 iteraciones | 0 errores | p50 1090.628 ms |

Pytest no se usó como criterio de esta fase debido al error nativo conocido de
`dss_python_backend` en Windows.

## 12. Evidencias

Las evidencias principales están bajo:

```text
docs/evidence/performance/
docs/evidence/qsts/
```

Incluyen configuraciones JSON, resultados CSV, resúmenes estadísticos,
métricas antes/después y archivos CSV de Locust.

IEEE8500:

```text
docs/evidence/performance/20261015T003106Z_local_ieee8500_snapshot/
```

## 13. Limitaciones

- Pytest permanece condicionado por el error nativo
  `Windows fatal exception: code 0xe0465043` asociado a `dss_python_backend`.
- RSS representa el proceso servidor completo, no un contexto OpenDSS
  individual.
- CPU depende del instante de lectura y del intervalo interno de psutil.
- Las sesiones y resultados todavía viven en memoria del proceso.
- La arquitectura sigue siendo monolítica.
- No hay RDS, workers remotos, SQS ni autoscaling.
- No hay seguridad final, autenticación ni TLS propio incorporado.
- Los payloads Snapshot de IEEE8500 son grandes porque incluyen voltajes y
  corrientes; el cliente de campaña requiere un límite WebSocket mayor.
- No se ejecutó QSTS de 24 horas sobre IEEE8500.
- No se ejecutó Locust sobre IEEE8500.

## 14. Estado final local

Antes de cloud quedan funcionando:

- IEEE13;
- IEEE34;
- IEEE123;
- IEEE8500 Snapshot;
- QSTS local validado;
- REST;
- WebSocket;
- frontend;
- `/metrics`;
- performance campaign;
- Locust para campañas locales;
- Docker preparado.

IEEE8500 QSTS está preparado y validado en escalas corta y de una hora, pero
el QSTS de 24 horas queda deliberadamente para la siguiente etapa.

## 15. Siguiente fase: Cloud

El siguiente escalón debe separar responsabilidades de infraestructura:

- API y workers;
- cola de trabajos;
- RDS;
- almacenamiento de estado;
- autoscaling;
- pruebas cloud;
- comparación local/cloud con los mismos scripts y evidencias.

AWS, SQS, RDS, workers y autoscaling no forman parte de esta entrega.
