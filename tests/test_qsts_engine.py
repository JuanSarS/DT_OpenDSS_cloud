from pathlib import Path

import pytest

from packages.simulation_core.engine import OpenDSSContextEngine
from packages.contracts.models import QSTSConfig
from packages.simulation_core.qsts_profiles import synthetic_mixed_daily_profile


PROJECT_ROOT = Path(__file__).resolve().parents[1]
IEEE123_MASTER = PROJECT_ROOT / "data" / "networks" / "ieee123" / "IEEE123Master.dss"
IEEE13_MASTER = PROJECT_ROOT / "data" / "networks" / "ieee13" / "IEEE13Nodeckt.dss"


def test_qsts_config_calculates_expected_step_count() -> None:
    config = QSTSConfig(duration_hours=24.0, step_minutes=5.0)

    assert config.total_steps == 288


def test_synthetic_daily_profile_is_deterministic_and_interpolated() -> None:
    first = synthetic_mixed_daily_profile(288, 5.0)
    second = synthetic_mixed_daily_profile(288, 5.0)

    assert first == second
    assert len(first) == 288
    assert min(first) == pytest.approx(0.46)
    assert max(first) == pytest.approx(1.0)
    assert first[204 - 1] == pytest.approx(1.0)
    assert first[48 - 1] == pytest.approx(0.46)


def test_qsts_synthetic_daily_applies_variable_load_multiplier() -> None:
    engine = OpenDSSContextEngine(IEEE123_MASTER)
    try:
        result = engine.solve_qsts(
            QSTSConfig(
                duration_hours=0.25,
                step_minutes=5.0,
                profile_source="synthetic_daily",
            )
        )
    finally:
        engine.close()

    multipliers = [step.load_multiplier for step in result.steps]
    assert multipliers == pytest.approx([0.5766666667, 0.5733333333, 0.57])
    assert len(set(multipliers)) == 3


def test_qsts_short_run_advances_time_and_converges() -> None:
    engine = OpenDSSContextEngine(IEEE123_MASTER)
    try:
        result = engine.solve_qsts(
            QSTSConfig(duration_hours=0.25, step_minutes=5.0)
        )
    finally:
        engine.close()

    assert result.total_steps == 3
    assert [step.step for step in result.steps] == [1, 2, 3]
    assert [step.simulated_minutes for step in result.steps] == [5.0, 10.0, 15.0]
    assert all(step.converged for step in result.steps)
    assert all(step.solve_ms >= 0 for step in result.steps)
    assert result.converged_steps == 3
    assert result.failed_steps == 0


def test_snapshot_still_works_after_qsts_support() -> None:
    engine = OpenDSSContextEngine(IEEE13_MASTER)
    try:
        result = engine.solve("snapshot-test", "ieee13")
    finally:
        engine.close()

    assert result.converged is True
    assert result.total_power_kw != 0
    assert result.total_power_kvar != 0
    assert result.voltages
    assert result.currents


def test_qsts_contexts_are_independent() -> None:
    first = OpenDSSContextEngine(IEEE123_MASTER, load_multiplier=0.8)
    second = OpenDSSContextEngine(IEEE123_MASTER, load_multiplier=1.2)
    try:
        assert first.identity != second.identity

        first_result = first.solve_qsts(
            QSTSConfig(duration_hours=5 / 60, step_minutes=5.0)
        )

        assert first_result.total_steps == 1
        assert first.load_multiplier == pytest.approx(1.0)
        assert second.load_multiplier == pytest.approx(1.2)
    finally:
        first.close()
        second.close()
