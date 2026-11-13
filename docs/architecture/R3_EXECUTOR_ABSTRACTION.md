# R3 - Simulation Executor Abstraction

## Objetivo

Desacoplar SimulationService del runtime concreto OpenDSS.

## Antes

SimulationService
→ LocalSimulationExecutor methods
→ OpenDSSContextEngine

SimulationService todavía participaba en el ciclo de vida del engine.

## Después

SimulationService
→ SimulationExecutor
→ SimulationJob
→ SimulationResult

LocalSimulationExecutor
→ OpenDSSContextEngine

## Responsabilidades

### SimulationService

- sesiones lógicas
- estado de API
- REST
- WebSocket
- resultados
- broadcasting
- métricas de API

### SimulationExecutor

Contrato abstracto:

- prepare_session
- submit
- status
- cancel
- session_info
- close_session

### LocalSimulationExecutor

- posee OpenDSSContextEngine
- crea contextos
- ejecuta Snapshot
- ejecuta QSTS
- realiza bridge thread/event loop
- mantiene estado de jobs
- realiza recycle
- cierra runtimes

## Contratos usados

- SimulationJob
- SimulationProgress
- SimulationResult
- JobStatus

## QSTS

Todos los steps de un QSTS permanecen dentro del mismo
runtime/contexto.

## Cancelación

La cancelación local es cooperativa.

QSTS puede detectar la cancelación entre steps.

Un Snapshot nativo ya iniciado puede terminar internamente
antes de observar la cancelación.

La cancelación fuerte de procesos/workers se implementará
posteriormente cuando exista un worker independiente.

## Backend

EXECUTION_BACKEND=local

La factory permite incorporar posteriormente otro executor
sin modificar SimulationService.

## Estado al terminar R3

La API continúa funcionando en un único proceso.

Todavía no existe comunicación de red entre API y worker.

La separación física corresponde a R4.
----- 
SimulationService
    ↓
SimulationExecutor Protocol
    ↓
LocalSimulationExecutor
    ↓
OpenDSSContextEngine
----
SimulationService:
- sesiones lógicas
- WebSocket
- resultados
- métricas API
- estado visible

LocalSimulationExecutor:
- OpenDSSContextEngine
- threads
- QSTS
- progreso
- recycle
- status
- cancel
- runtime sessions
----- 

