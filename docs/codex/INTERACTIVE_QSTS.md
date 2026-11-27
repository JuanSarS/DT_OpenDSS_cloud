# QSTS interactivo y operación colaborativa

## Levantar el laboratorio local

Desde la raíz del repositorio, con Docker Desktop abierto, ejecute:

```powershell
.\scripts\deploy_local.ps1
```

Si todavía no existen las credenciales locales, ejecute primero `python .\scripts\init_local_secrets.py`. El script solicita las contraseñas de las cuentas. La aplicación queda en `https://localhost:8443` y OpenAPI en `https://localhost:8443/docs`. Para detener el laboratorio use `.\scripts\stop_local.ps1`.

## Usar el navegador

1. Inicie sesión, seleccione un modelo y pulse **Crear simulación**. IEEE13 permite probar el interruptor `Line.671692`.
2. Seleccione **QSTS interactivo** y configure la duración y el paso simulado. El intervalo real gobierna el automático y se expresa en segundos. El modo inicial automático espera la orden **Automático** o **Reanudar**.
3. Pulse **Inicializar QSTS interactivo**. **Siguiente paso** ejecuta un único paso en manual o automático. **Automático**, **Pausar** y **Reanudar** controlan el avance. Cambie el valor de intervalo y pulse **Aplicar intervalo**. **Detener** conserva los resultados ya confirmados y **Reiniciar** crea otra ejecución desde el circuito inicial.
4. En **Interruptores**, use **Abrir** o **Cerrar**. **Ver** enfoca el elemento en el diagrama construido a partir de líneas y transformadores. **QSTS** muestra las curvas de potencia y tensión y los últimos 1000 pasos de la tabla. **Potencias** muestra el último paso y sus pérdidas. **Operaciones** muestra quién actuó, qué hizo y el paso confirmado.
5. En **Compartir simulación**, elija una cuenta y el rol de operador o espectador. En otro perfil del navegador, actualice la lista y abra la sesión desde **Invitaciones recibidas**. El propietario puede modificar el rol con **Guardar rol** o terminar el acceso con **Quitar acceso**.

## API

Las rutas públicas requieren cookie o token Bearer. Los sufijos se agregan a `/simulations/{session_id}`. OpenAPI describe los contratos y sus campos.

| Método | Sufijo | Solicitud o resultado |
|---|---|---|
| POST | `/qsts/interactive/start` | Duración, paso, perfil, modo e intervalo. Devuelve el estado inicial. |
| GET | `/qsts/interactive/state` | Estado, revisión, avance, último resultado y siguiente ejecución programada. Devuelve `null` antes de iniciar. |
| POST | `/qsts/interactive/step` | `run_id`, `expected_step` y `command_id`. Devuelve el resultado de ese paso y el estado. |
| POST | `/qsts/interactive/run` | `run_id`. Inicia o habilita el modo automático. |
| POST | `/qsts/interactive/pause` | `run_id`. Pausa los siguientes pasos programados. |
| POST | `/qsts/interactive/resume` | `run_id`. Reanuda en el modo configurado. |
| PUT | `/qsts/interactive/mode` | `run_id` y `execution_mode` de valor `manual` o `automatic`. |
| PUT | `/qsts/interactive/interval` | `run_id` e `interval_seconds` entre 0,1 y 3600. |
| POST | `/qsts/interactive/stop` | `run_id`. Detiene el avance y conserva los resultados confirmados. |
| POST | `/qsts/interactive/restart` | `run_id`. Crea una ejecución nueva con la configuración vigente desde el paso cero. |
| GET | `/qsts/interactive/results` | Resultados confirmados. Acepta `run_id` y `after_step` opcionales. |
| GET | `/qsts/interactive/network` | Ramas del modelo. Acepta `run_id` opcional. |
| GET | `/controls/switches` | Estado efectivo y polos abiertos por terminal de cada interruptor controlable. |
| GET | `/controls/switches/{element}` | Estado efectivo de un interruptor. Use su nombre completo, por ejemplo `Line.671692`. |
| POST | `/controls/switches/{element}` | `run_id`, `expected_step`, `command_id` y `action` de valor `open` o `close`. |
| GET | `/controls/history` | Historial reciente. Acepta `run_id` y `limit` opcionales. |
| GET | `/participants` | Roles e invitaciones vigentes para el propietario o administrador. |
| PUT | `/participants/{username}` | `role` de valor `operator` o `viewer`. Invita o cambia el rol. |
| DELETE | `/participants/{username}` | Revoca el acceso REST y cierra sus conexiones WebSocket de participante. |

