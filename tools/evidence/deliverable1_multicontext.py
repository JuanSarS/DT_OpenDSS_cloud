from __future__ import annotations

import argparse
import concurrent.futures
import json
import threading
import time
from pathlib import Path
from typing import Any
from uuid import uuid4

from packages.simulation_core.engine import OpenDSSContextEngine
from packages.simulation_core.topology_catalog import resolve_builtin_topology
from tools.evidence.common import ensure_run_dir, sha256_payload, write_csv, write_json


def parse_csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def canonical_result(result) -> dict[str, Any]:
    payload = result.model_dump(mode="json")
    payload.pop("session_id", None)
    payload.pop("elapsed_ms", None)
    return payload


def solve_once(model: str, barrier: threading.Barrier | None = None) -> dict[str, Any]:
    engine = OpenDSSContextEngine(resolve_builtin_topology(model), load_multiplier=1.0)
    try:
        if barrier is not None:
            barrier.wait(timeout=120)
        started = time.perf_counter()
        result = engine.solve(str(uuid4()), model)
        wall_ms = (time.perf_counter() - started) * 1000.0
        canonical = canonical_result(result)
        return {
            "model": model,
            "converged": result.converged,
            "wall_ms": round(wall_ms, 3),
            "engine_elapsed_ms": result.elapsed_ms,
            "result_hash": sha256_payload(canonical),
            "canonical": canonical,
        }
    finally:
        engine.close()


def max_abs_delta(left: Any, right: Any) -> float:
    maximum = 0.0
    if isinstance(left, dict) and isinstance(right, dict):
        if set(left) != set(right):
            return float("inf")
        for key in left:
            maximum = max(maximum, max_abs_delta(left[key], right[key]))
        return maximum
    if isinstance(left, list) and isinstance(right, list):
        if len(left) != len(right):
            return float("inf")
        for a, b in zip(left, right, strict=True):
            maximum = max(maximum, max_abs_delta(a, b))
        return maximum
    if isinstance(left, bool) or isinstance(right, bool):
        return 0.0 if left == right else float("inf")
    if isinstance(left, (int, float)) and isinstance(right, (int, float)):
        return abs(float(left) - float(right))
    return 0.0 if left == right else float("inf")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Evidencia Entregable 1: aislamiento multi-contexto y equivalencia secuencial."
    )
    parser.add_argument("--models", default="ieee13,ieee34,ieee123,ieee8500")
    parser.add_argument("--levels", default="2,4,8,16")
    parser.add_argument("--sequential-runs", type=int, default=16)
    parser.add_argument("--output-root", default="/evidence")
    args = parser.parse_args()

    models = parse_csv(args.models)
    levels = [int(item) for item in parse_csv(args.levels)]
    run_dir = ensure_run_dir(args.output_root, "multicontext")
    write_json(
        run_dir / "config.json",
        {
            "models": models,
            "levels": levels,
            "sequential_runs": args.sequential_runs,
            "criterion": "hash exacto del resultado excluyendo session_id y elapsed_ms",
        },
    )

    rows: list[dict[str, Any]] = []
    summaries: dict[str, Any] = {}

    for model in models:
        print(f"=== {model}: referencia secuencial ===", flush=True)
        sequential = [solve_once(model) for _ in range(args.sequential_runs)]
        reference = sequential[0]["canonical"]
        reference_hash = sequential[0]["result_hash"]
        sequential_exact = all(item["result_hash"] == reference_hash for item in sequential)
        model_summary: dict[str, Any] = {
            "reference_hash": reference_hash,
            "sequential_runs": len(sequential),
            "sequential_exact": sequential_exact,
            "concurrency": {},
        }
        for index, item in enumerate(sequential, start=1):
            rows.append(
                {
                    "model": model,
                    "mode": "sequential",
                    "level": 1,
                    "run": index,
                    "converged": item["converged"],
                    "wall_ms": item["wall_ms"],
                    "engine_elapsed_ms": item["engine_elapsed_ms"],
                    "result_hash": item["result_hash"],
                    "exact_match": item["result_hash"] == reference_hash,
                    "max_abs_delta": max_abs_delta(reference, item["canonical"]),
                }
            )

        for level in levels:
            print(f"=== {model}: concurrencia {level} ===", flush=True)
            barrier = threading.Barrier(level)
            started = time.perf_counter()
            with concurrent.futures.ThreadPoolExecutor(max_workers=level) as executor:
                futures = [executor.submit(solve_once, model, barrier) for _ in range(level)]
                concurrent_results = [future.result(timeout=900) for future in futures]
            batch_ms = (time.perf_counter() - started) * 1000.0

            exact_count = 0
            deltas: list[float] = []
            for index, item in enumerate(concurrent_results, start=1):
                exact = item["result_hash"] == reference_hash
                delta = max_abs_delta(reference, item["canonical"])
                exact_count += int(exact)
                deltas.append(delta)
                rows.append(
                    {
                        "model": model,
                        "mode": "concurrent",
                        "level": level,
                        "run": index,
                        "converged": item["converged"],
                        "wall_ms": item["wall_ms"],
                        "batch_wall_ms": round(batch_ms, 3),
                        "engine_elapsed_ms": item["engine_elapsed_ms"],
                        "result_hash": item["result_hash"],
                        "exact_match": exact,
                        "max_abs_delta": delta,
                    }
                )
            model_summary["concurrency"][str(level)] = {
                "runs": level,
                "exact_matches": exact_count,
                "all_exact": exact_count == level,
                "max_abs_delta": max(deltas) if deltas else 0.0,
                "batch_wall_ms": round(batch_ms, 3),
            }

        summaries[model] = model_summary

    passed = all(
        summary["sequential_exact"]
        and all(item["all_exact"] for item in summary["concurrency"].values())
        for summary in summaries.values()
    )
    summary_payload = {"passed": passed, "models": summaries}
    write_json(run_dir / "summary.json", summary_payload)
    write_csv(run_dir / "raw_results.csv", rows)

    lines = [
        "# Evidencia Entregable 1 — Multi-contexto OpenDSS",
        "",
        f"Resultado global: **{'PASS' if passed else 'FAIL'}**",
        "",
        "Se comparó cada ejecución concurrente contra una referencia estrictamente secuencial,",
        "excluyendo únicamente `session_id` y tiempos de ejecución del contenido comparable.",
        "",
        "| Red | Secuencial exacto | 2 | 4 | 8 | 16 |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for model in models:
        data = summaries[model]
        values = ["PASS" if data["sequential_exact"] else "FAIL"]
        for level in (2, 4, 8, 16):
            item = data["concurrency"].get(str(level), {})
            values.append("PASS" if item.get("all_exact") else "FAIL")
        lines.append(f"| {model} | " + " | ".join(values) + " |")
    (run_dir / "REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(json.dumps(summary_payload, indent=2))
    print(f"Evidence: {run_dir}")
    raise SystemExit(0 if passed else 2)


if __name__ == "__main__":
    main()
