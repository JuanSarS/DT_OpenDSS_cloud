Primero:
.\scripts\deploy_local.ps1

Luego, PowerShell Administrador:
.\scripts\trust_local_ca.ps1

Después:
.\scripts\run_all_smokes.ps1

Te pedirá una sola vez:
Password de admin:

y ejecutará:
compileall
docker compose config
contracts smoke
Snapshot REST + WSS
QSTS REST
QSTS WSS
IEEE8500 API
security tests
unit tests

Al final:
=====================================
 ALL SMOKES OK
=====================================