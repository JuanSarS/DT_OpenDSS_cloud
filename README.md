# OpenDSS Cloud API — Semana 4

Backend mínimo del núcleo SIL del proyecto de Gemelo Digital Híbrido.

## Qué implementa

- `GET /health`
- `POST /simulations`
- un contexto OpenDSS/AltDSS independiente por `session_id`
- `POST /simulations/{id}/solve`
- flujo de potencia `snapshot`
- tensiones nodales y corrientes por elemento en JSON
- tiempo de solución en `elapsed_ms` y logs
- pruebas automatizadas con `pytest`
- prueba de aislamiento usando dos sesiones paralelas con estados distintos
- comparación API vs. ejecución directa de AltDSS sobre IEEE 13

## Arquitectura

```text
app/
├── api/                 # HTTP/FastAPI
├── orchestration/       # ciclo de vida y coordinación de sesiones
├── domain/              # modelos y contratos
├── adapters/
│   └── opendss/         # adaptador concreto del motor SIL
└── platform/            # logging y aspectos transversales
```

La separación sigue la vista de desarrollo: las capas superiores no dependen
de detalles del motor. Más adelante se puede añadir otro adaptador (Typhoon HIL)
sin reescribir los endpoints.

## 1. Requisitos

- Python 3.11, 3.12 o 3.13 de 64 bits recomendado
- Git
- conexión a Internet solamente para instalar paquetes y descargar una vez IEEE 13

No es obligatorio instalar la aplicación de escritorio OpenDSS para esta
implementación. `altdss`/DSS-Extensions instala un motor nativo compatible y
multiplataforma.

## 2. Crear el entorno virtual

### Windows PowerShell

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### Linux/macOS

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

## 3. Descargar el caso IEEE 13

```bash
python scripts/bootstrap_ieee13.py
```

Al finalizar deben existir:

```text
data/networks/ieee13/
├── IEEE13Nodeckt.dss
├── IEEELineCodes.DSS
└── IEEE13Node_BusXY.csv
```

## 4. Ejecutar las pruebas

```bash
pytest -q
```

## 5. Arrancar FastAPI

```bash
uvicorn app.main:app --reload
```

Abrir:

- `http://127.0.0.1:8000/health`
- `http://127.0.0.1:8000/docs`

## 6. Probar el flujo completo

Crear una sesión:

```bash
curl -X POST "http://127.0.0.1:8000/simulations" \
  -H "Content-Type: application/json" \
  -d '{"topology":"ieee13","load_multiplier":1.0}'
```

La respuesta contiene un `session_id`.

Resolver:

```bash
curl -X POST "http://127.0.0.1:8000/simulations/REEMPLAZA_ID/solve"
```

## Cómo corre OpenDSS aquí

OpenDSS no es solamente una ventana de escritorio. El componente importante es
el **motor de cálculo** que interpreta comandos/archivos `.dss`, construye la red
eléctrica en memoria y resuelve el sistema.

En este proyecto:

```text
HTTP
  ↓
FastAPI
  ↓
SimulationService
  ↓
OpenDSSContextEngine
  ↓
altdss.NewContext()
  ↓
Motor DSS C-API
  ↓
IEEE13Nodeckt.dss
  ↓
Solve snapshot
  ↓
V, I, P, Q
  ↓
JSON
```

Cada llamada a `POST /simulations` crea un objeto independiente con
`altdss.NewContext()`. Por eso dos usuarios pueden tener parámetros y estados
distintos sin reutilizar el mismo estado eléctrico.

## Nota de concurrencia

FastAPI es asíncrono, pero la solución eléctrica es trabajo nativo/síncrono.
Por eso el adaptador se ejecuta con `asyncio.to_thread(...)`, fuera del bucle
principal. Además, cada sesión tiene un `asyncio.Lock` para impedir dos
soluciones simultáneas sobre el mismo contexto.

En fases posteriores conviene evolucionar de hilos a workers/procesos
persistentes con política de reciclaje, tal como requiere la validación M1.

## Estructura de respuesta

Ejemplo abreviado:

```json
{
  "session_id": "...",
  "topology": "ieee13",
  "converged": true,
  "elapsed_ms": 42.71,
  "load_multiplier": 1.0,
  "total_power_kw": -3567.0,
  "total_power_kvar": -1736.4,
  "voltages": {
    "650.1": {
      "real": 2401.0,
      "imag": 0.0,
      "magnitude": 2401.0,
      "angle_deg": 0.0
    }
  },
  "currents": {
    "Vsource.source": [
      {
        "real": 0.0,
        "imag": 0.0,
        "magnitude": 0.0,
        "angle_deg": 0.0
      }
    ]
  }
}
```

Los números del ejemplo son ilustrativos. La prueba automatizada compara los
valores devueltos por la API con una ejecución directa del mismo motor.
