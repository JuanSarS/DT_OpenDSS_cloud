from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Callable

from packages.contracts.models import (
    ModelSummary,
    QSTSConfig,
    QSTSResult,
    QSTSStepResult,
    SolveResponse,
)
from packages.simulation_core.engine import OpenDSSContextEngine


ProgressCallback = Callable[
    [QSTSStepResult, int, int],
    None,
]


class LocalSimulationExecutor:
    """
    Local execution adapter.

    It preserves the current monolithic execution model while moving
    native/blocking OpenDSS execution out of SimulationService.

    A future remote/cloud executor can replace this adapter without
    changing the REST/WebSocket contracts.
    """

    async def create_engine(
        self,
        topology_path: Path,
        load_multiplier: float = 1.0,
    ) -> OpenDSSContextEngine:
        return await asyncio.to_thread(
            OpenDSSContextEngine,
            topology_path,
            load_multiplier,
        )

    def model_summary(
        self,
        engine: OpenDSSContextEngine,
        topology: str,
    ) -> ModelSummary:
        return engine.model_summary(topology)

    async def solve_snapshot(
        self,
        engine: OpenDSSContextEngine,
        session_id: str,
        topology: str,
        load_multiplier: float | None = None,
    ) -> SolveResponse:
        if load_multiplier is not None:
            await asyncio.to_thread(
                engine.set_load_multiplier,
                load_multiplier,
            )

        return await asyncio.to_thread(
            engine.solve,
            session_id,
            topology,
        )

    async def solve_qsts(
        self,
        engine: OpenDSSContextEngine,
        config: QSTSConfig,
        progress_callback: ProgressCallback | None = None,
    ) -> QSTSResult:
        return await asyncio.to_thread(
            engine.solve_qsts,
            config,
            progress_callback,
        )

    async def close(
        self,
        engine: OpenDSSContextEngine,
    ) -> None:
        await asyncio.to_thread(engine.close)

    @staticmethod
    def identity(
        engine: OpenDSSContextEngine,
    ) -> int:
        return engine.identity

    @staticmethod
    def load_multiplier(
        engine: OpenDSSContextEngine,
    ) -> float:
        return engine.load_multiplier