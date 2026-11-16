from services.api_manager.orchestration.simulation_service import (
    SimulationService,
)
from services.api_manager.execution.factory import (
    build_simulation_executor,
)


simulation_executor = (
    build_simulation_executor()
)

simulation_service = SimulationService(
    executor=simulation_executor
)