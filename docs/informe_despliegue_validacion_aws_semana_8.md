# Informe de despliegue y validación Cloud en AWS

## Proyecto: Gemelo Digital Híbrido basado en OpenDSS

**Fecha de validación:** 21 de septiembre de 2026  
**Proveedor cloud:** Amazon Web Services (AWS)  
**Región:** `us-east-2`  
**Repositorio:** `DT_OpenDSS_cloud`  
**Rama desplegada:** `main`

---

## 1. Objetivo

El objetivo de esta fase fue desplegar y validar el backend del gemelo digital en una infraestructura cloud externa, verificando el funcionamiento integral de la API REST, el motor de simulación OpenDSS mediante AltDSS, la comunicación WebSocket, el manejo de múltiples sesiones, el acceso simultáneo desde diferentes dispositivos y el aislamiento entre simulaciones independientes.

La arquitectura seleccionada corresponde a una instancia única de AWS EC2 ejecutando la aplicación mediante Docker Compose. Esta decisión es coherente con la fase experimental actual, en la cual las sesiones de simulación, los suscriptores WebSocket y los últimos resultados permanecen gestionados dentro de una única instancia de aplicación.

---

## 2. Infraestructura AWS utilizada

| Parámetro | Configuración |
|---|---|
| Servicio | AWS EC2 |
| Región | `us-east-2` |
| Nombre de instancia | `OPENDSS_1` |
| Tipo de instancia | `t3.micro` |
| Arquitectura | AMD64 / x86-64 |
| AMI | `ubuntu/images/hvm-ssd-gp3/ubuntu-resolute-26.04-amd64-server-20260604` |
| Sistema operativo | Ubuntu Server 26.04 |
| Volumen EBS | `vol-024e636f8eb1b8ad9` |
| Capacidad | 8 GiB |
| Tipo de almacenamiento | gp3 |
| IP pública durante la prueba | `13.58.233.240` |
| Puerto de aplicación | TCP `8000` |
| Dirección de escucha | `0.0.0.0:8000` |

La dirección IP pública corresponde a la asignada a la instancia durante la sesión de validación. Debido a que no se configuró una dirección IP elástica, esta puede cambiar después de detener y volver a iniciar la instancia.

---

## 3. Contenerización y ejecución

La aplicación se desplegó mediante Docker y Docker Compose directamente dentro de la instancia EC2.

### Versiones verificadas

```text
Docker version 29.1.3, build 29.1.3-0ubuntu4.1
Docker Compose version 2.40.3+ds1-0ubuntu1
```

### Estado del servicio

```text
NAME                               IMAGE                            COMMAND                  SERVICE         CREATED       STATUS                 PORTS
dt_opendss_cloud-opendss-cloud-1   dt_opendss_cloud-opendss-cloud   "uvicorn app.main:ap…"   opendss-cloud   2 hours ago   Up 2 hours (healthy)   0.0.0.0:8000->8000/tcp, [::]:8000->8000/tcp
```

El estado `healthy` confirma que el mecanismo de `healthcheck` definido para el contenedor se encontraba operativo durante las pruebas.

---

## 4. Estrategia de despliegue

La estrategia empleada fue:

```text
Repositorio GitHub
       │
       ▼
AWS EC2
       │
       ▼
git clone / git pull
       │
       ▼
Docker Compose
       │
       ▼
Construcción local de imagen
       │
       ▼
Contenedor FastAPI + AltDSS
       │
       ▼
Puerto 8000
       │
       ▼
Clientes externos
```

El repositorio utilizado fue:

```text
DT_OpenDSS_cloud
Rama: main
```

Durante esta fase no se utilizó Amazon ECR ni otro registro externo de imágenes. La imagen Docker se construyó directamente en la instancia EC2 a partir del repositorio.

Esta decisión se tomó para controlar el consumo de créditos y costos de infraestructura durante la etapa experimental.

**Estado del registro de contenedores:** `PENDIENTE POR DECISIÓN DE COSTO`.

---

## 5. Modelos eléctricos disponibles

Se validaron los siguientes feeders IEEE:

- IEEE13
- IEEE34
- IEEE123

### Ajuste realizado al modelo IEEE34

Durante la validación se detectó que el archivo `Run_IEEE34Mod1.dss` incluía instrucciones interactivas como `Show`, las cuales intentaban abrir un editor desde OpenDSS.

En un entorno Linux headless dentro de Docker esto produjo el error asociado a:

```text
FireOffEditor
Editor could not be started.
```

