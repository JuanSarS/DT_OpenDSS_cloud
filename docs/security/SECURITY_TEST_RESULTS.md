# Security test results

Última validación local:

```text
18 passed
```

Incluye pruebas unitarias de JWT, roles admin, ownership, WebSocket token
requerido, token del worker y contratos de simulación.

Limitaciones actuales:

- Los tests eléctricos que importan AltDSS pueden abortar en el entorno Windows
  por una excepción nativa de `dss_python_backend`.
- Falta completar el smoke HTTP multiusuario contra Compose.
- Falta completar la recuperación R8 del worker.
