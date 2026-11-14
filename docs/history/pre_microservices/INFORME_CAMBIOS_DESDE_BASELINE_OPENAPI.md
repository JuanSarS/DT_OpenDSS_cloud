# Informe de cambios desde el análisis del contrato OpenAPI

**Fecha del informe:** 2026-11-10  
**Punto de comparación:** `bc43cd5` — `docs: capture baseline API and WebSocket contracts`  
**Rama:** `refactor/microservices-r1`

## 1. Alcance y conclusión ejecutiva

El último análisis identificable en el historial es el commit `bc43cd5`, que
capturó los contratos REST y WebSocket en `docs/baseline/`. Desde ese punto se
realizaron dos refactors confirmados y existe además un cambio local pendiente
en `SimulationService`.

El error `OpenAPI changed` no se debe exclusivamente a FastAPI. Se observan
dos causas independientes:

1. El esquema de archivos generado por el entorno actual usa
   `contentMediaType: application/octet-stream`, mientras el baseline usa
   `format: binary`. Esto es una diferencia de generación del esquema entre
   versiones del stack FastAPI/Pydantic/Starlette o de sus dependencias
   asociadas.
2. Varias descripciones y resúmenes con tildes están mal codificados en el
   archivo baseline (`DuraciÃ³n` o caracteres de reemplazo), mientras el
   servidor actual devuelve UTF-8 correcto (`Duración`). Esto es un problema
   de codificación del baseline, no un cambio funcional de la API.

Por tanto, el contrato no coincide por una combinación de representación
OpenAPI y corrupción de texto en el archivo de referencia. Los cambios de
arquitectura registrados después del baseline no agregan ni eliminan rutas
REST según la comparación realizada, pero sí deben validarse nuevamente
porque modifican la implementación interna.

## 2. Cambios realizados desde el último análisis

### 2.1. Contratos compartidos — commit `95a49d8`

Se extrajeron los contratos reutilizables desde `app/domain/` hacia
`packages/contracts/`:

- `packages/contracts/models.py`: modelos de solicitudes, respuestas y
  resultados compartidos.
- `packages/contracts/errors.py`: errores de dominio compartidos.
- `packages/contracts/ports.py`: puertos/interfaces compartidos.
- `app/domain/` conserva adaptadores o reexportaciones necesarias para la
  aplicación actual.
- `Dockerfile` incorpora el paquete `packages/` en la imagen.

El objetivo es permitir que el API, el worker y futuros servicios compartan
los mismos contratos sin duplicar modelos. Este cambio puede influir
indirectamente en OpenAPI si cambian anotaciones o modelos Pydantic, aunque la
comparación actual no detectó rutas nuevas ni eliminadas.

### 2.2. Extracción del núcleo OpenDSS — commit `0815a20`

Se extrajo la lógica reutilizable del motor a `packages/simulation_core/`:

- motor OpenDSS;
- catálogo de modelos;
- catálogo de topologías;
- perfiles QSTS.

También se actualizaron los adaptadores bajo `app/adapters/opendss/` para
reutilizar ese núcleo y se incorporó evidencia QSTS de IEEE123 en
`docs/evidence/qsts/`.

El cambio reduce el acoplamiento del API con la implementación concreta del
motor y prepara la futura separación de servicios. No modifica deliberadamente
la forma de las rutas HTTP, pero sí cambia las dependencias de ejecución de
las sesiones y de las simulaciones QSTS.

### 2.3. Cambio local pendiente — no confirmado

El árbol de trabajo contiene cambios no confirmados en
`app/orchestration/simulation_service.py` y nuevos archivos bajo
`services/api_manager/`.

El cambio sustituye llamadas directas a `asyncio.to_thread` y al motor por
`LocalSimulationExecutor`, con operaciones explícitas para:

- crear el motor;
- resolver Snapshot;
- resolver QSTS;
- cerrar y reciclar contextos;
- obtener identidad, multiplicador de carga y resumen.

