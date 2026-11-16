from pathlib import Path
import sys

try:
    from packages.contracts.jobs import SimulationJob
    from packages.contracts.models import QSTSConfig
    from packages.contracts.progress import SimulationProgress
except ModuleNotFoundError as error:
    if error.name != "packages":
        raise
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from packages.contracts.jobs import SimulationJob
    from packages.contracts.models import QSTSConfig
    from packages.contracts.progress import SimulationProgress


def main() -> None:
    job = SimulationJob(
        job_id="contract-smoke-job",
        session_id="contract-smoke-session",
        topology="ieee8500",
        simulation_type="qsts",
        qsts=QSTSConfig(
            duration_hours=0.25,
            step_minutes=5,
            profile_source="values",
            load_multipliers=[0.8, 1.0, 1.2],
        ),
    )

    serialized_job = job.model_dump_json()
    restored_job = SimulationJob.model_validate_json(
        serialized_job
    )

    assert restored_job == job

    progress = SimulationProgress(
        job_id=job.job_id,
        session_id=job.session_id,
        simulation_type="qsts",
        step=1,
        total_steps=3,
        progress_pct=33.333,
        load_multiplier=0.8,
    )

    serialized_progress = progress.model_dump_json()
    restored_progress = SimulationProgress.model_validate_json(
        serialized_progress
    )

    assert restored_progress == progress

    print("SimulationJob JSON OK")
    print("SimulationProgress JSON OK")
    print("CONTRACTS SMOKE OK")


if __name__ == "__main__":
    main()