El propietario administra participantes y configuración y puede detener o reiniciar. El operador puede avanzar, pausar, reanudar, operar interruptores e iniciar el automático cuando ese modo ya está habilitado. El espectador puede consultar y recibir eventos. El administrador global conserva su acceso. El servidor valida los permisos.

### Ejemplo con PowerShell

```powershell
$api = 'https://localhost:8443'
$login = Get-Credential
Invoke-RestMethod "$api/auth/token" -Method Post -Body @{
    username = $login.UserName
    password = $login.GetNetworkCredential().Password
} -SessionVariable dssSession | Out-Null
$json = @{ContentType = 'application/json'; WebSession = $dssSession}
$session = Invoke-RestMethod "$api/simulations" -Method Post @json -Body '{"topology":"ieee13"}'
$base = "$api/simulations/$($session.session_id)"
$config = '{"duration_hours":1,"step_minutes":10,"profile_source":"constant","execution_mode":"manual","interval_seconds":5}'
$run = Invoke-RestMethod "$base/qsts/interactive/start" -Method Post @json -Body $config
$stepCommand = @{run_id=$run.run_id; expected_step=0; command_id=[guid]::NewGuid().ToString()} | ConvertTo-Json
$first = Invoke-RestMethod "$base/qsts/interactive/step" -Method Post @json -Body $stepCommand
$operation = @{
    run_id=$run.run_id
    expected_step=$first.state.completed_steps
    command_id=[guid]::NewGuid().ToString()
    action='open'
} | ConvertTo-Json
Invoke-RestMethod "$base/controls/switches/Line.671692" -Method Post @json -Body $operation
Invoke-RestMethod "$base/qsts/interactive/run" -Method Post @json -Body (@{run_id=$run.run_id} | ConvertTo-Json)
```

### Semántica del avance y los controles

- OpenDSS usa el paso simulado en minutos. El API Manager usa un reloj monotónico real. El automático ejecuta un primer paso al iniciar o reanudar y espera el intervalo después de cada avance confirmado. Puede seguir con todos los navegadores desconectados.
- Forzar un paso en automático vuelve a contar el intervalo desde ese avance. El servidor serializa pasos y cambios eléctricos. `expected_step` y `run_id` rechazan solicitudes atrasadas. `command_id` permite repetir una solicitud confirmada sin repetir su efecto. Si el paso programado gana la carrera, una orden con el paso anterior recibe `409`. Consulte el estado antes de enviar otro comando.
- Cambiar el intervalo durante el automático vuelve a programar el próximo paso desde ese cambio. La pausa y la operación de interruptores esperan a que termine el paso en curso. La duración debe ser divisible por el paso. Se admiten hasta 10 000 pasos y los mismos perfiles de QSTS batch.
- El primer inicio usa el contexto de la sesión. El reinicio solicitado crea un contexto inicial nuevo. Si se perdió el worker se publica `interrupted`, se conserva el último paso confirmado y se detiene el temporizador. Un reinicio explícito puede preparar un worker disponible y comienza desde cero.
- Se catalogan las líneas habilitadas con `Switch=yes` y las líneas habilitadas referenciadas por un `SwtControl` habilitado. La orden abre o cierra todos los conductores en ambos terminales. Se consulta el estado nativo después de cada orden y cada paso, incluidos cambios posteriores de controles de OpenDSS. Los resultados previos a una operación se marcan como desactualizados hasta el siguiente cálculo.
- La planificación y la membresía permanecen en memoria, como la sesión existente. El historial REST conserva las últimas 3000 operaciones de la sesión. Cada orden confirmada también se registra en el log del API Manager. El diagrama es topológico.

### WebSocket

Conéctese a `/ws/simulations/{session_id}` mediante la cookie o el subprotocolo JWT existente. El evento inicial `snapshot` incluye `interactive` y `switches` si hay una ejecución. `interactive_state` indica cambios o una interrupción. `interactive_step` incluye `state.latest_result`, revisión y estados efectivos de interruptores. `switch_operation` agrega el actor, elemento, acción, paso confirmado y timestamp UTC. Los cambios de rol se envían como `participant_role` al participante afectado. Tras reconectar, consulte los resultados perdidos en `/results?after_step=...`. Snapshot y QSTS batch conservan sus rutas y eventos.
