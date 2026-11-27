# Estado de DT_OpenDSS_cloud

## 2026-11-25 · QSTS interactivo y operación colaborativa

Implementado en la rama local `codex/fix-collaboration-custom-models` sobre `7448c6e6d3f520a8d22bd3ede6f47589963fa4b6`. La fase de colaboración y modelos fue aceptada antes de esta implementación. La guía vigente de API, arranque y navegador está en `INTERACTIVE_QSTS.md`.

### Cambios de esta fase

| Archivo | Cambio |
|---|---|
| `packages/contracts/interactive.py`, `execution.py`, `errors.py` y `models.py` | Contratos de ejecución interactiva, pasos, interruptores, red, eventos y roles. Puerto de ejecución y errores de contexto. |
| `packages/simulation_core/engine.py` | Inicialización y avance compartidos con batch, lectura de ramas e interruptores, operación nativa y medidas de pérdidas. |
| `services/simulation_worker/executor.py` y `main.py` | Contexto y contador por ejecución, serialización con trabajos y cierre, comando interno tipado y autenticado. |
| `services/api_manager/execution/remote_executor.py` y `worker_pool.py` | RPC al worker fijado a la sesión. El flujo interactivo informa la pérdida de contexto sin reintentar la operación en otro worker. |
| `services/api_manager/orchestration/interactive_service.py` y `simulation_service.py` | Temporizador monotónico, admisión conjunta con Snapshot y batch, control de versiones e idempotencia, resultados, historial, membresía y WebSocket. |
| `services/api_manager/api/routes/interactive.py`, `simulations.py` y `services/api_manager/main.py` | REST/OpenAPI, validación de roles, conexión al router y limpieza al apagar el API Manager. |
| `services/frontend/templates/index.html`, `static/js/app.js`, `static/js/interactive.js` y `static/css/app.css` | Selector de modalidad, controles, permisos, gráficos y diagrama de ramas, historial y resincronización. |
| `tests/test_interactive_qsts.py` y `tests/security/test_ownership.py` | Equivalencia con batch, cambio eléctrico, ejecución automática, permisos, carrera de comandos, aislamiento y pérdida de contexto. |
| `docs/codex/INTERACTIVE_QSTS.md` y `STATUS.md` | Guía de operación y registro de esta fase. |

### Verificación

- **82 pruebas** superadas con `python -B -m pytest tests -q -p no:cacheprovider -p no:faulthandler --basetemp $labQstsDirectory --tb=line`, con un directorio temporal nuevo bajo `data/runtime`. Se compararon tres pasos interactivos con batch en IEEE13, IEEE34, IEEE123 e IEEE8500. Las pruebas REST y WebSocket se ejecutaron con el motor local y con el pool sobre el contrato HTTP del worker.
- En IEEE13, el sondeo nativo registró aproximadamente −3567,02 kW con `Line.671692` cerrada, −2514,58 kW después de abrirla y −3567,02 kW tras volver a cerrarla. Son valores de potencia de la fuente con la convención de signo de OpenDSS.
- Smoke en Edge con tres perfiles, cuentas sintéticas y procesos API Manager y worker separados en loopback. Verificó invitación por rol, controles del operador, vista de solo lectura, estado y diagrama del interruptor, historial y finalización automática tras desconectar las tres páginas. Usó HTTP/WS local.
- `node --check` pasó para ambos scripts frontend, `git diff --check` pasó y se verificaron 17 rutas públicas y una interna en OpenAPI. La configuración de Compose pasó `docker compose --env-file NUL -f infra/local/compose.yaml config --quiet --no-env-resolution`. Compose emitió un aviso sobre la configuración de usuario de Docker.

### Alcance verificado

- La ejecución activa permanece en un solo contexto. El reinicio explícito comienza desde cero. La pérdida del contexto en una sesión activa se verificó con ambos ejecutores. Quedan pendientes Caddy y AWS como destinos de ejecución.
- El diagrama usa las ramas de líneas y transformadores. Se controlan líneas habilitadas marcadas como interruptor o asociadas a un `SwtControl` habilitado. Los controles nativos de OpenDSS pueden cambiar su estado en un paso posterior y la interfaz refleja ese estado efectivo.
- El estado y la planificación siguen en memoria. No hubo cambios en las evidencias D1, D2 y D3. El versionamiento de modelos y la ampliación de compatibilidad DSS quedan para otra iteración.

## 2026-11-25 · Corrección local de colaboración y modelos

Rama local `codex/fix-collaboration-custom-models` sobre `7448c6e6d3f520a8d22bd3ede6f47589963fa4b6`. Cambios locales pendientes de revisión en 14 archivos versionados y cinco archivos nuevos, incluido este estado. Se conservaron las eliminaciones previas de los tres documentos raíz y el contexto de `AGENTS.md` y `docs/codex/`. Las evidencias originales D1, D2 y D3 siguen en su estado inicial.

### Colaboración

- La pantalla muestra **Invitaciones recibidas** con el propietario y el botón **Abrir simulación**. El propietario o administrador ve **Invitación enviada** junto al destinatario en **Espectadores autorizados**. Las invitaciones directas conceden acceso de lectura desde el envío. Las solicitudes aprobadas aparecen entre las simulaciones accesibles.
- El listado se actualiza con **Actualizar simulaciones e invitaciones** y al volver a la pestaña. Quien recibe un 403 al intentar entrar por ID puede solicitar acceso en la misma interfaz. El panel de permisos permite aprobar, rechazar y quitar acceso. Un fallo del panel conserva activa la entrada a la sesión.
- `GET /simulations` agrega `invited` para la cuenta autenticada. `GET /simulations/{id}/viewers?invited_only=true` devuelve las invitaciones activas al propietario o administrador con el formato existente `list[str]`. Para usuarios sin acceso, el listado de una sesión personalizada conserva su posibilidad de solicitar acceso y omite el identificador del modelo y la ruta del master.
- El servicio identifica cada suscripción WebSocket por usuario y cierra con 1008 las conexiones del espectador revocado. El frontend limpia los resultados y actualiza el listado. El visor conserva acceso de lectura mientras siga autorizado.
- Archivos principales `services/frontend/static/js/app.js`, `services/frontend/templates/index.html`, `services/frontend/static/css/sessions.css`, `services/api_manager/api/routes/simulations.py`, `services/api_manager/orchestration/simulation_service.py` y `packages/contracts/models.py`.

