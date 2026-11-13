# R2 — Simulation Contracts

## Objetivo

Separar la descripción de una simulación de su mecanismo
de ejecución.

## Contratos

### SimulationJob

Describe qué debe ejecutarse.

No contiene dependencias de FastAPI, WebSocket, AltDSS,
Docker ni AWS.

### SimulationProgress

Describe progreso incremental y compacto.

Puede viajar entre worker y API Manager.

### SimulationResult

Describe el resultado final.

Puede transportar resultados inline o una referencia futura
a almacenamiento externo.

### SimulationError

Describe errores serializables entre servicios.

## Regla QSTS

Un QSTS temporalmente dependiente permanece completo
dentro del mismo job/worker.

## Version

Todos los mensajes utilizan:

contract_version = "1.0"

## Estado de R2

Los contratos existen y están probados, pero todavía no se
utilizan para ejecutar la aplicación.

La ejecución continúa mediante LocalSimulationExecutor.

La integración de estos contratos con el executor corresponde
a R3.