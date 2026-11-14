# Implementation status

## Implementado

- Flujo custom frontend: upload API, selección de master, lectura/edición,
  validación backend y topology `custom:<model_id>:<master>`.
- JWT REST, roles, ownership de sesiones y autenticación WebSocket.
- Token independiente API → worker.
- Secretos locales Argon2 y Docker secrets.
- Eventos de seguridad en memoria y logs JSON.
- Endpoints administrativos de eventos y resumen.
- Rate limit HTTP y admisión concurrente básica.
- Imágenes Docker separadas: API sin AltDSS y worker con AltDSS.

## Evidencia

- `18 passed` en seguridad y contratos.
- `docker compose config --quiet` correcto.
- Build de `api-manager` y `simulation-worker` correcto tras limpiar la caché.
- API image: `altdss` ausente.
- Worker image: `altdss` importable.

## Pendiente

- Smoke de integración custom contra worker real.
- Tests HTTP multiusuario y WSS con Compose.
- HTTPS CA trust script y documentación operativa final.
- Retry/recreación completa de jobs R8.
- Laboratorio de seguridad y pruebas de carga R7 completas.

AWS, Terraform, Kubernetes, Redis y persistencia distribuida quedan fuera de
esta implementación local.
