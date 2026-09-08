from __future__ import annotations

import math
import threading
import time
from pathlib import Path

from altdss import altdss

from app.domain.models import ComplexValue, ModelSummary, SolveResponse


_ENGINE_LOAD_LOCK = threading.Lock()


def _complex_values(raw: list[float] | tuple[float, ...]) -> list[ComplexValue]:
    values: list[ComplexValue] = []
    for i in range(0, len(raw), 2):
        real = float(raw[i])
        imag = float(raw[i + 1])
        magnitude = math.hypot(real, imag)
        angle_deg = math.degrees(math.atan2(imag, real))
        values.append(
            ComplexValue(
                real=real,
                imag=imag,
                magnitude=magnitude,
                angle_deg=angle_deg,
            )
        )
    return values


class OpenDSSContextEngine:
    """
    One isolated OpenDSS/AltDSS memory context.

    The important line for the Week 4 acceptance criterion is:
        self._ctx = altdss.NewContext()

    Each instance owns a different engine context.
    """

    def __init__(self, topology_path: Path, load_multiplier: float = 1.0) -> None:
        # AltDSS changes the process working directory while resolving relative
        # Redirect statements. Serialize only model loading to avoid races.
        with _ENGINE_LOAD_LOCK:
            self._ctx = altdss.NewContext()
            self._topology_path = topology_path.resolve()
            self._ctx.Settings.AllowChangeDir = True
            self._ctx("Clear")
            self._ctx(f'Redirect "{self._topology_path.as_posix()}"')
            self._ctx.Solution.LoadMult = load_multiplier

    @property
    def identity(self) -> int:
        """Python identity used only by automated isolation tests."""
        return id(self._ctx)

    @property
    def load_multiplier(self) -> float:
        return float(self._ctx.Solution.LoadMult)

    def model_summary(self, topology: str) -> ModelSummary:
        classic = self._ctx.to_dss_python()
        circuit = classic.ActiveCircuit
        node_names = list(circuit.AllNodeNames)
        return ModelSummary(
            topology=topology,
            num_buses=len(list(circuit.AllBusNames)),
            num_nodes=len(node_names),
            node_names=node_names,
        )

    def close(self) -> None:
        """Release the native circuit before the session is removed."""
        self._ctx("Clear")
        self._ctx = None

    def solve(self, session_id: str, topology: str) -> SolveResponse:
        start = time.perf_counter()

        # Snapshot power flow.
        self._ctx("Set mode=snapshot")
        self._ctx.Solution.Solve()

        elapsed_ms = (time.perf_counter() - start) * 1000.0
        converged = bool(self._ctx.Solution.Converged)

        # Use DSS-Python compatibility view over THE SAME context for classic
        # circuit arrays and active-element currents.
        classic = self._ctx.to_dss_python()
        circuit = classic.ActiveCircuit

        node_names = list(circuit.AllNodeNames)
        voltage_values = _complex_values(list(circuit.AllBusVolts))
        voltages = {
            node: value for node, value in zip(node_names, voltage_values, strict=False)
        }

        currents: dict[str, list[ComplexValue]] = {}
        for element_name in list(circuit.AllElementNames):
            circuit.SetActiveElement(element_name)
            raw_currents = list(circuit.ActiveCktElement.Currents)
            currents[element_name] = _complex_values(raw_currents)

        # OpenDSS total power convention is power delivered INTO the circuit,
        # hence values are normally negative for a consuming feeder.
        total_power = self._ctx.TotalPower()

        return SolveResponse(
            session_id=session_id,
            topology=topology,
            converged=converged,
            elapsed_ms=round(elapsed_ms, 3),
            load_multiplier=self.load_multiplier,
            total_power_kw=float(total_power.real),
            total_power_kvar=float(total_power.imag),
            voltages=voltages,
            currents=currents,
        )
