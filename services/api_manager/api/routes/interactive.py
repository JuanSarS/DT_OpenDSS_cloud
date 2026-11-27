from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.routing import APIRoute

from packages.contracts.errors import (
    AccessDeniedError, InteractiveConflict, InteractiveContextLost, InteractiveExecutionError,
    OverloadedError, QuotaExceededError, SimulationNotFoundError, SwitchNotFoundError,
)
from packages.contracts.interactive import (
    InteractiveStart, InteractiveState, InteractiveStepResponse, InteractiveStepResult, IntervalCommand,
    ModeCommand, NetworkBranch, Participant, ParticipantUpdate, RunReference, StepCommand,
    SwitchCommand, SwitchOperation, SwitchState,
)
from services.api_manager.auth.dependencies import CurrentUser
from services.api_manager.auth.users import load_users
from services.api_manager.orchestration.container import simulation_service


class InteractiveRoute(APIRoute):
    def get_route_handler(self):
        handle = super().get_route_handler()

        async def translate_errors(request: Request):
            try:
                return await handle(request)
            except (SimulationNotFoundError, SwitchNotFoundError) as exc:
                raise HTTPException(404, detail=str(exc)) from exc
            except AccessDeniedError as exc:
                raise HTTPException(403, detail=str(exc)) from exc
            except InteractiveConflict as exc:
                raise HTTPException(409, detail=str(exc)) from exc
            except (QuotaExceededError, OverloadedError) as exc:
                raise HTTPException(429, detail=str(exc)) from exc
            except InteractiveContextLost as exc:
                raise HTTPException(503, detail=str(exc)) from exc
            except InteractiveExecutionError as exc:
                raise HTTPException(422, detail=str(exc)) from exc

        return translate_errors


_ACCESS_RESPONSES = {
    401: {"description": "Autenticación requerida."},
    403: {"description": "La cuenta no tiene el permiso requerido."},
    404: {"description": "No se encontró la simulación, la cuenta o el interruptor."},
    409: {"description": "El comando no coincide con la ejecución, el paso o el estado actual."},
}
router = APIRouter(prefix="/simulations/{session_id}", route_class=InteractiveRoute, responses=_ACCESS_RESPONSES)
qsts = APIRouter(
    prefix="/qsts/interactive", tags=["QSTS interactivo"], route_class=InteractiveRoute,
    responses={
        429: {"description": "No hay capacidad para admitir otro paso en este momento."},
        503: {"description": "El worker no confirmó el estado del contexto interactivo."},
    },
)
controls = APIRouter(
    prefix="/controls", tags=["Interruptores"], route_class=InteractiveRoute,
    responses={503: {"description": "No se pudo confirmar el estado eléctrico en el worker."}},
)


@qsts.post("/start", summary="Inicializar un QSTS interactivo")
async def start(session_id: str, request: InteractiveStart, user: CurrentUser) -> InteractiveState:
    return await simulation_service.interactive.start(session_id, request, user.username, user.role == "admin")


@qsts.get("/state", summary="Consultar tiempo simulado, intervalo real y estado del QSTS")
async def state(session_id: str, user: CurrentUser) -> InteractiveState | None:
    service = simulation_service.interactive
    return service.state(service.read(session_id, user.username, user.role == "admin"))


@qsts.post("/step", summary="Forzar un paso individual, incluso en modo automático")
async def step(session_id: str, command: StepCommand, user: CurrentUser) -> InteractiveStepResponse:
    return await simulation_service.interactive.step(session_id, command, user.username, user.role == "admin")


@qsts.post("/run", summary="Iniciar la ejecución automática")
async def run(session_id: str, command: RunReference, user: CurrentUser) -> InteractiveState:
    return await simulation_service.interactive.transition(session_id, command, "run", user.username, user.role == "admin")


@qsts.post("/pause", summary="Pausar sin perder el estado eléctrico")
async def pause(session_id: str, command: RunReference, user: CurrentUser) -> InteractiveState:
    return await simulation_service.interactive.transition(session_id, command, "pause", user.username, user.role == "admin")


@qsts.post("/resume", summary="Reanudar en el modo configurado")
async def resume(session_id: str, command: RunReference, user: CurrentUser) -> InteractiveState:
    return await simulation_service.interactive.transition(session_id, command, "resume", user.username, user.role == "admin")


@qsts.put("/interval", summary="Cambiar el intervalo entre pasos en segundos reales")
async def interval(session_id: str, command: IntervalCommand, user: CurrentUser) -> InteractiveState:
    return await simulation_service.interactive.transition(session_id, command, "interval", user.username, user.role == "admin")


