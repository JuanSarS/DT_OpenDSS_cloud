from __future__ import annotations

import math
import statistics
import threading
import time
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from altdss import altdss
import psutil

from packages.contracts.errors import SwitchNotFoundError
from packages.contracts.interactive import InteractiveStepResult, NetworkBranch, SwitchAction, SwitchState
from packages.contracts.models import (
    ComplexValue,
    ModelSummary,
    QSTSConfig,
    QSTSResult,
    QSTSStepResult,
    SolveResponse,
)
from packages.simulation_core.qsts_profiles import qsts_profile

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


def _percentile(values: list[float], percentile: float) -> float:
    if len(values) == 1:
        return values[0]
    position = (len(values) - 1) * percentile
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return values[lower]
    fraction = position - lower
    return values[lower] + (values[upper] - values[lower]) * fraction


@dataclass
class QSTSSequence:
    config: QSTSConfig
    profile: list[float] | None
    process: psutil.Process
    completed: int = 0
    rss_mb: float = 0.0


class OpenDSSContextEngine:
    """
    One isolated OpenDSS/AltDSS memory context.

    The important line for the Week 4 acceptance criterion is:
        self._ctx = altdss.NewContext()

    Each instance owns a different engine context.
    """

    def __init__(
        self, topology_path: Path, load_multiplier: float = 1.0, *, model_commands: list[str] | None = None
    ) -> None:
        # AltDSS changes the process working directory while resolving relative
        # Redirect statements. Serialize only model loading to avoid races.
        with _ENGINE_LOAD_LOCK:
            self._ctx = altdss.NewContext()
            self._topology_path = topology_path.resolve()
            self._ctx("Clear")
            if model_commands is None:
                self._ctx.Settings.AllowChangeDir = True
                self._ctx(f'Redirect "{self._topology_path.as_posix()}"')
            else:
                self._ctx.Settings.AllowChangeDir = False
                self._ctx.Settings.AllowDOScmd = False
                self._ctx.Settings.AllowEditor = False
                try:
                    self._ctx(model_commands + ["MakeBusList"])
                except Exception:
                    with suppress(Exception):
                        self.close()
                    raise
            self._ctx.Solution.LoadMult = load_multiplier

    @property
    def identity(self) -> int:
        """Python identity used only by automated isolation tests."""
        return id(self._ctx)

    @property
    def load_multiplier(self) -> float:
        return float(self._ctx.Solution.LoadMult)

    def set_load_multiplier(self, load_multiplier: float) -> None:
        self._ctx.Solution.LoadMult = load_multiplier

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

    def begin_qsts(self, config: QSTSConfig, process: psutil.Process | None = None) -> QSTSSequence:
        """Initialize daily mode once. Subsequent steps retain the solution and controls."""
        self._ctx(f"Set mode=daily stepsize={config.step_minutes}m number=1 controlmode=time")
        profile = config.load_multipliers
        if profile is None:
            profile = qsts_profile(
                config.profile_source, config.total_steps, config.step_minutes, config.load_multiplier,
            )
        return QSTSSequence(config, profile, process if process is not None else psutil.Process())

    def advance_qsts(self, sequence: QSTSSequence) -> QSTSStepResult:
        if sequence.completed >= sequence.config.total_steps:
            raise ValueError("El QSTS ya completó todos sus pasos.")
        if sequence.profile is not None:
            self._ctx.Solution.LoadMult = sequence.profile[sequence.completed]
        started_at = time.perf_counter()
        self._ctx.Solution.Solve()
        solve_ms = (time.perf_counter() - started_at) * 1000.0
        circuit = self._ctx.to_dss_python().ActiveCircuit
        voltage_pu = [float(value) for value in circuit.AllBusVmagPu]
        sequence.rss_mb = sequence.process.memory_info().rss / 1024**2
        sequence.completed += 1
        simulated_minutes = sequence.completed * sequence.config.step_minutes
        power = self._ctx.TotalPower()
        return QSTSStepResult(
            step=sequence.completed,
            simulated_minutes=simulated_minutes,
            simulated_hour=simulated_minutes / 60,
            opendss_hour=float(self._ctx.Solution.Hour),
            opendss_time_of_step_us=float(self._ctx.Solution.TimeOfStep),
            converged=bool(self._ctx.Solution.Converged),
            solve_ms=round(solve_ms, 3),
            load_multiplier=self.load_multiplier,
            total_kw=float(power.real),
            total_kvar=float(power.imag),
            min_voltage_pu=min(voltage_pu) if voltage_pu else None,
            max_voltage_pu=max(voltage_pu) if voltage_pu else None,
            solution_iterations=int(self._ctx.Solution.Iterations),
            rss_mb=round(sequence.rss_mb, 3),
        )

    def advance_interactive(self, sequence: QSTSSequence) -> InteractiveStepResult:
        step = self.advance_qsts(sequence)
        losses = self._ctx.Losses()
        return InteractiveStepResult(
            **step.model_dump(), loss_kw=float(losses.real) / 1000, loss_kvar=float(losses.imag) / 1000,
        )

    def branch_catalog(self) -> tuple[list[NetworkBranch], dict[str, str]]:
        controlled = {
            control.SwitchedObj_str.casefold() for control in self._ctx.SwtControl if control.Enabled
        }
        branches = []
        switches = {}
        for line in self._ctx.Line:
            if not line.Enabled:
                continue
            element = line.FullName()
            if line.Switch or element.casefold() in controlled:
                switches[element.casefold()] = element
            branches.append(NetworkBranch(
                element=element, bus_from=line.Bus1.split(".", 1)[0], bus_to=line.Bus2.split(".", 1)[0],
            ))
        for transformer in self._ctx.Transformer:
            if not transformer.Enabled:
                continue
            buses = transformer.Buses
            for bus in buses[1:]:
                branches.append(NetworkBranch(
                    element=transformer.FullName(), bus_from=buses[0].split(".", 1)[0],
                    bus_to=bus.split(".", 1)[0],
                ))
        return branches, switches

    def switch_state(self, element: str) -> SwitchState:
        circuit = self._ctx.to_dss_python().ActiveCircuit
        if circuit.SetActiveElement(element) < 0:
            raise SwitchNotFoundError("No se encontró el interruptor en OpenDSS.")
        active = circuit.ActiveCktElement
        open_conductors = [
            [bool(active.IsOpen(terminal, phase)) for phase in range(1, active.NumConductors + 1)]
            for terminal in range(1, active.NumTerminals + 1)
        ]
        disconnected = [any(terminals) for terminals in zip(*open_conductors, strict=True)]
        status = "open" if all(disconnected) else "partial" if any(disconnected) else "closed"
        return SwitchState(element=element, status=status, open_conductors=open_conductors)

    def operate_switch(self, element: str, action: SwitchAction) -> SwitchState:
        circuit = self._ctx.to_dss_python().ActiveCircuit
        if circuit.SetActiveElement(element) < 0:
            raise SwitchNotFoundError("No se encontró el interruptor en OpenDSS.")
        active = circuit.ActiveCktElement
        operate = active.Open if action == "open" else active.Close
        for terminal in range(1, active.NumTerminals + 1):
            operate(terminal, 0)
        return self.switch_state(element)

    def solve_qsts(
        self,
        config: QSTSConfig,
        progress_callback: Callable[[QSTSStepResult, int, int], None] | None = None,
    ) -> QSTSResult:
        """Run QSTS steps on this engine's already-loaded OpenDSS context."""
        process = psutil.Process()
        rss_start_mb = process.memory_info().rss / 1024**2
        rss_peak_mb = rss_start_mb
        started_at = time.perf_counter()
        step_results: list[QSTSStepResult] = []

        sequence = self.begin_qsts(config, process)
        for step in range(1, config.total_steps + 1):
            step_result = self.advance_qsts(sequence)
            rss_peak_mb = max(rss_peak_mb, sequence.rss_mb)
            step_results.append(step_result)
            if progress_callback is not None:
                progress_callback(step_result, step, config.total_steps)

        solve_times = sorted(result.solve_ms for result in step_results)
        elapsed_ms = (time.perf_counter() - started_at) * 1000.0
        return QSTSResult(
            config=config,
            total_steps=len(step_results),
            converged_steps=sum(result.converged for result in step_results),
            failed_steps=sum(not result.converged for result in step_results),
            elapsed_ms=round(elapsed_ms, 3),
            solve_mean_ms=round(statistics.mean(solve_times), 3),
            solve_p50_ms=round(_percentile(solve_times, 0.50), 3),
            solve_p95_ms=round(_percentile(solve_times, 0.95), 3),
            solve_max_ms=max(solve_times),
            rss_start_mb=round(rss_start_mb, 3),
            rss_peak_mb=round(rss_peak_mb, 3),
            steps=step_results,
        )
