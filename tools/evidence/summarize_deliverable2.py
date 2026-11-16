from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from statistics import mean
from typing import Any


def read_json(path: Path) -> Any:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8-sig"))


def aggregated_locust(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"file": str(path), "missing": True}
    with path.open(newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
    row = next((item for item in rows if item.get("Name") == "Aggregated"), None)
    if row is None and rows:
        row = rows[-1]
    if row is None:
        return {"file": str(path), "missing": False, "empty": True}

    def number(*keys: str) -> float | int | None:
        for key in keys:
            value = row.get(key)
            if value not in (None, ""):
                try:
                    f = float(value)
                    return int(f) if f.is_integer() else f
                except ValueError:
                    return value
        return None

    return {
        "file": str(path),
        "request_count": number("Request Count"),
        "failure_count": number("Failure Count"),
        "rps": number("Requests/s"),
        "mean_ms": number("Average Response Time"),
        "p50_ms": number("50%", "Median Response Time"),
        "p95_ms": number("95%"),
        "p99_ms": number("99%"),
        "max_ms": number("Max Response Time"),
    }


def metric_summary(payload: Any) -> dict[str, Any]:
    datapoints = (payload or {}).get("Datapoints", []) if isinstance(payload, dict) else []
    averages = [float(item["Average"]) for item in datapoints if "Average" in item]
    maximums = [float(item["Maximum"]) for item in datapoints if "Maximum" in item]
    return {
        "samples": len(datapoints),
        "average_of_averages": round(mean(averages), 3) if averages else None,
        "peak": round(max(maximums), 3) if maximums else None,
    }


def autoscaling_summary(path: Path) -> dict[str, Any]:
    samples: list[dict[str, Any]] = []
    if path.exists():
        for line in path.read_text(encoding="utf-8-sig").splitlines():
            if line.strip():
                samples.append(json.loads(line))
    desired = [int(item.get("desired_count", 0)) for item in samples]
    running = [int(item.get("running_count", 0)) for item in samples]
    return {
        "samples": len(samples),
        "desired_min": min(desired) if desired else None,
        "desired_max": max(desired) if desired else None,
        "running_min": min(running) if running else None,
        "running_max": max(running) if running else None,
        "scale_out_observed": bool(desired and max(desired) > min(desired)),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", required=True)
    args = parser.parse_args()
    run_dir = Path(args.run_dir)

    payload = {
        "locust_5_users": aggregated_locust(run_dir / "locust_5_stats.csv"),
        "locust_10_users": aggregated_locust(run_dir / "locust_10_stats.csv"),
        "cpu": metric_summary(read_json(run_dir / "cloudwatch_CPUUtilization.json")),
        "memory": metric_summary(read_json(run_dir / "cloudwatch_MemoryUtilization.json")),
        "autoscaling": autoscaling_summary(run_dir / "autoscaling_timeline.jsonl"),
    }
    failure_counts = [
        item.get("failure_count")
        for key, item in payload.items()
        if key.startswith("locust_") and isinstance(item, dict)
    ]
    payload["passed_load"] = all(value in (0, 0.0) for value in failure_counts if value is not None)

    (run_dir / "PERFORMANCE_SUMMARY.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    l5 = payload["locust_5_users"]
    l10 = payload["locust_10_users"]
    auto = payload["autoscaling"]
    cpu = payload["cpu"]
    mem = payload["memory"]
    report = f"""# Evidencia Entregable 2 — rendimiento cloud

## Resultado de carga

| Campaña | Requests | Failures | RPS | p50 ms | p95 ms | p99 ms | max ms |
|---|---:|---:|---:|---:|---:|---:|---:|
| 5 usuarios | {l5.get('request_count')} | {l5.get('failure_count')} | {l5.get('rps')} | {l5.get('p50_ms')} | {l5.get('p95_ms')} | {l5.get('p99_ms')} | {l5.get('max_ms')} |
| 10 usuarios | {l10.get('request_count')} | {l10.get('failure_count')} | {l10.get('rps')} | {l10.get('p50_ms')} | {l10.get('p95_ms')} | {l10.get('p99_ms')} | {l10.get('max_ms')} |

## Recursos workers

- CPU promedio de promedios: **{cpu.get('average_of_averages')} %**
- CPU pico: **{cpu.get('peak')} %**
- Memoria promedio de promedios: **{mem.get('average_of_averages')} %**
- Memoria pico: **{mem.get('peak')} %**

## Auto scaling

- Desired min: **{auto.get('desired_min')}**
- Desired max: **{auto.get('desired_max')}**
- Running min: **{auto.get('running_min')}**
- Running max: **{auto.get('running_max')}**
- Scale-out observado: **{'SI' if auto.get('scale_out_observed') else 'NO'}**

> Si `Scale-out observado` es NO, no declarar cumplida esa parte del Entregable 2: repetir la campaña con mayor duración/carga o un target CPU menor.
"""
    (run_dir / "REPORT.md").write_text(report, encoding="utf-8")
    print(json.dumps(payload, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