Para corregir el problema, el modelo operativo se ajustó para utilizar:

```text
ieee34Mod1.dss
```

De esta forma se separó la definición eléctrica del circuito de las operaciones interactivas diseñadas para entornos de escritorio.

Después de esta modificación, IEEE34 fue ejecutado correctamente tanto en Docker como en AWS.

---

## 6. Validación funcional externa

La validación completa se realizó desde un equipo externo a AWS utilizando la dirección pública de la instancia.

El Smoke Test verificó exitosamente:

```text
/health                         OK
/docs                           OK
/models                         OK
Creación de simulación          OK
Consulta de sesión              OK
Conexión WebSocket              OK
Snapshot inicial                OK
Solve OpenDSS                   OK
Convergencia                    OK
Broadcast WebSocket             OK
DELETE sesión                   OK
Validación 404 posterior        OK
```

La secuencia de eventos WebSocket observada fue:

```text
simulation_started
model_loaded
solving
result
completed
```

Resultado final:

```text
SMOKE OK
```

---

## 7. Validación multiusuario

Se realizaron pruebas simultáneas desde:

- un computador;
- un teléfono celular.

Ambos clientes pudieron conectarse a una misma sesión y visualizar de manera simultánea el estado y los resultados de la simulación.

La arquitectura validada fue:

```text
1 sesión de simulación
        │
        ├── Cliente PC
        └── Cliente móvil
```

Esto confirmó que múltiples observadores pueden consumir una misma simulación sin crear un nuevo contexto OpenDSS para cada cliente.

---

## 8. Aislamiento entre simulaciones

También se ejecutaron dos simulaciones independientes de manera simultánea, una desde el computador y otra desde el teléfono celular.

Cada cliente mantuvo su propia sesión y sus propios resultados.

La prueba confirmó:

```text
Simulación A → contexto independiente
Simulación B → contexto independiente

A ≠ B
```

No se observó cruce ni afectación de resultados entre las dos simulaciones.

Esto valida el principio de aislamiento de contexto por sesión.

---

## 9. Línea base de latencia cloud

Se realizaron campañas de **10 iteraciones** para cada feeder desde un cliente externo hacia la instancia AWS.

### 9.1 Resumen comparativo

| Métrica media | IEEE13 | IEEE34 | IEEE123 |
|---|---:|---:|---:|
| `/health` | 132.93 ms | 129.55 ms | 131.97 ms |
| Crear simulación | 172.58 ms | 151.11 ms | 146.94 ms |
| Conexión WebSocket | 214.50 ms | 220.48 ms | 234.78 ms |
| Snapshot WebSocket | 0.27 ms | 0.25 ms | 0.35 ms |
| Solve HTTP | 169.81 ms | 222.72 ms | 401.41 ms |
| Motor OpenDSS | **0.15 ms** | **1.89 ms** | **3.32 ms** |
| Resultado WebSocket | 117.02 ms | 245.55 ms | 274.17 ms |
| Evento `completed` | 117.07 ms | 245.64 ms | 274.32 ms |
| Eliminación de sesión | 125.82 ms | 132.51 ms | 132.90 ms |

---

## 10. Resultados IEEE13

### Métricas principales

| Métrica | Mínimo | Media | Mediana | P95 | Máximo |
|---|---:|---:|---:|---:|---:|
| Health | 115.18 ms | 132.93 ms | 116.79 ms | 257.32 ms | 257.32 ms |
| Create | 137.03 ms | 172.58 ms | 140.05 ms | 298.04 ms | 298.04 ms |
| WS connect | 199.90 ms | 214.50 ms | 212.90 ms | 241.30 ms | 241.30 ms |
| WS snapshot | 0.20 ms | 0.27 ms | 0.24 ms | 0.41 ms | 0.41 ms |
| Solve HTTP | 120.13 ms | 169.81 ms | 129.04 ms | 253.61 ms | 253.61 ms |
| Motor OpenDSS | 0.10 ms | 0.15 ms | 0.11 ms | 0.52 ms | 0.52 ms |
| WS result | 108.74 ms | 117.02 ms | 115.44 ms | 130.71 ms | 130.71 ms |
| WS completed | 108.79 ms | 117.07 ms | 115.50 ms | 130.75 ms | 130.75 ms |
| Delete | 121.85 ms | 125.82 ms | 122.93 ms | 146.42 ms | 146.42 ms |

Tiempo total de la campaña:

```text
9.71 s
```

---

## 11. Resultados IEEE34

