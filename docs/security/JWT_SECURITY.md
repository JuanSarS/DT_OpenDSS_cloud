# JWT security

El API emite tokens Bearer mediante `POST /auth/token` y valida firma,
expiración, issuer, audience, usuario y rol en cada dependencia.

Con `AUTH_ENABLED=true` una petición sin token o con token inválido devuelve
`401`. Un usuario autenticado sin permisos de administrador recibe `403` en
endpoints administrativos.

`AUTH_ENABLED=false` existe únicamente para desarrollo y tests legacy; usa un
principal interno `dev-admin` y no debe usarse en producción.

El JWT del usuario nunca se envía al simulation-worker. El API usa
`WORKER_SHARED_TOKEN` para autenticar la comunicación interna.