Este cambio es interno y no explica por sí mismo la diferencia observada en
`/openapi.json`, porque no cambia las firmas de las rutas FastAPI. Sin embargo,
debe probarse antes de confirmarlo, especialmente el callback QSTS que conecta
el hilo de trabajo con el event loop mediante
`asyncio.run_coroutine_threadsafe(...)`.

## 3. Evidencia del error OpenAPI

La comparación ejecutada contra `http://127.0.0.1:8000/openapi.json` encontró
la primera diferencia en el esquema de `POST /models/upload`.

### Baseline

```json
{
  "type": "string",
  "format": "binary",
  "title": "File"
}
```

### Servidor actual

```json
{
  "type": "string",
  "contentMediaType": "application/octet-stream",
  "title": "File"
}
```

El entorno que respondió la solicitud reportó:

```text
fastapi  0.129.0
pydantic 2.12.5
starlette 0.52.1
```

El archivo `requirements.txt` declara rangos abiertos, por ejemplo
`fastapi>=0.115,<1.0`, y no existe un lockfile que congele la combinación
exacta. Por ello, reinstalar dependencias puede generar un OpenAPI diferente
sin que cambie el código de las rutas.

## 4. Diferencias de codificación detectadas

Además de la diferencia del upload, la comparación estructural encontró
descripciones distintas en:

- `info.description`;
- resumen y descripción de `/metrics`;
- resumen y descripción de las rutas `/simulations`;
- descripciones de `QSTSSolveRequest`;
- descripciones de `SolveRequest`.

El baseline contiene textos como `DuraciÃ³n` y el servidor devuelve
`Duración`. El archivo baseline tiene BOM UTF-8, pero su contenido ya contiene
texto doblemente codificado. Esto indica que el problema se introdujo al
generar o guardar el baseline, no durante la llamada actual a FastAPI.

## 5. Documentación considerada

Los cambios y su impacto se contrastaron con:

- `docs/FASES_1_A_7_DOCUMENTACION_TECNICA.md`: arquitectura, REST, WebSocket,
  QSTS y uso de `asyncio.run_coroutine_threadsafe`.
- `docs/INFORME_SEMANAS_5_6.md`: ciclo de vida de sesiones, aislamiento y
  ejecución fuera del event loop.
- `docs/INFORME_SEMANAS_7_8_LOCAL.md`: catálogo, Docker, modelos
  personalizados, configuración y pruebas locales.
- `docs/CLOUD_READINESS.md`: límites actuales de estado en memoria y
  preparación pendiente para cloud.
- `README.md`: comandos de instalación, pruebas y operación local.

La documentación confirma que la aplicación mantiene el estado de sesiones en
memoria, usa un único proceso/worker y separa progresivamente el núcleo
OpenDSS del API. También confirma que Docker instala desde rangos de
dependencias, por lo que la reproducibilidad del contrato requiere fijar
versiones o regenerar el baseline de manera controlada.

## 6. Recomendaciones

1. Decidir si el contrato esperado es el generado por las versiones actuales.
2. Si se aceptan las versiones actuales, regenerar
   `docs/baseline/contracts/openapi_baseline.json` usando UTF-8 real y volver a
   ejecutar la comparación.
3. Si se necesita estabilidad exacta, fijar FastAPI, Pydantic, Starlette y
   dependencias relacionadas en un lockfile o con versiones exactas.
4. Generar y comparar JSON estructuralmente, evitando conversiones por
   `Get-Content`/`ConvertTo-Json` que puedan alterar codificación o formato.
5. Ejecutar la suite y los smoke tests después de validar el cambio local de
   `LocalSimulationExecutor`.

No se recomienda modificar manualmente el esquema generado en la aplicación
solo para satisfacer el baseline: eso ocultaría la causa de reproducibilidad
y podría producir un contrato incoherente con el runtime.