### Métricas principales

| Métrica | Mínimo | Media | Mediana | P95 | Máximo |
|---|---:|---:|---:|---:|---:|
| Health | 112.33 ms | 129.55 ms | 115.60 ms | 237.16 ms | 237.16 ms |
| Create | 134.80 ms | 151.11 ms | 137.93 ms | 260.16 ms | 260.16 ms |
| WS connect | 200.36 ms | 220.48 ms | 222.97 ms | 253.62 ms | 253.62 ms |
| WS snapshot | 0.20 ms | 0.25 ms | 0.22 ms | 0.35 ms | 0.35 ms |
| Solve HTTP | 125.71 ms | 222.72 ms | 241.80 ms | 348.66 ms | 348.66 ms |
| Motor OpenDSS | 1.58 ms | 1.89 ms | 1.78 ms | 2.90 ms | 2.90 ms |
| WS result | 210.89 ms | 245.55 ms | 235.81 ms | 350.74 ms | 350.74 ms |
| WS completed | 210.95 ms | 245.64 ms | 235.88 ms | 350.81 ms | 350.81 ms |
| Delete | 118.97 ms | 132.51 ms | 128.00 ms | 195.94 ms | 195.94 ms |

Tiempo total de la campaña:

```text
10.77 s
```

---

## 12. Resultados IEEE123

### Métricas principales

| Métrica | Mínimo | Media | Mediana | P95 | Máximo |
|---|---:|---:|---:|---:|---:|
| Health | 114.99 ms | 131.97 ms | 119.62 ms | 241.84 ms | 241.84 ms |
| Create | 141.77 ms | 146.94 ms | 146.21 ms | 154.22 ms | 154.22 ms |
| WS connect | 203.35 ms | 234.78 ms | 224.88 ms | 352.18 ms | 352.18 ms |
| WS snapshot | 0.22 ms | 0.35 ms | 0.37 ms | 0.50 ms | 0.50 ms |
| Solve HTTP | 360.57 ms | 401.41 ms | 381.41 ms | 530.36 ms | 530.36 ms |
| Motor OpenDSS | 3.04 ms | 3.32 ms | 3.32 ms | 3.63 ms | 3.63 ms |
| WS result | 232.98 ms | 274.17 ms | 262.32 ms | 414.03 ms | 414.03 ms |
| WS completed | 233.07 ms | 274.32 ms | 262.45 ms | 414.17 ms | 414.17 ms |
| Delete | 124.56 ms | 132.90 ms | 128.04 ms | 155.07 ms | 155.07 ms |

Tiempo total de la campaña:

```text
17.33 s
```

---

## 13. Análisis de latencias

Los resultados muestran que la latencia básica HTTP permanece relativamente estable entre los tres feeders, con valores medios alrededor de 130 ms.

Esto permite identificar un piso aproximado de comunicación entre el cliente externo y la instancia AWS.

El tiempo interno de OpenDSS aumenta con el tamaño del feeder:

```text
IEEE13   → 0.15 ms
IEEE34   → 1.89 ms
IEEE123  → 3.32 ms
```

Sin embargo, el tiempo total observado por el cliente es considerablemente mayor:

```text
IEEE13   → 169.81 ms
IEEE34   → 222.72 ms
IEEE123  → 401.41 ms
```

Por tanto, el tiempo total no está dominado por el cálculo eléctrico.

La diferencia corresponde al conjunto de actividades asociadas con:

- comunicación de red;
- procesamiento de FastAPI;
- scheduling;
- serialización;
- generación de respuesta JSON;
- gestión de eventos;
- broadcast WebSocket;
- retorno HTTP.

Esta diferencia debe interpretarse como **overhead de plataforma y comunicación**, y no exclusivamente como latencia de red.

---

## 14. Comportamiento del feeder IEEE123

IEEE123 presentó el mayor tiempo total de respuesta de los tres modelos.

Resultados principales:

```text
Solve HTTP medio:        401.41 ms
Solve HTTP mediana:      381.41 ms
Solve HTTP máximo:       530.36 ms

Motor OpenDSS medio:       3.32 ms
Motor OpenDSS máximo:      3.63 ms

WS result medio:         274.17 ms
WS completed medio:      274.32 ms
```

Incluso para el modelo de mayor tamaño considerado en esta campaña, el ciclo de respuesta se mantuvo dentro de una escala sub-segundo.

---

## 15. Observación sobre P95

Las campañas utilizaron 10 iteraciones por feeder.

