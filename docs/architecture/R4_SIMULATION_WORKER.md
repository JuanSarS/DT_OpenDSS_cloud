Antes R4

API Manager
└── LocalSimulationExecutor
    └── OpenDSS


Después R4

API Manager :8000
└── RemoteSimulationExecutor
    │
    │ HTTP + NDJSON
    ▼
Simulation Worker :8100
└── LocalSimulationExecutor
    └── OpenDSS


----- 

Y deja explícito:
EXECUTION_BACKEND=local

sigue soportado.
EXECUTION_BACKEND=worker_http

activa separación física.

También:
El puerto interno 8100 no está diseñado para exposición pública.