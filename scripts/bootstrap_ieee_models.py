from __future__ import annotations

import shutil
from pathlib import Path

from dss.examples import download_repo_snapshot


ROOT = Path(__file__).resolve().parents[1]
NETWORKS = ROOT / "data" / "networks"


def copy_tree(source: Path, destination: Path) -> None:
    if not source.is_dir():
        raise FileNotFoundError(f"No existe el testcase: {source}")
    if destination.exists():
        shutil.rmtree(destination)
    shutil.copytree(source, destination)


def create_headless_master(destination: Path, source_name: str, target_name: str) -> None:
    source = destination / source_name
    target = destination / target_name
    content = source.read_text(encoding="utf-8", errors="ignore").rstrip()
    target.write_text(
        f"{content}\n\n! Cloud headless master: increase iterations for Snapshot convergence.\n"
        "Set Maxiterations=20\n",
        encoding="utf-8",
    )


def main() -> None:
    cache = ROOT / ".cache" / "electricdss-tst"
    base = download_repo_snapshot(cache, repo_name="electricdss-tst", use_version=False)
    cases = base / "Version8" / "Distrib" / "IEEETestCases"
    mappings = {
        "ieee13": ("13Bus", "IEEE13Nodeckt.dss"),
        "ieee34": ("34Bus", "ieee34Mod1.dss"),
        "ieee123": ("123Bus", "IEEE123Master.dss"),
        "ieee8500": ("8500-Node", "Master.dss"),
    }
    NETWORKS.mkdir(parents=True, exist_ok=True)
    for model_id, (source_name, master) in mappings.items():
        source = cases / source_name
        copy_tree(source, NETWORKS / model_id)
        if not (NETWORKS / model_id / master).exists():
            raise FileNotFoundError(f"Master esperado no encontrado: {source / master}")
        print(f"OK: {model_id} -> {master}")
    create_headless_master(NETWORKS / "ieee8500", "Master.dss", "Master_cloud.dss")
    print("OK: ieee8500 -> Master_cloud.dss (headless)")


if __name__ == "__main__":
    main()