Con el estimador discreto utilizado para el percentil 95, el P95 coincide con el máximo cuando el tamaño de muestra es 10.

Por esta razón, los valores P95 deben considerarse exploratorios.

Para una caracterización estadística más robusta se recomienda posteriormente realizar campañas de 30 a 50 iteraciones o más.

Para la presente fase, las 10 iteraciones se consideran suficientes como línea base inicial de funcionamiento cloud.

---

## 16. Modelos personalizados

Durante esta fase se mantuvo:

```text
ALLOW_CUSTOM_MODELS=true
```

Esto permite continuar validando la carga y ejecución de modelos OpenDSS personalizados.

No obstante, mantener esta capacidad habilitada en un servicio público debe considerarse una condición experimental.

Para una exposición prolongada a Internet se recomienda:

```text
ALLOW_CUSTOM_MODELS=false
```

cuando la función no sea necesaria, o proteger posteriormente esta capacidad mediante mecanismos de autenticación y autorización.

---

## 17. Limitaciones actuales

La arquitectura cloud validada corresponde a un prototipo experimental de instancia única.

Actualmente:

- las sesiones se mantienen en memoria de proceso;
- los suscriptores WebSocket se gestionan en memoria;
- el último resultado de cada sesión permanece asociado al proceso;
- no existe persistencia distribuida;
- no existe recuperación transparente de sesiones después de reiniciar el contenedor;
- no existe escalamiento horizontal;
- no se ha implementado autenticación;
- se utiliza HTTP en lugar de HTTPS;
- se utiliza WebSocket `ws://` en lugar de `wss://`;
- el puerto `8000` permanece expuesto durante las pruebas;
- no se utiliza un registro externo de imágenes.

Estas condiciones son aceptables dentro de la fase experimental actual, pero deberán reevaluarse en una etapa posterior si la plataforma evoluciona hacia un entorno de producción.

---

## 18. Estado de criterios de la fase

| Criterio | Estado |
|---|---|
| Despliegue AWS EC2 | CUMPLE |
| Docker | CUMPLE |
| Docker Compose | CUMPLE |
| Health check | CUMPLE |
| API REST externa | CUMPLE |
| OpenDSS / AltDSS en cloud | CUMPLE |
| WebSocket externo | CUMPLE |
| IEEE13 | CUMPLE |
| IEEE34 | CUMPLE |
| IEEE123 | CUMPLE |
| Acceso simultáneo PC + celular | CUMPLE |
| Multi-viewer | CUMPLE |
| Aislamiento entre simulaciones | CUMPLE |
| Smoke Test | CUMPLE |
| Línea base de latencia | CUMPLE |
| Registry / Amazon ECR | PENDIENTE POR DECISIÓN DE COSTO |
| HTTPS / WSS | PENDIENTE |
| Autenticación | PENDIENTE |
| Persistencia distribuida | PENDIENTE |

---

## 19. Conclusiones

El despliegue realizado el 21 de septiembre de 2026 permitió verificar que el backend desarrollado para el gemelo digital puede operar correctamente fuera del entorno local y ejecutarse sobre una infraestructura AWS EC2 contenerizada.

La validación confirmó:

- exposición funcional de la API REST;
- ejecución de OpenDSS mediante AltDSS;
- operación de los feeders IEEE13, IEEE34 e IEEE123;
- comunicación WebSocket;
- difusión de eventos en tiempo real;
- acceso simultáneo desde computador y teléfono celular;
- múltiples observadores sobre una misma sesión;
- aislamiento entre simulaciones independientes;
- ejecución completa del Smoke Test;
- registro cuantitativo de latencias cloud.

Los resultados muestran además que el cálculo eléctrico interno representa una fracción pequeña del tiempo total observado desde el cliente, lo cual indica que para los feeders evaluados el comportamiento global está condicionado principalmente por el overhead de plataforma y comunicación, y no por el tiempo de solución del flujo de potencia.

La arquitectura actual es adecuada para continuar con las siguientes etapas experimentales del proyecto. Las capacidades relacionadas con seguridad, persistencia distribuida, TLS, escalamiento y registro de imágenes quedan identificadas como trabajos posteriores y no como fallas del despliegue validado.

---

## 20. Resultado general

**Estado de la fase:** VALIDADA

La infraestructura AWS EC2 quedó operativa y funcional para el prototipo actual del gemelo digital, con evidencia de ejecución cloud, conectividad externa, múltiples sesiones, multiusuario, WebSocket y línea base de desempeño.
