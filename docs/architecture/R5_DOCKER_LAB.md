Browser
  ↓
api-manager:8000
  ↓ HTTP/NDJSON
simulation-worker:8100
  ↓
OpenDSS

API image:
- NO AltDSS
- NO dss-python
- NO data/networks

Worker image:
- AltDSS
- dss-python
- simulation_core
- data/networks

custom-models volume is shared
