- 1. Congelar lo actual. Hacemos commit/tag de la versión monolítica que ya sabemos que funciona, incluyendo IEEE8500, QSTS, frontend, métricas y pruebas. No empezamos moviendo archivos a ciegas.

- 2. Reorganizar el repositorio sin cambiar comportamiento. Separaremos services, packages, infra, tests y docs, pero inicialmente todo deberá seguir funcionando exactamente igual.

- 3. Extraer los contratos. SimulationJob, SimulationProgress, SimulationResult y SimulationError. Esta será la frontera entre API y simulador.

- 4. Crear el executor. Primero un LocalExecutor que reproduzca exactamente el actual asyncio.to_thread(). Aquí no debe cambiar ninguna funcionalidad.

- 5. Separar simulation-worker. OpenDSS sale físicamente del API. Tendremos dos contenedores locales y probaremos Snapshot/QSTS entre ellos.

- 6. Implementar Sprint 5 y 6 sobre esa arquitectura. JWT REST/WS, ownership, máximo dos simulaciones por usuario, 429, logs estructurados, secrets y caída/reintento de worker. Varios objetivos se resolverán casi simultáneamente gracias a la separación.

- 7. Crear infraestructura AWS declarativa. ECR + ECS/Fargate + S3 + CloudWatch + IAM + orquestación mediante Terraform. Las mismas imágenes locales pasan a cloud.

- 8. Ejecutar las pruebas finales y producir Entregables 2 y 3. Performance Campaign, Locust, seguridad, resiliencia, capturas, tablas, checklists, retrospectivas y documentación formal.