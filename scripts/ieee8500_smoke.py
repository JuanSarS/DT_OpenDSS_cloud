from __future__ import annotations

import re
import time
from pathlib import Path

import psutil

from app.adapters.opendss.engine import OpenDSSContextEngine
from app.adapters.opendss.topology_catalog import NETWORKS_ROOT


def referenced_files(master: Path) -> list[Path]:
    references: list[Path] = []
    for line in master.read_text(encoding="utf-8", errors="ignore").splitlines():
        match = re.match(r"\s*(?:redirect|compile|buscoords)\s+(.+)", line, re.IGNORECASE)
        if not match:
            continue
        value = match.group(1).strip().strip('"').split()[0]
        if value.startswith("("):
            value = value[1:].strip('"')
        references.append(master.parent / value)
    return references


def main() -> None:
    master = NETWORKS_ROOT / "ieee8500" / "Master_cloud.dss"
    if not master.exists():
        raise FileNotFoundError(f"Falta el master IEEE8500: {master}")
    missing = [path for path in referenced_files(master) if not path.exists()]
    if missing:
        raise FileNotFoundError(f"Dependencias IEEE8500 faltantes: {missing}")

    process = psutil.Process()
    rss_before = process.memory_info().rss / 1024**2
    load_started = time.perf_counter()
    engine = OpenDSSContextEngine(master)
    load_ms = (time.perf_counter() - load_started) * 1000.0
    rss_after_load = process.memory_info().rss / 1024**2
    result = engine.solve("ieee8500-smoke", "ieee8500")
    rss_after_solve = process.memory_info().rss / 1024**2
    summary = engine.model_summary("ieee8500")
    engine.close()

    print("====================================")
    print(" IEEE8500 Snapshot Smoke")
    print("====================================")
    print(f"Master: {master}")
    print(f"Converged: {result.converged}")
    print(f"Buses: {summary.num_buses}")
    print(f"Nodes: {summary.num_nodes}")
    print(f"Total kW: {result.total_power_kw}")
    print(f"Total kvar: {result.total_power_kvar}")
    print(f"Solve: {result.elapsed_ms} ms")
    print(f"Load: {load_ms:.3f} ms")
    print(f"RSS before: {rss_before:.3f} MB")
    print(f"RSS after load: {rss_after_load:.3f} MB")
    print(f"RSS after solve: {rss_after_solve:.3f} MB")
    if not result.converged:
        raise RuntimeError("IEEE8500 Snapshot no convergió")
    print("\nIEEE8500 SNAPSHOT OK")


if __name__ == "__main__":
    main()
