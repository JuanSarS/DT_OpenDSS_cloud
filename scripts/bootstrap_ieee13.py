from __future__ import annotations

import shutil
from pathlib import Path

from dss.examples import download_repo_snapshot


PROJECT_ROOT = Path(__file__).resolve().parents[1]

NETWORKS_ROOT = PROJECT_ROOT / "data" / "networks"
IEEE13_DEST = NETWORKS_ROOT / "ieee13"


def copy_required(source: Path, destination: Path) -> None:
    if not source.exists():
        raise FileNotFoundError(
            f"No se encontró el archivo requerido:\n{source}"
        )

    destination.parent.mkdir(parents=True, exist_ok=True)

    shutil.copy2(source, destination)

    print(f"OK: {destination}")


def main() -> None:

    NETWORKS_ROOT.mkdir(parents=True, exist_ok=True)
    IEEE13_DEST.mkdir(parents=True, exist_ok=True)

    cache = PROJECT_ROOT / ".cache" / "electricdss-tst"
    cache.parent.mkdir(parents=True, exist_ok=True)

    print()
    print("Descargando casos de prueba DSS-Extensions...")
    print()

    base = download_repo_snapshot(
        cache,
        repo_name="electricdss-tst",
        use_version=False,
    )

    # Carpeta general de casos IEEE
    ieee_cases_root = (
        base
        / "Version8"
        / "Distrib"
        / "IEEETestCases"
    )

    # Caso IEEE 13
    ieee13_source = ieee_cases_root / "13Bus"

    # ---------------------------------------------------------
    # Archivos propios del caso IEEE 13
    # ---------------------------------------------------------

    master_source = (
        ieee13_source
        / "IEEE13Nodeckt.dss"
    )

    busxy_source = (
        ieee13_source
        / "IEEE13Node_BusXY.csv"
    )

    bridge_linecodes_source = (
        ieee13_source
        / "IEEELineCodes.DSS"
    )

    # ---------------------------------------------------------
    # Archivo REAL compartido de LineCodes
    #
    # ieee13/IEEELineCodes.DSS contiene:
    #
    #     redirect ../IEEELineCodes.DSS
    #
    # Por eso necesitamos conservar también el archivo del
    # directorio padre.
    # ---------------------------------------------------------

    real_linecodes_source = (
        ieee_cases_root
        / "IEEELineCodes.DSS"
    )

    print("Copiando archivos...")
    print()

    copy_required(
        master_source,
        IEEE13_DEST / "IEEE13Nodeckt.dss",
    )

    copy_required(
        busxy_source,
        IEEE13_DEST / "IEEE13Node_BusXY.csv",
    )

    copy_required(
        bridge_linecodes_source,
        IEEE13_DEST / "IEEELineCodes.DSS",
    )

    copy_required(
        real_linecodes_source,
        NETWORKS_ROOT / "IEEELineCodes.DSS",
    )

    print()
    print("IEEE 13 preparado correctamente.")
    print()

    print("Estructura:")
    print()
    print("data/")
    print("└── networks/")
    print("    ├── IEEELineCodes.DSS")
    print("    └── ieee13/")
    print("        ├── IEEE13Nodeckt.dss")
    print("        ├── IEEE13Node_BusXY.csv")
    print("        └── IEEELineCodes.DSS")
    print()


if __name__ == "__main__":
    main()