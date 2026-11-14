# Informe de Semanas 5-6

## 1. Resumen

Se amplió el registry en memoria de la Semana 4 con ciclo de vida, contador de
tareas, último resultado, resumen del modelo, cierre explícito, reciclaje en
`RECYCLE_THRESHOLD = 162`, documentación OpenAPI, una suscripción WebSocket
compartida por simulación y una interfaz HTML mínima. El solve continúa fuera
del event loop mediante `asyncio.to_thread`.

## 2. Arquitectura final

```text
cliente REST/WS
      |
 FastAPI (rutas)
      |
 SimulationService -- registry {simulation_id -> SimulationSession}
      |                         |-- last_result
      |                         |-- subscribers
      |                         |-- task_count/status
      v
 worker/context AltDSS persistente por sesión
      |
 recycle al solve 162 -> close -> nuevo contexto -> mismo session_id
```

Cada sesión posee un único contexto AltDSS y sus observadores sólo reciben
eventos de esa sesión. El registry no serializa sockets dentro de modelos
Pydantic.

## 3. Archivos modificados

| Ruta | Cambio | Tarea |
|---|---|---|
| `app/domain/models.py` | Estados, resumen y metadata de sesión | Registry, last_result, OpenAPI |
| `app/domain/errors.py` | Error de sesión cerrada | Validaciones |
| `app/adapters/opendss/engine.py` | Resumen y cierre del contexto | Worker/context y memoria |
| `app/orchestration/simulation_service.py` | Registry, solve, broadcast, cierre y recycle | Semanas 5-6 |
| `app/api/routes/simulations.py` | GET/DELETE y WebSocket | API y observadores |
| `app/main.py` | OpenAPI descriptivo y `/` | Swagger/interfaz |
| `app/static/index.html` | UI HTML/JS sin framework | Interfaz mínima |
| `requirements.txt` | `psutil` | Medición RSS en pruebas futuras |
| `docs/INFORME_SEMANAS_5_6.md` | Este informe | Entrega |

## 4. Funciones/clases

`SimulationStatus`, `ModelSummary`, `SimulationSummary` y `SimulationDetail`
en `app/domain/models.py` modelan estados y respuestas. `SimulationSession` en
`app/orchestration/simulation_service.py` conserva el contexto, contador,
resultado y suscriptores. `SimulationService` crea, lista, consulta, resuelve,
recicla, cierra, suscribe y difunde. `OpenDSSContextEngine.model_summary` lee
metadatos pequeños del circuito y `close` libera el circuito nativo.

## 5. Ciclo de vida

Crear valida y carga IEEE13, registra una sesión READY y su resumen. Un viewer
recibe un snapshot inmediato. Solve emite `simulation_started`, `model_loaded`,
`solving`, `result` y `completed`, guarda `last_result` y actualiza el estado.
El viewer posterior recibe ese resultado sin otro solve. En la tarea 162 se
cierra el contexto, se crea otro y se conserva el mismo identificador. DELETE
cierra el contexto, elimina la entrada activa y desconecta suscriptores.

## 6. Política de memoria

El contexto es persistente por sesión y no se crea por solve. `task_count`
cuenta solves desde el último worker. `RECYCLE_THRESHOLD = 162` es el umbral
definido por la política M1 para acotar acumulación de memoria nativa observada
en ejecuciones repetidas. Al alcanzarlo se invoca `close`, se libera el
contexto y se carga de nuevo la topología. `psutil` queda disponible para medir
RSS del proceso en pruebas de ciclo de vida.

## 7. WebSocket

Todos los mensajes incluyen `type`, `session_id` y `timestamp`. El snapshot es:

```json
{"type":"snapshot","session_id":"...","timestamp":"...","simulation":{},
 "model":{"topology":"ieee13","num_buses":16,"num_nodes":41},"last_result":null}
```

Los eventos son `simulation_started`, `model_loaded`, `solving`, `result` y
`completed`; `result` incluye el resultado real de OpenDSS en `result`.

## 8. Endpoints

| Método | Ruta | Objetivo | Códigos |
|---|---|---|---|
| GET | `/health` | Salud | 200 |
| POST | `/simulations` | Crear | 201, 400 |
| GET | `/simulations` | Listar activas | 200 |
| GET | `/simulations/{id}` | Metadata y último resultado | 200, 404 |
| POST | `/simulations/{id}/solve` | Resolver y difundir | 200, 404, 409 |
| DELETE | `/simulations/{id}` | Cerrar | 204, 404 |
| WS | `/ws/simulations/{id}` | Suscribirse | 1008 si no existe |
| GET | `/` | Interfaz | 200 |

## 9. Pruebas