### Modelos personalizados

- `GET /models/custom` lista modelos persistidos para administradores. Se registra la cuenta que carga el modelo. Los modelos heredados sin esa información quedan disponibles al administrador. La metadata devuelve el identificador y las rutas relativas de masters. Se retiró el campo `workspace` de carga y detalle porque contenía una ruta interna y no tenía consumidores en el repositorio.
- Se conservan las mayúsculas y las rutas relativas del ZIP. Se sugiere un único `Master.dss` o `Main.dss`, o el único DSS del modelo. Las selecciones ambiguas requieren elegir. Se restaura el modelo y el master al recargar la misma pestaña mientras estén disponibles para la cuenta autenticada. Una edición se prueba con el worker sobre una copia temporal. Solo se publica si se prepara y cierra el contexto de validación. Para editar una dependencia por API, `PUT /models/custom/{id}/files/{path}` admite `master` en el cuerpo para validar desde el punto de entrada.
- La creación de simulaciones personalizadas exige administrador y respeta `ALLOW_CUSTOM_MODELS`. Un administrador puede compartir resultados de esas sesiones con espectadores. El API y el worker validan el workspace. Se limitan archivos y bytes descomprimidos y se rechazan enlaces y colisiones de rutas.
- La carga personalizada admite un subconjunto eléctrico de DSS. Se expanden `Redirect` y `Compile` dentro del workspace. Las referencias relativas se resuelven desde el archivo que las declara y se comprueban antes de entregar comandos al motor. Las operaciones de exportación, ejecución externa y otras opciones fuera de ese subconjunto se rechazan con un diagnóstico. Por ejemplo, al tratar el archivo integrado de IEEE8500 como una carga personalizada, el analizador rechaza una expresión posicional en `Triplex_Linecodes.dss`. IEEE8500 integrado sigue cubierto por las pruebas de regresión.
- Cada sesión conserva su contexto AltDSS y su afinidad con el worker. El reciclado local reutiliza los comandos comprobados que cargó la sesión. Ante pérdida del worker, la recuperación existente vuelve a leer el modelo publicado. Si se editó después de crear la sesión, esa recuperación puede cargar la versión posterior.
- Archivos principales `services/api_manager/api/routes/models.py`, `services/api_manager/orchestration/custom_models.py`, `packages/common/custom_model_paths.py`, `packages/simulation_core/custom_dss.py`, `packages/simulation_core/engine.py`, `services/simulation_worker/topology_resolver.py`, `services/simulation_worker/executor.py`, `services/api_manager/execution/remote_executor.py`, `services/api_manager/execution/worker_pool.py` y `packages/contracts/errors.py`.

### Verificación local

- Antes de la corrección se reprodujeron tres fallos de colaboración y seis de modelos con las pruebas nuevas. Los casos cubrieron la marca de invitación ausente, respuestas incorrectas de solicitudes, el WebSocket que seguía abierto, selección de master, edición inválida y colisiones de archivo.
- Suite completa de Windows con `python -B -m pytest tests -q -p no:cacheprovider -p no:faulthandler --basetemp $labTestDirectory --tb=line`, con `$labTestDirectory` en un directorio nuevo debajo de `data/runtime`. **69 pruebas pasaron**. Los casos nuevos están en `tests/test_collaboration_access.py` y `tests/test_custom_models.py`.
- `node --check services/frontend/static/js/app.js`, `git diff --check` y `docker compose --env-file NUL -f infra/local/compose.yaml config --quiet --no-env-resolution` terminaron con código 0. Compose emitió un aviso de acceso a su configuración de usuario.
- Una comprobación con `node:vm` confirmó que, con un master ambiguo, se exige elegir y se restaura posteriormente el modelo y el master seleccionado al inicializar de nuevo la interfaz con el mismo almacenamiento de pestaña.
- Smoke en Microsoft Edge con dos contextos de navegador, cuentas sintéticas, API Manager y worker en procesos Uvicorn separados sobre loopback. Verificó la etiqueta **Invitación enviada** y la apertura desde **Invitaciones recibidas**, además de entrada con fallo del panel de permisos, solicitudes, aprobación y rechazo, resultados Snapshot y revocación del WebSocket. También verificó carga y reselección de un ZIP con master anidado en mayúsculas, persistencia del catálogo tras recargar y QSTS batch de 3/3 pasos con perfil CSV. El tráfico navegador–API usó HTTP y WS local. Quedan pendientes una ejecución con Caddy y validación en AWS.

### Revisión del usuario

1. Como propietario o administrador, crea una simulación y pulsa **Invitar**. Comprueba la etiqueta **Invitación enviada** en el panel.
2. En otro perfil de navegador, inicia sesión como destinatario y pulsa **Actualizar simulaciones e invitaciones**. Abre la simulación desde **Invitaciones recibidas**.
3. Ejecuta la simulación desde la cuenta propietaria y comprueba que la cuenta espectadora recibe el resultado. Al pulsar **Quitar acceso**, verifica que se cierra la sesión en el navegador del espectador.

El usuario aceptó la corrección antes de iniciar la implementación interactiva.
