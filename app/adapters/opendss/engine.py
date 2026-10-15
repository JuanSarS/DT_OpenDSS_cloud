from __future__ import annotations

import math
import statistics
import threading
import time
from pathlib import Path
from typing import Callable

from altdss import altdss
import psutil

from app.domain.models import (
    ComplexValue,
    ModelSummary,
    QSTSConfig,
    QSTSResult,
    QSTSStepResult,
    SolveResponse,
)
from app.domain.qsts_profiles import qsts_profile


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

        # The AltDSS property setters require enum integers for these fields.
        # The DSS command parser accepts the documented names and units.
        self._ctx(
            "Set "
            f"mode=daily stepsize={config.step_minutes}m "
            "number=1 controlmode=time"
        )

        profile = config.load_multipliers
        if profile is None:
            profile = qsts_profile(
                config.profile_source,
                config.total_steps,
                config.step_minutes,
                config.load_multiplier,
            )

        for step in range(1, config.total_steps + 1):
            if profile is not None:
                self._ctx.Solution.LoadMult = profile[step - 1]

            solve_started_at = time.perf_counter()
            self._ctx.Solution.Solve()
            solve_ms = (time.perf_counter() - solve_started_at) * 1000.0

            classic = self._ctx.to_dss_python()
            circuit = classic.ActiveCircuit
            voltage_pu = [float(value) for value in circuit.AllBusVmagPu]
            load_multiplier = self.load_multiplier
            rss_mb = process.memory_info().rss / 1024**2
            rss_peak_mb = max(rss_peak_mb, rss_mb)
            simulated_minutes = step * config.step_minutes

            step_result = QSTSStepResult(
                    step=step,
                    simulated_minutes=simulated_minutes,
                    simulated_hour=simulated_minutes / 60.0,
                    opendss_hour=float(self._ctx.Solution.Hour),
                    opendss_time_of_step_us=float(self._ctx.Solution.TimeOfStep),
                    converged=bool(self._ctx.Solution.Converged),
                    solve_ms=round(solve_ms, 3),
                    load_multiplier=load_multiplier,
                    total_kw=float(self._ctx.TotalPower().real),
                    total_kvar=float(self._ctx.TotalPower().imag),
                    min_voltage_pu=min(voltage_pu) if voltage_pu else None,
                    max_voltage_pu=max(voltage_pu) if voltage_pu else None,
                    solution_iterations=int(self._ctx.Solution.Iterations),
                    rss_mb=round(rss_mb, 3),
                )
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
