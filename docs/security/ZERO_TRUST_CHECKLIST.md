# Zero Trust checklist

| Control | Estado | Evidencia | Pendiente |
|---|---|---|---|
| JWT obligatorio con `AUTH_ENABLED=true` | PASS | `services/api_manager/auth/dependencies.py`; `tests/security/test_auth.py` | Integración REST completa |
| Tokens expiran y validan issuer/audience | PASS | `services/api_manager/auth/jwt.py` | Test de token expirado |
| Ownership por sesión | PASS | `SimulationService._authorize_session`; `tests/security/test_ownership.py` | Test HTTP multiusuario |
| Rol admin separado | PASS | `require_admin`; `tests/security/test_admin_security.py` | Panel visual admin |
| Worker con token independiente | PASS | `services/simulation_worker/security.py`; `tests/security/test_worker_auth.py` | Smoke Docker autenticado |
| Worker no publicado al host | PASS | `infra/local/compose.yaml` usa `expose` | Verificación de puerto en cada deploy |
| Secretos fuera de la imagen | PASS | Docker secrets y `.dockerignore` | Generar `secrets/local` antes de levantar |
| Logs JSON de seguridad | PASS | `security/events.py`, `logging_config.py` | Persistencia externa |
| Rate limit en memoria | PASS | `security/rate_limit.py`, middleware HTTP | Límite distribuido para cloud |
| HTTPS/WSS exterior | PENDING | Caddyfile local | Instalar/trust de CA y smoke WSS |
| Resultados visibles al propietario | PASS | Ownership aplicado a resultados | Test HTTP multiusuario |
| Resiliencia de worker | PENDING | No implementada todavía | R8 retry/recreate completo |
