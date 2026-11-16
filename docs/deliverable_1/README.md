# Entregable 1 — Evidencia multi-contexto

Objetivo: demostrar equivalencia total frente a referencia secuencial para IEEE13, IEEE34, IEEE123 e IEEE8500, usando concurrencia 2, 4, 8 y 16.

Ejecuta:

```powershell
.\scripts\run_deliverable1_evidence.ps1
```

Cada corrida crea:

```text
docs/evidence/deliverable_1/<timestamp>_multicontext/
├── config.json
├── raw_results.csv
├── summary.json
└── REPORT.md
```

`raw_results.csv` conserva hashes de resultados, convergencia, tiempos y máxima diferencia absoluta. El criterio PASS exige que todas las ejecuciones concurrentes coincidan exactamente con la referencia secuencial, excluyendo únicamente `session_id` y campos de tiempo.

El contenedor de evidencia usa el mismo `simulation_core` y redes de la aplicación, pero crea un `OpenDSSContextEngine` aislado por ejecución.
