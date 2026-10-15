import csv
import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.adapters.opendss.engine import OpenDSSContextEngine
from app.adapters.opendss.topology_catalog import resolve_topology
from app.domain.models import QSTSConfig


EVIDENCE_DIR = PROJECT_ROOT / "docs" / "evidence" / "qsts"


def write_evidence(result, timestamp: str) -> tuple[Path, Path]:
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    csv_path = EVIDENCE_DIR / f"qsts_ieee123_{timestamp}.csv"
    json_path = EVIDENCE_DIR / f"qsts_ieee123_{timestamp}.json"

    fieldnames = [
        "step",
        "simulated_minutes",
        "simulated_hour",
        "opendss_hour",
        "opendss_time_of_step_us",
        "load_multiplier",
        "converged",
        "solve_ms",
        "total_kw",
        "total_kvar",
        "min_voltage_pu",
        "max_voltage_pu",
        "solution_iterations",
        "rss_mb",
    ]
    with csv_path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        for step in result.steps:
            writer.writerow(step.model_dump())

    with json_path.open("w", encoding="utf-8") as file:
        json.dump(result.model_dump(mode="json"), file, indent=2)

    return csv_path, json_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Ejecuta un QSTS local.")
    parser.add_argument(
        "--profile-source",
        choices=("constant", "synthetic_daily", "model"),
        default="synthetic_daily",
    )
    parser.add_argument("--duration-hours", type=float, default=24.0)
    parser.add_argument("--step-minutes", type=float, default=5.0)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = QSTSConfig(
        duration_hours=args.duration_hours,
        step_minutes=args.step_minutes,
        profile_source=args.profile_source,
    )
    engine = OpenDSSContextEngine(resolve_topology("ieee123"), load_multiplier=1.0)
    try:
        print("========================================")
        print(" OpenDSS QSTS Local Test")
        print("========================================")
        print("Modelo: IEEE123")
        print("Modo: Daily")
        print(f"Duración: {config.duration_hours} horas")
        print(f"Paso: {config.step_minutes} minutos")
        print(f"Número de pasos: {config.total_steps}")
        print(f"Perfil: {config.profile_source}")
        print()

        result = engine.solve_qsts(config)
    finally:
        engine.close()

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_UTC")
    csv_path, json_path = write_evidence(result, timestamp)

    print("========================================")
    print(" SUMMARY")
    print("========================================")
    print(f"Steps: {result.total_steps}")
    print(f"Converged: {result.converged_steps}")
    print(f"Failed: {result.failed_steps}")
    print(f"Solve mean: {result.solve_mean_ms:.3f} ms")
    print(f"Solve p50: {result.solve_p50_ms:.3f} ms")
    print(f"Solve p95: {result.solve_p95_ms:.3f} ms")
    print(f"Solve max: {result.solve_max_ms:.3f} ms")
    print(f"RSS start: {result.rss_start_mb:.3f} MB")
    print(f"RSS peak: {result.rss_peak_mb:.3f} MB")
    print(f"RSS delta: {result.rss_peak_mb - result.rss_start_mb:.3f} MB")
    print(f"Total QSTS: {result.elapsed_ms:.3f} ms")
    load_multipliers = [step.load_multiplier for step in result.steps]
    powers = [step.total_kw for step in result.steps if step.total_kw is not None]
    minimum_voltages = [
        step.min_voltage_pu for step in result.steps if step.min_voltage_pu is not None
    ]
    maximum_voltages = [
        step.max_voltage_pu for step in result.steps if step.max_voltage_pu is not None
    ]
    print(f"LoadMult min/max: {min(load_multipliers):.4f}/{max(load_multipliers):.4f}")
    print(f"Potencia activa min/max: {min(powers):.3f}/{max(powers):.3f} kW")
    print(f"Vmin global: {min(minimum_voltages):.6f} p.u.")
    print(f"Vmax global: {max(maximum_voltages):.6f} p.u.")
    print(f"CSV: {csv_path}")
    print(f"JSON: {json_path}")
    print()
    print("QSTS OK")


if __name__ == "__main__":
    main()
