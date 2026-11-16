import pytest
from pydantic import ValidationError

from packages.contracts.errors import (
    SimulationError,
    SimulationErrorCode,
)
from packages.contracts.jobs import JobStatus, SimulationJob
from packages.contracts.models import (
    QSTSConfig,
    QSTSResult,
    QSTSStepResult,
    SolveResponse,
)
from packages.contracts.progress import SimulationProgress
from packages.contracts.results import SimulationResult


def test_snapshot_job_json_roundtrip() -> None:
    job = SimulationJob(
        job_id="job-1",
        session_id="session-1",
        topology="ieee123",
        simulation_type="snapshot",
        load_multiplier=1.0,
    )

    payload = job.model_dump_json()
    restored = SimulationJob.model_validate_json(payload)

    assert restored == job
    assert restored.contract_version == "1.0"
    assert restored.qsts is None


def test_qsts_job_json_roundtrip() -> None:
    job = SimulationJob(
        job_id="job-2",
        session_id="session-2",
        topology="ieee8500",
        simulation_type="qsts",
        qsts=QSTSConfig(
            duration_hours=0.25,
            step_minutes=5,
            profile_source="values",
            load_multipliers=[0.8, 1.0, 1.2],
        ),
    )

    payload = job.model_dump_json()
    restored = SimulationJob.model_validate_json(payload)

    assert restored == job
    assert restored.qsts is not None
    assert restored.qsts.total_steps == 3


def test_qsts_job_requires_qsts_configuration() -> None:
    with pytest.raises(ValidationError):
        SimulationJob(
            job_id="job-3",
            session_id="session-3",
            topology="ieee123",
            simulation_type="qsts",
        )


def test_snapshot_job_rejects_qsts_configuration() -> None:
    with pytest.raises(ValidationError):
        SimulationJob(
            job_id="job-4",
            session_id="session-4",
            topology="ieee123",
            simulation_type="snapshot",
            qsts=QSTSConfig(),
        )


def test_progress_json_roundtrip() -> None:
    progress = SimulationProgress(
        job_id="job-5",
        session_id="session-5",
        simulation_type="qsts",
        status=JobStatus.RUNNING,
        step=2,
        total_steps=3,
        progress_pct=66.667,
        simulated_minutes=10.0,
        simulated_hour=10.0 / 60.0,
        converged=True,
        solve_ms=0.12,
        load_multiplier=1.0,
        total_kw=-3000.0,
        total_kvar=-1200.0,
        min_voltage_pu=0.98,
        max_voltage_pu=1.04,
    )

    payload = progress.model_dump_json()
    restored = SimulationProgress.model_validate_json(payload)

    assert restored == progress
    assert restored.step == 2
    assert restored.total_steps == 3


def test_snapshot_result_json_roundtrip() -> None:
    snapshot = SolveResponse(
        session_id="session-6",
        topology="ieee123",
        converged=True,
        elapsed_ms=1.2,
        load_multiplier=1.0,
        total_power_kw=-3000.0,
        total_power_kvar=-1000.0,
        voltages={},
        currents={},
    )

    result = SimulationResult(
        job_id="job-6",
        session_id="session-6",
        topology="ieee123",
        simulation_type="snapshot",
        snapshot=snapshot,
    )

    payload = result.model_dump_json()
    restored = SimulationResult.model_validate_json(payload)

    assert restored == result
    assert restored.snapshot is not None
    assert restored.snapshot.converged is True


def test_qsts_result_json_roundtrip() -> None:
    step = QSTSStepResult(
        step=1,
        simulated_minutes=5.0,
        simulated_hour=5.0 / 60.0,
        converged=True,
        solve_ms=0.1,
        load_multiplier=1.0,
        total_kw=-3000.0,
        total_kvar=-1000.0,
        min_voltage_pu=0.98,
        max_voltage_pu=1.04,
    )

    qsts = QSTSResult(
        config=QSTSConfig(
            duration_hours=5.0 / 60.0,
            step_minutes=5.0,
            profile_source="constant",
        ),
        total_steps=1,
        converged_steps=1,
        failed_steps=0,
        elapsed_ms=0.1,
        solve_mean_ms=0.1,
        solve_p50_ms=0.1,
        solve_p95_ms=0.1,
        solve_max_ms=0.1,
        rss_start_mb=100.0,
        rss_peak_mb=101.0,
        steps=[step],
    )

    result = SimulationResult(
        job_id="job-7",
        session_id="session-7",
        topology="ieee123",
        simulation_type="qsts",
        qsts=qsts,
    )

    restored = SimulationResult.model_validate_json(
        result.model_dump_json()
    )

    assert restored == result
    assert restored.qsts is not None
    assert restored.qsts.total_steps == 1


def test_result_rejects_wrong_payload_type() -> None:
    snapshot = SolveResponse(
        session_id="session-8",
        topology="ieee123",
        converged=True,
        elapsed_ms=1.0,
        load_multiplier=1.0,
        total_power_kw=-1.0,
        total_power_kvar=-1.0,
        voltages={},
        currents={},
    )

    with pytest.raises(ValidationError):
        SimulationResult(
            job_id="job-8",
            session_id="session-8",
            topology="ieee123",
            simulation_type="qsts",
            snapshot=snapshot,
        )


def test_simulation_error_json_roundtrip() -> None:
    error = SimulationError(
        job_id="job-9",
        session_id="session-9",
        code=SimulationErrorCode.WORKER_ERROR,
        message="Worker failed",
        retryable=True,
        attempt=2,
        details={
            "worker": "worker-1",
        },
    )

    restored = SimulationError.model_validate_json(
        error.model_dump_json()
    )

    assert restored == error
    assert restored.retryable is True
    assert restored.attempt == 2