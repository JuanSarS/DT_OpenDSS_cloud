# OpenDSS Cloud - Semanas 7 y 8 local

Gemelo digital híbrido con FastAPI, AltDSS/OpenDSS y WebSockets. Esta entrega
prepara ejecución local, Docker y LAN; **no provisiona AWS**.

## Python local

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python scripts/bootstrap_ieee_models.py
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

La aplicación sirve `/`, `/docs`, `/health` y `/models`. Las sesiones y sus
contextos AltDSS viven en memoria; no ejecutar múltiples workers/replicas.

## Pruebas

```powershell
python -m pytest --collect-only -q
python -m pytest -v
python -m pytest tests/test_ws_basic.py -v
```

## Docker

```powershell
docker build -t opendss-cloud:local .
docker run --rm -p 8000:8000 opendss-cloud:local
docker compose up --build
```

El contenedor escucha en `0.0.0.0:8000`, usa usuario no-root y persiste
`data/runtime/custom_models` en un volumen. Verifica:
`curl http://127.0.0.1:8000/health`, `/docs`, `/` y `/models`.

## Smoke HTTP/WebSocket

Con el servidor local o Docker ya iniciado:

```powershell
python scripts/smoke_test.py
# Servidor remoto:
$env:BASE_URL="http://IP_DEL_HOST:8000"; $env:WS_BASE_URL="ws://IP_DEL_HOST:8000"
python scripts/smoke_test.py
```

## Modelos

`GET /models` obtiene dinámicamente IEEE13, IEEE34 e IEEE123. El selector de
la UI usa esa respuesta, no un catálogo JavaScript hardcodeado. Para cargar un
modelo: elige un `.dss` autosuficiente o `.zip` con su estructura relativa y
archivos auxiliares. La API devuelve `model_id` y la lista de masters:

```powershell
curl -F "file=@mi-red.zip" http://127.0.0.1:8000/models/upload
curl -X POST "http://127.0.0.1:8000/models/custom/MODEL_ID/validate?master=master.dss"
```

Los archivos `.dss` se pueden consultar/guardar con
`GET/PUT /models/custom/{model_id}/files/{ruta}` y luego revalidar. Un modelo
personalizado válido se crea como `topology=custom:MODEL_ID:ruta/master.dss`.
Se rechazan rutas absolutas, `..`, ZIP Slip, extensiones no permitidas y
límites configurables.

## Crear/unirse y LAN

La UI permite crear una simulación o validar un `session_id` mediante
`GET /simulations/{id}` antes de conectar al WebSocket. Unirse no crea un
contexto ni ejecuta solve. Dos pestañas que usan el mismo ID observan la misma
sesión y broadcast. La URL WebSocket se construye con `window.location`
(`ws`/`wss`), por lo que funciona detrás de Docker, LAN y un futuro proxy AWS.

En Windows obtén la IP con `ipconfig` y abre `http://IP_DEL_HOST:8000/` desde
otro equipo. Puede ser necesario permitir el puerto en Firewall de Windows;
este proyecto no modifica el firewall.

## Configuración

Copia `.env.example` a `.env` y ajusta host, puerto, límites de sesiones/carga,
`ALLOW_CUSTOM_MODELS`, workspace y timeout. No se versionan secretos ni `.env`.

## Limitaciones y siguiente paso

Actualmente no hay JWT, TLS propio, autoscaling, persistencia distribuida ni
estado WebSocket externo. Los modelos personalizados son locales/volumen.
Registry cloud, URL pública, latencia e aislamiento de AWS quedan
**PENDIENTE DE DESPLIEGUE AWS**. Véanse
[`docs/CLOUD_READINESS.md`](docs/CLOUD_READINESS.md) y
[`docs/INFORME_SEMANAS_7_8_LOCAL.md`](docs/INFORME_SEMANAS_7_8_LOCAL.md).
