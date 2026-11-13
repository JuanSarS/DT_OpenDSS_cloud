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