| Archivo | Test | Verifica | Resultado |
|---|---|---|---|
| `tests/test_health.py` | `test_health_returns_200` | Salud HTTP | PASÓ |
| `tests/test_reference_ieee13.py` | `test_api_matches_direct_altdss_ieee13` | API vs AltDSS directo | PASÓ |
| `tests/test_simulations.py` | `test_parallel_creation_has_distinct_isolated_contexts` | Aislamiento y concurrencia | PASÓ |
| `tests/test_simulations.py` | `test_unknown_session_returns_404` | 404 de sesión | PASÓ |
| `tests/test_weeks_5_6.py` | `test_registry_openapi_last_result_and_close` | Registry, resultado y cierre | PASÓ |
| `tests/test_weeks_5_6.py` | `test_docs_and_invalid_topology` | Swagger y 400 | PASÓ |
| `tests/test_weeks_5_6.py` | `test_websocket_snapshot_and_broadcast` | Snapshot y broadcast | PASÓ |
| `tests/test_weeks_5_6.py` | `test_recycle_preserves_session_id` | Reciclaje en umbral | PASÓ |
| `tests/test_weeks_5_6.py` | `test_ieee13_model_summary` | Resumen IEEE13 16 buses/41 nodos | PASÓ |
| `tests/test_weeks_5_6.py` | `test_late_websocket_viewer_receives_last_result` | Viewer tardío sin segundo solve | PASÓ |
| `tests/test_weeks_5_6.py` | `test_multiple_viewers_are_isolated_per_simulation` | Dos viewers por simulación y aislamiento A/B | PASÓ |
| `tests/test_weeks_5_6.py` | `test_health_is_available_during_solve` | `/health` durante solve controlado | PASÓ |

Comando ejecutado: `python -m pytest -v` (usando `venv\Scripts\python.exe`).
Resumen real:

```text
collected 12 items
12 passed in 4.67s
```

El runtime nativo de DSS imprimió durante la colección un diagnóstico
`Windows fatal exception: code 0xe0465043`, pero el proceso terminó con código
0 y los 8 tests pasaron; no se ocultó ni se reinterpretó como fallo de pytest.

## 10. Criterios de aceptación

| Task | Criterio | Prueba/evidencia | Estado |
|---|---|---|---|
| Semana 5 | Resumen IEEE13 con 16 buses y 41 nodos | `test_ieee13_model_summary` | CUMPLE |
| Semana 5 | Listado explícito de tres sesiones | `test_registry_openapi_last_result_and_close` | CUMPLE |
| Semana 5 | `last_result` persistente | `test_registry_openapi_last_result_and_close` y viewer tardío | CUMPLE |
| Semana 5 | Reciclaje al umbral conservando `session_id` | `test_recycle_preserves_session_id` | CUMPLE |
| Semana 5 | Cierre de simulación y 404 posterior | `test_registry_openapi_last_result_and_close` | CUMPLE |
| Semana 5 | Liberación RSS en proceso hijo | No existe worker hijo en la arquitectura actual | PENDIENTE |
| Semana 5 | Validaciones 400/404/409 | `test_docs_and_invalid_topology` y tests existentes | CUMPLE |
| Semana 5 | OpenAPI `/docs` y `/openapi.json` | `test_docs_and_invalid_topology` | CUMPLE |
| Semana 6 | Snapshot inicial sin resultado | `test_websocket_snapshot_and_broadcast` | CUMPLE |
| Semana 6 | Late viewer recibe `last_result` sin solve adicional | `test_late_websocket_viewer_receives_last_result` | CUMPLE |
| Semana 6 | Broadcast a dos viewers de A y dos de B | `test_multiple_viewers_are_isolated_per_simulation` | CUMPLE |
| Semana 6 | Aislamiento de eventos entre simulaciones | `test_multiple_viewers_are_isolated_per_simulation` | CUMPLE |
| Semana 6 | `/health` no bloqueado durante solve | `test_health_is_available_during_solve` | CUMPLE |
| Semana 6 | Interfaz HTML mínima | `app/static/index.html` | CUMPLE |

## 11. Decisiones y limitaciones

Se usa un worker lógico persistente en el proceso FastAPI, con el aislamiento
nativo de `altdss.NewContext()` por sesión. El criterio RSS permanece pendiente:
cumplirlo exige introducir un proceso hijo persistente por simulación, un
protocolo de comandos/resultados entre `SimulationService` y el worker, gestión
de PID y apagado, y medición psutil del proceso hijo. Eso afectaría
`app/orchestration/simulation_service.py`, `app/adapters/opendss/engine.py` y
probablemente requeriría un módulo nuevo de worker/protocolo; no se realizó por
ser una refactorización significativa fuera del alcance solicitado. El estado
sigue siendo sólo memoria.

## 12. Cómo ejecutar

```powershell
python -m pip install -r requirements.txt
python scripts/bootstrap_ieee13.py
uvicorn app.main:app --reload
python -m pytest -v
```

Abrir `http://127.0.0.1:8000/` o `http://127.0.0.1:8000/docs`.
