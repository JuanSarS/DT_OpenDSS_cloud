# Cloud readiness (local, AWS pendiente)

## Listo localmente

- Imagen Docker reproducible con FastAPI, Uvicorn y AltDSS.
- Configuración por entorno, healthcheck y volumen para modelos personalizados.
- Bind `0.0.0.0` y UI same-origin compatible con LAN/proxy.
- REST y WebSocket para múltiples observadores de una misma sesión.
- Catálogo IEEE13/34/123 y carga validada de proyectos DSS.

## PENDIENTE DE DESPLIEGUE AWS

No se han creado credenciales, registry, ECS, App Runner, EC2, ALB,
Terraform ni CloudFormation. También quedan pendientes URL pública, métricas de
latencia cloud, aislamiento cloud, TLS en infraestructura y estrategia de
persistencia distribuida.

## Limitaciones operativas actuales

Una sola instancia y un solo worker: sesiones, subscribers y `last_result`
son memoria del proceso. Los modelos personalizados usan filesystem/volume
local. No hay JWT ni autoscaling. Un reverse proxy o balanceador futuro debe
mantener afinidad/estado WebSocket o mover el estado a servicios externos.
