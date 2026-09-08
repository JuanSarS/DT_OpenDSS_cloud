class SimulationNotFoundError(KeyError):
    """Raised when a simulation session does not exist."""


class TopologyNotFoundError(ValueError):
    """Raised when the requested topology is not available."""


class SimulationClosedError(RuntimeError):
    """Raised when an operation targets a closed simulation."""