@qsts.put("/mode", summary="Elegir avance manual o automático")
async def mode(session_id: str, command: ModeCommand, user: CurrentUser) -> InteractiveState:
    return await simulation_service.interactive.transition(session_id, command, "mode", user.username, user.role == "admin")


@qsts.post("/stop", summary="Detener el QSTS y conservar los resultados confirmados")
async def stop(session_id: str, command: RunReference, user: CurrentUser) -> InteractiveState:
    return await simulation_service.interactive.transition(session_id, command, "stop", user.username, user.role == "admin")


@qsts.post("/restart", summary="Reiniciar desde el circuito inicial con un nuevo identificador de ejecución")
async def restart(session_id: str, command: RunReference, user: CurrentUser) -> InteractiveState:
    return await simulation_service.interactive.transition(session_id, command, "restart", user.username, user.role == "admin")


@qsts.get("/results", summary="Consultar los resultados confirmados a partir de un paso")
async def results(
    session_id: str, user: CurrentUser, after_step: Annotated[int, Query(ge=0)] = 0, run_id: UUID | None = None,
) -> list[InteractiveStepResult]:
    session = simulation_service.interactive.read(session_id, user.username, user.role == "admin")
    run = session.interactive
    if run_id is not None and (run is None or run.run_id != run_id):
        raise InteractiveConflict("Los resultados corresponden a otra ejecución.")
    return run.steps[after_step:] if run is not None else []


@qsts.get("/network", summary="Consultar ramas de líneas y transformadores del circuito")
async def network(session_id: str, user: CurrentUser, run_id: UUID | None = None) -> list[NetworkBranch]:
    session = simulation_service.interactive.read(session_id, user.username, user.role == "admin")
    run = session.interactive
    if run_id is not None and (run is None or run.run_id != run_id):
        raise InteractiveConflict("La red corresponde a otra ejecución.")
    return run.branches if run is not None else []


@controls.get("/switches", summary="Listar interruptores y su estado efectivo en OpenDSS")
async def switches(session_id: str, user: CurrentUser) -> list[SwitchState]:
    return await simulation_service.interactive.switches(session_id, user.username, user.role == "admin")


@controls.get("/switches/{element:path}", summary="Leer el estado efectivo de un interruptor")
async def switch_state(session_id: str, element: str, user: CurrentUser) -> SwitchState:
    available = await simulation_service.interactive.switches(session_id, user.username, user.role == "admin")
    for switch in available:
        if switch.element.casefold() == element.casefold():
            return switch
    raise SwitchNotFoundError("El elemento no es un interruptor controlable.")


@controls.post("/switches/{element:path}", summary="Abrir o cerrar un interruptor entre pasos QSTS")
async def operate_switch(session_id: str, element: str, command: SwitchCommand, user: CurrentUser) -> SwitchOperation:
    return await simulation_service.interactive.operate(
        session_id, element, command, user.username, user.role == "admin",
    )


@controls.get("/history", summary="Consultar las operaciones de interruptores más recientes")
async def history(
    session_id: str, user: CurrentUser, run_id: UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=3000)] = 200,
) -> list[SwitchOperation]:
    session = simulation_service.interactive.read(session_id, user.username, user.role == "admin")
    return [entry for entry in session.switch_history if run_id is None or entry.run_id == run_id][-limit:]


@router.get("/participants", tags=["Participantes"], summary="Listar operadores y espectadores de la sesión")
async def participants(session_id: str, user: CurrentUser) -> list[Participant]:
    return simulation_service.list_participants(session_id, user.username, user.role == "admin")


@router.put("/participants/{username}", tags=["Participantes"], summary="Invitar a un usuario o cambiar su rol")
async def set_participant(
    session_id: str, username: str, request: ParticipantUpdate, user: CurrentUser,
) -> Participant:
    admin = user.role == "admin"
    simulation_service.list_participants(session_id, user.username, admin)
    target = load_users().get(username)
    if target is None or target.disabled:
        raise HTTPException(404, detail="Usuario no encontrado.")
    return await simulation_service.set_participant(
        session_id, username, request.role, user_id=user.username, is_admin=admin,
    )


@router.delete("/participants/{username}", tags=["Participantes"], status_code=204, summary="Revocar acceso a un participante")
async def remove_participant(session_id: str, username: str, user: CurrentUser) -> None:
    await simulation_service.remove_participant(
        session_id, username, user_id=user.username, is_admin=user.role == "admin",
    )


router.include_router(qsts)
router.include_router(controls)
